"""MITRE ATT&CK techniques relevant to social engineering, plus the defensive-action lookup table.

IDs and names are from the public ATT&CK Enterprise matrix (attack.mitre.org).
"""
import re

TECHNIQUES: dict[str, dict] = {
    "T1566": {
        "name": "Phishing",
        "explanation": "The attacker sent a deceptive message to trick the target into giving access or taking a harmful action.",
        "defenses": [
            "Run regular phishing-awareness training that uses real examples like this incident.",
            "Enable a one-click 'report phishing' button and route reports to the SOC.",
            "Enforce SPF, DKIM and DMARC to reduce spoofed sender addresses.",
        ],
    },
    "T1566.002": {
        "name": "Spearphishing Link",
        "explanation": "A targeted message pushed the victim to click a malicious link, typically to a fake login or payment page.",
        "defenses": [
            "Block the IOC domains/URLs at the web proxy and email gateway.",
            "Deploy URL rewriting / time-of-click link scanning on email and chat.",
            "Require phishing-resistant MFA (FIDO2/passkeys) so harvested passwords are useless.",
        ],
    },
    "T1566.003": {
        "name": "Spearphishing via Service",
        "explanation": "The attacker approached the target through a third-party service (social media, personal messaging, job sites) outside corporate email controls.",
        "defenses": [
            "Train staff that recruiters, 'executives' or admirers on personal channels are a common lure.",
            "Publish an official list of company communication channels and verify out-of-band.",
            "Report the attacker profile/handle to the hosting platform for takedown.",
        ],
    },
    "T1566.004": {
        "name": "Spearphishing Voice",
        "explanation": "The attacker used phone calls or voice messages (vishing) to pressure the target into acting.",
        "defenses": [
            "Adopt a callback policy: verify requests by calling a number from the internal directory, never one supplied by the caller.",
            "Block the IOC phone numbers on corporate telephony.",
            "Train helpdesk and finance staff on vishing scripts.",
        ],
    },
    "T1598": {
        "name": "Phishing for Information",
        "explanation": "The goal was to elicit sensitive information (personal, financial or account details) rather than to deliver malware.",
        "defenses": [
            "Never share personal, payroll or banking information over chat or email; use verified HR/finance portals.",
            "Flag unsolicited requests for SSNs, bank details or ID documents for security review.",
            "Monitor for follow-on account takeover or identity-fraud attempts against the targeted employee.",
        ],
    },
    "T1598.003": {
        "name": "Spearphishing Link (Phishing for Information)",
        "explanation": "A targeted link led the victim to a page designed to capture credentials or other sensitive data.",
        "defenses": [
            "Block the credential-harvesting domains and hunt for any users who visited them.",
            "Require phishing-resistant MFA and alert on logins from new devices after a reported lure.",
            "Remind staff that IT will never ask them to 'verify' a password via a link.",
        ],
    },
    "T1656": {
        "name": "Impersonation",
        "explanation": "The attacker pretended to be a trusted person (an executive, IT staff, a vendor) to exploit that trust.",
        "defenses": [
            "Require out-of-band verification (call back via the internal directory) for any unusual request from an 'executive' or 'IT'.",
            "Enforce dual approval for payments, vendor bank changes and account resets.",
            "Tag external senders visibly in email and chat clients.",
        ],
    },
    "T1199": {
        "name": "Trusted Relationship",
        "explanation": "The attacker abused (or posed as) a trusted third party such as a vendor, partner or service provider.",
        "defenses": [
            "Verify vendor bank-detail changes using contact details already on file, never from the request.",
            "Maintain an approved-vendor register with named points of contact.",
            "Review third-party access and alert on anomalous partner activity.",
        ],
    },
    "T1534": {
        "name": "Internal Spearphishing",
        "explanation": "The lure appeared to come from inside the organisation, leveraging internal trust and context.",
        "defenses": [
            "Investigate whether the impersonated internal account is compromised and reset its credentials.",
            "Alert on internal messages containing payment or credential requests.",
            "Remind staff that internal senders can be compromised too; verify unusual asks.",
        ],
    },
    "T1657": {
        "name": "Financial Theft",
        "explanation": "The attacker's end goal was to steal money, e.g. via wire transfer, gift cards or cryptocurrency.",
        "defenses": [
            "Enforce dual authorization and a cooling-off period for urgent or first-time payments.",
            "Share the payment IOCs (accounts, wallets) with your bank's fraud team.",
            "Treat any request for gift cards or crypto as fraud by default.",
        ],
    },
    "T1589.001": {
        "name": "Gather Victim Identity Information: Credentials",
        "explanation": "The attacker was collecting account credentials for later use against the organisation.",
        "defenses": [
            "Force a password reset for the targeted account and review recent sign-ins.",
            "Enable leaked-credential monitoring and MFA fatigue protections.",
            "Reinforce that no legitimate process asks for passwords or MFA codes over chat.",
        ],
    },
    "T1585.001": {
        "name": "Establish Accounts: Social Media Accounts",
        "explanation": "The attacker built a fake social media persona to establish rapport before exploiting the target.",
        "defenses": [
            "Report the fake profile to the platform for takedown.",
            "Train staff on long-con rapport-building scams (romance, fake recruiters).",
            "Limit publicly exposed employee details that attackers use for targeting.",
        ],
    },
}

TECHNIQUE_IDS: tuple[str, ...] = tuple(TECHNIQUES)

TACTICS = ["urgency", "authority", "scarcity", "fear", "likability", "reciprocity"]

TACTIC_DESCRIPTIONS = {
    "urgency": "Artificial time pressure to prevent careful thought.",
    "authority": "Claims of seniority or official status to discourage questioning.",
    "scarcity": "Framing an opportunity as limited or exclusive.",
    "fear": "Threats of negative consequences (lockout, discipline, loss).",
    "likability": "Flattery and rapport to lower the target's guard.",
    "reciprocity": "Favours or gifts that create a sense of obligation.",
}

GENERIC_DEFENSES = [
    "Report the conversation to the security team and share the IOCs with your threat-intel feed.",
    "Verify any unusual request through a separate, known-good channel before acting.",
]

_ID_RE = re.compile(r"T\d{4}(?:\.\d{3})?")


def canonical_technique(value: str) -> str | None:
    """Map free-form model output (e.g. 'T1656 Impersonation') to 'T1656 — Impersonation'."""
    match = _ID_RE.search(value or "")
    if not match or match.group(0) not in TECHNIQUES:
        return None
    tid = match.group(0)
    return f"{tid} — {TECHNIQUES[tid]['name']}"


def technique_label(tid: str) -> str:
    """'T1656' -> 'T1656 — Impersonation' (the form stored on incident_profiles)."""
    return f"{tid} — {TECHNIQUES[tid]['name']}"


def technique_id(value: str) -> str | None:
    match = _ID_RE.search(value or "")
    return match.group(0) if match and match.group(0) in TECHNIQUES else None


def technique_prompt_list() -> str:
    return "\n".join(f"- {tid} — {t['name']}: {t['explanation']}" for tid, t in TECHNIQUES.items())
