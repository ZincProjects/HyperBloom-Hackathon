# Extraction eval

A small, fixed, hand-labeled test set for MIRAGE's structured-extraction step, plus the harness that scores it.

```bash
python eval/run_eval.py
```

Run it from the repo root with the backend virtualenv's Python (`backend/.venv/Scripts/python` on Windows,
`backend/.venv/bin/python` elsewhere). With `ANTHROPIC_API_KEY` set (env or `backend/.env`) it calls the real
extraction path. Without a key it falls back to the offline regex/keyword baseline and says so in the output.

| Flag | Effect |
|---|---|
| `--mock` | Force the offline heuristic baseline (no API calls) |
| `--repeat N` | Run every case N times: reports the mean and how often the technique was identical across runs |
| `--update-readme` | Write the result block between the `EVAL` markers in the root README |
| `--json PATH` | Save per-case outputs (actual vs expected) |

## What gets run

Each fixture's transcript goes straight into `app.llm.extract_profile`, the same function `POST /incidents/{id}/close`
uses. That covers the same prompt, schema-constrained output, pydantic validation and single retry. Conversation
generation is skipped. A case that ends in `needs_review` (invalid output twice) or an API error scores zero and stays
in the denominator.

## Scoring

| Metric | Definition |
|---|---|
| Technique matches | Exact match of the MITRE ATT&CK technique ID |
| IOC-type overlap | Jaccard overlap of the *set of IOC types* (`url`, `phone`, `email`, `payment_account`, `other`); values are not compared |
| Tactic-tag overlap | Jaccard overlap of the manipulation-tactic sets |
| Case passes | Technique matches **and** both overlaps are at least 50% |

Jaccard penalises both missed labels and extra labels, so an extractor that tags every tactic doesn't score well.
`attacker_goal` and `attacker_goal_confidence` are reported but not scored.

## Fixtures

| File | Script type | Difficulty | Expected technique |
|---|---|---|---|
| `01_ceo_fraud_cfo_wire` | CEO Fraud | clean | T1656 |
| `02_ceo_fraud_gift_cards` | CEO Fraud | clean | T1656 |
| `03_fake_it_reset_link` | Fake IT Support | clean | T1598.003 |
| `04_fake_it_no_link` | Fake IT Support | clean | T1656 |
| `05_romance_crypto` | Romance Scam | clean | T1657 |
| `06_romance_gift_cards` | Romance Scam | clean | T1657 |
| `07_recruiter_portal_link` | Recruiter Scam | clean | T1598.003 |
| `08_recruiter_chat_harvest` | Recruiter Scam | clean | T1598 |
| `09_ambiguous_vendor_remittance` | vendor bank change + credential link | ambiguous | T1598.003 |
| `10_ambiguous_fragmentary_recon` | fragmentary reconnaissance | ambiguous | T1598 |

Each fixture has a `notes` field explaining its labels. The transcripts were written for this eval. They use
different wording and infrastructure from the simulator's seed scripts, so neither the mock baseline's keyword
lists nor the attacker prompts were built from them.

## Labeling guide

Labels follow the same written rules the extraction prompt gives the model
([backend/app/prompts.py](../backend/app/prompts.py)). The task is inherently multi-label (a CEO-fraud wire request is
also financial theft), so an exact-match score is only meaningful if labeler and model share one tie-break policy.

**Technique:** the first rule that matches.
1. A link to a page meant to capture credentials, codes, or personal/financial data → `T1598.003`
2. Pretending to be a specific trusted person or internal function (executive, IT, HR, a known vendor) → `T1656`
3. Eliciting personal, account or financial information directly in the chat, without such a link → `T1598`
4. An outsider building rapport, then asking for money, gift cards or crypto → `T1657`
5. Otherwise the best remaining fit; `T1566` only if nothing more specific applies

**IOC types:** only indicators the attacker supplied. Gift-card, wallet and bank instructions are `payment_account`.
Messaging handles and ticket/invoice numbers are `other`.

**Tactics:** only when the attacker clearly used them (definitions in `backend/app/mitre.py`).

## Honest limits

- n=10, written and labeled by the same team that wrote the prompt. The tie-break rules were written before any
  scored run, and the fixtures were not used to tune the prompt. Tuning the prompt against these cases would make
  this no longer a held-out measurement. Add new cases before doing that.
- It measures agreement with our labels on these transcripts, not accuracy on live attacker traffic.
- `claude-opus-5` does not accept `temperature`, so repeated runs can differ. Use `--repeat` to measure how much.
