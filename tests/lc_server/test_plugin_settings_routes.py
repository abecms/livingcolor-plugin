"""Tests for LivingColor plugin settings API."""

from __future__ import annotations


def _client():
    from delivery_http_client import delivery_api_client

    return delivery_api_client()


def test_plugin_settings_round_trip(_isolate_hermes_home, monkeypatch):
    from delivery_runtime.automation import config as automation_config
    import lc_constants

    hermes_home = _isolate_hermes_home
    lc_home = hermes_home / "livingcolor"
    lc_home.mkdir(parents=True)
    monkeypatch.setattr(lc_constants, "get_livingcolor_home", lambda: lc_home)
    monkeypatch.setattr(automation_config, "get_livingcolor_home", lambda: lc_home)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)

    client = _client()

    initial = client.get("/api/delivery/plugin-settings")
    assert initial.status_code == 200
    assert initial.json()["stripeSecretConfigured"] is False
    assert initial.json()["billing"]["stripeCustomerId"] is None

    updated = client.put(
        "/api/delivery/plugin-settings",
        json={
            "stripeSecretKey": "sk_test_settings_api",
            "billing": {
                "stripeCustomerId": "cus_123",
                "dailyRateCents": 80000,
                "currency": "eur",
                "invoiceMode": "draft",
                "approvalRequired": False,
                "maxInvoiceCents": 500000,
            },
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["stripeSecretConfigured"] is True
    assert payload["stripeSecretKeyPreview"].endswith("_api")
    assert payload["billing"]["stripeCustomerId"] == "cus_123"
    assert payload["billing"]["dailyRateCents"] == 80000

    loaded = client.get("/api/delivery/plugin-settings")
    assert loaded.status_code == 200
    assert loaded.json()["stripeSecretConfigured"] is True
    assert "sk_test" in (loaded.json()["stripeSecretKeyPreview"] or "")
    assert loaded.json()["billing"]["stripeCustomerId"] == "cus_123"


def test_plugin_settings_legacy_root_path(_isolate_hermes_home, monkeypatch):
    from delivery_runtime.automation import config as automation_config
    import lc_constants
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dashboard.plugin_api import router as plugin_router

    hermes_home = _isolate_hermes_home
    lc_home = hermes_home / "livingcolor"
    lc_home.mkdir(parents=True)
    monkeypatch.setattr(lc_constants, "get_livingcolor_home", lambda: lc_home)
    monkeypatch.setattr(automation_config, "get_livingcolor_home", lambda: lc_home)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)

    app = FastAPI()
    app.include_router(plugin_router, prefix="/api/plugins/livingcolor")
    client = TestClient(app)

    updated = client.put(
        "/api/plugins/livingcolor/settings",
        json={
            "billing": {
                "stripeCustomerId": "cus_legacy",
                "dailyRateCents": 10000,
                "currency": "eur",
                "invoiceMode": "draft",
                "approvalRequired": True,
                "maxInvoiceCents": None,
            },
        },
    )
    assert updated.status_code == 200
    assert updated.json()["billing"]["stripeCustomerId"] == "cus_legacy"
