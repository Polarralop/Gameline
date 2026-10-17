"""Claude backend. Uses a forced tool call so the reply is always valid JSON."""

from __future__ import annotations

from typing import Any

import anthropic

from .base import EstimatorLLM

DEFAULT_MODEL = "claude-sonnet-5-5"


class ClaudeLLM(EstimatorLLM):
    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.model = model

    def complete_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            tools=[{"name": "submit", "description": "Return the result.", "input_schema": schema}],
            tool_choice={"type": "tool", "name": "submit"},
        )
        for block in msg.content:
            if block.type == "tool_use":
                return dict(block.input)
        raise RuntimeError("Claude returned no structured output")
