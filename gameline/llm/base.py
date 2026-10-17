"""Provider-agnostic LLM interface.

The rest of the app only talks to EstimatorLLM.complete_json(). Swapping
Claude for Gemini means adding one class and changing GAMELINE_LLM.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class EstimatorLLM(ABC):
    @abstractmethod
    def complete_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Return a dict matching the JSON schema."""
