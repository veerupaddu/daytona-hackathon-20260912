"""Sample tests that Daytona is reachable and can create a sandbox."""

from __future__ import annotations

import os
import unittest

from daytona import ListSandboxesQuery

from providers.daytona import (
    connect_daytona,
    create_python_sandbox,
    delete_sandbox,
    load_daytona_settings,
    upload_and_exec,
)


class TestDaytonaConnection(unittest.TestCase):
    """Live checks against the Daytona API using ``DAYTONA_API_KEY``."""

    def test_daytona_api_key_is_set(self) -> None:
        """Fail fast when ``.env`` does not contain a Daytona API key."""
        self.assertTrue(
            (os.environ.get("DAYTONA_API_KEY") or "").strip(),
            "DAYTONA_API_KEY is missing from .env",
        )

    def test_daytona_connection(self) -> None:
        """Authenticate and list sandboxes to prove the API accepts the key."""
        client = connect_daytona()
        sandboxes = list(client.list(ListSandboxesQuery(limit=1), request_timeout=30))
        self.assertIsInstance(sandboxes, list)

    def test_daytona_creates_sandbox(self) -> None:
        """Create a Python sandbox, run a snippet, then delete the sandbox."""
        client = connect_daytona()
        sandbox = create_python_sandbox(client, name="daytona-hack-connection-test")
        try:
            self.assertTrue(sandbox.id)
            self.assertIsNotNone(sandbox.state)
            output = upload_and_exec(sandbox, 'print("sandbox-ok")')
            self.assertIn("sandbox-ok", output)
        finally:
            delete_sandbox(sandbox)


if __name__ == "__main__":
    api_key, api_url = load_daytona_settings()
    del api_key
    client = connect_daytona()
    print(f"Daytona connected at {api_url}")

    sandbox = create_python_sandbox(client, name="daytona-hack-connection-test")
    try:
        print(f"Created sandbox {sandbox.id} ({sandbox.state})")
        output = upload_and_exec(sandbox, 'print("sandbox-ok")')
        print(f"Exec output: {output.strip()}")
    finally:
        delete_sandbox(sandbox)
        print("Deleted sandbox")
