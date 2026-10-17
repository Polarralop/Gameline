"""API keys that users paste into Gameline (Preferences or onboarding).

Saved to the .env file in the per-user data folder, which the LLM backends
already read, and applied to the running app straight away.
"""

from __future__ import annotations

import os

from dotenv import set_key, unset_key

from .paths import data_dir

KEY_VARS = {"gemini": "GEMINI_API_KEY", "claude": "ANTHROPIC_API_KEY"}
KEY_URLS = {
    "gemini": "https://aistudio.google.com/apikey",
    "claude": "https://console.anthropic.com/settings/keys",
}


def needs_key(backend: str) -> bool:
    return backend in KEY_VARS


def get_key(backend: str) -> str:
    return os.getenv(KEY_VARS[backend], "").strip() if needs_key(backend) else ""


def masked(backend: str) -> str:
    """'Saved key ending in a1b2', or '' when there is no key."""
    key = get_key(backend)
    return f"Saved key ending in {key[-4:]}" if key else ""


def save_key(backend: str, value: str) -> None:
    var = KEY_VARS[backend]
    value = value.strip()
    env = data_dir() / ".env"
    env.touch(exist_ok=True)
    if value:
        set_key(str(env), var, value, quote_mode="never")
        os.environ[var] = value
    else:
        unset_key(str(env), var)
        os.environ.pop(var, None)
