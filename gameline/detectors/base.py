"""The one interface every game detector implements.

A detector answers a single question: which games are running right now?
The watcher polls every detector, merges the results, and decides what
counts as a "game launched" or "game closed" event. Detectors stay dumb and
stateless so they are cheap to call every few seconds.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class DetectedGame:
    """A game seen running by some detector."""

    name: str
    # Which detector found it, e.g. "macos_process" or "steam_registry".
    source: str
    pid: int | None = None
    # Unix timestamp of process start, when the detector knows it.
    started_at: float | None = None
    # Store-specific id (Steam AppID, Epic app name) when known.
    app_id: str | None = None

    @property
    def key(self) -> str:
        """Stable identity used to dedupe the same game across detectors."""
        return (self.app_id or self.name).lower()


class GameDetector(ABC):
    """Base class for detector plug-ins."""

    #: Short id shown in logs and stored in DetectedGame.source.
    name: str = "base"

    def is_available(self) -> bool:
        """Whether this detector can run on this machine (OS, launcher installed)."""
        return True

    @abstractmethod
    def get_running_games(self) -> list[DetectedGame]:
        """Return the games running right now. Must be fast and never raise."""
