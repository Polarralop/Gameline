"""Offline backend for tests and for demoing without an API key.

Guesses effort from the task title so the demo still looks sensible.
"""

from __future__ import annotations

from typing import Any

from .base import EstimatorLLM

_KEYWORDS = {"exam": 10, "midterm": 8, "project": 12, "essay": 6, "lab": 3, "quiz": 2}


class StubLLM(EstimatorLLM):
    def complete_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        lowered = prompt.lower()
        hours = next((h for k, h in _KEYWORDS.items() if k in lowered), 4)
        n = max(1, round(hours / 2))
        return {
            "effort_hours": hours,
            "importance": 4 if hours >= 8 else 3,
            "rationale": "Offline estimate from task keywords.",
            "chunks": [{"title": f"Work block {i + 1}", "hours": hours / n} for i in range(n)],
        }
