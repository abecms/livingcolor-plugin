"""Tests for LivingColor .env loading precedence."""

from __future__ import annotations

import os


def test_livingcolor_dotenv_overrides_stale_hermes_key(monkeypatch, tmp_path):
    hermes_home = tmp_path / "hermes"
    livingcolor_home = hermes_home / "livingcolor"
    livingcolor_home.mkdir(parents=True)
    (livingcolor_home / ".env").write_text("OPENROUTER_API_KEY=sk-or-v1-livingcolor-key\n", encoding="utf-8")

    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    os.environ["OPENROUTER_API_KEY"] = "bad-key"

    from lc_server.env_loader import load_livingcolor_dotenv

    load_livingcolor_dotenv(override=True)

    assert os.environ["OPENROUTER_API_KEY"] == "sk-or-v1-livingcolor-key"
