# MIRAGE — AI Deception & Threat Intelligence

MIRAGE puts AI "employee" decoys in front of social-engineering attackers. The decoys chat back like real, slightly
distractible staff, stall the attacker and draw out their infrastructure, and never reveal they are AI. When a
conversation closes, a second LLM pass turns the transcript into a structured incident record (MITRE ATT&CK
technique, IOCs, manipulation tactics, attacker goal). That record is embedded and compared against every past
incident, so MIRAGE can tell when two conversations with different decoys come from the **same attacker or
campaign**.

Real attackers won't show up for a demo, so MIRAGE includes a **Red-Team Simulator**: a second LLM plays a scripted
scammer (CEO fraud, fake IT support, romance scam, recruiter scam). That lets the whole pipeline run live and
self-contained.

```mermaid
flowchart LR
    A[Attacker LLM<br/>scam script] -- message --> P[Decoy persona LLM<br/>Amy / Marcus]
    P -- stalls & probes --> A
    P --> T[(Transcript<br/>messages)]
    T -- Close & analyze --> X[Extraction LLM<br/>strict JSON + pydantic]
    X --> R[(incident_profiles<br/>technique · IOCs · tactics · goal)]
    R --> E[all-MiniLM-L6-v2<br/>embedding]
    E --> S{cosine similarity<br/>vs past incidents}
    S -- above threshold --> L[(incident_links)]
    L --> U[union-find<br/>attacker clusters]
    U --> D[Dashboard · Threat Map · Report]
```

---

## Reliability: measured, not claimed

MIRAGE doesn't quote an accuracy figure it can't back up. The extraction step is scored by a harness anyone can
re-run, against 10 hand-labeled transcripts: 8 clean cases across the four scam types, plus 2 deliberately ambiguous
ones. The latest measured result:

<!-- EVAL:START -->
Measured with `python eval/run_eval.py` on 2026-09-14. Analyzer: `mock-heuristic` (max_attempts=2).

```text
RESULT: 7/10 technique matches, 85% IOC-type overlap, 46% tactic-tag overlap, 0/10 needs_review (held-out eval, n=10, analyzer=mock-heuristic)
by difficulty: ambiguous (n=2): 1/2 technique, 50% IOC-type, 50% tactics | clean (n=8): 6/8 technique, 94% IOC-type, 45% tactics
cases passing all checks: 2/10 (technique exact + IOC-type and tactic overlap >= 50%)
attacker_goal_confidence: high 3, medium 7, low 0
```

What this measures: agreement with our own labels on n=10 hand-labeled transcripts (2 ambiguous, 8 clean). It is a small, fixed test set, not a guarantee of accuracy on live or unseen attacker traffic.

> **Note:** this block was produced by the offline regex/keyword baseline, not by Claude. Re-run with `ANTHROPIC_API_KEY` set and `--update-readme` to record the Claude number.
<!-- EVAL:END -->

**When the model isn't confident, MIRAGE fails visibly instead of fabricating.** Every extraction must pass a strict
schema. If the output fails validation on the first attempt and again on one retry (with the validation error fed
back), the incident is marked **needs_review**. No guessed profile, IOCs or campaign links are written. The raw model
output is kept for an analyst, and the dashboard shows a distinct badge with a **Retry extraction** button. This is a
deliberate design choice: a missing profile is safer than a confident-looking wrong one.
Every profile that does pass also carries the model's self-reported `attacker_goal_confidence` (high/medium/low),
shown next to the goal summary.

How the extraction call is tightened:
- **Closed vocabularies, enforced twice.** Schema-constrained decoding (`output_config.format` with enums) and strict
  pydantic `Literal`s with `extra="forbid"` both cover technique IDs, tactics, IOC types and confidence. Near-misses
  such as `Urgency` or `T1656 — Impersonation` are rejected, not normalised.
