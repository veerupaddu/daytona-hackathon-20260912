"""Web UI: prompt → Nosana + Daytona → Neo4j analysis."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from studio.graph import GraphStore
from studio.orchestrator import run_turn, summarize_logs

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
load_dotenv(REPO_ROOT / ".env")

store = GraphStore()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    store.close()


app = FastAPI(title="Nosana + Daytona studio", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class PromptRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    status = store.status()
    nosana_deploy = (
        os.environ.get("NOSANA_DEPLOYMENT_URL") or "https://deploy.nosana.com/deployments"
    ).strip()
    nosana_logs = (
        os.environ.get("NOSANA_LOGS_URL") or (nosana_deploy.rstrip("/") + "#logs")
    ).strip()
    nosana_job = (
        os.environ.get("NOSANA_JOB_URL") or "https://explore.nosana.com"
    ).strip()
    status["references"] = {
        "neo4j": [
            {"label": "Explore graph", "url": "https://workspace.neo4j.io/workspace/explore", "detail": "Visual graph of Session, Prompt, Nosana, Daytona"},
            {"label": "Query workspace", "url": status["aura_query_url"], "detail": "Run Cypher on stored logs"},
            {"label": "Neo4j Browser", "url": status["browser_url"], "detail": "Open Aura with this instance URI"},
        ],
        "nosana": [
            {"label": "Deployment logs", "url": nosana_logs, "detail": "GPU pull, container, and runtime logs"},
            {"label": "Explorer job", "url": nosana_job, "detail": "On-chain job events and host details"},
        ],
        "daytona": [
            {"label": "Audit logs", "url": "https://app.daytona.io/dashboard/audit-logs", "detail": "Sandbox create, start, stop, and exec history"},
            {"label": "Sandboxes", "url": "https://app.daytona.io/dashboard/sandboxes", "detail": "Live sandbox list"},
        ],
    }
    return {"ok": True, **status}


@app.get("/api/graph")
def graph() -> dict:
    return store.fetch_graph()


@app.post("/api/run")
def run_prompt(body: PromptRequest) -> dict:
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is empty")
    return run_turn(prompt, store)


@app.get("/api/analysis")
def analysis() -> dict:
    return store.analyze_runs()


@app.post("/api/summarize")
def summarize() -> dict:
    return summarize_logs(store)
