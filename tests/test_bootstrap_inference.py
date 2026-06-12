# tests/test_bootstrap_inference.py
"""Bootstrap must not pin OpenRouter or overwrite Hermes model config."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_bootstrap_does_not_call_openrouter_helpers(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    (tmp_path / "hermes").mkdir()
    (tmp_path / "hermes" / "config.yaml").write_text(
        "model:\n  provider: anthropic\n  default: claude-sonnet-4-20250514\n",
        encoding="utf-8",
    )

    with patch("lc_server.bundled_credentials.ensure_bundled_openrouter_credentials") as openrouter_mock, patch(
        "lc_server.model_defaults.ensure_livingcolor_fixed_model"
    ) as model_mock:
        from lc_server.bootstrap import bootstrap_livingcolor_server

        bootstrap_livingcolor_server()

    openrouter_mock.assert_not_called()
    model_mock.assert_not_called()

    saved = (tmp_path / "hermes" / "config.yaml").read_text(encoding="utf-8")
    assert "anthropic" in saved
    assert "claude-sonnet-4-20250514" in saved
