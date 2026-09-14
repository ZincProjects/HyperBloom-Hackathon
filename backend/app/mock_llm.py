"""Deterministic offline stand-in for Claude (MIRAGE_LLM_MODE=mock, or auto with no API key).

Lets the whole pipeline - simulation, extraction, embeddings, linking, reports - run without network
access. Extraction here is a regex/keyword heuristic, so it is clearly labelled `mock-heuristic`.
"""
import re

from .mitre import TECHNIQUES
from .schemas import IOC, ExtractedProfile
from .seed_data import ATTACKER_SCRIPTS, PERSONA_MOCK_LINES

_SCRIPT_LINES = {s["name"]: s["mock_lines"] for s in ATTACKER_SCRIPTS}


def _first_name(incident) -> str:
    return incident.persona.name.split()[0]


def persona_reply(incident) -> str:
    turn = sum(1 for m in incident.messages if m.sender == "persona")
    return PERSONA_MOCK_LINES[(turn + incident.persona_id) % len(PERSONA_MOCK_LINES)]


def attacker_reply(incident) -> str:
    lines = _SCRIPT_LINES.get(incident.attacker_script.name) or [
        "I need you to act on this right now, please don't make me escalate it."
    ]
    # The opening message was attacker turn 0, so the next line index is (attacker turns - 1).
    turn = sum(1 for m in incident.messages if m.sender == "attacker") - 1
    if turn >= len(lines):  # keep escalating with the last two lines
        turn = len(lines) - 2 + (turn - len(lines)) % 2
    return lines[max(turn, 0)].replace("{target_first_name}", _first_name(incident))


# --- Heuristic extraction ------------------------------------------------------
_URL_RE = re.compile(r"https?://[^\s,)\"']+")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RE = re.compile(r"\+\d[\d\s().-]{8,}\d")
_PAYMENT_RE = re.compile(
    r"(?:(?:acct|account|routing|wallet)\s*(?:#|no\.?)?\s*)?(?:XXXX-\d{4}|bc1q-[A-Za-z0-9-]+)", re.I
)
_GIFT_CARD_RE = re.compile(r"\b(?:steam|apple|google play|amazon)\s+gift\s+cards?\b", re.I)
_REF_RE = re.compile(r"\b(?:INC|INV|REQ)-\d{4,}\b")
_HANDLE_RE = re.compile(r"(?<![\w.])@[A-Za-z_]\w{3,}")

_TACTIC_KEYWORDS = {
    "urgency": ["urgent", "asap", "right now", "immediately", "today", "minutes", "before 3pm", "expires", "until tomorrow", "every minute"],
    "authority": ["ceo", "board", "service desk", "security monitoring", "standard procedure", "senior talent partner", "manager is aware"],
    "scarcity": ["only 3", "other candidates", "lose this spot", "one of only", "limited"],
    "fear": ["lock", "lockout", "lose email", "falls apart", "want to know why", "failed attempt", "frozen"],
    "likability": ["kind person", "make me smile", "impressed", "trust you", "something special", "really talk to you"],
    "reciprocity": ["remember who stepped up", "pay you back", "reimbursed", "double"],
}

_TECHNIQUE_KEYWORDS = {
    "T1656": ["ceo", "wire", "invoice", "acquisition", "board"],
    "T1598.003": ["password", "sign in", "reset", "verification code", "mfa"],
    "T1657": ["gift card", "wallet", "crypto", "pay you back", "customs"],
    "T1598": ["ssn", "date of birth", "onboarding", "direct deposit", "background check"],
}

_GOALS = {
    "T1656": "Impersonate a company executive to pressure the target into an urgent, confidential wire transfer to an attacker-controlled account.",
    "T1598.003": "Pose as IT support to steer the target to a fake reset portal and harvest their password and MFA code.",
    "T1657": "Build a fake romantic connection, then invent an emergency so the target sends money via crypto or gift cards.",
    "T1598": "Lure the target with a fake job offer to harvest their SSN, bank details and an upfront background-check fee.",
}


def extract_profile(messages) -> ExtractedProfile:
    attacker_text = "\n".join(m.content for m in messages if m.sender == "attacker")
    lower = attacker_text.lower()

    iocs: list[IOC] = []
    urls = [u.rstrip(".") for u in _URL_RE.findall(attacker_text)]
    iocs += [IOC(type="url", value=u) for u in urls]
    iocs += [IOC(type="email", value=e) for e in _EMAIL_RE.findall(attacker_text)]
    iocs += [IOC(type="phone", value=p.strip()) for p in _PHONE_RE.findall(attacker_text)]
    iocs += [IOC(type="payment_account", value=p.strip()) for p in _PAYMENT_RE.findall(attacker_text)]
    iocs += [IOC(type="payment_account", value=g) for g in _GIFT_CARD_RE.findall(attacker_text)]
    iocs += [IOC(type="other", value=r) for r in _REF_RE.findall(attacker_text)]
    iocs += [IOC(type="other", value=h) for h in _HANDLE_RE.findall(attacker_text)]

    tactics = [t for t, words in _TACTIC_KEYWORDS.items() if any(w in lower for w in words)]
    scores = {tid: sum(lower.count(w) for w in words) for tid, words in _TECHNIQUE_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        best = "T1566"
    goal = _GOALS.get(best, "Manipulate the target into taking a harmful action or disclosing sensitive information.")

    return ExtractedProfile(
        mitre_technique=f"{best} — {TECHNIQUES[best]['name']}",
        iocs=iocs,
        manipulation_tactics=tactics,
        attacker_goal=goal,
    )
