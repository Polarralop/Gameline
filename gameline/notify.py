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
import sys

from desktop_notifier import DesktopNotifier

log = logging.getLogger(__name__)

APP_NAME = "Gameline"
_notifier: DesktopNotifier | None = None


# macOS hides banners from the frontmost app unless its notification delegate
# says otherwise. Once Gameline has its own window it is often frontmost (for
# example right after clicking "Launch fake game"), so opt into banners anyway.
_UN_PRESENT_SOUND, _UN_PRESENT_LIST, _UN_PRESENT_BANNER = 1 << 1, 1 << 3, 1 << 4

if sys.platform == "darwin":
    from desktop_notifier.backends.macos import NotificationCenterDelegate
    from rubicon.objc import objc_method
    from rubicon.objc.runtime import objc_block, objc_id

    class _ForegroundDelegate(NotificationCenterDelegate):  # type: ignore[misc, valid-type]
        @objc_method
        def userNotificationCenter_willPresentNotification_withCompletionHandler_(
            self, center: objc_id, notification: objc_id, completion_handler: objc_block
        ) -> None:
            completion_handler(_UN_PRESENT_BANNER | _UN_PRESENT_LIST | _UN_PRESENT_SOUND)

    def _show_in_foreground(notifier: DesktopNotifier) -> None:
        backend = getattr(notifier, "_backend", None)
        if backend is None or not hasattr(backend, "nc"):
            return
        delegate = _ForegroundDelegate.alloc().init()
        delegate.implementation = backend
        backend.nc_delegate = delegate  # keep a strong reference
        backend.nc.delegate = delegate

else:

    def _show_in_foreground(notifier: DesktopNotifier) -> None:
        pass


def _get() -> DesktopNotifier:
    global _notifier
    if _notifier is None:
        _notifier = DesktopNotifier(app_name=APP_NAME)
        try:
            _show_in_foreground(_notifier)
        except Exception:
            log.exception("Could not enable foreground banners")
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
    log.info("Notify: %s | %s", title, message.replace("\n", " / "))
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
