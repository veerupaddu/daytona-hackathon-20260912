"""One user prompt → Nosana plan → Daytona exec → Neo4j logs."""

from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from providers.daytona import run_in_daytona
from providers.nosana import ask_nosana_llm
from studio.graph import GraphStore

PLAN_INSTRUCTION = """The user asked:

{prompt}

Write a short Python script that answers them and prints the result.
Output only valid Python source. No markdown fences, no explanation.
"""


def extract_python(text: str) -> str:
    """Pull a Python block out of an LLM reply if fences are present."""
    fenced = re.search(r"```(?:python)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return text.strip()


def run_turn(prompt: str, store: GraphStore) -> dict[str, Any]:
    """Call Nosana, run the generated code on Daytona, log both to the graph."""
    session_id = f"session-{uuid.uuid4().hex[:10]}"
    prompt_id = f"prompt-{uuid.uuid4().hex[:10]}"
    nosana_id = f"nosana-{uuid.uuid4().hex[:10]}"
    daytona_id = f"daytona-{uuid.uuid4().hex[:10]}"
    created_at = datetime.now(timezone.utc).isoformat()

    nosana_reply = ""
    nosana_error = ""
    nosana_ms = 0
    code = ""
    daytona_output = ""
    daytona_error = ""
    daytona_ms = 0

    started = time.perf_counter()
    try:
        nosana_reply = ask_nosana_llm(PLAN_INSTRUCTION.format(prompt=prompt))
        code = extract_python(nosana_reply)
    except Exception as exc:
        nosana_error = str(exc)
    nosana_ms = int((time.perf_counter() - started) * 1000)

    if code and not nosana_error:
        started = time.perf_counter()
        try:
            daytona_output = run_in_daytona(code)
        except Exception as exc:
            daytona_error = str(exc)
        daytona_ms = int((time.perf_counter() - started) * 1000)
    elif not code:
        daytona_error = "Nosana did not return runnable Python, so Daytona was skipped."

    turn = {
        "session_id": session_id,
        "prompt_id": prompt_id,
        "nosana_id": nosana_id,
        "daytona_id": daytona_id,
        "created_at": created_at,
        "prompt": prompt,
        "nosana_reply": nosana_reply,
        "nosana_error": nosana_error,
        "nosana_ms": nosana_ms,
        "code": code,
        "daytona_output": daytona_output,
        "daytona_error": daytona_error,
        "daytona_ms": daytona_ms,
    }
    store.record_turn(turn)
    turn["graph_backend"] = store.backend
    return turn


def summarize_logs(store: GraphStore, *, limit: int = 12) -> dict[str, Any]:
    """Build a local analysis, then ask Nosana to summarize the log rows."""
    analysis = store.analyze_runs(limit)
    lines = [
        f"Runs: {analysis['run_count']}",
        f"Avg Nosana: {analysis['avg_nosana_ms']} ms",
        f"Avg Daytona: {analysis['avg_daytona_ms']} ms",
        f"Nosana failures: {analysis['nosana_failures']}",
        f"Daytona failures: {analysis['daytona_failures']}",
    ]
    for run in analysis["runs"][:8]:
        lines.append(
            f"- prompt={run.get('prompt')!r} nosana_ms={run.get('nosana_ms')} "
            f"daytona_ms={run.get('daytona_ms')} "
            f"out={str(run.get('daytona_output') or run.get('daytona_error') or '')[:120]!r}"
        )
    digest = "\n".join(lines)
    summary = ""
    error = ""
    started = time.perf_counter()
    try:
        summary = ask_nosana_llm(
            "Summarize these Nosana + Daytona pipeline logs for an operator. "
            "Cover execution time, failures, and the key messages. "
            "Use short bullet points.\n\n"
            f"{digest}"
        )
    except Exception as exc:
        error = str(exc)
        summary = (
            "Nosana summary unavailable. Local analysis:\n"
            + "\n".join(f"- {m}" for m in analysis["key_messages"])
            + f"\n- Average Nosana {analysis['avg_nosana_ms']} ms, "
            f"Daytona {analysis['avg_daytona_ms']} ms across {analysis['run_count']} runs."
        )
    analysis["llm_summary"] = summary
    analysis["llm_error"] = error
    analysis["llm_ms"] = int((time.perf_counter() - started) * 1000)
    analysis["digest"] = digest
    return analysis
