"""End-to-end needs_review path through the real FastAPI app (offline mock LLM, throwaway SQLite DB).

    cd backend && python tests/test_needs_review.py
"""
import os
import sys
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp())
os.environ.update({
    "DATABASE_URL": f"sqlite:///{(_tmp / 'test.db').as_posix()}",
    "MIRAGE_LLM_MODE": "mock",
    "MIRAGE_EMBEDDINGS": "hashing",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402

from app import config  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


def test_startup_adds_columns_missing_from_an_older_database():
    from app import models  # noqa: F401

    Base.metadata.create_all(engine)
    with engine.begin() as conn:  # simulate a database created before these columns existed
        conn.execute(text("ALTER TABLE incidents DROP COLUMN raw_extraction_output"))
        conn.execute(text("ALTER TABLE incident_profiles DROP COLUMN attacker_goal_confidence"))
    with TestClient(app):
        pass
    inspector = inspect(engine)
    assert "raw_extraction_output" in {c["name"] for c in inspector.get_columns("incidents")}
    assert "attacker_goal_confidence" in {c["name"] for c in inspector.get_columns("incident_profiles")}


def test_invalid_extraction_flags_needs_review_then_retry_recovers():
    with TestClient(app) as client:
        incident_id = client.post("/incidents/simulate", json={"persona_id": 1, "attacker_script_id": 1}).json()["incident_id"]
        for _ in range(3):
            assert client.post(f"/incidents/{incident_id}/respond").status_code == 200

        config.MOCK_FORCE_INVALID_EXTRACTION = True
        res = client.post(f"/incidents/{incident_id}/close")
        assert res.status_code == 200, res.text
        detail = res.json()
        assert detail["status"] == "needs_review"
        assert detail["profile"] is None, "no guessed profile may be written"
        assert detail["review_message"].startswith("Flagged for manual review")
        raw = detail["raw_extraction_output"]
        assert "attempt 1" in raw and "attempt 2" in raw and "attempt 3" not in raw
        assert "T1566.999" in raw and "validation error" in raw

        assert client.get(f"/incidents/{incident_id}/report").status_code == 409
        assert client.post(f"/incidents/{incident_id}/respond").status_code == 409
        stats = client.get("/dashboard/stats").json()
        assert stats["needs_review_incidents"] == 1 and stats["analyzed_incidents"] == 0
        listed = next(i for i in client.get("/incidents").json() if i["id"] == incident_id)
        assert listed["status"] == "needs_review" and not listed["analyzed"]

        config.MOCK_FORCE_INVALID_EXTRACTION = False
        detail = client.post(f"/incidents/{incident_id}/close").json()
        assert detail["status"] == "closed"
        assert detail["profile"]["mitre_technique"] == "T1656 — Impersonation"
        assert detail["profile"]["attacker_goal_confidence"] in {"high", "medium", "low"}
        assert detail["raw_extraction_output"] is None and detail["review_message"] is None
        report = client.get(f"/incidents/{incident_id}/report")
        assert report.status_code == 200 and "self-reported confidence" in report.json()["markdown"]
        assert client.get("/dashboard/stats").json()["needs_review_incidents"] == 0


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"{len(tests)} passed")
