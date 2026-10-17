"""A clock that can run faster than real time, for demo mode.

At speed 360, one real second is six app minutes, so a 3h session alert
fires after 30 real seconds. Everything time-based reads clock.now().
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta


class Clock:
    def __init__(self, speed: float = 1.0) -> None:
        self._lock = threading.Lock()
        self._anchor_real = time.monotonic()
        self._anchor_app = datetime.now()
        self._speed = speed

    @property
    def speed(self) -> float:
        return self._speed

    def now(self) -> datetime:
        with self._lock:
            elapsed = time.monotonic() - self._anchor_real
            return self._anchor_app + timedelta(seconds=elapsed * self._speed)

    def set_speed(self, speed: float) -> None:
        """Change speed without jumping: re-anchor at the current app time."""
        with self._lock:
            elapsed = time.monotonic() - self._anchor_real
            self._anchor_app += timedelta(seconds=elapsed * self._speed)
            self._anchor_real = time.monotonic()
            self._speed = speed


class FixedClock(Clock):
    """Manually advanced clock for tests."""

    def __init__(self, at: datetime) -> None:
        super().__init__()
        self._at = at

    def now(self) -> datetime:
        return self._at

    def advance(self, **kwargs: float) -> None:
        self._at += timedelta(**kwargs)
