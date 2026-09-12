# Nosana + Daytona studio

Hackathon app that plans Python on a **Nosana** GPU LLM (GPT-OSS 20B), executes it in an ephemeral **Daytona** sandbox, and stores timings plus logs in **Neo4j**.

```
Prompt → Nosana writes Python → Daytona runs it → Neo4j records the graph
```

The web studio shows each step, Neo4j insights (run graph + timings) above log analysis, and links to Nosana deployment logs and Daytona audit logs.

## Repository layout

```
studio/                 FastAPI app, orchestrator, Neo4j store, UI
  app.py
  orchestrator.py
  graph.py
  static/
providers/              Daytona sandbox + Nosana LLM / job helpers
jobs/gpt-oss-20b.json   Official Ollama job definition (16 GB VRAM)
scripts/setup_neo4j.py  Neo4j constraints and indexes
tests/
onetime.sh              First-time venv, Docker Neo4j, and schema
run.sh                  Start or restart the studio UI
issue.md                Known Nosana GPU / 503 behavior
.env.example            Public template — copy to .env (gitignored)
```

Secrets stay in `.env`. That file is gitignored and must not be committed.

## Prerequisites

- Python 3.10+
- Node.js 20+ (Nosana CLI)
- [Daytona API key](https://app.daytona.io/dashboard/keys)
- [Nosana API key](https://deploy.nosana.com) and GPU credits
- Optional: [Neo4j Aura](https://console.neo4j.io) (or local Docker)

GPT-OSS 20B needs about 16 GB VRAM. A typical 60-minute job is on the order of **0.2–0.32 credits**, depending on the GPU market. Prefer a host that is **idle now**. Markets with zero idle hosts (often `nvidia-5080`) stay **queued** and the public URL returns **HTTP 503**. See [issue.md](issue.md).

## Setup

```bash
git clone <your-fork-url> daytona-hack
cd daytona-hack
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install -g @nosana/cli
cp .env.example .env
```

Fill `.env` with your keys. Leave unused values blank.

| Variable | Used by | Notes |
|---|---|---|
| `DAYTONA_API_KEY` | Sandbox runs and tests | Required for execution |
| `DAYTONA_API_URL` | Optional | Default `https://app.daytona.io/api` |
| `NOSANA_API_KEY` | Posting GPU jobs | `nos_…` key |
| `NOSANA_LLM_URL` | Studio + LLM tests | Public HTTPS URL of a **running** job (port 11434) |
| `NOSANA_LLM_MODEL` | Chat calls | Default `gpt-oss:20b` |
| `NOSANA_DEPLOYMENT_URL` | Studio links | Your deployment page |
| `NOSANA_LOGS_URL` | Studio links | Defaults to `{deployment}#logs` |
| `NOSANA_JOB_URL` | Studio links | Explorer job page |
| `NEO4J_URI` | Graph store | Aura `neo4j+s://…` or `bolt://127.0.0.1:7687` |
| `NEO4J_USERNAME` / `NEO4J_PASSWORD` | Bolt | Instance user, not Aura API client creds |
| `NEO4J_DATABASE` | Bolt | Usually `neo4j` |
| `AURA_INSTANCEID` | Optional | Deep-link to the Aura console |

Restart `./run.sh` after you change `NOSANA_LLM_URL` so uvicorn picks up the new endpoint.

## Web studio

From the repo root, with `.venv` active:

```bash
# Once per machine (venv, Neo4j container, graph schema)
./onetime.sh

# Every time you want the UI (stays running in this terminal; Ctrl+C to stop)
./run.sh
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Example prompt: `Calculate 2 + 2 and print the result`. `./run.sh stop` stops only the UI. `docker compose down` stops local Neo4j.

On load (and after each run) the studio:

1. Shows the latest prompt, Nosana Python, and Daytona stdout from Neo4j
2. Draws **Neo4j insights** — one Session → Prompt → Nosana → Daytona path per unique prompt, plus grouped GPU vs sandbox timings
3. Summarizes stored logs in **Log analysis** (Step 4)

Repeated prompts (for example several 503 retries) collapse to a single graph row with a count (`×3`). If Neo4j is unreachable, the studio still runs with an in-memory graph.

Inspect the same data in Aura:

- [Explore](https://workspace.neo4j.io/workspace/explore)
- [Query](https://workspace.neo4j.io/workspace/query)
- [Browser](https://browser.neo4j.io)

```cypher
MATCH (s:Session)-[:ASKED]->(p:Prompt)-[:PLANNED_ON]->(n:NosanaLog)-[:EXECUTED_IN]->(d:DaytonaLog)
RETURN s, p, n, d ORDER BY p.created_at DESC LIMIT 25
```

Studio cards also open [Nosana Deploy logs](https://deploy.nosana.com/deployments) and [Daytona audit logs](https://app.daytona.io/dashboard/audit-logs).

## Providers

### Daytona

Creates an ephemeral Python sandbox, runs a snippet, then deletes it.

```bash
python -m providers.daytona
```

```python
from providers.daytona import run_in_daytona

print(run_in_daytona("print(2 + 2)"))
```

Use `api_url` / `DAYTONA_API_URL`, not the deprecated `server_url`.

### Nosana (GPT-OSS 20B)

There is no official Nosana Python SDK. The studio talks HTTP to a running Ollama job (`/api/tags`, `/v1/chat/completions`). Posting a job uses `@nosana/cli` and **spends credits**. Idle time still burns them; there is no pause.

```bash
python -m providers.nosana
```

```python
from providers.nosana import add_two_numbers_via_llm, ask_nosana_llm, run_in_nosana

run_in_nosana(market="nvidia-5080", timeout_minutes=60)
print(add_two_numbers_via_llm(7, 5))
```

Wait until the endpoint is healthy (`GET /api/tags` → 200), then set `NOSANA_LLM_URL`. If the response is 503, the job is queued or still pulling weights — pick a ready GPU or wait. Stop the deployment when you are done.

Prefer `NOSANA_API_KEY` over a funded CLI wallet (`~/.nosana/nosana_key.json`).

## Tests

None of these post a new paid Nosana job. Activate `.venv` first.

```bash
python -m unittest discover -s tests -v
```

| File | What it does |
|---|---|
| `tests/test_daytona_connection.py` | Connection + creates a sandbox |
| `tests/test_providers.py` | CLI + `jobs/gpt-oss-20b.json` validation |
| `tests/test_nosana_llm.py` | Live `7 + 5`; skips if `NOSANA_LLM_URL` is empty |

## Troubleshooting

- `No module named 'daytona'` — use `.venv/bin/python` and `pip install -r requirements.txt`. Import `daytona`, not `daytona_sdk`.
- `DAYTONA_API_KEY is not set` — copy `.env.example` to `.env`.
- `nosana job post` fails with 0 SOL — set `NOSANA_API_KEY`.
- LLM tests skip — deploy GPT-OSS, then set `NOSANA_LLM_URL`.
- Studio health says **Nosana queued / starting** or chat fails with **HTTP 503** — the GPU job is not serving yet. See [issue.md](issue.md). Restart `./run.sh` after you point `.env` at a new URL.
- Studio graph is empty — run `./onetime.sh` (or `python scripts/setup_neo4j.py`) and confirm Bolt credentials (not Aura API client id/secret).
- Prompt / Nosana / Daytona boxes look empty after a refresh — they load from the latest Neo4j run; confirm Aura has `Prompt` / `NosanaLog` / `DaytonaLog` nodes.
