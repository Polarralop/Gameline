"""Claude backend. Structured outputs (output_config.format) guarantee valid JSON."""

from __future__ import annotations

import json
from typing import Any

import anthropic

from .base import EstimatorLLM

DEFAULT_MODEL = "claude-sonnet-5-5"


class ClaudeLLM(EstimatorLLM):
    def __init__(self, model: str = DEFAULT_MODEL, effort: str = "low") -> None:
        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.model = model
        # Estimation is a short, simple task: low effort keeps it fast and cheap.
        self.effort = effort

    def complete_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
        )
        if msg.stop_reason == "refusal":
            raise RuntimeError("Claude declined the request")
        text = next(b.text for b in msg.content if b.type == "text")
        return json.loads(text)
