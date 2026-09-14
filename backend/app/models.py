"""SQLAlchemy models. Portable types only (JSON, Text, Float) so the schema runs on SQLite and Postgres."""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(200))
    backstory: Mapped[str] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AttackerScript(Base):
    __tablename__ = "attacker_scripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    system_prompt: Mapped[str] = mapped_column(Text)
    opening_message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("personas.id"))
    # Null when the attacker messages were supplied manually rather than by the simulator.
    attacker_script_id: Mapped[int | None] = mapped_column(ForeignKey("attacker_scripts.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | closed
    channel: Mapped[str] = mapped_column(String(16), default="text")  # text | email | voice

    persona: Mapped[Persona] = relationship()
    attacker_script: Mapped[AttackerScript | None] = relationship()
    messages: Mapped[list["Message"]] = relationship(
        back_populates="incident", order_by="Message.id", cascade="all, delete-orphan"
    )
    profile: Mapped["IncidentProfile | None"] = relationship(
        back_populates="incident", uselist=False, cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    sender: Mapped[str] = mapped_column(String(16))  # attacker | persona
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="messages")


class IncidentProfile(Base):
    __tablename__ = "incident_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), unique=True)
    mitre_technique: Mapped[str] = mapped_column(String(200))
    iocs: Mapped[list] = mapped_column(JSON, default=list)  # [{type, value}]
    manipulation_tactics: Mapped[list] = mapped_column(JSON, default=list)  # [str]
    attacker_goal: Mapped[str] = mapped_column(Text)
    # Stored as a JSON float array; cosine similarity is computed in Python.
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    embedding_model: Mapped[str] = mapped_column(String(120), default="")
    analyzer: Mapped[str] = mapped_column(String(60), default="")  # which LLM (or mock) produced it
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="profile")


class IncidentLink(Base):
    __tablename__ = "incident_links"
    __table_args__ = (UniqueConstraint("incident_a_id", "incident_b_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_a_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    incident_b_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    similarity_score: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
