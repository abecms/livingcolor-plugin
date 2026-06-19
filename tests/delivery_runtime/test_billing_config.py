"""Tests for project-level sprint billing configuration."""

from __future__ import annotations

from delivery_runtime.automation.config import load_delivery_automation_config
from delivery_runtime.readiness.project_settings import (
    BillingSettings,
    load_project_billing_settings,
    persist_project_billing_settings,
)


def test_billing_config_defaults_are_safe(_isolate_hermes_home):
    config = load_delivery_automation_config(project_key="BN")

    assert config.billing.stripe_customer_id is None
    assert config.billing.daily_rate_cents is None
    assert config.billing.currency == "eur"
    assert config.billing.invoice_mode == "draft"
    assert config.billing.approval_required is False
    assert config.billing.max_invoice_cents is None


def test_project_billing_settings_round_trip(_isolate_hermes_home):
    saved = persist_project_billing_settings(
        project_key="BN",
        stripe_customer_id="cus_123",
        daily_rate_cents=80000,
        currency="EUR",
        invoice_mode="finalize",
        approval_required=True,
        max_invoice_cents=500000,
    )

    assert saved == BillingSettings(
        stripe_customer_id="cus_123",
        daily_rate_cents=80000,
        currency="eur",
        invoice_mode="finalize",
        approval_required=True,
        max_invoice_cents=500000,
    )

    loaded = load_project_billing_settings("BN")
    assert loaded == saved

    config = load_delivery_automation_config(project_key="BN")
    assert config.billing == saved
