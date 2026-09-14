"""MIRAGE API. Run from backend/:  uvicorn app.main:app --reload"""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, embeddings
from .db import SessionLocal, init_db
from .routers import dashboard, incidents, personas
from .seed import seed

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("mirage")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed(db)
    log.info("LLM mode: %s (chat=%s, extraction=%s)", config.llm_mode(), config.CHAT_MODEL, config.EXTRACTION_MODEL)
    if config.llm_mode() == "mock":
        log.warning("Running with the OFFLINE MOCK LLM. Set ANTHROPIC_API_KEY for live Claude conversations.")
    # Load the embedding model in the background so the first Close & Analyze is fast.
    threading.Thread(target=embeddings.warm_up, daemon=True).start()
    yield


app = FastAPI(title="MIRAGE", description="AI deception & threat-intelligence platform", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(dashboard.router)
app.include_router(personas.router)
app.include_router(incidents.router)
