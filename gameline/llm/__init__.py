"""LLM backends. get_llm() picks one by name, defaulting to the GAMELINE_LLM env var.

claude      Claude API (ANTHROPIC_API_KEY), the default
claude-cli  local Claude Code CLI on your Claude subscription (personal use only)
stub        offline keyword guesses, for tests and demos without network
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from .base import EstimatorLLM

# .env from the repo (development) and the data folder (also used by Gameline.app).
from ..paths import REPO_ROOT, data_dir  # noqa: E402

load_dotenv(REPO_ROOT / ".env")
load_dotenv(data_dir() / ".env")


BACKENDS = {"claude": "Claude API key", "claude-cli": "Claude subscription", "stub": "Offline (rough guesses)"}


def default_backend() -> str:
    return os.getenv("GAMELINE_LLM", "claude").lower()


def get_llm(name: str | None = None) -> EstimatorLLM:
    name = (name or default_backend()).lower()
    if name == "claude":
        from .claude import ClaudeLLM

        return ClaudeLLM()
    if name == "claude-cli":
        from .claude_cli import ClaudeCLILLM

        return ClaudeCLILLM()
    if name == "stub":
        from .stub import StubLLM

        return StubLLM()
    raise ValueError(f"Unknown LLM backend: {name!r}")
