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

Built for HyperBloom Hacks as a working end-to-end MVP: FastAPI + SQLAlchemy backend, React dashboard, Claude for
the three LLM roles, local ONNX embeddings for campaign linking.

---

## Contents

1. [How it works](#how-it-works)
2. [Reliability: measured, not claimed](#reliability-measured-not-claimed)
3. [Features](#features)
4. [Tech stack](#tech-stack)
5. [Quick start](#quick-start)
6. [Configuration](#configuration)
7. [Using the dashboard](#using-the-dashboard)
8. [Demo script](#demo-script-4-minutes)
9. [API reference](#api-reference)
10. [Data model](#data-model)
11. [Inside the pipeline](#inside-the-pipeline)
12. [Seed data](#seed-data)
13. [Safety by design](#safety-by-design)
14. [Tests and eval](#tests-and-eval)
15. [Troubleshooting](#troubleshooting)
16. [Deploying](#deploying)
17. [Project layout](#project-layout)
18. [Limitations and next steps](#limitations-and-next-steps)

---

## How it works

```mermaid
flowchart LR
    A[Attacker LLM<br/>scam script] -- message --> P[Decoy persona LLM<br/>Amy / Marcus]
    P -- stalls & probes --> A
    P --> T[(Transcript<br/>messages)]
    T -- Close & analyze --> X[Extraction LLM<br/>schema-constrained JSON + pydantic]
    X -- valid --> R[(incident_profiles<br/>technique · IOCs · tactics · goal · confidence)]
    X -- invalid twice --> NR[needs_review<br/>raw output kept, no profile]
    R --> E[all-MiniLM-L6-v2<br/>ONNX embedding]
    E --> S{cosine similarity<br/>vs past incidents}
    S -- above threshold --> L[(incident_links)]
    L --> U[union-find<br/>attacker clusters]
    U --> D[Dashboard · Threat Map · Report]
```

An incident moves through three stages:

1. **Engage.** `POST /incidents/simulate` creates an incident and stores the attacker's scripted opening message.
   Each `POST /incidents/{id}/respond` advances the conversation by one exchange: the decoy persona replies (Claude,
   with the persona's system prompt and the full history), then the simulated attacker reacts (Claude, with the scam
   script's system prompt). Every message is saved as soon as it is generated.
2. **Analyze.** `POST /incidents/{id}/close` marks the incident closed and sends the full transcript to the extraction
   call. The output is validated against a strict schema, retried once with the validation error if needed, and
   either stored as an incident profile or flagged `needs_review`.
3. **Correlate.** The profile's goal and indicators are embedded into a 384-dimension vector and compared with every
   stored profile. Pairs above the similarity threshold are linked, and connected groups of links form attacker
   clusters that the Threat Map draws as campaigns.

```mermaid
sequenceDiagram
    participant UI as Dashboard
    participant API as FastAPI
    participant C as Claude
    participant DB as Database
    UI->>API: POST /incidents/{id}/close
    API->>DB: status = closed
    API->>C: transcript + extraction prompt (JSON schema)
    C-->>API: JSON
    alt valid on attempt 1 or 2
        API->>API: embed goal + indicators (fastembed)
        API->>DB: incident_profile, incident_links above threshold
        API-->>UI: profile, linked incidents, new_link_count
    else invalid twice
        API->>DB: status = needs_review, raw_extraction_output
        API-->>UI: review_message, profile = null
    end
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

## Features

- **Decoy personas** that sound like real, slightly scattered employees. They stall ("one sec, my manager just pinged
  me"), ask questions that extract intel (callback number, employee ID, exact account), and never hand over anything
  sensitive.
- **Red-Team Simulator** with four adaptive scam scripts. The attacker LLM follows the typical beats of each scam,
  reacts to what the decoy actually says, and escalates when stalled.
- **Structured extraction** into a MITRE ATT&CK technique (from 12 real IDs), typed IOCs, manipulation tactics from a
  fixed six-word vocabulary, a one-sentence attacker goal, and a self-reported confidence level.
- **`needs_review` fallback** when extraction output fails validation twice, with the raw output kept for debugging and
  one-click retry.
- **Campaign linking** with cosine similarity over local MiniLM embeddings and union-find clustering.
- **Dashboard** with live transcripts, auto-play, IOC highlighting in the transcript, confidence badges, stat cards,
  and a force-directed Threat Map of campaigns with their shared infrastructure.
- **Markdown incident reports** with MITRE mapping, IOC table, tactics, linked incidents, recommended defensive actions
  and the full transcript. Copy or download from the UI.
- **Offline mock mode** so the whole app runs with no API key or network.
- **Eval harness** with a one-command, reportable score, plus contract and end-to-end tests.

---

## Tech stack

| Layer | Technology (versions tested) |
|---|---|
| Backend | Python 3.13, FastAPI 0.141, Uvicorn 0.52, SQLAlchemy 2.0, Pydantic 2.11 |
| LLM | Anthropic Python SDK 1.5, `claude-opus-5` for persona, attacker and extraction calls |
| Embeddings | fastembed 0.8 (ONNX Runtime 1.30) running `sentence-transformers/all-MiniLM-L6-v2` |
| Database | SQLite by default; Postgres via `DATABASE_URL` (psycopg 3) |
| Frontend | React 19, Vite 7, Tailwind CSS 4, d3-force 3, react-markdown 10 with remark-gfm, JetBrains Mono |

---

## Quick start

### Prerequisites

- **Python 3.10–3.13** (tested on 3.13; the Render config pins 3.13.5).
- **Node.js 20.19+ or 22.12+** (required by Vite 7).
- Optional: an **Anthropic API key** for live Claude conversations. Without one, MIRAGE runs in
  [offline mock mode](#offline-mock-mode).
- Internet access on first backend start, to download the ~90 MB embedding model. It is cached afterwards.

### 1. Backend

From the repo root:

```bash
cd backend
```

Create a virtual environment. On Windows, if `python` points at a version without packages you need, use
`py -3.13 -m venv .venv` instead.

```bash
python -m venv .venv
```

Activate it: `.venv\Scripts\Activate.ps1` (PowerShell), `.venv\Scripts\activate.bat` (cmd), or
`source .venv/bin/activate` (macOS/Linux). Then install dependencies:

```bash
pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env
```

Open `backend/.env` and set `ANTHROPIC_API_KEY` (leave it empty for mock mode). Then start the API:

```bash
uvicorn app.main:app --reload --port 8000
```

On first start, MIRAGE:
- creates the SQLite database at `backend/mirage.db`
- seeds 2 personas and 4 attacker scripts (only those missing; existing data is kept)
- adds any columns introduced after your database was first created
- loads the embedding model in a background thread, downloading it into `backend/.model_cache` on the first run

Check it's up at http://localhost:8000/health. Interactive API docs are at http://localhost:8000/docs.

### 2. Frontend

In a second terminal, from the repo root:

```bash
cd frontend
```

```bash
npm install
```

```bash
npm run dev
```

Open http://localhost:5173. In development the dashboard calls `/api/*`, and Vite proxies that to
`http://127.0.0.1:8000` with the `/api` prefix removed, so no CORS setup is needed locally.

### Running both from the repo root

If you'd rather not activate the virtualenv, these run from the repo root (two terminals):

```bash
backend/.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

```bash
npm --prefix frontend run dev
```

On macOS/Linux, the Python path is `backend/.venv/bin/python`. Claude Code users can also start the `backend`,
`frontend` and `backend-force-invalid-extraction` configurations in [.claude/launch.json](.claude/launch.json).

### Offline mock mode

Without `ANTHROPIC_API_KEY` (or with `MIRAGE_LLM_MODE=mock`), MIRAGE swaps Claude for a deterministic offline stand-in:
- the attacker sends each script's pre-written lines in order, escalating at the end
- the decoy cycles through canned stalling and probing replies
- extraction is a regex/keyword heuristic that returns JSON through the same parse, validate and retry path as Claude

Embeddings, similarity linking, clustering, reports and the whole UI still run for real. The header badge shows
**OFFLINE MOCK LLM**, and profiles are labelled `analyzer: mock-heuristic`. Mock mode is a useful backup if the venue
Wi-Fi fails, but demo in live mode. Because mock transcripts repeat the same lines, same-script incidents link at
100% similarity; live conversations score lower (see [threshold calibration](#4-linking-and-threshold-calibration)).

### Resetting data

- **From the dashboard:** **Reset demo** (top right) deletes all incidents, messages, profiles and links, and keeps
  personas and scripts.
- **From the API:** `POST /demo/reset` does the same.
- **Full reset:** from `backend/`, `python -m app.seed --reset` drops every table and re-seeds.

---

## Configuration

All settings are environment variables, read from the process environment or `backend/.env`
(see [backend/.env.example](backend/.env.example)). Restart the backend after changing them.

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required for live Claude conversations |
| `DATABASE_URL` | `sqlite:///backend/mirage.db` | Any SQLAlchemy URL. `postgresql://…` and `postgres://…` are normalised to psycopg 3 |
| `MIRAGE_LLM_MODE` | `auto` | `auto` (live if a key is set, otherwise mock), `live` (always call Claude; errors surface if the key is missing), or `mock` |
| `MIRAGE_CHAT_MODEL` | `claude-opus-5` | Model for the persona and attacker turns |
| `MIRAGE_EXTRACTION_MODEL` | `claude-opus-5` | Model for structured extraction |
| `MIRAGE_CHAT_EFFORT` | `low` | Effort for chat turns (short replies, lower latency) |
| `MIRAGE_EXTRACTION_EFFORT` | `medium` | Effort for extraction |
| `MIRAGE_EXTRACTION_TEMPERATURE` | `0` | Sent on the extraction call only, and only to models that accept sampling params (not Opus 5 / 4.8 / 4.7 or Sonnet 5) |
| `MIRAGE_STRUCTURED_OUTPUTS` | `1` | Schema-constrained decoding for extraction |
| `MIRAGE_REFUSAL_FALLBACKS` | `1` | Server-side refusal fallbacks (`fallbacks: "default"`); turned off automatically if the API rejects them |
| `MIRAGE_EMBEDDINGS` | `auto` | `auto` (all-MiniLM-L6-v2 via fastembed/ONNX, falling back to hashing if unavailable) or `hashing` |
| `MIRAGE_MODEL_CACHE` | `backend/.model_cache` | Where the embedding model is downloaded |
| `MIRAGE_SIMILARITY_THRESHOLD` | `0.70` | Cosine threshold for linking incidents (see [calibration](#4-linking-and-threshold-calibration)) |
| `MIRAGE_CORS_ORIGINS` | `*` | Comma-separated allowed origins, for a split frontend/backend deploy |
| `MIRAGE_MOCK_FORCE_INVALID_EXTRACTION` | `0` | Testing only: the offline mock extractor emits schema-invalid output, to demo the `needs_review` path |

The frontend has one build-time variable:

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_URL` | `/api` | Base URL of the backend. Leave unset in development (Vite proxy). Set it to the backend's public URL for a deployed build |

**Latency and cost.** Each exchange makes two Claude calls (decoy reply, then attacker reply), and each close makes
one extraction call, or two if a retry is needed. If turns feel slow on stage, set `MIRAGE_CHAT_MODEL` to a faster
model and keep extraction on Opus. Auto-play pauses after 8 exchanges as a cost guard.

### Using Postgres

```bash
docker run -d --name mirage-pg -e POSTGRES_USER=mirage -e POSTGRES_PASSWORD=mirage -e POSTGRES_DB=mirage -p 5432:5432 postgres:16
```

Then set `DATABASE_URL=postgresql://mirage:mirage@localhost:5432/mirage` in `backend/.env` and restart. Tables are
created on startup. The models only use portable types (`JSON`, `Text`, `Float`), so the same code runs on both
databases. Embeddings are stored as JSON float arrays and compared in Python. At hackathon scale (dozens of
incidents) that needs no vector DB; `pgvector` is the natural next step at larger scale.

---

## Using the dashboard

The dashboard is a single page with a header, stat cards, and two tabs.

**Header and stat cards.** The badge shows **LIVE · \<model\>** or **OFFLINE MOCK LLM**. The cards show total
incidents (with analyzed and needs-review counts), open threats, attacker clusters (and how many are multi-incident
campaigns), IOCs extracted (and similarity links), and the most common manipulation tactics.

**Live Incidents tab** has three columns:

| Column | What's in it |
|---|---|
| Left: Red-Team Simulator and incident feed | Pick a decoy persona and attacker script, then **Start new simulation**. The feed lists every incident with its reference (`MIR-0001`), status, cluster badge, one-line summary, exchange count and technique ID |
| Middle: transcript | Attacker messages on the left (red), decoy replies on the right (cyan). Controls: **Next exchange**, **Auto-play** (one exchange every ~2.5 s, pausing after 8), and **Close & analyze**, which glows once 4 exchanges have happened. After analysis, extracted IOCs are highlighted amber in the transcript |
| Right: analysis | Before closing, an explainer. While closing, the pipeline steps. After closing: campaign-match banner, attacker goal with confidence badge, MITRE technique with plain-English explanation and ATT&CK link, tactic tags, IOC table, linked incidents with similarity bars, analyzer and embedding details, and **Generate report** |

**Status colors.** Red = active threat, green = closed, amber = part of a multi-incident cluster, violet = needs review.

**Needs review.** The right column shows the review message, an explanation, **Retry extraction**, and a collapsible
**Raw extractor output (debug)** panel with each attempt's output and validation error. No report can be generated
until an extraction passes.

**Report.** **Generate report** opens the markdown report in a modal with **Copy markdown** and **Download .md**.

**Threat Map tab.** A force-directed graph of analyzed incidents: nodes show the technique ID and reference, edges are
labelled with similarity, and multi-incident clusters sit inside a pulsing **CAMPAIGN-NN** halo. The side panel lists
each cluster with the scripts and personas involved and any IOC values shared across its incidents. Click a node or
incident chip to open it.

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

## API reference

Base URL `http://localhost:8000` locally (or `/api` through the Vite dev proxy). Request and response bodies are JSON.
Interactive docs with every schema are at `/docs`.

### Endpoints

| Method & path | Description |
|---|---|
| `GET /health` | LLM mode, models, extraction settings, embedding backend, DB dialect, similarity threshold |
| `GET /personas` | List personas |
| `GET /personas/{id}` | One persona, including its system prompt |
| `POST /personas` | Create a persona. The system prompt is rendered from the template unless `system_prompt` is given |
| `GET /attacker-scripts` | List Red-Team Simulator scripts |
| `GET /attacker-scripts/{id}` | One script, including its system prompt |
| `POST /incidents/simulate` | Start a simulated incident and store the attacker's opening message |
| `POST /incidents/manual` | Start an incident from a real attacker message (no simulator); the decoy replies once |
| `POST /incidents/{id}/respond` | Advance one exchange |
| `POST /incidents/{id}/close` | Close, extract, embed and link (or flag `needs_review`). Calling it again retries extraction |
| `GET /incidents` | Incident feed, newest first |
| `GET /incidents/{id}` | Full incident detail |
| `GET /incidents/{id}/report` | Markdown incident report |
| `GET /dashboard/stats` | Header statistics |
| `GET /threat-map` | Graph nodes, links and clusters |
| `POST /demo/reset` | Delete all incidents, messages, profiles and links (keeps personas and scripts) |

### Request bodies

| Endpoint | Body |
|---|---|
| `POST /personas` | `{"name", "role", "backstory", "quirks"?, "system_prompt"?}` |
| `POST /incidents/simulate` | `{"persona_id": 1, "attacker_script_id": 1}` |
| `POST /incidents/manual` | `{"persona_id": 1, "attacker_message": "Hi, it's the CEO..."}` |
| `POST /incidents/{id}/respond` | Optional `{"attacker_message": "..."}`. Required for manual incidents; for simulated ones it injects a message in place of the simulated attacker's turn |

### Responses

- **`POST /incidents/simulate`** returns `{incident_id, opening_message, incident}`.
- **`POST /incidents/{id}/respond`** returns `{new_messages, incident}`. The decoy replies if the last message is from
  the attacker; the simulated attacker then replies unless you injected a message.
- **`POST /incidents/{id}/close`** returns the incident detail plus `new_link_count`.
- **`GET /incidents/{id}/report`** returns `{incident_id, filename, markdown}`.

**Incident detail** (from `GET /incidents/{id}`, `/respond`, `/close`) contains:

| Field | Meaning |
|---|---|
| `id`, `ref` | Numeric ID and display reference, e.g. `MIR-0001` |
| `status` | `active`, `closed` or `needs_review` |
| `persona`, `attacker_script`, `source` | Who was targeted, which script (null for manual), `simulator` or `manual` |
| `started_at`, `closed_at`, `channel` | Timestamps (UTC, ISO 8601) and channel (`text`) |
| `messages` | `[{id, sender: "attacker"\|"persona", content, created_at}]` |
| `message_count`, `exchange_count` | Totals; one exchange = one decoy reply |
| `analyzed`, `mitre_technique`, `summary` | Whether a profile exists, its technique label, and a one-line summary |
| `profile` | Null until analyzed. `{mitre_technique, technique_id, technique_name, technique_explanation, iocs: [{type, value}], manipulation_tactics, attacker_goal, attacker_goal_confidence, analyzer, embedding_model, embedding_dims, created_at}` |
| `linked_incidents` | `[{incident_id, ref, similarity, persona_name, attacker_script, mitre_technique, attacker_goal, status}]`, highest similarity first |
| `cluster_id`, `cluster_size`, `cluster_members` | The incident's attacker cluster (lowest member ID) and its members |
| `review_message`, `raw_extraction_output` | Set only when `status` is `needs_review` |

**`GET /dashboard/stats`** returns `total_incidents`, `open_incidents`, `closed_incidents`, `needs_review_incidents`,
`analyzed_incidents`, `unique_attacker_clusters` (connected components, a lone incident counts as its own attacker),
`multi_incident_clusters`, `total_links`, `total_iocs`, `top_tactics: [{tactic, count}]` and
`top_techniques: [{technique, count}]`.

**`GET /threat-map`** returns `nodes` (one per analyzed incident, with cluster ID and size), `links`
(`{source, target, similarity}`), `clusters` (`{cluster_id, size, incident_ids, techniques, attacker_scripts,
personas_targeted, shared_iocs}`), and the `threshold`.

**`GET /health`** in mock mode looks like:

```json
{"status":"ok","llm_mode":"mock","chat_model":"claude-opus-5","extraction_model":"claude-opus-5","extraction":{"analyzer":"mock-heuristic","max_attempts":2},"embeddings":{"model":"sentence-transformers/all-MiniLM-L6-v2","loaded":true},"database":"sqlite","similarity_threshold":0.7}
```

### Errors

| Status | When |
|---|---|
| `400` | A manual incident's `/respond` call has no `attacker_message` |
| `404` | Persona, script or incident not found |
| `409` | Responding to an incident that isn't active; a second request while one is still processing the same incident; requesting a report before analysis or while `needs_review` |
| `422` | Request body fails validation |
| `502` | A Claude call failed: authentication, rate limit, network, or a refusal. Turns saved before the failure are kept, so calling the endpoint again resumes |

### A full conversation from the terminal

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

## Data model

Six tables, created on startup ([backend/app/models.py](backend/app/models.py)).

| Table | Columns | Notes |
|---|---|---|
| `personas` | `id`, `name`, `role`, `backstory`, `system_prompt`, `created_at` | The system prompt is rendered from the persona template |
| `attacker_scripts` | `id`, `name` (unique), `description`, `system_prompt`, `opening_message`, `created_at` | `opening_message` may contain `{target_first_name}` |
| `incidents` | `id`, `persona_id`, `attacker_script_id` (nullable), `started_at`, `closed_at`, `status`, `channel`, `raw_extraction_output` | `status` is `active`, `closed` or `needs_review`. A null script means manual input |
| `messages` | `id`, `incident_id`, `sender`, `content`, `created_at` | `sender` is `attacker` or `persona` |
| `incident_profiles` | `id`, `incident_id` (unique), `mitre_technique`, `iocs` (JSON), `manipulation_tactics` (JSON), `attacker_goal`, `attacker_goal_confidence`, `embedding` (JSON float array), `embedding_model`, `analyzer`, `created_at` | One per analyzed incident. `embedding_model` prevents comparing vectors from different models |
| `incident_links` | `id`, `incident_a_id`, `incident_b_id`, `similarity_score`, `created_at` | Unique per pair. `incident_a` is the newer incident |

**Schema upgrades.** SQLAlchemy's `create_all` never alters existing tables, so on startup MIRAGE adds any column
introduced since your database was created (currently `incidents.raw_extraction_output` and
`incident_profiles.attacker_goal_confidence`). This works on both SQLite and Postgres.

---

## Inside the pipeline

### 1. Decoy personas

Persona prompts ([backend/app/prompts.py](backend/app/prompts.py)) give each decoy a name, role, backstory and
personality quirks. They then set rules the persona follows without ever mentioning them:
- never reveal or imply it is an AI, bot or decoy
- keep the attacker talking with plausible stalls
- draw out details with natural questions, roughly one per reply (full name and title, employee or ticket ID,
  callback number, the exact link or account, who approved it)
- sound willing but always hesitate at the final step, and never claim to have completed an irreversible action
- never write anything that looks like a real password, code, account or card number, or SSN; use `XXXX-1234` style
  placeholders if a number must appear
- reply in 1–3 short, chat-like sentences

Chat turns run at effort `low` and never set `temperature`.

### 2. Simulated attackers

Each attacker prompt names the scam and the attacker's goal, gives a cover identity, lists the campaign
infrastructure to reuse (links, phones, emails, payment destinations), and outlines 4 typical beats. The model is
told to react to what the target says rather than recite a script, and to escalate (time pressure, authority,
consequences) when the target stalls. It is framed as a red-team simulation for training, and it is never told the
target is an AI. Its history starts with a short user "kickoff" turn so the conversation alternates correctly.

### 3. Structured extraction

The extraction call ([backend/app/llm.py](backend/app/llm.py)) sends the transcript with:
- a system prompt listing the 12 allowed technique IDs with explanations, tie-break rules, IOC rules, tactic
  definitions and a confidence rubric
- `output_config.format` with a JSON schema whose enums match the pydantic `Literal`s
- effort `medium`, and `temperature=0` only where the model accepts it

**Technique tie-break rules** (first match wins):
1. A link to a page meant to capture credentials, codes, or personal or financial data → `T1598.003`
2. Pretending to be a specific trusted person or internal function (executive, IT, HR, a known vendor) → `T1656`
3. Eliciting personal, account or financial information directly in the conversation, without such a link → `T1598`
4. An outsider building rapport and then asking for money, gift cards or crypto → `T1657`
5. Otherwise the best remaining fit; `T1566` only if nothing more specific applies

**Allowed techniques:** `T1566` Phishing · `T1566.002` Spearphishing Link · `T1566.003` Spearphishing via Service ·
`T1566.004` Spearphishing Voice · `T1598` Phishing for Information · `T1598.003` Spearphishing Link (Phishing for
Information) · `T1656` Impersonation · `T1199` Trusted Relationship · `T1534` Internal Spearphishing · `T1657`
Financial Theft · `T1589.001` Gather Victim Identity Information: Credentials · `T1585.001` Establish Accounts: Social
Media Accounts.

**IOC types:** `url`, `phone`, `email`, `payment_account` (bank accounts, wallets, gift-card or payment-app
instructions), `other` (handles, ticket and invoice numbers). Only indicators the attacker supplied count.

**Tactics:** `urgency`, `authority`, `scarcity`, `fear`, `likability`, `reciprocity`.

**Confidence:** `high` if the attacker explicitly asked for the end goal, `medium` if it was strongly implied or the
conversation ended before the ask, `low` if it had to be inferred from fragments.

**Validation and retry.** The reply is parsed as JSON (code fences are tolerated) and validated with
`ExtractedProfile` ([backend/app/schemas.py](backend/app/schemas.py)): exact enum values, no extra keys, non-empty IOC
values, a goal of 5–400 characters. On failure the model gets its own reply back plus the validation error and one
more attempt. If that also fails, the close handler sets `needs_review` and stores both raw outputs and errors. API
failures (auth, network, refusal) are different: they return HTTP 502 and leave the incident closed without a
profile, so you can simply retry.

### 4. Linking and threshold calibration

**Embedding** ([backend/app/pipeline.py](backend/app/pipeline.py)). The embedded text is the attacker goal plus the
normalised core indicator strings (domains, emails, phones, masked accounts, wallets, handles, ticket numbers), for
example `"<goal sentence> Indicators: INV-20931 XXXX-7731 daniel.reyes.ceo@acmecorp-exec.example ..."`. It is encoded
with `all-MiniLM-L6-v2` into a unit-normalised 384-dimension vector.

**Linking.** Cosine similarity against every stored profile from the same embedding model. Any pair above
`SIMILARITY_THRESHOLD` becomes an `incident_links` row.

**Clustering** ([backend/app/clustering.py](backend/app/clustering.py)). Union-find over the links. Each connected
component is one attacker cluster, identified by its lowest incident ID.

**Threshold calibration.** The original spec used 0.85. We measured MiniLM on paraphrased profiles, the way two live
extractions of the same campaign actually differ (different wording, and sometimes a different but valid technique
or IOC subset). Same-campaign pairs scored **0.73–0.88** and different campaigns at most **0.61**, so at 0.85 most
same-campaign pairs would not link. Leaving the technique and tactic labels out of the embedded text also widened
the gap, because those small shared vocabularies (almost every scam uses "urgency") pushed unrelated campaigns closer
together. The default is therefore **0.70**. You can change it with `MIRAGE_SIMILARITY_THRESHOLD`, and the value is
shown on the Threat Map. The `hashing` embedding fallback is not calibrated for this threshold; use it only if
fastembed can't be installed.

**Why fastembed, not sentence-transformers.** The model runs through ONNX Runtime instead of PyTorch. We checked the
vectors against the PyTorch build: cosine 1.0 on identical text and identical pairwise similarities, so the
calibration above is unchanged. The whole backend then uses about 250 MB instead of about 525 MB, which fits a
512 MB free instance.

### 5. Reports

Reports ([backend/app/report.py](backend/app/report.py)) are built without an extra LLM call. Sections: metadata
table, attacker goal with confidence, MITRE technique with explanation and ATT&CK link, IOC table, manipulation
tactics with definitions, linked incidents, recommended defensive actions, and the full transcript. Defensive actions
come from a lookup table keyed by technique, plus a "treat as one campaign" action when linked incidents exist.

---

## Seed data

Seeded on startup from [backend/app/seed_data.py](backend/app/seed_data.py).

**Personas**

| Persona | Role | Character |
|---|---|---|
| Amy Tran | Accounts Payable Associate (new hire, Finance) | Three weeks in, still learning the approval workflow, apologetic and chatty, anxious about getting things wrong |
| Marcus Bell | IT Helpdesk Technician | Two years on the helpdesk, eager to please, wants a ticket number for everything, distracted by his queue |

**Attacker scripts**

| Script | Cover identity | Goal |
|---|---|---|
| CEO Fraud | "Daniel Reyes", CEO, between board meetings | A same-day $48,500 wire to "Harbor Point Advisory" |
| Fake IT Support | "Kevin Walsh", IT Service Desk, ticket INC-448812 | Credentials on a fake reset portal, then the MFA code |
| Romance Scam | "Ethan Walker", offshore wind engineer | $2,000 in crypto or gift cards for an "emergency" |
| Recruiter Scam | "Priya Shah", Brightpath Talent Group | SSN, date of birth and bank details via a fake onboarding portal, plus an $85 fee |

The personas "work" at the fictional **Acme Corp**. Personas you add with `POST /personas` persist; seeding only
inserts missing names.

---

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
- Secrets stay out of the repo: `backend/.env`, the SQLite database and the model cache are git-ignored.

---

## Tests and eval

Run these with the backend virtualenv's Python. None of them need an API key.

```bash
cd backend && python tests/test_llm_contract.py
```

```bash
cd backend && python tests/test_needs_review.py
```

```bash
python eval/run_eval.py
```

- **`test_llm_contract.py`** (12 tests) checks the live Claude request shape against a mock HTTP transport:
  schema-constrained extraction, temperature only where the model accepts it and never on chat turns, exactly one
  retry, strict rejection of near-miss values, refusal handling, fallback degradation and PII masking.
- **`test_needs_review.py`** (2 tests) drives the real FastAPI app with the offline mock and a throwaway SQLite DB:
  invalid extraction leads to `needs_review` with raw output stored, the report is blocked, retry recovers, and the
  column migration is applied to an older database.
- **`eval/run_eval.py`** runs the extraction eval described in [Reliability](#reliability-measured-not-claimed). Run
  it from the repo root. With a key it scores Claude; without one it scores the offline baseline and says so.

| `run_eval.py` flag | Effect |
|---|---|
| `--mock` | Force the offline heuristic baseline (no API calls) |
| `--repeat N` | Run every case N times; reports the mean and how often the technique was identical across runs |
| `--update-readme` | Rewrite the result block in this README |
| `--json PATH` | Save per-case expected vs actual output |

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Header says **OFFLINE MOCK LLM** | No `ANTHROPIC_API_KEY` was found. Add it to `backend/.env` and restart the backend |
| `ModuleNotFoundError` when starting the backend | Wrong Python. Activate `backend/.venv`, or call its Python directly. On Windows, `python` may be a different install without the packages |
| Dashboard toast: "Cannot reach the MIRAGE backend" | The backend isn't running on port 8000, or the port is taken by another process |
| HTTP 502 "Anthropic authentication failed" | The key is wrong or revoked. Check `backend/.env` |
| HTTP 502 "Rate limited" | Too many calls in a short time. Wait a few seconds and retry; turn auto-play off |
| HTTP 409 "already processing" | A second request hit an incident mid-exchange. Wait for the current one to finish |
| `/health` shows `hashing-bow-384` | The embedding model couldn't load (usually no internet on first start). Restart with internet access; hashing isn't calibrated for the 0.70 threshold |
| Incidents never link in live mode | Check both use the same script and were analyzed with the same embedding model (`/health`). Try lowering `MIRAGE_SIMILARITY_THRESHOLD` slightly |
| Incident stuck on **Needs review** | Open **Raw extractor output (debug)** to see why, then **Retry extraction** |
| Windows warning about symlinks during model download | Harmless: the Hugging Face cache falls back to copying files |
| Want a completely fresh database | Stop the backend, then run `python -m app.seed --reset` from `backend/` |

---

## Deploying

MIRAGE is not currently deployed; these notes describe the intended setup. The backend and frontend deploy
separately. Vercel's per-request function timeouts and lack of a persistent connection pool don't suit a FastAPI app
that makes multi-second LLM calls and holds a Postgres connection.

- **Backend on Render, via [render.yaml](render.yaml).** In the Render dashboard, choose **New → Blueprint** and
  connect this repo. Enter `ANTHROPIC_API_KEY` when prompted, then **Apply**. The Blueprint creates:
  - the `mirage-backend` web service: free plan, Singapore, root `backend`, Python 3.13.5, health check `/health`.
    The build pre-downloads the embedding model and fails if it can't load.
  - the free `mirage-db` Postgres database, with `DATABASE_URL` wired from it automatically.

  It also sets `MIRAGE_LLM_MODE=live`, so a missing key fails visibly instead of silently mocking.
  `MIRAGE_CORS_ORIGINS` starts as `*`; set it to the Vercel frontend URL once that exists.
  Free-tier caveats: the service sleeps after 15 idle minutes and the first request takes about a minute. Free
  Postgres expires 30 days after creation and is deleted 14 days later unless upgraded. Only one free Postgres
  database is allowed per workspace.
- **Frontend on Vercel:** root directory `frontend`, framework preset Vite (build `npm run build`, output `dist`),
  and environment variable `VITE_API_URL=https://<your-backend>.onrender.com`. It is baked in at build time, so
  redeploy after changing it.

---

## Project layout

```
.
├── README.md
├── render.yaml                Render Blueprint (backend web service + free Postgres)
├── .claude/launch.json        dev server configs: backend, backend-force-invalid-extraction, frontend
├── backend/
│   ├── requirements.txt
│   ├── .env.example           all backend settings with defaults
│   ├── app/
│   │   ├── main.py            FastAPI app, startup (tables, migrations, seeding, model warm-up), CORS
│   │   ├── config.py          env-driven settings (DB URL, models, threshold, CORS)
│   │   ├── db.py              engine, sessions, create_all + column migrations
│   │   ├── models.py          SQLAlchemy models (6 tables)
│   │   ├── schemas.py         extraction contract (strict pydantic + JSON schema) and request bodies
│   │   ├── prompts.py         persona / attacker / extraction system prompts
│   │   ├── llm.py             Claude calls, refusal handling, validation + one retry, PII masking
│   │   ├── mock_llm.py        offline stand-in for Claude
│   │   ├── pipeline.py        close -> extract -> embed -> link
│   │   ├── embeddings.py      fastembed (ONNX MiniLM) with hashing fallback, cosine similarity
│   │   ├── clustering.py      union-find attacker clusters
│   │   ├── serializers.py     ORM -> JSON for the API
│   │   ├── report.py          markdown report + defensive-action lookup
│   │   ├── mitre.py           ATT&CK techniques, explanations, defenses, tactic vocabulary
│   │   ├── seed.py            idempotent seeding; `python -m app.seed [--reset]`
│   │   ├── seed_data.py       default personas and attacker scripts
│   │   └── routers/
│   │       ├── personas.py    /personas, /attacker-scripts
│   │       ├── incidents.py   /incidents/*
│   │       └── dashboard.py   /health, /dashboard/stats, /threat-map, /demo/reset
│   └── tests/
│       ├── test_llm_contract.py
│       └── test_needs_review.py
├── eval/
│   ├── README.md              scoring, labeling guide, limits
│   ├── run_eval.py            extraction eval harness
│   └── fixtures/              10 hand-labeled transcripts (8 clean, 2 ambiguous)
└── frontend/
    ├── package.json
    ├── vite.config.js         React + Tailwind plugins, /api dev proxy
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx            state, auto-play loop, layout, toasts
        ├── api.js             fetch wrapper (VITE_API_URL)
        ├── index.css          Tailwind theme, report styles
        └── components/
            ├── StatsBar.jsx       header stat cards
            ├── Sidebar.jsx        simulator form + incident feed
            ├── IncidentView.jsx   transcript, controls, IOC highlighting
            ├── AnalysisPanel.jsx  profile, needs-review panel, linked incidents
            ├── ReportModal.jsx    markdown report with copy/download
            ├── ThreatMap.jsx      d3-force campaign graph
            └── ui.jsx             badges, buttons, panels
```

---

## Limitations and next steps

- **Single-user demo.** No authentication or multi-tenancy.
- **Text channel only.** `channel` supports `email` and `voice` in the data model, but only text is implemented.
- **Small eval set.** n=10 hand-labeled transcripts; it measures agreement with our labels, not accuracy on real
  attacker traffic.
- **Mock mode is a baseline, not a model.** Its extraction is keyword matching and its conversations are scripted.
- **Similarity search is brute force** in Python, fine for dozens of incidents.

Next steps: a voice channel (Whisper and ElevenLabs), `pgvector` for large-scale similarity search, a real inbound
channel (email or SMS webhook) feeding `POST /incidents/manual`, and a larger, independently labeled eval set.

No license file is included yet.
