"""Contract tests for the live Claude path, run against a mock HTTP transport (no API key or network).

    cd backend && python tests/test_llm_contract.py
"""
import json
import os
import sys
import typing
from pathlib import Path
from types import SimpleNamespace

os.environ["MIRAGE_LLM_MODE"] = "live"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic  # noqa: E402
import httpx2  # noqa: E402
from anthropic import DefaultHttpxClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app import llm, schemas  # noqa: E402
from app.prompts import EXTRACTION_SYSTEM_PROMPT  # noqa: E402

_ORIGINAL_UNSUPPORTED = set(llm._SAMPLING_UNSUPPORTED)

GOOD_PROFILE = {
    "mitre_technique": "T1656",
    "iocs": [{"type": "payment_account", "value": "acct XXXX-7731"}],
    "manipulation_tactics": ["urgency", "authority"],
    "attacker_goal": "Impersonate the CEO to get the target to wire money to an attacker account.",
    "attacker_goal_confidence": "high",
}


def message(text, stop_reason="end_turn"):
    return {
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5",
        "content": [{"type": "text", "text": text}] if text else [],
        "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def api_error(status, kind, text):
    return status, {"type": "error", "error": {"type": kind, "message": text}}


class FakeAPI:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        body = json.loads(request.content)
        self.requests.append({"url": str(request.url), "headers": request.headers, "body": body})
        status, payload = self.responses.pop(0)
        return httpx2.Response(status, json=payload)


def install(fake, extraction_model="claude-opus-5"):
    llm._client = anthropic.Anthropic(
        api_key="test-key", base_url="http://mock.anthropic", max_retries=0,
        http_client=DefaultHttpxClient(transport=httpx2.MockTransport(fake)),
    )
    llm._fallbacks_enabled = True
    llm._SAMPLING_UNSUPPORTED.clear()
    llm._SAMPLING_UNSUPPORTED.update(_ORIGINAL_UNSUPPORTED)
    llm.EXTRACTION_MODEL = extraction_model


def make_incident():
    msgs = [
        SimpleNamespace(sender="attacker", content="Hi Amy, it's Daniel. Are you at your desk?"),
        SimpleNamespace(sender="persona", content="hi! who is this exactly?"),
        SimpleNamespace(sender="attacker", content="Wire $48,500 to acct XXXX-7731 now."),
    ]
    return SimpleNamespace(
        messages=msgs,
        persona=SimpleNamespace(name="Amy Tran", system_prompt="PERSONA PROMPT"),
        attacker_script=SimpleNamespace(name="CEO Fraud", system_prompt="ATTACKER PROMPT"),
    )


def expect_raises(exc_type, fn):
    try:
        fn()
    except exc_type as exc:
        return exc
    raise AssertionError(f"expected {exc_type.__name__}")


# --- Conversational calls -------------------------------------------------------
def test_persona_request_shape_and_masking():
    fake = FakeAPI([(200, message("Amy: sure, my card is 4111 1111 1111 1234 lol"))])
    install(fake)
    reply = llm.persona_reply(make_incident())
    req = fake.requests[0]
    assert "beta=true" in req["url"], req["url"]
    assert llm.FALLBACK_BETA in req["headers"]["anthropic-beta"]
    body = req["body"]
    assert body["model"] == "claude-opus-5" and body["fallbacks"] == "default"
    assert body["output_config"] == {"effort": "low"}
    assert "temperature" not in body
    assert body["system"] == "PERSONA PROMPT"
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert reply == "sure, my card is XXXX-1234 lol", reply


def test_attacker_history_starts_with_user_turn_and_no_temperature():
    fake = FakeAPI([(200, message("Please hurry, the deal closes at 3pm."))])
    install(fake, extraction_model="claude-haiku-4-5")  # even when the extractor accepts temperature
    incident = make_incident()
    incident.messages.append(SimpleNamespace(sender="persona", content="let me double check first"))
    reply = llm.attacker_reply(incident)
    body = fake.requests[0]["body"]
    assert body["system"] == "ATTACKER PROMPT"
    assert "temperature" not in body
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user", "assistant", "user"]
    assert reply.startswith("Please hurry")


# --- Extraction call ------------------------------------------------------------
def test_extraction_is_schema_constrained_and_omits_temperature_on_opus_5():
    fake = FakeAPI([(200, message(json.dumps(GOOD_PROFILE)))])
    install(fake)
    profile, analyzer = llm.extract_profile(make_incident().messages)
    body = fake.requests[0]["body"]
    assert body["system"] == EXTRACTION_SYSTEM_PROMPT
    assert body["output_config"] == {
        "effort": "medium", "format": {"type": "json_schema", "schema": schemas.EXTRACTION_JSON_SCHEMA},
    }
    assert "temperature" not in body  # Opus 5 rejects sampling params with a 400
    assert profile.mitre_technique == "T1656" and profile.attacker_goal_confidence == "high"
    assert analyzer == "claude-opus-5"


def test_extraction_sends_temperature_zero_when_model_accepts_it():
    fake = FakeAPI([(200, message(json.dumps(GOOD_PROFILE)))])
    install(fake, extraction_model="claude-haiku-4-5")
    llm.extract_profile(make_incident().messages)
    assert fake.requests[0]["body"]["temperature"] == 0


def test_rejected_temperature_is_dropped_and_remembered():
    fake = FakeAPI([
        api_error(400, "invalid_request_error", "temperature: not supported for this model"),
        (200, message(json.dumps(GOOD_PROFILE))),
    ])
    install(fake, extraction_model="claude-sonnet-4-6")
    llm.extract_profile(make_incident().messages)
    assert fake.requests[0]["body"]["temperature"] == 0
    assert "temperature" not in fake.requests[1]["body"]
    assert not llm.sampling_supported("claude-sonnet-4-6")


def test_extraction_retries_once_with_error_feedback():
    bad = dict(GOOD_PROFILE, mitre_technique="T1656 — Impersonation")  # label form, not the bare ID
    fake = FakeAPI([(200, message("```json\n" + json.dumps(bad) + "\n```")), (200, message(json.dumps(GOOD_PROFILE)))])
    install(fake)
    profile, _ = llm.extract_profile(make_incident().messages)
    assert profile.mitre_technique == "T1656"
    retry_messages = fake.requests[1]["body"]["messages"]
    assert [m["role"] for m in retry_messages] == ["user", "assistant", "user"]
    assert "mitre_technique" in retry_messages[2]["content"]


def test_extraction_stops_after_one_retry_and_keeps_raw_output():
    fake = FakeAPI([
        (200, message("not json at all")),
        (200, message(json.dumps(dict(GOOD_PROFILE, manipulation_tactics=["greed"])))),
        (200, message(json.dumps(GOOD_PROFILE))),  # must never be requested
    ])
    install(fake)
    exc = expect_raises(llm.ExtractionValidationError, lambda: llm.extract_profile(make_incident().messages))
    assert len(fake.requests) == 2, "retry once, then stop"
    assert isinstance(exc, llm.LLMError)
    assert "not json at all" in exc.raw_output and '"greed"' in exc.raw_output
    assert "attempt 1" in exc.raw_output and "attempt 2" in exc.raw_output


def test_strict_schema_rejects_near_misses():
    near_misses = [
        {"mitre_technique": "t1656"},
        {"mitre_technique": "T1656 — Impersonation"},
        {"mitre_technique": "T9999"},
        {"manipulation_tactics": ["Urgency"]},
        {"manipulation_tactics": ["greed"]},
        {"attacker_goal_confidence": "certain"},
        {"iocs": [{"type": "URL", "value": "https://x.example"}]},
        {"iocs": [{"type": "url", "value": "   "}]},
        {"unexpected_key": "x"},
    ]
    for change in near_misses:
        expect_raises(ValidationError, lambda: schemas.ExtractedProfile.model_validate({**GOOD_PROFILE, **change}))
    missing = dict(GOOD_PROFILE)
    del missing["attacker_goal_confidence"]
    expect_raises(ValidationError, lambda: schemas.ExtractedProfile.model_validate(missing))
    schemas.ExtractedProfile.model_validate(GOOD_PROFILE)


def test_json_schema_enums_match_pydantic_literals():
    props = schemas.EXTRACTION_JSON_SCHEMA["properties"]
    assert props["mitre_technique"]["enum"] == list(typing.get_args(schemas.TechniqueId))
    assert props["manipulation_tactics"]["items"]["enum"] == list(typing.get_args(schemas.Tactic))
    assert props["iocs"]["items"]["properties"]["type"]["enum"] == list(typing.get_args(schemas.IOCType))
    assert props["attacker_goal_confidence"]["enum"] == list(typing.get_args(schemas.Confidence))
    assert set(schemas.EXTRACTION_JSON_SCHEMA["required"]) == set(schemas.ExtractedProfile.model_fields)


# --- Failure handling -----------------------------------------------------------
def test_refusal_raises_llm_error():
    fake = FakeAPI([(200, message("", stop_reason="refusal"))])
    install(fake)
    exc = expect_raises(llm.LLMError, lambda: llm.persona_reply(make_incident()))
    assert "declined" in str(exc)


def test_fallbacks_rejected_then_plain_request():
    fake = FakeAPI([api_error(400, "invalid_request_error", "fallbacks: not enabled for this org"), (200, message("ok one sec"))])
    install(fake)
    assert llm.persona_reply(make_incident()) == "ok one sec"
    assert "fallbacks" not in fake.requests[1]["body"]
    assert "beta=true" not in fake.requests[1]["url"]


def test_auth_error_is_readable():
    fake = FakeAPI([api_error(401, "authentication_error", "invalid x-api-key")])
    install(fake)
    exc = expect_raises(llm.LLMError, lambda: llm.persona_reply(make_incident()))
    assert "ANTHROPIC_API_KEY" in str(exc)


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"{len(tests)} passed")