- **Temperature.** `temperature=0` is sent on the extraction call only; persona and attacker turns keep the
  conversational default. `claude-opus-5` rejects sampling parameters with a 400, so on that model temperature is
  omitted and determinism comes from constrained decoding. `run_eval.py --repeat N` measures the remaining
  run-to-run variation.
- **One written tie-break policy** for the technique choice (a CEO-fraud wire is also "financial theft"). The
  extraction prompt and the eval labels share it.

Scoring definitions, the labeling guide and the fixtures are in [eval/README.md](eval/README.md).

---

## Quick start

**Prerequisites:** Python 3.10–3.13 (PyTorch has no wheels for 3.14 yet) and Node 20.19+ or 22.12+.

### 1. Backend

```bash
cd backend
python -m venv .venv
```

Activate it with `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (macOS/Linux). Then:

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env
```

Put your `ANTHROPIC_API_KEY` in `backend/.env`, then start the API:

```bash
uvicorn app.main:app --reload --port 8000
```

On first start, MIRAGE creates the SQLite DB, seeds 2 personas and 4 attacker scripts, and loads the embedding model
in the background. The model (~90 MB) downloads from Hugging Face on the first run and works offline after that.
Interactive API docs are at http://localhost:8000/docs.

### 2. Frontend

```bash
cd frontend
npm install
```

```bash
npm run dev
```

Open http://localhost:5173. Vite proxies `/api/*` to the backend on port 8000.

### No API key? Offline mock mode

