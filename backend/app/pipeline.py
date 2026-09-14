"""Close-incident pipeline: structured extraction -> embedding -> similarity linking."""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import SIMILARITY_THRESHOLD
from .embeddings import cosine_similarity, embed
from .llm import extract_profile
from .mitre import technique_label
from .models import Incident, IncidentLink, IncidentProfile
from .schemas import ExtractedProfile


_INDICATOR_CORE_RE = re.compile(
    r"https?://\S+|[\w.+-]+@[\w.-]+|\+[\d\s().-]{8,}\d|XXXX-\d{4}|bc1q-[\w-]+|@\w+|\b[A-Z]{2,4}-\d{3,}\b"
)


def _indicator_tokens(profile: ExtractedProfile) -> list[str]:
    """Core indicator strings, independent of how the extractor phrased each IOC value."""
    tokens: set[str] = set()
    for ioc in profile.iocs:
        tokens.update(m.rstrip(".,;") for m in _INDICATOR_CORE_RE.findall(ioc.value)) or tokens.add(ioc.value)
    return sorted(tokens)


def profile_text(profile: ExtractedProfile) -> str:
    """The text that gets embedded: what the attacker wanted plus the infrastructure they used.

    Technique and tactic labels are deliberately left out: they come from small shared vocabularies
    (almost every scam uses "urgency"), which inflated cross-campaign similarity in calibration, and
    the extractor may pick different-but-valid techniques for two runs of the same campaign.
    """
    indicators = " ".join(_indicator_tokens(profile)) or "none"
    return f"{profile.attacker_goal} Indicators: {indicators}"


def analyze_incident(db: Session, incident: Incident) -> list[IncidentLink]:
    """Extract + embed + link. Raises llm.ExtractionValidationError / llm.LLMError if extraction fails;
    nothing is written in that case."""
    extracted, analyzer = extract_profile(incident.messages)
    vector, model_name = embed(profile_text(extracted))

    new_links: list[IncidentLink] = []
    others = db.scalars(select(IncidentProfile).where(IncidentProfile.incident_id != incident.id))
    for other in others:
        if other.embedding_model != model_name:  # vectors from different models aren't comparable
            continue
        score = cosine_similarity(vector, other.embedding)
        if score > SIMILARITY_THRESHOLD:
            new_links.append(IncidentLink(
                incident_a_id=incident.id,
                incident_b_id=other.incident_id,
                similarity_score=round(min(score, 1.0), 4),
            ))

    incident.profile = IncidentProfile(
        mitre_technique=technique_label(extracted.mitre_technique),
        iocs=[ioc.model_dump() for ioc in extracted.iocs],
        manipulation_tactics=list(extracted.manipulation_tactics),
        attacker_goal=extracted.attacker_goal,
        attacker_goal_confidence=extracted.attacker_goal_confidence,
        embedding=vector,
        embedding_model=model_name,
        analyzer=analyzer,
    )
    db.add_all(new_links)
    db.commit()
    return new_links
