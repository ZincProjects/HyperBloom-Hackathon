import logging
import threading
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..llm import ExtractionValidationError, LLMError, attacker_reply, persona_reply
from ..models import AttackerScript, Incident, Message, Persona
from ..pipeline import analyze_incident
from ..report import build_report
from ..schemas import ManualIncidentRequest, RespondRequest, SimulateRequest
from ..serializers import (
    REVIEW_MESSAGE, all_clusters, incident_detail, incident_ref, incident_summary, message_dict,
)

log = logging.getLogger("mirage.incidents")
router = APIRouter(prefix="/incidents", tags=["incidents"])

# One exchange/close at a time per incident, so auto-play can't interleave LLM turns.
_locks: dict[int, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()


@contextmanager
def _incident_lock(incident_id: int):
    with _locks_guard:
        lock = _locks[incident_id]
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "This incident is already processing a request - try again in a moment.")
    try:
        yield
    finally:
        lock.release()


def _get_incident(db: Session, incident_id: int) -> Incident:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(404, "Incident not found")
    return incident


def _add_message(db: Session, incident: Incident, sender: str, content: str) -> Message:
    message = Message(sender=sender, content=content)
    incident.messages.append(message)
    db.commit()  # persist each turn immediately so a later failure doesn't lose it
    return message


def _render_opening(template: str, persona: Persona) -> str:
    return template.replace("{target_first_name}", persona.name.split()[0])


@router.post("/simulate", status_code=201)
def simulate(body: SimulateRequest, db: Session = Depends(get_db)):
    persona = db.get(Persona, body.persona_id)
    if persona is None:
        raise HTTPException(404, "Persona not found")
    script = db.get(AttackerScript, body.attacker_script_id)
    if script is None:
        raise HTTPException(404, "Attacker script not found")

    incident = Incident(persona=persona, attacker_script=script, status="active", channel="text")
    db.add(incident)
    opening = Message(sender="attacker", content=_render_opening(script.opening_message, persona))
    incident.messages.append(opening)
    db.commit()
    return {
        "incident_id": incident.id,
        "opening_message": message_dict(opening),
        "incident": incident_detail(db, incident),
    }


@router.post("/manual", status_code=201)
def manual_incident(body: ManualIncidentRequest, db: Session = Depends(get_db)):
    """Start an incident from a real attacker message (no simulator); the persona replies once."""
    persona = db.get(Persona, body.persona_id)
    if persona is None:
        raise HTTPException(404, "Persona not found")
    incident = Incident(persona=persona, attacker_script=None, status="active", channel="text")
    db.add(incident)
    incident.messages.append(Message(sender="attacker", content=body.attacker_message.strip()))
    db.commit()
    try:
        _add_message(db, incident, "persona", persona_reply(incident))
    except LLMError as exc:
        raise HTTPException(502, f"Incident {incident_ref(incident.id)} created, but the persona reply failed: {exc}")
    return {"incident_id": incident.id, "incident": incident_detail(db, incident)}


@router.post("/{incident_id}/respond")
def respond(incident_id: int, body: RespondRequest | None = None, db: Session = Depends(get_db)):
    """Advance the conversation by one exchange: persona reply, then the attacker's next message."""
    incident = _get_incident(db, incident_id)
    if incident.status != "active":
        raise HTTPException(409, f"Incident is {incident.status.replace('_', ' ')}")
    injected = (body.attacker_message or "").strip() if body else ""
    if incident.attacker_script is None and not injected:
        raise HTTPException(400, "Manual incidents need an attacker_message for each exchange")

    new_messages: list[Message] = []
    with _incident_lock(incident_id):
        try:
            if injected:
                new_messages.append(_add_message(db, incident, "attacker", injected))
            if incident.messages and incident.messages[-1].sender == "attacker":
                new_messages.append(_add_message(db, incident, "persona", persona_reply(incident)))
            if incident.attacker_script is not None and not injected:
                new_messages.append(_add_message(db, incident, "attacker", attacker_reply(incident)))
        except LLMError as exc:
            # Turns generated before the failure are already saved; calling /respond again resumes.
            raise HTTPException(502, str(exc))

    return {
        "new_messages": [message_dict(m) for m in new_messages],
        "incident": incident_detail(db, incident),
    }


@router.post("/{incident_id}/close")
def close(incident_id: int, db: Session = Depends(get_db)):
    """Close the incident, then extract the profile, embed it, and link similar incidents.

    If extraction output fails schema validation on both attempts, no profile is written: the incident
    becomes needs_review with the raw output stored. Calling close again retries extraction.
    """
    incident = _get_incident(db, incident_id)
    new_link_count = 0
    with _incident_lock(incident_id):
        if incident.status == "active":
            incident.status = "closed"
            incident.closed_at = datetime.now(timezone.utc)
            db.commit()
        has_attacker_text = any(m.sender == "attacker" for m in incident.messages)
        if incident.profile is None and has_attacker_text:
            try:
                new_link_count = len(analyze_incident(db, incident))
            except ExtractionValidationError as exc:
                db.rollback()
                incident.status = "needs_review"
                incident.raw_extraction_output = exc.raw_output
                db.commit()
                log.warning("%s flagged needs_review: %s", incident_ref(incident.id), exc)
            except LLMError as exc:  # API/network failure, not a validation failure
                db.rollback()
                raise HTTPException(502, f"Extraction call failed: {exc} Call close again to retry.")
            else:
                incident.status = "closed"
                incident.raw_extraction_output = None
                db.commit()

    detail = incident_detail(db, incident)
    detail["new_link_count"] = new_link_count
    return detail


@router.get("")
def list_incidents(db: Session = Depends(get_db)):
    incidents = db.scalars(
        select(Incident)
        .options(
            selectinload(Incident.messages), selectinload(Incident.profile),
            selectinload(Incident.persona), selectinload(Incident.attacker_script),
        )
        .order_by(Incident.id.desc())
    ).all()
    clusters, index = all_clusters(db)
    return [incident_summary(i, clusters, index) for i in incidents]


@router.get("/{incident_id}")
def get_incident(incident_id: int, db: Session = Depends(get_db)):
    return incident_detail(db, _get_incident(db, incident_id))


@router.get("/{incident_id}/report")
def get_report(incident_id: int, db: Session = Depends(get_db)):
    incident = _get_incident(db, incident_id)
    if incident.status == "needs_review":
        raise HTTPException(409, REVIEW_MESSAGE)
    if incident.profile is None:
        raise HTTPException(409, "Close & analyze the incident before generating a report")
    return {
        "incident_id": incident.id,
        "filename": f"{incident_ref(incident.id)}-report.md",
        "markdown": build_report(db, incident),
    }
