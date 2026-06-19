from __future__ import annotations

from pathlib import Path

from lc_server.integrations.project_chat_context import (
    livingcolor_project_chat_session_title,
    livingcolor_project_system_prompt,
    normalize_livingcolor_project_key,
    resolve_livingcolor_project_cwd,
    _session_title_matches_livingcolor_project,
)
from livingcolor_pm_tools import resolve_active_livingcolor_project_key


def test_normalize_livingcolor_project_key():
    assert normalize_livingcolor_project_key(" bn ") == "BN"
    assert normalize_livingcolor_project_key("") is None
    assert normalize_livingcolor_project_key(None) is None


def test_project_key_from_sidecar_channel():
    import lc_server.integrations.project_chat_context as module

    sidecar = "ws://127.0.0.1:9119/api/pub?token=abc&channel=lc-TVP-deadbeef"
    assert module._project_key_from_sidecar_url(sidecar) == "TVP"
    assert module._project_key_from_channel("lc-BN-1234") == "BN"
    assert module._project_key_from_sidecar_url("ws://127.0.0.1/api/pub?channel=plain-channel") is None


def test_resolve_pty_project_key_prefers_context_var():
    import lc_server.integrations.project_chat_context as module

    sidecar = "ws://127.0.0.1:9119/api/pub?channel=lc-BN-deadbeef"
    token = module._LC_PTY_PROJECT_KEY.set("TVP")
    try:
        assert module._resolve_pty_project_key(sidecar_url=sidecar) == "TVP"
    finally:
        module._LC_PTY_PROJECT_KEY.reset(token)

    assert module._resolve_pty_project_key(sidecar_url=sidecar) == "BN"


def test_livingcolor_project_system_prompt_names_project():
    prompt = livingcolor_project_system_prompt("tvp")
    assert "Jira project TVP" in prompt
    assert "livingcolor_get_delivery_context" in prompt
    assert "NOT a Kanban worker" in prompt
    assert "which project they are on" in prompt.lower()


def test_livingcolor_project_chat_session_title():
    assert livingcolor_project_chat_session_title("bn") == "LivingColor BN"


def test_session_title_matches_livingcolor_project(monkeypatch, tmp_path):
    import sys

    import lc_server.integrations.project_chat_context as module

    fake_db_path = tmp_path / "state.db"
    fake_db_path.write_text("", encoding="utf-8")

    class FakeDB:
        def __init__(self, db_path=None, read_only=False):
            assert Path(db_path) == fake_db_path

        def get_session(self, session_id: str):
            if session_id == "good":
                return {"id": "good"}
            if session_id == "bad":
                return {"id": "bad"}
            return None

        def get_session_title(self, session_id: str) -> str | None:
            if session_id == "good":
                return "LivingColor BN"
            return "Cron job BN tickets"

    monkeypatch.setattr(module, "livingcolor_pm_state_db_path", lambda: fake_db_path)
    monkeypatch.setitem(sys.modules, "hermes_state", type("hermes_state", (), {"SessionDB": FakeDB}))
    assert module._session_title_matches_livingcolor_project("good", "BN") is True
    assert module._session_title_matches_livingcolor_project("bad", "BN") is False
    assert module._session_title_matches_livingcolor_project("missing", "BN") is False


def test_resolve_livingcolor_chat_project_key_prefers_pty_env(monkeypatch):
    import lc_server.integrations.project_chat_context as module

    monkeypatch.delenv("HERMES_TUI_LIVINGCOLOR_PROJECT_KEY", raising=False)
    assert (
        module._resolve_livingcolor_chat_project_key(
            session={"livingcolor_project_key": "BN"},
            explicit=None,
        )
        == "BN"
    )

    monkeypatch.setenv("HERMES_TUI_LIVINGCOLOR_PROJECT_KEY", "TVP")
    assert (
        module._resolve_livingcolor_chat_project_key(
            session={"livingcolor_project_key": "BN"},
            explicit=None,
        )
        == "TVP"
    )


def test_resolve_active_livingcolor_project_key_from_env(monkeypatch):
    monkeypatch.setenv("HERMES_TUI_LIVINGCOLOR_PROJECT_KEY", "BN")
    assert resolve_active_livingcolor_project_key() == "BN"


def test_resolve_active_livingcolor_project_key_pm_chat_requires_env(monkeypatch):
    monkeypatch.delenv("HERMES_TUI_LIVINGCOLOR_PROJECT_KEY", raising=False)
    monkeypatch.setenv("HERMES_TUI_TOOLSETS", "livingcolor")
    import pytest

    with pytest.raises(ValueError, match="missing from the dashboard chat session"):
        resolve_active_livingcolor_project_key()


def test_apply_livingcolor_pty_env_pins_toolsets(monkeypatch):
    import lc_server.integrations.project_chat_context as module

    monkeypatch.setattr(module, "ensure_livingcolor_pm_profile", lambda: None)
    monkeypatch.setattr(module, "_livingcolor_resume_allowed", lambda *_args, **_kwargs: False)

    env: dict[str, str] = {}
    module._apply_livingcolor_pty_env(env, "BN", resume="stale-session")

    assert env["HERMES_TUI_LIVINGCOLOR_PROJECT_KEY"] == "BN"
    assert env["LIVINGCOLOR_PROJECT_KEY"] == "BN"
    assert env["HERMES_TUI_TOOLSETS"] == "livingcolor"
    assert env["HERMES_TUI_SKILLS"] == "livingcolor-pm"
    assert "HERMES_TUI_RESUME" not in env


def test_resolve_livingcolor_project_cwd_from_mapping(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    mapping = {"BN": {"default_repo": str(repo)}}

    monkeypatch.setattr(
        "delivery_runtime.readiness.project_mapping.load_project_mapping",
        lambda: mapping,
    )

    assert resolve_livingcolor_project_cwd("BN") == str(repo.resolve())
