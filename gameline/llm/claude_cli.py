"""Claude subscription backend: runs the local Claude Code CLI in headless mode.

Uses whatever account `claude` is logged into, so estimates bill to that
Claude subscription instead of an API key. Personal use only: a consumer
subscription must not power an app shipped to other people, so the API
backend stays the default.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import EstimatorLLM

# Apps launched from Finder get a minimal PATH, so also look in the usual spots.
_CANDIDATES = [
    Path.home() / ".local/bin/claude",
    Path("/opt/homebrew/bin/claude"),
    Path("/usr/local/bin/claude"),
]

AUTH_HINTS = ("authenticate", "oauth", "log in", "login", "not logged")


class ClaudeCLIError(RuntimeError):
    def __init__(self, message: str, auth: bool = False) -> None:
        super().__init__(message)
        self.auth = auth


def find_claude() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    return next((str(p) for p in _CANDIDATES if p.exists()), None)


def _env() -> dict[str, str]:
    # Drop the API key so the CLI uses the subscription login, not API billing.
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def _run(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    exe = find_claude()
    if not exe:
        raise ClaudeCLIError("Claude Code isn't installed (no `claude` command found).")
    # Run from a temp dir so no project CLAUDE.md or settings leak into the call.
    return subprocess.run(
        [exe, *args], capture_output=True, text=True, timeout=timeout, cwd=tempfile.gettempdir(), env=_env()
    )


def _ask(prompt: str, system: str, extra: list[str], timeout: float) -> dict[str, Any]:
    proc = _run(
        ["-p", prompt, "--output-format", "json", "--system-prompt", system, "--tools", "",
         "--no-session-persistence", *extra],
        timeout,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ClaudeCLIError((proc.stderr or proc.stdout or "No output from claude").strip()[:300])
    if out.get("is_error"):
        message = str(out.get("result") or out.get("terminal_reason") or "Claude returned an error")
        auth = any(h in message.lower() for h in AUTH_HINTS)
        if auth:
            forget_status()  # the cached "logged in" is no longer true
        raise ClaudeCLIError(message, auth=auth)
    return out


class ClaudeCLILLM(EstimatorLLM):
    def __init__(self, model: str = "claude-opus-5-5", effort: str = "low", timeout: float = 120) -> None:
        self.model = model
        self.effort = effort
        self.timeout = timeout

    def complete_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        out = _ask(
            prompt,
            system,
            ["--json-schema", json.dumps(schema), "--model", self.model, "--effort", self.effort],
            self.timeout,
        )
        data = out.get("structured_output")
        if isinstance(data, dict):
            return data
        # Fall back to parsing the text result if structured output is missing.
        try:
            return json.loads(out.get("result", ""))
        except (TypeError, json.JSONDecodeError):
            raise ClaudeCLIError("Claude didn't return structured output")


# --- account status, for the Preferences page --------------------------------


@dataclass
class AccountStatus:
    installed: bool
    logged_in: bool = False
    working: bool | None = None  # None = not checked yet
    email: str = ""
    plan: str = ""
    message: str = ""

    @property
    def label(self) -> str:
        if not self.installed:
            return "Claude Code not installed"
        if not self.logged_in:
            return "Not logged in"
        who = self.email + (f" ({self.plan.title()})" if self.plan else "")
        if self.working is False:
            return f"Session expired · {who}" if "expired" in self.message.lower() else f"Login not working · {who}"
        return f"Logged in · {who}"

    @property
    def ok(self) -> bool:
        return self.installed and self.logged_in and self.working is not False


# --- cached status --------------------------------------------------------
# Checking runs the CLI (and a tiny test call), which is slow and can make
# macOS ask about folder access, so the result is remembered for a while.

CACHE_HOURS = 12


def _cache_file():
    from ..paths import data_dir

    return data_dir() / "claude_status.json"


def cached_status(max_age_hours: float = CACHE_HOURS) -> AccountStatus | None:
    """The last saved status if it's recent enough, else None."""
    import time

    try:
        data = json.loads(_cache_file().read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if time.time() - data.get("checked_at", 0) > max_age_hours * 3600:
        return None
    data.pop("checked_at", None)
    return AccountStatus(**data)


def save_status(status: AccountStatus) -> None:
    import time
    from dataclasses import asdict

    try:
        _cache_file().write_text(json.dumps({**asdict(status), "checked_at": time.time()}))
    except OSError:
        pass


def forget_status() -> None:
    """Drop the cached status (after login, logout, or a failed call)."""
    try:
        _cache_file().unlink()
    except OSError:
        pass


def account_status(verify: bool = True) -> AccountStatus:
    """Read `claude auth status`; with verify, also make a tiny real call,
    because a saved login can be expired while auth status still says logged in."""
    if not find_claude():
        return AccountStatus(installed=False)
    try:
        info = json.loads(_run(["auth", "status", "--json"], timeout=20).stdout or "{}")
    except (json.JSONDecodeError, subprocess.TimeoutExpired, ClaudeCLIError) as exc:
        return AccountStatus(installed=True, message=str(exc))
    status = AccountStatus(
        installed=True,
        logged_in=bool(info.get("loggedIn")),
        email=info.get("email", ""),
        plan=info.get("subscriptionType", ""),
    )
    if status.logged_in and verify:
        try:
            _ask("Reply with OK.", "Reply with OK.", ["--model", "haiku"], timeout=60)
            status.working = True
        except (ClaudeCLIError, subprocess.TimeoutExpired) as exc:
            status.working = False
            status.message = str(exc)
    if verify:
        save_status(status)
    return status


def open_login_terminal() -> None:
    """Open Terminal running `claude auth login`. The login flow is interactive
    (browser plus prompts), so it gets a real terminal instead of a hidden process."""
    exe = find_claude() or "claude"
    command = f"{exe} auth login --claudeai"
    script = f'tell application "Terminal"\n activate\n do script "{command}"\nend tell'
    subprocess.Popen(["osascript", "-e", script])


def logout() -> None:
    forget_status()
    _run(["auth", "logout"], timeout=30)
