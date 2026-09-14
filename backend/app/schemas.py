"""Pydantic models: the LLM extraction contract plus API request bodies."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .mitre import TECHNIQUES, canonical_technique

IOCType = Literal["url", "phone", "email", "payment_account", "other"]
Tactic = Literal["urgency", "authority", "scarcity", "fear", "likability", "reciprocity"]


# --- Structured extraction output -------------------------------------------
class IOC(BaseModel):
    type: IOCType
    value: str = Field(min_length=1, max_length=500)

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, v):
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("value")
    @classmethod
    def _strip_value(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("IOC value must not be empty")
        return v


class ExtractedProfile(BaseModel):
    mitre_technique: str
    iocs: list[IOC]
    manipulation_tactics: list[Tactic]
    attacker_goal: str = Field(min_length=5, max_length=400)

    @field_validator("mitre_technique")
    @classmethod
    def _known_technique(cls, v: str) -> str:
        canonical = canonical_technique(v)
        if canonical is None:
            raise ValueError(
                f"mitre_technique '{v}' is not in the allowed list; use one of: {', '.join(TECHNIQUES)}"
            )
        return canonical

    @field_validator("manipulation_tactics", mode="before")
    @classmethod
    def _normalize_tactics(cls, v):
        if not isinstance(v, list):
            return v
        seen: list = []
        for item in v:
            item = item.strip().lower() if isinstance(item, str) else item
            if item not in seen:
                seen.append(item)
        return seen

    @field_validator("iocs")
    @classmethod
    def _dedupe_iocs(cls, v: list[IOC]) -> list[IOC]:
        seen, out = set(), []
        for ioc in v:
            key = (ioc.type, ioc.value.lower())
            if key not in seen:
                seen.add(key)
                out.append(ioc)
        return out


# --- API request bodies ------------------------------------------------------
class PersonaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=200)
    backstory: str = Field(min_length=1)
    quirks: str = ""
    # Optional override; otherwise rendered from the persona prompt template.
    system_prompt: str | None = None


class SimulateRequest(BaseModel):
    persona_id: int
    attacker_script_id: int


class ManualIncidentRequest(BaseModel):
    persona_id: int
    attacker_message: str = Field(min_length=1)


class RespondRequest(BaseModel):
    # Required for manual incidents (no attacker script); optional injection otherwise.
    attacker_message: str | None = None
