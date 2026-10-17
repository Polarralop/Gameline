"""LLM backends. get_llm() picks one from the GAMELINE_LLM env var."""

from __future__ import annotations

import os

from .base import EstimatorLLM


def get_llm(name: str | None = None) -> EstimatorLLM:
    name = (name or os.getenv("GAMELINE_LLM", "claude")).lower()
    if name == "claude":
        from .claude import ClaudeLLM

        return ClaudeLLM()
    if name == "stub":
        from .stub import StubLLM

        return StubLLM()
    raise ValueError(f"Unknown LLM backend: {name!r}")
