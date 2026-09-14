"""Seed default personas and attacker scripts. Runs automatically on startup; also usable directly:

    python -m app.seed           # insert anything missing
    python -m app.seed --reset   # drop ALL tables (incidents included) and re-seed
"""
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import COMPANY_NAME
from .db import Base, SessionLocal, engine, init_db
from .models import AttackerScript, Persona
from .prompts import render_attacker_prompt, render_persona_prompt
from .seed_data import ATTACKER_SCRIPTS, PERSONAS


def seed(db: Session) -> None:
    existing_personas = set(db.scalars(select(Persona.name)))
    for p in PERSONAS:
        if p["name"] in existing_personas:
            continue
        db.add(Persona(
            name=p["name"],
            role=p["role"],
            backstory=p["backstory"],
            system_prompt=render_persona_prompt(p["name"], p["role"], p["backstory"], p["quirks"], COMPANY_NAME),
        ))

    existing_scripts = set(db.scalars(select(AttackerScript.name)))
    for s in ATTACKER_SCRIPTS:
        if s["name"] in existing_scripts:
            continue
        db.add(AttackerScript(
            name=s["name"],
            description=s["description"],
            opening_message=s["opening_message"],
            system_prompt=render_attacker_prompt(
                s["name"], s["scam_description"], s["goal"], s["cover_identity"], s["infrastructure"],
                s["beats"], COMPANY_NAME,
            ),
        ))
    db.commit()


def reset() -> None:
    from . import models  # noqa: F401

    Base.metadata.drop_all(engine)
    init_db()


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset()
        print("Dropped and recreated all tables.")
    else:
        init_db()
    with SessionLocal() as session:
        seed(session)
        print(f"Seeded: {session.query(Persona).count()} personas, {session.query(AttackerScript).count()} attacker scripts.")