Without `ANTHROPIC_API_KEY` (or with `MIRAGE_LLM_MODE=mock`), MIRAGE swaps Claude for a deterministic offline stand-in:
scripted attacker lines, canned decoy replies, and a regex/keyword extractor. Embeddings, similarity linking,
clustering, reports and the whole UI still run for real. The header badge shows **OFFLINE MOCK LLM**, and profiles
are labelled `analyzer: mock-heuristic`. This is useful as a backup if the venue Wi-Fi dies, but demo in live mode.

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required for live Claude conversations |
| `DATABASE_URL` | `sqlite:///backend/mirage.db` | Any SQLAlchemy URL. `postgresql://…` and `postgres://…` are normalised to psycopg 3 |
| `MIRAGE_LLM_MODE` | `auto` | `auto` (live if a key is set), `live`, or `mock` |
| `MIRAGE_CHAT_MODEL` | `claude-opus-5` | Model for the persona and attacker turns |
| `MIRAGE_EXTRACTION_MODEL` | `claude-opus-5` | Model for structured extraction |
| `MIRAGE_CHAT_EFFORT` | `low` | Effort for chat turns (short replies, lower latency) |
| `MIRAGE_EXTRACTION_EFFORT` | `medium` | Effort for extraction |
| `MIRAGE_EXTRACTION_TEMPERATURE` | `0` | Sent on the extraction call only, and only to models that accept sampling params (not Opus 5 / 4.8 / 4.7 or Sonnet 5) |
| `MIRAGE_STRUCTURED_OUTPUTS` | `1` | Schema-constrained decoding for extraction |
| `MIRAGE_MOCK_FORCE_INVALID_EXTRACTION` | `0` | Testing only: the offline mock extractor emits schema-invalid output, to demo the `needs_review` path |
| `MIRAGE_REFUSAL_FALLBACKS` | `1` | Server-side refusal fallbacks (`fallbacks: "default"`); turned off automatically if the API rejects them |
| `MIRAGE_EMBEDDINGS` | `auto` | `auto` (sentence-transformers, falling back to hashing if unavailable) or `hashing` |
| `MIRAGE_SIMILARITY_THRESHOLD` | `0.70` | Cosine threshold for linking incidents (see [calibration](#how-the-campaign-linking-works)) |
| `MIRAGE_CORS_ORIGINS` | `*` | Comma-separated origins, for a split frontend/backend deploy |

Each exchange makes two Claude calls (decoy reply, then attacker reply). If turns feel slow on stage, you can set
`MIRAGE_CHAT_MODEL` to a faster model and keep extraction on Opus.

### Using Postgres

```bash
docker run -d --name mirage-pg -e POSTGRES_USER=mirage -e POSTGRES_PASSWORD=mirage -e POSTGRES_DB=mirage -p 5432:5432 postgres:16
```

Then set `DATABASE_URL=postgresql://mirage:mirage@localhost:5432/mirage` in `backend/.env`. The models only use
portable types (`JSON`, `Text`, `Float`), so the same code runs on both databases. Embeddings are stored as JSON float
arrays and compared in Python. At hackathon scale (dozens of incidents) that needs no vector DB. `pgvector` is the
natural next step at larger scale.

---

## Demo script (≈4 minutes)

**Before going on stage:** start both servers, click **Reset demo** (top right), and confirm the header badge says
**LIVE · claude-opus-5**.

1. **Open the dashboard.** *"MIRAGE deploys AI employees as bait for social engineers. The stat cards up top are our
   live threat picture."*
2. **Start a new simulation: Amy Tran vs. CEO Fraud.** *"Amy is a three-week-old finance hire, exactly who a CEO-fraud
   crew targets. The attacker here is also an LLM, running a scam script that adapts to what she says."*
3. **Click *Next exchange* about 5 times, narrating as you go** (or turn on *Auto-play*).
   - *"Watch Amy: chatty, apologetic, over-sharing about onboarding. She never says no. She stalls."*
   - *"She's asking for a callback number, who approved it, the exact account. Every question is intel collection."*
   - *"The attacker is escalating: urgency, the board, 'I'll remember who stepped up'. It reacts to her stalling
     instead of reading a fixed script."*
   - *"Amy never hands over anything real. Any number she mentions is masked, like XXXX-1234."*
4. **Click *Close & analyze*.** *"A second LLM pass reads the whole transcript and returns strict JSON, validated
   against a schema."* Point at the right panel: the **MITRE ATT&CK technique** with a plain-English explanation, the
   **IOC table** (the payment account, invoice link, lookalike email), and the **manipulation tactic** tags. The same
   IOCs light up amber in the transcript. Point at the **confidence badge** next to the goal: *"the model rates its
   own summary, and we show that instead of hiding uncertainty."*
5. **Start a second simulation with a *different* persona and the *same* script: Marcus Bell vs. CEO Fraud.** Play 4–5
   exchanges. *"Different target: Marcus is a helpdesk tech. Different conversation, different wording."*
6. **Click *Close & analyze*.** The amber **Campaign match detected** banner and toast appear, with the similarity
   score. Open the **Threat Map** tab: the two incidents sit inside one pulsing **CAMPAIGN-01** halo, with their shared
   infrastructure listed beside it.
   *"This is the ML clustering recognising it's the same attack campaign, not just two LLM calls. Each incident
   profile is embedded into a vector, and cosine similarity plus union-find clustering over those links says these
   two conversations share an attacker, even though they hit different people."*
7. *(Optional)* **Run Marcus vs. Fake IT Support and close it.** It appears as its own separate node, showing the
   system doesn't link everything. Then click **Generate report** on any closed incident: a ready-to-share markdown
   report with MITRE mapping, an IOC table, linked incidents and recommended defensive actions. Copy or download it.
8. *(Optional, if asked "what if the model gets it wrong?")* Quote the eval line from
   [Reliability](#reliability-measured-not-claimed), then explain `needs_review`. To show it live, restart the
   backend with `MIRAGE_LLM_MODE=mock` and `MIRAGE_MOCK_FORCE_INVALID_EXTRACTION=1` and close an incident. It gets a
   violet **Needs review** badge, no profile, and a **Retry extraction** button.

---

## API

| Method & path | Description |
|---|---|
| `GET /health` | LLM mode, models, embedding backend, DB dialect, threshold |
| `GET /personas` · `POST /personas` · `GET /personas/{id}` | Personas (POST renders the system prompt from the template unless `system_prompt` is given) |
| `GET /attacker-scripts` · `GET /attacker-scripts/{id}` | Seeded Red-Team Simulator scripts |
| `POST /incidents/simulate` | `{persona_id, attacker_script_id}` creates an incident plus the attacker's opening message |
| `POST /incidents/{id}/respond` | One exchange: decoy reply, then attacker reply. Returns `new_messages` and the incident |
| `POST /incidents/{id}/close` | Close, extract (schema-constrained + pydantic-validated, one retry), embed, link. If validation fails twice: `status: "needs_review"`, `profile: null`, `review_message`, and `raw_extraction_output`. Calling it again retries extraction |
| `POST /incidents/manual` | `{persona_id, attacker_message}` starts from a real message (no simulator). Continue with `/respond` + `{attacker_message}` |
| `GET /incidents` | Feed: status, one-line summary, cluster size |
| `GET /incidents/{id}` | Messages, profile, linked incidents with similarity scores, cluster members |
| `GET /incidents/{id}/report` | `{filename, markdown}` incident report |
| `GET /dashboard/stats` | Totals, open and needs-review incidents, attacker clusters (connected components), top tactics and techniques |
| `GET /threat-map` | Graph nodes, links and clusters with shared IOCs |
| `POST /demo/reset` | Delete all incidents (keeps personas and scripts) |

One full simulated conversation from the terminal:

```bash
curl -s -X POST localhost:8000/incidents/simulate -H "Content-Type: application/json" -d '{"persona_id":1,"attacker_script_id":1}'
```

```bash
curl -s -X POST localhost:8000/incidents/1/respond
```

```bash
curl -s -X POST localhost:8000/incidents/1/close
```

```bash
curl -s localhost:8000/incidents/1/report
```

---

## How the campaign linking works

1. **Extraction** ([backend/app/llm.py](backend/app/llm.py), [backend/app/prompts.py](backend/app/prompts.py)). The
   transcript goes to Claude with schema-constrained output. The MITRE technique must be one of 12 real ATT&CK
   technique IDs ([backend/app/mitre.py](backend/app/mitre.py)), and tactics must come from the fixed six-word
   vocabulary. The reply is validated with the strict `ExtractedProfile` pydantic model. If validation fails, the
   model gets the validation error back and exactly one retry; after that the incident goes to `needs_review` (see
   [Reliability](#reliability-measured-not-claimed)).
2. **Embedding** ([backend/app/pipeline.py](backend/app/pipeline.py)). The embedded text is the attacker goal plus the
   normalised core indicator strings (domains, emails, phones, masked accounts, handles, ticket numbers), encoded with
   `all-MiniLM-L6-v2` into 384 dimensions.
3. **Linking.** Cosine similarity against every stored profile. Any pair above `SIMILARITY_THRESHOLD` becomes an
   `incident_links` row.
4. **Clustering** ([backend/app/clustering.py](backend/app/clustering.py)). Union-find over the links. Each connected
   component is one attacker cluster.

**Threshold calibration.** The original spec used 0.85. We measured MiniLM on paraphrased profiles, the way two live
extractions of the same campaign actually differ (different wording, and sometimes a different but valid technique
or IOC subset). Same-campaign pairs scored **0.73–0.88** and different campaigns at most **0.61**, so at 0.85 most
same-campaign pairs would not link. Leaving the technique and tactic labels out of the embedded text also widened
the gap, because those small shared vocabularies (almost every scam uses "urgency") pushed unrelated campaigns closer
together. The default is therefore **0.70**. You can change it with `MIRAGE_SIMILARITY_THRESHOLD`, and the value is
shown on the Threat Map. The `hashing` embedding fallback is not calibrated for this threshold; use it only if
sentence-transformers can't be installed.

## Safety by design

- Decoys are told never to produce real-looking sensitive data. As a code-level backstop,
  `llm.mask_sensitive()` rewrites any SSN pattern or long digit run in persona output to `XXX-XX-XXXX` / `XXXX-1234`
  before it is stored.
- All attacker infrastructure is non-routable: `.example` domains (RFC 2606), the fictional 555-01xx and
  +44 7700 900xxx phone ranges, and masked account numbers.
- Claude calls check `stop_reason == "refusal"` and surface a readable error (HTTP 502). Server-side refusal
  fallbacks are enabled by default.
- Extraction never guesses: output that fails schema validation twice puts the incident in `needs_review` instead of
  writing a profile.
- Every turn is committed as soon as it is generated. If an LLM call fails mid-exchange, the next `/respond` resumes
  instead of losing the conversation. A per-incident lock stops auto-play from interleaving turns.

## Tests and eval

```bash
cd backend && python tests/test_llm_contract.py
```

```bash
cd backend && python tests/test_needs_review.py
```

```bash
python eval/run_eval.py
```

- **`test_llm_contract.py`** checks the live Claude request shape against a mock HTTP transport: schema-constrained
  extraction, temperature only where the model accepts it and never on chat turns, exactly one retry, strict
  rejection of near-miss values, refusal handling, fallback degradation and PII masking.
- **`test_needs_review.py`** drives the real FastAPI app with the offline mock and a throwaway SQLite DB: invalid
  extraction leads to `needs_review` with raw output stored, the report is blocked, retry recovers, and the column
  migration is applied to an older database.
- **`eval/run_eval.py`** runs the extraction eval described in [Reliability](#reliability-measured-not-claimed).
  Use the backend virtualenv's Python and run it from the repo root.

## Deploying

- **Backend on Render:** create a Web Service with root directory `backend`, build command
  `pip install -r requirements.txt`, and start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Add a
  Render Postgres instance and set `DATABASE_URL` (its `postgres://` URL works as-is), `ANTHROPIC_API_KEY`, and
  `MIRAGE_CORS_ORIGINS=https://<your-app>.vercel.app`. PyTorch plus MiniLM needs about 1 GB of RAM, which exceeds
  Render's free tier. Use a paid instance, or set `MIRAGE_EMBEDDINGS=hashing` and re-tune the threshold.
- **Frontend on Vercel:** set root directory `frontend`, framework preset Vite, and environment variable
  `VITE_API_URL=https://<your-backend>.onrender.com`.

## Project layout

```
backend/
  app/
    main.py            FastAPI app, startup seeding, CORS
    config.py          env-driven settings (DB URL, models, threshold)
    models.py          SQLAlchemy models (personas, attacker_scripts, incidents, messages, incident_profiles, incident_links)
    prompts.py         persona / attacker / extraction system prompts
    llm.py             Claude calls, refusal handling, JSON validation + retry, PII masking
    mock_llm.py        offline stand-in for Claude
    pipeline.py        close -> extract -> embed -> link
    embeddings.py      sentence-transformers with hashing fallback, cosine similarity
    clustering.py      union-find attacker clusters
    report.py          markdown report + defensive-action lookup
    mitre.py           ATT&CK techniques, explanations, defenses, tactic vocabulary
    seed_data.py       default personas and attacker scripts
    routers/           personas, incidents, dashboard endpoints
  tests/               LLM contract tests, needs_review end-to-end test
eval/
  fixtures/            10 hand-labeled transcripts (8 clean, 2 ambiguous)
  run_eval.py          extraction eval harness (one command, reportable score)
frontend/
  src/App.jsx          state, auto-play loop, layout
  src/components/      StatsBar, Sidebar, IncidentView, AnalysisPanel, ReportModal, ThreatMap (d3-force)
```

## Out of scope / next steps

No auth or multi-tenancy (single-user demo). Stretch goals: a voice channel (Whisper and ElevenLabs), pgvector for
large-scale similarity search, and a real inbound channel (email or SMS webhook) feeding `POST /incidents/manual`.
