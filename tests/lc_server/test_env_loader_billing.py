"""Tests for LivingColor env template bootstrap."""

from __future__ import annotations

from lc_server.env_loader import ensure_livingcolor_env_template, stripe_api_key_configured


def test_ensure_livingcolor_env_template_creates_file(_isolate_hermes_home, monkeypatch):
    from delivery_runtime.automation import config as automation_config
    import lc_constants

    hermes_home = _isolate_hermes_home
    lc_home = hermes_home / "livingcolor"
    lc_home.mkdir(parents=True)
    monkeypatch.setattr(lc_constants, "get_livingcolor_home", lambda: lc_home)
    monkeypatch.setattr(automation_config, "get_livingcolor_home", lambda: lc_home)

    path = ensure_livingcolor_env_template()
    assert path.is_file()
    assert "STRIPE_SECRET_KEY" in path.read_text(encoding="utf-8")

    # Idempotent
    ensure_livingcolor_env_template()
    assert path.read_text(encoding="utf-8").count("STRIPE_SECRET_KEY") == 1


def test_stripe_api_key_configured_reads_hermes_env(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    assert stripe_api_key_configured() is True
