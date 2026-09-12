#!/usr/bin/env python3
"""Helpers for connecting to Daytona and running Python in a sandbox."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"


def _in_project_venv() -> bool:
    """Return True when this process is the project ``.venv`` interpreter.

    Do not compare ``sys.executable.resolve()`` to the venv ``python``
    symlink. On Homebrew, both resolve to the same framework binary.
    """
    return Path(sys.prefix).resolve() == (REPO_ROOT / ".venv").resolve()


def _reexec_in_venv() -> None:
    """Re-run this file with the project venv if system Python lacks daytona."""
    if _in_project_venv():
        return
    try:
        import daytona  # noqa: F401
        return
    except ImportError:
        pass
    if VENV_PYTHON.is_file():
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])
    sys.exit(
        "The daytona package is not installed.\n"
        "  python3 -m venv .venv\n"
        "  .venv/bin/pip install -r requirements.txt\n"
        "  source .venv/bin/activate"
    )


_reexec_in_venv()

from dotenv import load_dotenv
from daytona import CreateSandboxFromSnapshotParams, Daytona, DaytonaConfig, Sandbox

load_dotenv(REPO_ROOT / ".env")

DEFAULT_API_URL = "https://app.daytona.io/api"


def load_daytona_settings() -> tuple[str, str]:
    """Read Daytona credentials from the environment.

    Loads ``DAYTONA_API_KEY`` and optional ``DAYTONA_API_URL`` after ``.env``
    has been applied. Does not print the key.

    Returns:
        A ``(api_key, api_url)`` pair. ``api_url`` falls back to the Daytona
        Cloud API if ``DAYTONA_API_URL`` is unset.

    Raises:
        RuntimeError: If ``DAYTONA_API_KEY`` is missing or blank.
    """
    api_key = (os.environ.get("DAYTONA_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("DAYTONA_API_KEY is not set in .env")
    api_url = (os.environ.get("DAYTONA_API_URL") or DEFAULT_API_URL).strip()
    return api_key, api_url


def connect_daytona() -> Daytona:
    """Create an authenticated Daytona client.

    Uses ``api_url`` (not the deprecated ``server_url``) so the SDK talks to
    Daytona Cloud or a self-hosted API without a deprecation warning.

    Returns:
        A ready-to-use ``Daytona`` client.

    Raises:
        RuntimeError: If the API key is not configured.
    """
    api_key, api_url = load_daytona_settings()
    return Daytona(DaytonaConfig(api_key=api_key, api_url=api_url))


def create_python_sandbox(
    client: Daytona,
    *,
    name: str | None = None,
    timeout: float = 90,
) -> Sandbox:
    """Create an ephemeral Python sandbox.

    The sandbox is marked ephemeral so Daytona deletes it automatically if
    this process exits without calling ``delete_sandbox``. A unique suffix is
    added to ``name`` so leftover sandboxes do not cause a name conflict.

    Args:
        client: Authenticated Daytona client from ``connect_daytona``.
        name: Optional sandbox name prefix. Daytona assigns one if omitted.
        timeout: Seconds to wait for the sandbox to become ready.

    Returns:
        A started ``Sandbox`` with a Python toolchain.
    """
    sandbox_name = f"{name}-{uuid.uuid4().hex[:8]}" if name else None
    params = CreateSandboxFromSnapshotParams(
        language="python",
        name=sandbox_name,
        ephemeral=True,
        labels={"purpose": "daytona-hack-sample"},
    )
    return client.create(params, timeout=timeout)


def upload_and_exec(sandbox: Sandbox, code_snippet: str) -> str:
    """Run a Python snippet in the sandbox with the language toolbox.

    Uses ``process.code_run`` (not a manual ``/tmp/run.py`` upload) so the
    default Python interpreter is used.

    Args:
        sandbox: Running Daytona sandbox.
        code_snippet: Python source to execute.

    Returns:
        Combined standard output from the snippet.

    Raises:
        RuntimeError: If the remote process exits with a non-zero status.
    """
    result = sandbox.process.code_run(code_snippet)
    if result.exit_code not in (0, None):
        raise RuntimeError(
            f"sandbox code_run failed (exit {result.exit_code}): {result.result}"
        )
    return result.result or ""


def delete_sandbox(sandbox: Sandbox, timeout: float = 60) -> None:
    """Delete a sandbox and wait until it is destroyed.

    Args:
        sandbox: Sandbox returned by ``create_python_sandbox``.
        timeout: Seconds to wait for deletion to finish.
    """
    sandbox.delete(timeout=timeout, wait=True)


def run_in_daytona(code_snippet: str) -> str:
    """Run a Python snippet on Daytona and tear the sandbox down.

    Args:
        code_snippet: Python source executed inside a fresh sandbox.

    Returns:
        Standard output from the remote Python process.
    """
    client = connect_daytona()
    sandbox = create_python_sandbox(client, name="daytona-hack-run")
    try:
        return upload_and_exec(sandbox, code_snippet)
    finally:
        delete_sandbox(sandbox)


if __name__ == "__main__":
    print(run_in_daytona('print("hello from daytona")'))
    print(run_in_daytona("print(2 + 2)"))
