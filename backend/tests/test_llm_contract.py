"""Contract tests for the live Claude path, run against a mock HTTP transport (no API key or network).

    cd backend && python tests/test_llm_contract.py
"""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ["MIRAGE_LLM_MODE"] = "live"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic  # noqa: E402
import httpx2  # noqa: E402
from anthropic import DefaultHttpxClient  # noqa: E402

from app import llm  # noqa: E402


def message(text, stop_reason="end_turn"):
    return {
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5",
        "content": [{"type": "text", "text": text}] if text else [],
        "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


class FakeAPI:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        body = json.loads(request.content)
        self.requests.append({"url": str(request.url), "headers": request.headers, "body": body})
        status, payload = self.responses.pop(0)
        return httpx2.Response(status, json=payload)


def install(fake):
    llm._client = anthropic.Anthropic(
        api_key="test-key", base_url="http://mock.anthropic", max_retries=0,
        http_client=DefaultHttpxClient(transport=httpx2.MockTransport(fake)),
    )
    llm._fallbacks_enabled = True


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
    assert body["system"] == "PERSONA PROMPT"
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert reply == "sure, my card is XXXX-1234 lol", reply


def test_attacker_history_starts_with_user_turn():
    fake = FakeAPI([(200, message("Please hurry, the deal closes at 3pm."))])
    install(fake)
    incident = make_incident()
    incident.messages.append(SimpleNamespace(sender="persona", content="let me double check first"))
    reply = llm.attacker_reply(incident)
    body = fake.requests[0]["body"]
    assert body["system"] == "ATTACKER PROMPT"
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user", "assistant", "user"]
    assert reply.startswith("Please hurry")


def test_extraction_retries_once_with_error_feedback():
    good = {
        "mitre_technique": "T1656 — Impersonation",
        "iocs": [{"type": "payment_account", "value": "acct XXXX-7731"}],
        "manipulation_tactics": ["urgency", "authority"],
        "attacker_goal": "Impersonate the CEO to get the target to wire money to an attacker account.",
    }
    bad = dict(good, mitre_technique="T9999 — Made Up")
    fake = FakeAPI([(200, message("```json\n" + json.dumps(bad) + "\n```")), (200, message(json.dumps(good)))])
    install(fake)
    profile, analyzer = llm.extract_profile(make_incident().messages)
    assert profile.mitre_technique == "T1656 — Impersonation" and analyzer == "claude-opus-5"
    retry_messages = fake.requests[1]["body"]["messages"]
    assert [m["role"] for m in retry_messages] == ["user", "assistant", "user"]
    assert "not in the allowed list" in retry_messages[2]["content"]


def test_extraction_fails_after_second_invalid_reply():
    fake = FakeAPI([(200, message("not json")), (200, message("still not json"))])
    install(fake)
    try:
        llm.extract_profile(make_incident().messages)
    except llm.LLMError as exc:
        assert "after a retry" in str(exc)
    else:
        raise AssertionError("expected LLMError")


def test_refusal_raises_llm_error():
    fake = FakeAPI([(200, message("", stop_reason="refusal"))])
    install(fake)
    try:
        llm.persona_reply(make_incident())
    except llm.LLMError as exc:
        assert "declined" in str(exc)
    else:
        raise AssertionError("expected LLMError")


def test_fallbacks_rejected_then_plain_request():
    error = {"type": "error", "error": {"type": "invalid_request_error", "message": "fallbacks: not enabled for this org"}}
    fake = FakeAPI([(400, error), (200, message("ok one sec"))])
    install(fake)
    assert llm.persona_reply(make_incident()) == "ok one sec"
    assert "fallbacks" not in fake.requests[1]["body"]
    assert "beta=true" not in fake.requests[1]["url"]


def test_auth_error_is_readable():
    error = {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
    fake = FakeAPI([(401, error)])
    install(fake)
    try:
        llm.persona_reply(make_incident())
    except llm.LLMError as exc:
        assert "ANTHROPIC_API_KEY" in str(exc)
    else:
        raise AssertionError("expected LLMError")


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"{len(tests)} passed")
