import json
import subprocess

import pytest

from gameline.llm import claude_cli


def fake_run(stdout):
    return lambda args, timeout: subprocess.CompletedProcess(args, 0, stdout=json.dumps(stdout), stderr="")


def test_structured_output_is_returned(monkeypatch):
    monkeypatch.setattr(claude_cli, "_run", fake_run({"is_error": False, "structured_output": {"effort_hours": 3}}))
    assert claude_cli.ClaudeCLILLM().complete_json("s", "p", {}) == {"effort_hours": 3}


def test_expired_login_is_flagged_as_auth_error(monkeypatch):
    monkeypatch.setattr(
        claude_cli, "_run",
        fake_run({"is_error": True, "result": "Failed to authenticate: OAuth session expired"}),
    )
    with pytest.raises(claude_cli.ClaudeCLIError) as err:
        claude_cli.ClaudeCLILLM().complete_json("s", "p", {})
    assert err.value.auth


def test_subprocess_env_drops_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert "ANTHROPIC_API_KEY" not in claude_cli._env()
