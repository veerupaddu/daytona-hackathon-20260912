"""Sample checks that Daytona and Nosana are configured and reachable.

Does not create Daytona sandboxes or post paid Nosana jobs.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from dotenv import load_dotenv

from providers.nosana import GPT_OSS_20B_JOB, JOB_FILE

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")


class TestDaytonaAndNosana(unittest.TestCase):
    """Lightweight checks for both providers without posting a Nosana job."""
    @classmethod
    def setUpClass(cls) -> None:
        """Cache API keys from ``.env`` for the Daytona and Nosana checks."""
        cls.daytona_key = (os.environ.get("DAYTONA_API_KEY") or "").strip()
        cls.nosana_key = (os.environ.get("NOSANA_API_KEY") or "").strip()

    def test_daytona_sdk_lists_sandboxes(self) -> None:
        """List sandboxes through the shared Daytona helpers.

        Skips when ``DAYTONA_API_KEY`` is unset. Creating a sandbox is covered
        by ``test_daytona_connection.TestDaytonaConnection``.
        """
        if not self.daytona_key:
            self.skipTest("DAYTONA_API_KEY is not set in .env")

        from daytona import ListSandboxesQuery

        from providers.daytona import connect_daytona

        client = connect_daytona()
        page = list(client.list(ListSandboxesQuery(limit=1), request_timeout=30))
        self.assertIsInstance(page, list)

    def test_nosana_api_key_present(self) -> None:
        """Require a Nosana key that uses the ``nos_`` prefix."""
        self.assertTrue(
            self.nosana_key.startswith("nos_"),
            "NOSANA_API_KEY is missing or does not look like a Nosana key",
        )

    def test_nosana_cli_is_installed(self) -> None:
        """Confirm the ``nosana`` CLI is on PATH and reports a version."""
        nosana = shutil.which("nosana")
        self.assertIsNotNone(nosana, "nosana CLI is not on PATH")
        result = subprocess.run(
            [nosana, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((result.stdout or result.stderr).strip())

    def test_nosana_job_json_matches_gpt_oss_20b(self) -> None:
        """Check the job file and the Python payload target GPT-OSS 20B."""
        self.assertTrue(JOB_FILE.exists(), "jobs/gpt-oss-20b.json is missing")
        on_disk = json.loads(JOB_FILE.read_text())
        self.assertEqual(on_disk["global"]["variables"]["MODEL"], "gpt-oss:20b")
        self.assertEqual(GPT_OSS_20B_JOB["global"]["variables"]["MODEL"], "gpt-oss:20b")
        self.assertEqual(on_disk["ops"][0]["id"], "gpt-oss:20b")

    def test_nosana_job_definition_validates(self) -> None:
        """Run ``nosana job validate`` against the local job definition."""
        nosana = shutil.which("nosana")
        if not nosana:
            self.skipTest("nosana CLI is not on PATH")

        result = subprocess.run(
            [nosana, "job", "validate", str(JOB_FILE)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            result.stderr or result.stdout or "nosana job validate failed",
        )


if __name__ == "__main__":
    unittest.main()
