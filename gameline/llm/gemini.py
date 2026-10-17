"""Gemini backend (google-genai SDK, Interactions API).

Structured output via response_format with a JSON schema, so the reply is
valid JSON matching the same schema the Claude backends use.
"""

from __future__ import annotations

import json
from typing import Any

from google import genai

from .base import EstimatorLLM

DEFAULT_MODEL = "gemini-3.8-flash"


class GeminiLLM(EstimatorLLM):
    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.client = genai.Client()  # reads GEMINI_API_KEY
        self.model = model

    def complete_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        interaction = self.client.interactions.create(
            model=self.model,
            system_instruction=system,
            input=prompt,
            response_format={"type": "text", "mime_type": "application/json", "schema": schema},
            store=False,  # one-off calls; nothing to continue later
        )
        text = interaction.output_text
        if not text:
            raise RuntimeError(f"Gemini returned no output (status: {interaction.status})")
        return json.loads(text)
