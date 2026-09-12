import json
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
JOB_FILE = REPO_ROOT / "jobs" / "gpt-oss-20b.json"

load_dotenv(REPO_ROOT / ".env")

GPT_OSS_20B_JOB = {
    "version": "0.1",
    "type": "container",
    "meta": {
        "trigger": "python",
        "template": "gpt-oss",
        "variant": "20b",
        "recommended_gpu": "nvidia-5080",
        "timeout_minutes": 60,
        "system_requirements": {
            "vram_total_mb": 16384
        },
    },
    "global": {
        "variables": {
            "MODEL": "gpt-oss:20b"
        }
    },
    "ops": [
        {
            "id": "gpt-oss:20b",
            "type": "container/run",
            "args": {
                "gpu": True,
                "image": "docker.io/ollama/ollama:0.32.6",
                "expose": [
                    {
                        "port": 11434,
                        "health_checks": [
                            {
                                "path": "/api/tags",
                                "type": "http",
                                "method": "GET",
                                "continuous": False,
                                "expected_status": 200,
                            }
                        ],
                    }
                ],
                "resources": [
                    {
                        "type": "Ollama",
                        "model": "%%global.variables.MODEL%%",
                    }
                ],
            },
        }
    ],
}


def run_in_nosana(
    market: str = "nvidia-5080",
    timeout_minutes: int = 60,
) -> str:
    """Post a GPT-OSS 20B job to the Nosana GPU grid.

    Writes ``jobs/gpt-oss-20b.json`` from ``GPT_OSS_20B_JOB`` and runs ``nosana job post``.
    This spends credits. Prefer ``nosana job validate`` in tests.

    Args:
        market: Nosana GPU market slug, for example ``nvidia-5080``.
        timeout_minutes: Reserved GPU time. Nosana requires at least 60.

    Returns:
        Standard output from the Nosana CLI.

    Raises:
        RuntimeError: If ``nosana job post`` exits non-zero.
    """
    JOB_FILE.write_text(json.dumps(GPT_OSS_20B_JOB, indent=2) + "\n")

    cmd = [
        "nosana",
        "job",
        "post",
        "--file",
        str(JOB_FILE),
        "--gpu",
        "--market",
        market,
        "--timeout",
        str(timeout_minutes),
    ]
    api_key = os.environ.get("NOSANA_API_KEY")
    if api_key:
        cmd.extend(["--api", api_key])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "nosana job post failed")
    return result.stdout


def nosana_llm_base_url() -> str:
    """Return the OpenAI-compatible base URL for a running Nosana LLM job.

    Reads ``NOSANA_LLM_URL`` from ``.env``. Accepts either the host root
    (``https://....nos.ci``) or a URL that already ends with ``/v1``.

    Returns:
        Base URL with no trailing slash.

    Raises:
        RuntimeError: If ``NOSANA_LLM_URL`` is unset.
    """
    raw = (os.environ.get("NOSANA_LLM_URL") or "").strip().rstrip("/")
    if not raw:
        raise RuntimeError(
            "NOSANA_LLM_URL is not set. After GPT-OSS is running, paste the "
            "job endpoint (port 11434) into .env."
        )
    return raw


def nosana_llm_status() -> dict[str, object]:
    """Probe the configured Ollama endpoint without spending a chat call."""
    try:
        base = nosana_llm_base_url()
    except RuntimeError as exc:
        return {"ready": False, "status": "unset", "detail": str(exc), "url": ""}
    tags_url = urljoin(base + "/", "api/tags")
    try:
        response = httpx.get(tags_url, timeout=8)
    except httpx.HTTPError as exc:
        return {
            "ready": False,
            "status": "unreachable",
            "detail": str(exc),
            "url": base,
        }
    if response.status_code == 200:
        return {"ready": True, "status": "ready", "detail": "Ollama /api/tags ok", "url": base}
    if response.status_code == 503:
        return {
            "ready": False,
            "status": "queued",
            "detail": (
                "Nosana returned 503 (Service Initializing). The GPU job is "
                "queued or still pulling weights. Wait until deploy.nosana.com "
                "shows a running replica, then retry. NVIDIA 5080 often has no "
                "idle hosts — the old URL stays 503 until a host is assigned."
            ),
            "url": base,
        }
    return {
        "ready": False,
        "status": f"http_{response.status_code}",
        "detail": response.text[:240],
        "url": base,
    }


def ask_nosana_llm(prompt: str, *, timeout: float = 120) -> str:
    """Send a chat prompt to the deployed Nosana Ollama model.

    Args:
        prompt: User message for ``gpt-oss:20b`` (or ``NOSANA_LLM_MODEL``).
        timeout: Seconds to wait for the completion response.

    Returns:
        Assistant message text.

    Raises:
        RuntimeError: If the URL is missing or the HTTP call fails.
        httpx.HTTPError: If the endpoint is unreachable.
    """
    base = nosana_llm_base_url()
    model = (os.environ.get("NOSANA_LLM_MODEL") or "gpt-oss:20b").strip()
    chat_url = urljoin(base + "/", "v1/chat/completions")
    last_error: Exception | None = None
    response = None
    for attempt in range(1, 5):
        try:
            response = httpx.post(
                chat_url,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "temperature": 0,
                },
                timeout=timeout,
            )
            if response.status_code == 503:
                last_error = RuntimeError(
                    "Nosana GPU is not serving yet (HTTP 503). "
                    "The job is queued or still starting Ollama. "
                    "Watch deploy.nosana.com until the replica is running, "
                    "then run again. A 5080 with zero idle hosts stays 503."
                )
                time.sleep(min(8 * attempt, 20))
                continue
            response.raise_for_status()
            break
        except httpx.HTTPError as exc:
            last_error = exc
            time.sleep(2)
    else:
        raise last_error or RuntimeError("Nosana chat failed without a response")
    if response is None:
        raise last_error or RuntimeError("Nosana chat failed without a response")
    payload = response.json()
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected LLM response: {payload}") from exc


def add_two_numbers_via_llm(left: int, right: int) -> str:
    """Ask the Nosana LLM to add two integers.

    Args:
        left: First addend.
        right: Second addend.

    Returns:
        Raw model text. Callers should assert the numeric sum appears in it.
    """
    prompt = (
        f"Calculate {left} + {right}. "
        "Reply with only the integer sum, no words or punctuation."
    )
    return ask_nosana_llm(prompt)


if __name__ == "__main__":
    print(run_in_nosana())
    print(add_two_numbers_via_llm(7, 5) )
