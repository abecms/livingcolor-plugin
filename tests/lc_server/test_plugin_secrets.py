"""Tests for LivingColor plugin secret storage."""

from __future__ import annotations

from lc_server.integrations.plugin_secrets import (
    load_stripe_secret_key,
    persist_stripe_secret_key,
    redact_secret,
    stripe_secret_key_configured,
)


def test_redact_secret_masks_middle():
    assert redact_secret("sk_test_1234567890abcdef") == "sk_test...cdef"


def test_persist_stripe_secret_key_writes_livingcolor_env(_isolate_hermes_home, monkeypatch):
    from delivery_runtime.automation import config as automation_config
    import lc_constants

    hermes_home = _isolate_hermes_home
    lc_home = hermes_home / "livingcolor"
    lc_home.mkdir(parents=True)
    monkeypatch.setattr(lc_constants, "get_livingcolor_home", lambda: lc_home)
    monkeypatch.setattr(automation_config, "get_livingcolor_home", lambda: lc_home)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)

    persist_stripe_secret_key("sk_test_plugin_config")
    env_path = lc_home / ".env"
    assert env_path.is_file()
    assert "STRIPE_SECRET_KEY=sk_test_plugin_config" in env_path.read_text(encoding="utf-8")
    assert load_stripe_secret_key() == "sk_test_plugin_config"
    assert stripe_secret_key_configured() is True


def test_persist_stripe_secret_key_clear_removes_value(_isolate_hermes_home, monkeypatch):
    from delivery_runtime.automation import config as automation_config
    import lc_constants

    hermes_home = _isolate_hermes_home
    lc_home = hermes_home / "livingcolor"
    lc_home.mkdir(parents=True)
    monkeypatch.setattr(lc_constants, "get_livingcolor_home", lambda: lc_home)
    monkeypatch.setattr(automation_config, "get_livingcolor_home", lambda: lc_home)

    persist_stripe_secret_key("sk_test_plugin_config")
    persist_stripe_secret_key("")
    assert "STRIPE_SECRET_KEY=" not in (lc_home / ".env").read_text(encoding="utf-8")
    assert stripe_secret_key_configured() is False
