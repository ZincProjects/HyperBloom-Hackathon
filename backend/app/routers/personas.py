from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import COMPANY_NAME
from ..db import get_db
from ..models import AttackerScript, Persona
from ..prompts import render_persona_prompt
from ..schemas import PersonaCreate
from ..serializers import persona_dict, script_dict

router = APIRouter(tags=["personas & scripts"])


@router.get("/personas")
def list_personas(db: Session = Depends(get_db)):
    return [persona_dict(p) for p in db.scalars(select(Persona).order_by(Persona.id))]


@router.get("/personas/{persona_id}")
def get_persona(persona_id: int, db: Session = Depends(get_db)):
    persona = db.get(Persona, persona_id)
    if persona is None:
        raise HTTPException(404, "Persona not found")
    return persona_dict(persona, include_prompt=True)


@router.post("/personas", status_code=201)
def create_persona(body: PersonaCreate, db: Session = Depends(get_db)):
    persona = Persona(
        name=body.name,
        role=body.role,
        backstory=body.backstory,
        system_prompt=body.system_prompt
        or render_persona_prompt(body.name, body.role, body.backstory, body.quirks or "- Friendly and chatty.", COMPANY_NAME),
    )
    db.add(persona)
    db.commit()
    return persona_dict(persona, include_prompt=True)


@router.get("/attacker-scripts")
def list_attacker_scripts(db: Session = Depends(get_db)):
    return [script_dict(s) for s in db.scalars(select(AttackerScript).order_by(AttackerScript.id))]


@router.get("/attacker-scripts/{script_id}")
def get_attacker_script(script_id: int, db: Session = Depends(get_db)):
    script = db.get(AttackerScript, script_id)
    if script is None:
        raise HTTPException(404, "Attacker script not found")
    return script_dict(script, include_prompt=True)
