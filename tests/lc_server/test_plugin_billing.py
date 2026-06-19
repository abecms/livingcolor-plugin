"""Tests for plugin-level sprint billing configuration."""

from __future__ import annotations

from lc_server.integrations.plugin_billing import (
    load_plugin_billing_settings,
    persist_plugin_billing_settings,
)


def test_plugin_billing_settings_round_trip(_isolate_hermes_home):
    saved = persist_plugin_billing_settings(
        stripe_customer_id="cus_123",
        daily_rate_cents=80000,
        currency="EUR",
        invoice_mode="finalize",
        approval_required=True,
        max_invoice_cents=500000,
    )

    assert saved.stripe_customer_id == "cus_123"
    assert saved.daily_rate_cents == 80000
    assert saved.currency == "eur"
    assert saved.invoice_mode == "finalize"
    assert saved.approval_required is True
    assert saved.max_invoice_cents == 500000

    loaded = load_plugin_billing_settings()
    assert loaded == saved
