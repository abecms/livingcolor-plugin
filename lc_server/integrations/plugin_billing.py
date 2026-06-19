"""Plugin-wide sprint billing settings persisted under ~/.hermes/livingcolor/billing.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from delivery_runtime.readiness.project_settings import (
    BillingSettings,
    _normalize_billing_currency,
    _normalize_invoice_mode,
    _normalize_optional_positive_int,
)


def _billing_config_path() -> Path:
    from lc_constants import ensure_livingcolor_home_layout

    return ensure_livingcolor_home_layout() / "billing.json"


def _billing_settings_from_map(billing_map: dict[str, Any]) -> BillingSettings:
    stripe_customer_id = str(
        billing_map.get("stripe_customer_id")
        or billing_map.get("stripeCustomerId")
        or ""
    ).strip()
    return BillingSettings(
        stripe_customer_id=stripe_customer_id or None,
        daily_rate_cents=_normalize_optional_positive_int(
            billing_map.get("daily_rate_cents") or billing_map.get("dailyRateCents")
        ),
        currency=_normalize_billing_currency(
            billing_map.get("currency") or billing_map.get("billingCurrency")
        ),
        invoice_mode=_normalize_invoice_mode(
            billing_map.get("invoice_mode") or billing_map.get("invoiceMode")
        ),
        approval_required=bool(
            billing_map.get("approval_required") or billing_map.get("approvalRequired") or False
        ),
        max_invoice_cents=_normalize_optional_positive_int(
            billing_map.get("max_invoice_cents") or billing_map.get("maxInvoiceCents")
        ),
    )


def _billing_settings_to_map(settings: BillingSettings) -> dict[str, Any]:
    return {
        "stripe_customer_id": settings.stripe_customer_id,
        "daily_rate_cents": settings.daily_rate_cents,
        "currency": settings.currency,
        "invoice_mode": settings.invoice_mode,
        "approval_required": settings.approval_required,
        "max_invoice_cents": settings.max_invoice_cents,
    }


def _has_billing_values(settings: BillingSettings) -> bool:
    return bool(
        settings.stripe_customer_id
        or settings.daily_rate_cents
        or settings.max_invoice_cents
    )


def _load_billing_from_project_mapping() -> BillingSettings | None:
    from delivery_runtime.readiness.project_settings import load_project_mapping

    mapping = load_project_mapping()
    if not isinstance(mapping, dict):
        return None

    for entry in mapping.values():
        if not isinstance(entry, dict):
            continue
        billing = entry.get("billing")
        if not isinstance(billing, dict):
            continue
        settings = _billing_settings_from_map(billing)
        if _has_billing_values(settings):
            return settings
    return None


def load_plugin_billing_settings() -> BillingSettings:
    path = _billing_config_path()
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        if isinstance(raw, dict):
            settings = _billing_settings_from_map(raw)
            if _has_billing_values(settings):
                return settings

    migrated = _load_billing_from_project_mapping()
    if migrated is not None:
        persist_plugin_billing_settings(
            stripe_customer_id=migrated.stripe_customer_id,
            daily_rate_cents=migrated.daily_rate_cents,
            currency=migrated.currency,
            invoice_mode=migrated.invoice_mode,
            approval_required=migrated.approval_required,
            max_invoice_cents=migrated.max_invoice_cents,
        )
        return migrated

    return BillingSettings()


def persist_plugin_billing_settings(
    *,
    stripe_customer_id: str | None,
    daily_rate_cents: int | None,
    currency: str = "eur",
    invoice_mode: str = "draft",
    approval_required: bool = False,
    max_invoice_cents: int | None = None,
) -> BillingSettings:
    settings = BillingSettings(
        stripe_customer_id=(stripe_customer_id or "").strip() or None,
        daily_rate_cents=_normalize_optional_positive_int(daily_rate_cents),
        currency=_normalize_billing_currency(currency),
        invoice_mode=_normalize_invoice_mode(invoice_mode),
        approval_required=bool(approval_required),
        max_invoice_cents=_normalize_optional_positive_int(max_invoice_cents),
    )

    path = _billing_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_billing_settings_to_map(settings), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return settings
