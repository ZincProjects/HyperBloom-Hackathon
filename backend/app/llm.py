"""LLM calls for the three roles (persona, attacker, extractor), routed to Claude or the offline mock."""
import json
import logging
import re

import anthropic
from pydantic import ValidationError

from . import mock_llm
from .config import (
    CHAT_EFFORT, CHAT_MODEL, EXTRACTION_EFFORT, EXTRACTION_MODEL, REFUSAL_FALLBACKS, llm_mode,
)
from .prompts import (
    ATTACKER_KICKOFF, EXTRACTION_RETRY_TEMPLATE, EXTRACTION_SYSTEM_PROMPT, format_transcript,
)
from .schemas import ExtractedProfile

log = logging.getLogger("mirage.llm")

FALLBACK_BETA = "server-side-fallback-2026-07-01"
CHAT_MAX_TOKENS = 4000
EXTRACTION_MAX_TOKENS = 8000


class LLMError(RuntimeError):
    """An LLM call failed in a way the API layer should surface (HTTP 502)."""


_client: anthropic.Anthropic | None = None
_fallbacks_enabled = REFUSAL_FALLBACKS


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=3, timeout=90.0)
    return _client


def _create(**kwargs):
    """messages.create with server-side refusal fallbacks when available."""
    global _fallbacks_enabled
    client = _get_client()
    if _fallbacks_enabled:
        try:
            return client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
        except anthropic.BadRequestError as exc:
            if "fallback" not in str(exc).lower():
                raise
            log.warning("Refusal fallbacks rejected by the API (%s); continuing without them", exc)
            _fallbacks_enabled = False
    return client.messages.create(**kwargs)


def _complete(*, model: str, system: str, messages: list[dict], max_tokens: int, effort: str) -> str:
    try:
        response = _create(
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            output_config={"effort": effort},
        )
    except anthropic.AuthenticationError as exc:
        raise LLMError("Anthropic authentication failed - check ANTHROPIC_API_KEY.") from exc
    except anthropic.RateLimitError as exc:
        raise LLMError("Rate limited by the Anthropic API - wait a few seconds and retry.") from exc
    except anthropic.APIStatusError as exc:
        raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMError("Could not reach the Anthropic API - check your network connection.") from exc
    except anthropic.AnthropicError as exc:  # e.g. missing credentials
        raise LLMError(f"Anthropic client error: {exc}") from exc

    if response.stop_reason == "refusal":
        category = getattr(response.stop_details, "category", None) if response.stop_details else None
        raise LLMError(f"The model declined this turn (refusal category: {category}).")
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        raise LLMError(f"The model returned no text (stop_reason={response.stop_reason}).")
    return text


# --- Chat post-processing -------------------------------------------------------
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_LONG_NUMBER_RE = re.compile(r"\b\d(?:[ -]?\d){5,}\b")


def mask_sensitive(text: str) -> str:
    """Safety net for persona output: no realistic-looking SSNs or account/card/OTP numbers, ever."""
    text = _SSN_RE.sub("XXX-XX-XXXX", text)
    return _LONG_NUMBER_RE.sub(lambda m: "XXXX-" + re.sub(r"\D", "", m.group(0))[-4:], text)


def _clean_chat(text: str, speaker_name: str | None = None) -> str:
    text = text.strip()
    prefixes = ["ATTACKER:", "PERSONA:"] + ([f"{speaker_name}:", f"{speaker_name.split()[0]}:"] if speaker_name else [])
    for prefix in prefixes:
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


# --- Roles ---------------------------------------------------------------------
def persona_reply(incident) -> str:
    """The decoy employee's reply to the latest attacker message."""
    if llm_mode() == "mock":
        text = mock_llm.persona_reply(incident)
    else:
        history = [
            {"role": "user" if m.sender == "attacker" else "assistant", "content": m.content}
            for m in incident.messages
        ]
        text = _complete(
            model=CHAT_MODEL, system=incident.persona.system_prompt, messages=history,
            max_tokens=CHAT_MAX_TOKENS, effort=CHAT_EFFORT,
        )
    return mask_sensitive(_clean_chat(text, incident.persona.name))


def attacker_reply(incident) -> str:
    """The simulated attacker's next message, reacting to the persona's latest reply."""
    if llm_mode() == "mock":
        text = mock_llm.attacker_reply(incident)
    else:
        history = [{"role": "user", "content": ATTACKER_KICKOFF}] + [
            {"role": "assistant" if m.sender == "attacker" else "user", "content": m.content}
            for m in incident.messages
        ]
        text = _complete(
            model=CHAT_MODEL, system=incident.attacker_script.system_prompt, messages=history,
            max_tokens=CHAT_MAX_TOKENS, effort=CHAT_EFFORT,
        )
    return _clean_chat(text)


def _parse_profile(raw: str) -> ExtractedProfile:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in the reply")
    return ExtractedProfile.model_validate(json.loads(text[start:end + 1]))


def extract_profile(messages) -> tuple[ExtractedProfile, str]:
    """Structured incident profile from the transcript: (validated profile, analyzer name)."""
    if llm_mode() == "mock":
        return mock_llm.extract_profile(messages), "mock-heuristic"

    conversation = [{
        "role": "user",
        "content": f"<transcript>\n{format_transcript(messages)}\n</transcript>",
    }]
    for attempt in (1, 2):
        raw = _complete(
            model=EXTRACTION_MODEL, system=EXTRACTION_SYSTEM_PROMPT, messages=conversation,
            max_tokens=EXTRACTION_MAX_TOKENS, effort=EXTRACTION_EFFORT,
        )
        try:
            return _parse_profile(raw), EXTRACTION_MODEL
        except (ValueError, ValidationError) as exc:  # JSONDecodeError is a ValueError
            log.warning("Extraction attempt %d failed validation: %s", attempt, exc)
            if attempt == 2:
                raise LLMError(f"Extraction output failed validation after a retry: {exc}") from exc
            conversation += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": EXTRACTION_RETRY_TEMPLATE.format(error=exc)},
            ]
    raise AssertionError("unreachable")
