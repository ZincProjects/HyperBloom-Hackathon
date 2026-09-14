"""ORM -> JSON-ready dicts shared by the routers."""
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .clustering import build_clusters, cluster_index
from .mitre import TECHNIQUES, technique_id
from .models import AttackerScript, Incident, IncidentLink, IncidentProfile, Message, Persona


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:  # SQLite drops tzinfo; everything is stored as UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def incident_ref(incident_id: int) -> str:
    return f"MIR-{incident_id:04d}"


def persona_dict(p: Persona, include_prompt: bool = False) -> dict:
    data = {"id": p.id, "name": p.name, "role": p.role, "backstory": p.backstory, "created_at": iso(p.created_at)}
    if include_prompt:
        data["system_prompt"] = p.system_prompt
    return data


def script_dict(s: AttackerScript, include_prompt: bool = False) -> dict:
    data = {"id": s.id, "name": s.name, "description": s.description, "opening_message": s.opening_message}
    if include_prompt:
        data["system_prompt"] = s.system_prompt
    return data


def message_dict(m: Message) -> dict:
    return {"id": m.id, "sender": m.sender, "content": m.content, "created_at": iso(m.created_at)}


def profile_dict(p: IncidentProfile) -> dict:
    tid = technique_id(p.mitre_technique)
    technique = TECHNIQUES.get(tid, {})
    return {
        "mitre_technique": p.mitre_technique,
        "technique_id": tid,
        "technique_name": technique.get("name"),
        "technique_explanation": technique.get("explanation"),
        "iocs": p.iocs,
        "manipulation_tactics": p.manipulation_tactics,
        "attacker_goal": p.attacker_goal,
        "analyzer": p.analyzer,
        "embedding_model": p.embedding_model,
        "embedding_dims": len(p.embedding or []),
        "created_at": iso(p.created_at),
    }


def all_clusters(db: Session) -> tuple[dict[int, list[int]], dict[int, int]]:
    profiled = list(db.scalars(select(IncidentProfile.incident_id)))
    clusters = build_clusters(profiled, db.scalars(select(IncidentLink)).all())
    return clusters, cluster_index(clusters)


def linked_incidents(db: Session, incident_id: int) -> list[dict]:
    links = db.scalars(select(IncidentLink).where(
        or_(IncidentLink.incident_a_id == incident_id, IncidentLink.incident_b_id == incident_id)
    )).all()
    out = []
    for link in links:
        other_id = link.incident_b_id if link.incident_a_id == incident_id else link.incident_a_id
        other = db.get(Incident, other_id)
        if other is None:
            continue
        out.append({
            "incident_id": other.id,
            "ref": incident_ref(other.id),
            "similarity": link.similarity_score,
            "persona_name": other.persona.name,
            "attacker_script": other.attacker_script.name if other.attacker_script else None,
            "mitre_technique": other.profile.mitre_technique if other.profile else None,
            "attacker_goal": other.profile.attacker_goal if other.profile else None,
            "status": other.status,
        })
    return sorted(out, key=lambda item: item["similarity"], reverse=True)


def _summary(incident: Incident) -> str:
    if incident.profile:
        return incident.profile.attacker_goal
    if incident.messages:
        last = incident.messages[-1].content
        return last if len(last) <= 110 else last[:107] + "..."
    return "No messages yet"


def incident_summary(incident: Incident, clusters: dict[int, list[int]], index: dict[int, int]) -> dict:
    cluster_id = index.get(incident.id)
    cluster_size = len(clusters.get(cluster_id, [])) if cluster_id is not None else 0
    return {
        "id": incident.id,
        "ref": incident_ref(incident.id),
        "status": incident.status,
        "channel": incident.channel,
        "persona": {"id": incident.persona.id, "name": incident.persona.name, "role": incident.persona.role},
        "attacker_script": (
            {"id": incident.attacker_script.id, "name": incident.attacker_script.name}
            if incident.attacker_script else None
        ),
        "source": "simulator" if incident.attacker_script_id else "manual",
        "started_at": iso(incident.started_at),
        "closed_at": iso(incident.closed_at),
        "message_count": len(incident.messages),
        "exchange_count": sum(1 for m in incident.messages if m.sender == "persona"),
        "analyzed": incident.profile is not None,
        "mitre_technique": incident.profile.mitre_technique if incident.profile else None,
        "summary": _summary(incident),
        "cluster_id": cluster_id,
        "cluster_size": cluster_size,
    }


def incident_detail(db: Session, incident: Incident) -> dict:
    clusters, index = all_clusters(db)
    data = incident_summary(incident, clusters, index)
    data["messages"] = [message_dict(m) for m in incident.messages]
    data["profile"] = profile_dict(incident.profile) if incident.profile else None
    data["linked_incidents"] = linked_incidents(db, incident.id)
    cluster_id = index.get(incident.id)
    data["cluster_members"] = clusters.get(cluster_id, []) if cluster_id is not None else []
    return data
