"""Detector plug-ins and a helper that merges their results.

Add a new detector by subclassing GameDetector and listing it in
default_detectors(). Planned: steam_macos (registry.vdf), epic manifests,
and Windows registry/manifest detectors (written but untested).
"""

from __future__ import annotations

from collections.abc import Iterable

from .base import DetectedGame, GameDetector
from .macos_process import MacProcessDetector

__all__ = ["DetectedGame", "GameDetector", "MacProcessDetector", "default_detectors", "get_running_games"]


def default_detectors(tagged_names: Iterable[str] = ()) -> list[GameDetector]:
    candidates: list[GameDetector] = [MacProcessDetector(tagged_names=tagged_names)]
    return [d for d in candidates if d.is_available()]


def get_running_games(detectors: Iterable[GameDetector]) -> list[DetectedGame]:
    """Union of all detectors, deduped by game key (first detector wins)."""
    merged: dict[str, DetectedGame] = {}
    for detector in detectors:
        for game in detector.get_running_games():
            merged.setdefault(game.key, game)
    return list(merged.values())
