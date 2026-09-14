"""Pydantic models: the LLM extraction contract plus API request bodies."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .mitre import TACTICS, TECHNIQUE_IDS

IOC_TYPES = ("url", "phone", "email", "payment_account", "other")
CONFIDENCE_LEVELS = ("high", "medium", "low")

# Closed vocabularies: the model must return one of these exact strings or validation fails.
TechniqueId = Literal[TECHNIQUE_IDS]
Tactic = Literal[tuple(TACTICS)]
IOCType = Literal[IOC_TYPES]
Confidence = Literal[CONFIDENCE_LEVELS]


# --- Structured extraction output -------------------------------------------
class IOC(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: IOCType
    value: str

    @field_validator("value")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("IOC value must not be empty")
        return v


class ExtractedProfile(BaseModel):
    """The extraction contract. No normalisation of categorical fields: near-misses such as
    'Urgency', 't1656' or 'T1656 — Impersonation' fail validation instead of being guessed at."""

    model_config = ConfigDict(extra="forbid")

    mitre_technique: TechniqueId
    iocs: list[IOC]
    manipulation_tactics: list[Tactic]
    attacker_goal: str = Field(min_length=5, max_length=400)
    attacker_goal_confidence: Confidence

    @field_validator("manipulation_tactics")
    @classmethod
    def _dedupe_tactics(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))

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


# Sent as output_config.format so decoding itself is constrained to the same vocabularies.
# Hand-written because structured outputs rejects minLength/maxLength; pydantic still enforces those.
EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "mitre_technique": {"type": "string", "enum": list(TECHNIQUE_IDS)},
        "iocs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": list(IOC_TYPES)},
                    "value": {"type": "string"},
                },
                "required": ["type", "value"],
                "additionalProperties": False,
            },
        },
        "manipulation_tactics": {"type": "array", "items": {"type": "string", "enum": list(TACTICS)}},
        "attacker_goal": {"type": "string"},
        "attacker_goal_confidence": {"type": "string", "enum": list(CONFIDENCE_LEVELS)},
    },
    "required": ["mitre_technique", "iocs", "manipulation_tactics", "attacker_goal", "attacker_goal_confidence"],
    "additionalProperties": False,
}


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
