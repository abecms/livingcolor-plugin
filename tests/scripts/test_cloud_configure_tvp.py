"""Tests for TVP cloud configuration script."""

from __future__ import annotations

from delivery_runtime.pm_inbox.sprint_report import build_sprint_report_snapshot


def test_cloud_configure_tvp_starts_sprint_and_billing(_isolate_hermes_home, monkeypatch):
    monkeypatch.setenv("STRIPE_TEST_CUSTOMER_ID", "cus_test_cloud")
    monkeypatch.setenv("LIVINGCOLOR_TEST_PROJECT_KEY", "TVP")

    from scripts import cloud_configure_tvp as module

    assert module.main() == 0

    from lc_server.integrations.plugin_billing import load_plugin_billing_settings

    billing = load_plugin_billing_settings()
    assert billing.stripe_customer_id == "cus_test_cloud"
    assert billing.daily_rate_cents == 80_000

    snapshot = build_sprint_report_snapshot(project_key="TVP")
    assert snapshot is not None
    assert int(snapshot.get("sprintNumber") or 0) >= 1
