"""Text embeddings for incident profiles.

Primary backend: all-MiniLM-L6-v2 run through ONNX Runtime via fastembed. It produces the same vectors as the
sentence-transformers/PyTorch build of the model (checked: cosine 1.0 on identical text, identical pairwise
similarities), so the similarity threshold calibration carries over, at roughly a third of the memory. That keeps
the backend inside a 512 MB instance.
Fallback: a dependency-free hashed bag-of-words embedder so the pipeline never blocks.
"""
import hashlib
import logging
import math
import re
import threading

from .config import EMBEDDING_BACKEND, EMBEDDING_MODEL_NAME, MODEL_CACHE_DIR

log = logging.getLogger("mirage.embeddings")

HASHING_MODEL_NAME = "hashing-bow-384"
_HASH_DIM = 384

_model = None
_model_failed = False
_lock = threading.Lock()


def _load_model():
    global _model, _model_failed
    if _model is not None or _model_failed:
        return _model
    with _lock:
        if _model is None and not _model_failed:
            try:
                from fastembed import TextEmbedding

                _model = TextEmbedding(EMBEDDING_MODEL_NAME, cache_dir=str(MODEL_CACHE_DIR))
                log.info("Loaded embedding model %s (ONNX, cache: %s)", EMBEDDING_MODEL_NAME, MODEL_CACHE_DIR)
            except Exception as exc:  # ImportError, download failure, onnxruntime issues...
                _model_failed = True
                log.warning("fastembed unavailable (%s); using hashing embedder", exc)
    return _model


def status() -> dict:
    """Embedding backend state, without forcing a model load."""
    if EMBEDDING_BACKEND == "hashing" or _model_failed:
        return {"model": HASHING_MODEL_NAME, "loaded": True}
    return {"model": EMBEDDING_MODEL_NAME, "loaded": _model is not None}


def warm_up() -> None:
    """Load (and on first run, download) the model ahead of the first /close call."""
    if EMBEDDING_BACKEND != "hashing":
        _load_model()


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
    model = None if EMBEDDING_BACKEND == "hashing" else _load_model()
    if model is None:
        return _hashing_embed(text), HASHING_MODEL_NAME
    vector = [float(x) for x in next(iter(model.embed([text])))]
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector], EMBEDDING_MODEL_NAME


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
