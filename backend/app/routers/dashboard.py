from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import config, embeddings
from ..db import engine, get_db
from ..llm import extraction_settings
from ..models import Incident, IncidentLink, IncidentProfile, Message
from ..serializers import all_clusters, incident_ref
from ..mitre import technique_id

router = APIRouter(tags=["dashboard"])


@router.get("/health")
def health():
    return {
        "status": "ok",
        "llm_mode": config.llm_mode(),
        "chat_model": config.CHAT_MODEL,
        "extraction_model": config.EXTRACTION_MODEL,
        "extraction": extraction_settings(),
        "embeddings": embeddings.status(),
        "database": engine.dialect.name,
        "similarity_threshold": config.SIMILARITY_THRESHOLD,
    }


@router.get("/dashboard/stats")
def stats(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(Incident.id))) or 0
    open_count = db.scalar(select(func.count(Incident.id)).where(Incident.status == "active")) or 0
    review_count = db.scalar(select(func.count(Incident.id)).where(Incident.status == "needs_review")) or 0
    profiles = db.scalars(select(IncidentProfile)).all()
    clusters, _ = all_clusters(db)

    tactic_counts = Counter(t for p in profiles for t in p.manipulation_tactics)
    technique_counts = Counter(p.mitre_technique for p in profiles)
    return {
        "total_incidents": total,
        "open_incidents": open_count,
        "closed_incidents": total - open_count - review_count,
        "needs_review_incidents": review_count,
        "analyzed_incidents": len(profiles),
        # Connected components of the incident_links graph (a singleton is its own attacker).
        "unique_attacker_clusters": len(clusters),
        "multi_incident_clusters": sum(1 for members in clusters.values() if len(members) > 1),
        "total_links": db.scalar(select(func.count(IncidentLink.id))) or 0,
        "total_iocs": sum(len(p.iocs) for p in profiles),
        "top_tactics": [{"tactic": t, "count": c} for t, c in tactic_counts.most_common()],
        "top_techniques": [{"technique": t, "count": c} for t, c in technique_counts.most_common(5)],
    }


@router.get("/threat-map")
def threat_map(db: Session = Depends(get_db)):
    """Graph of analyzed incidents (nodes) and similarity links (edges), grouped into clusters."""
    clusters, index = all_clusters(db)
    profiles = {p.incident_id: p for p in db.scalars(select(IncidentProfile))}
    incidents = {i.id: i for i in db.scalars(select(Incident).where(Incident.id.in_(profiles.keys())))}

    nodes = []
    for iid, profile in sorted(profiles.items()):
        incident = incidents[iid]
        cluster_id = index[iid]
        nodes.append({
            "id": iid,
            "ref": incident_ref(iid),
            "persona_name": incident.persona.name,
            "attacker_script": incident.attacker_script.name if incident.attacker_script else "Manual input",
            "status": incident.status,
            "technique_id": technique_id(profile.mitre_technique),
            "mitre_technique": profile.mitre_technique,
            "attacker_goal": profile.attacker_goal,
            "cluster_id": cluster_id,
            "cluster_size": len(clusters[cluster_id]),
        })

    links = [
        {"source": l.incident_a_id, "target": l.incident_b_id, "similarity": l.similarity_score}
        for l in db.scalars(select(IncidentLink))
    ]

    cluster_list = []
    for cluster_id, members in sorted(clusters.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        ioc_counts = Counter()
        for iid in members:
            ioc_counts.update({ioc["value"] for ioc in profiles[iid].iocs})
        cluster_list.append({
            "cluster_id": cluster_id,
            "size": len(members),
            "incident_ids": members,
            "techniques": sorted({profiles[i].mitre_technique for i in members}),
            "attacker_scripts": sorted({n["attacker_script"] for n in nodes if n["id"] in members}),
            "personas_targeted": sorted({n["persona_name"] for n in nodes if n["id"] in members}),
            "shared_iocs": sorted(v for v, c in ioc_counts.items() if c > 1),
        })

    return {"nodes": nodes, "links": links, "clusters": cluster_list, "threshold": config.SIMILARITY_THRESHOLD}


@router.post("/demo/reset")
def reset_incidents(db: Session = Depends(get_db)):
    """Delete all incidents, messages, profiles and links (personas and scripts are kept)."""
    for model in (IncidentLink, IncidentProfile, Message, Incident):
        db.execute(delete(model))
    db.commit()
    return {"status": "reset"}
