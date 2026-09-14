"""Runtime configuration, read once from the environment (and backend/.env if present)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _normalize_db_url(url: str) -> str:
    # Render/Heroku hand out postgres:// URLs; SQLAlchemy wants an explicit driver.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


# --- Database -------------------------------------------------------------
# One connection string swaps the whole DB layer: sqlite:///... or postgresql://...
DATABASE_URL = _normalize_db_url(
    os.getenv("DATABASE_URL") or f"sqlite:///{(BACKEND_DIR / 'mirage.db').as_posix()}"
)

# --- LLM ------------------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
# auto: live Claude calls when ANTHROPIC_API_KEY is set, otherwise the offline mock.
# live: always call Claude (errors surface if the key is missing). mock: never call Claude.
LLM_MODE = os.getenv("MIRAGE_LLM_MODE", "auto").lower()
CHAT_MODEL = os.getenv("MIRAGE_CHAT_MODEL", "claude-opus-5")
EXTRACTION_MODEL = os.getenv("MIRAGE_EXTRACTION_MODEL", "claude-opus-5")
# Persona/attacker turns are short chat replies: low effort keeps each exchange snappy.
CHAT_EFFORT = os.getenv("MIRAGE_CHAT_EFFORT", "low")
EXTRACTION_EFFORT = os.getenv("MIRAGE_EXTRACTION_EFFORT", "medium")
# Server-side refusal fallbacks (re-run a policy-declined request on another model).
REFUSAL_FALLBACKS = os.getenv("MIRAGE_REFUSAL_FALLBACKS", "1") == "1"

# --- Embeddings / similarity ---------------------------------------------
# auto: sentence-transformers if importable, else a dependency-free hashing embedder.
EMBEDDING_BACKEND = os.getenv("MIRAGE_EMBEDDINGS", "auto").lower()
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Two incident profiles whose embeddings exceed this cosine similarity are linked
# as the same attacker / campaign. Calibrated for all-MiniLM-L6-v2 on paraphrased profiles:
# same-campaign pairs scored 0.73-0.88, different campaigns at most 0.61. MiniLM rarely
# scores paraphrases above 0.85, so 0.85 missed most same-campaign pairs.
SIMILARITY_THRESHOLD = float(os.getenv("MIRAGE_SIMILARITY_THRESHOLD", "0.70"))

# Fictional organisation the decoy personas "work" for.
COMPANY_NAME = "Acme Corp"

CORS_ORIGINS = [o.strip() for o in os.getenv("MIRAGE_CORS_ORIGINS", "*").split(",") if o.strip()]


def llm_mode() -> str:
    """Resolve the effective LLM mode: 'live' or 'mock'."""
    if LLM_MODE == "live":
        return "live"
    if LLM_MODE == "mock":
        return "mock"
    return "live" if ANTHROPIC_API_KEY else "mock"
