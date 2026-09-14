"""Text embeddings for incident profiles.

Primary backend: sentence-transformers all-MiniLM-L6-v2 (local, offline after first download).
Fallback: a dependency-free hashed bag-of-words embedder so the pipeline never blocks.
"""
import hashlib
import logging
import math
import re
import threading

from .config import EMBEDDING_BACKEND, EMBEDDING_MODEL_NAME

log = logging.getLogger("mirage.embeddings")

HASHING_MODEL_NAME = "hashing-bow-384"
_HASH_DIM = 384

_model = None
_model_failed = False
_lock = threading.Lock()


def _load_sentence_transformer():
    global _model, _model_failed
    if _model is not None or _model_failed:
        return _model
    with _lock:
        if _model is None and not _model_failed:
            try:
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
                log.info("Loaded embedding model %s", EMBEDDING_MODEL_NAME)
            except Exception as exc:  # ImportError, download failure, torch issues...
                _model_failed = True
                log.warning("sentence-transformers unavailable (%s); using hashing embedder", exc)
    return _model


def status() -> dict:
    """Embedding backend state, without forcing a model load."""
    if EMBEDDING_BACKEND == "hashing" or _model_failed:
        return {"model": HASHING_MODEL_NAME, "loaded": True}
    return {"model": EMBEDDING_MODEL_NAME, "loaded": _model is not None}


def warm_up() -> None:
    """Load the model ahead of the first /close call (it takes a few seconds)."""
    if EMBEDDING_BACKEND != "hashing":
        _load_sentence_transformer()


def _hashing_embed(text: str) -> list[float]:
    vec = [0.0] * _HASH_DIM
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    grams = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
    for gram in grams:
        digest = hashlib.md5(gram.encode()).digest()
        idx = int.from_bytes(digest[:4], "little") % _HASH_DIM
        vec[idx] += 1.0 if digest[4] & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(text: str) -> tuple[list[float], str]:
    """Return (unit-normalised vector, model name)."""
    model = None if EMBEDDING_BACKEND == "hashing" else _load_sentence_transformer()
    if model is None:
        return _hashing_embed(text), HASHING_MODEL_NAME
    vector = model.encode(text, normalize_embeddings=True)
    return [float(x) for x in vector], EMBEDDING_MODEL_NAME


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
