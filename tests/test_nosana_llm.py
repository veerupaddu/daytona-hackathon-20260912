"""Tests for a GPT-OSS job already running on Nosana.

These calls need ``NOSANA_LLM_URL`` in ``.env`` (the job's public HTTPS
endpoint). They do not post a new paid job.
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

from dotenv import load_dotenv

from providers.nosana import add_two_numbers_via_llm, ask_nosana_llm

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")


def _llm_url() -> str:
    return (os.environ.get("NOSANA_LLM_URL") or "").strip()


class TestNosanaLlm(unittest.TestCase):
    """Live chat checks against a deployed Nosana Ollama endpoint."""

    def test_nosana_llm_adds_two_numbers(self) -> None:
        """Ask the model to add 7 and 5 and expect 12 in the reply.

        Skips when ``NOSANA_LLM_URL`` is empty so CI does not spend GPU
        credits or fail before a job is posted.
        """
        if not _llm_url():
            self.skipTest(
                "NOSANA_LLM_URL is unset. Deploy GPT-OSS 20B, then set the "
                "job URL in .env and re-run this test."
            )

        left, right = 7, 5
        expected = left + right
        reply = add_two_numbers_via_llm(left, right)
        self.assertTrue(reply.strip(), "LLM returned an empty reply")
        numbers = [int(n) for n in re.findall(r"-?\d+", reply)]
        self.assertIn(
            expected,
            numbers,
            f"expected {expected} in LLM reply, got: {reply!r}",
        )

    def test_nosana_llm_chat_roundtrip(self) -> None:
        """Send a tiny prompt and require a non-empty assistant message."""
        if not _llm_url():
            self.skipTest("NOSANA_LLM_URL is unset")

        reply = ask_nosana_llm("Reply with the word pong only.")
        self.assertTrue(reply.strip())


if __name__ == "__main__":
    unittest.main()
