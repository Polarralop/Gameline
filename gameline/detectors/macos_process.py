"""macOS process detector: scan running processes with psutil.

A process counts as a game if either:
  1. its executable lives under a known game library folder (Steam's
     steamapps/common, Epic's install folder), or
  2. its process name or .app bundle name was tagged as a game by the user
     (this is also how the demo-mode fake game gets detected).

Games often spawn helpers (crash handlers, launchers), so results are
deduped per game, keeping the earliest-started process.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable
from pathlib import Path

import psutil

from .base import DetectedGame, GameDetector

HOME = Path.home()

DEFAULT_LIBRARY_ROOTS = [
    HOME / "Library/Application Support/Steam/steamapps/common",
    Path("/Users/Shared/Epic Games"),
]

_ATTRS = ["pid", "name", "exe", "create_time"]


def bundle_name(exe: str) -> str | None:
    """'/Applications/Foo Bar.app/Contents/MacOS/foo' -> 'Foo Bar'."""
    for part in Path(exe).parts:
        if part.endswith(".app"):
            return part[: -len(".app")]
    return None


def library_game_name(exe: str, roots: Iterable[Path]) -> str | None:
    """The game folder name if exe sits under one of the library roots."""
    path = Path(exe)
    for root in roots:
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if rel.parts:
            return rel.parts[0]
    return None


class MacProcessDetector(GameDetector):
    name = "macos_process"

    def __init__(
        self,
        tagged_names: Iterable[str] = (),
        library_roots: Iterable[Path] = DEFAULT_LIBRARY_ROOTS,
        process_iter: Callable[..., Iterable[psutil.Process]] = psutil.process_iter,
    ) -> None:
        self.tagged = {n.lower() for n in tagged_names}
        self.library_roots = [Path(r) for r in library_roots]
        # Injectable so tests can feed fake processes.
        self._process_iter = process_iter

    def is_available(self) -> bool:
        return sys.platform == "darwin"

    def tag(self, name: str) -> None:
        """Mark a process or app name as a game (from the setup UI)."""
        self.tagged.add(name.lower())

    def _match(self, proc_name: str | None, exe: str | None) -> str | None:
        if exe:
            game = library_game_name(exe, self.library_roots)
            if game:
                return game
            bundle = bundle_name(exe)
            if bundle and bundle.lower() in self.tagged:
                return bundle
        if proc_name and proc_name.lower() in self.tagged:
            return proc_name
        return None

    def get_running_games(self) -> list[DetectedGame]:
        found: dict[str, DetectedGame] = {}
        try:
            procs = self._process_iter(_ATTRS)
            for proc in procs:
                info = proc.info  # psutil fills this from attrs; denied fields are None
                game = self._match(info.get("name"), info.get("exe"))
                if not game:
                    continue
                hit = DetectedGame(
                    name=game,
                    source=self.name,
                    pid=info.get("pid"),
                    started_at=info.get("create_time"),
                )
                prev = found.get(hit.key)
                if prev is None or (hit.started_at or float("inf")) < (
                    prev.started_at or float("inf")
                ):
                    found[hit.key] = hit
        except (psutil.Error, OSError):
            # A detector must never crash the polling loop.
            pass
        return list(found.values())
