"""Desktop notifications, with a fallback when macOS won't deliver them.

desktop-notifier is async; the watcher runs on a plain worker thread, so
notify() wraps each send in its own event loop. If the native notification
fails (no permission, unbundled Python), we fall back to osascript's
`display notification`, which is delivered by Script Editor's identity.

Run `python -m gameline.notify` to fire a test notification.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess

from desktop_notifier import DesktopNotifier

log = logging.getLogger(__name__)

APP_NAME = "Gameline"
_notifier: DesktopNotifier | None = None


def _get() -> DesktopNotifier:
    global _notifier
    if _notifier is None:
        _notifier = DesktopNotifier(app_name=APP_NAME)
    return _notifier


async def _send_native(title: str, message: str) -> None:
    notifier = _get()
    if not await notifier.request_authorisation():
        raise PermissionError("Notification permission denied")
    await notifier.send(title=title, message=message)


def _send_osascript(title: str, message: str) -> None:
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    script = f'display notification "{esc(message)}" with title "{esc(title)}"'
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True)


def notify(title: str, message: str) -> str:
    """Show a notification. Returns which backend delivered it."""
    try:
        asyncio.run(_send_native(title, message))
        return "native"
    except Exception as exc:  # any failure here should not kill the watcher
        log.warning("Native notification failed (%s); using osascript", exc)
    _send_osascript(title, message)
    return "osascript"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    backend = notify("Gameline test", "If you can see this, notifications work.")
    print("Delivered via:", backend)
