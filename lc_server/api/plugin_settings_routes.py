"""LivingColor plugin-level settings API."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from delivery_runtime.api.schemas import BillingConfigPayload
from lc_server.env_loader import prepare_delivery_agent_environment
from lc_server.integrations.plugin_billing import (
    load_plugin_billing_settings,
    persist_plugin_billing_settings,
)
from lc_server.integrations.plugin_secrets import (
    load_stripe_secret_key,
    persist_stripe_secret_key,
    redact_secret,
    stripe_secret_key_configured,
)

router = APIRouter(tags=["settings"])


class PluginSettingsResponse(BaseModel):
    stripeSecretConfigured: bool = False
    stripeSecretKeyPreview: str | None = None
    billing: BillingConfigPayload = Field(default_factory=BillingConfigPayload)


class PluginSettingsUpdateRequest(BaseModel):
    stripeSecretKey: str | None = Field(default=None)
    billing: BillingConfigPayload | None = None


def _billing_payload() -> BillingConfigPayload:
    billing = load_plugin_billing_settings()
    return BillingConfigPayload(
        stripeCustomerId=billing.stripe_customer_id,
        dailyRateCents=billing.daily_rate_cents,
        currency=billing.currency,
        invoiceMode=billing.invoice_mode,
        approvalRequired=billing.approval_required,
        maxInvoiceCents=billing.max_invoice_cents,
    )


@router.get("/plugin-settings", response_model=PluginSettingsResponse)
def get_plugin_settings() -> PluginSettingsResponse:
    prepare_delivery_agent_environment()
    key = load_stripe_secret_key()
    return PluginSettingsResponse(
        stripeSecretConfigured=bool(key),
        stripeSecretKeyPreview=redact_secret(key) or None,
        billing=_billing_payload(),
    )


@router.put("/plugin-settings", response_model=PluginSettingsResponse)
@router.post("/plugin-settings", response_model=PluginSettingsResponse)
def update_plugin_settings(body: PluginSettingsUpdateRequest) -> PluginSettingsResponse:
    if body.stripeSecretKey is not None:
        persist_stripe_secret_key(body.stripeSecretKey)
    if body.billing is not None:
        persist_plugin_billing_settings(
            stripe_customer_id=body.billing.stripeCustomerId,
            daily_rate_cents=body.billing.dailyRateCents,
            currency=body.billing.currency,
            invoice_mode=body.billing.invoiceMode,
            approval_required=body.billing.approvalRequired,
            max_invoice_cents=body.billing.maxInvoiceCents,
        )
    prepare_delivery_agent_environment()
    key = load_stripe_secret_key()
    return PluginSettingsResponse(
        stripeSecretConfigured=stripe_secret_key_configured(),
        stripeSecretKeyPreview=redact_secret(key) or None,
        billing=_billing_payload(),
    )


# Stale dashboard bundles rewrite /api/settings → /api/plugins/livingcolor/settings.
legacy_router = APIRouter(tags=["settings"])


@legacy_router.get("/settings", response_model=PluginSettingsResponse)
def get_plugin_settings_legacy() -> PluginSettingsResponse:
    return get_plugin_settings()


@legacy_router.put("/settings", response_model=PluginSettingsResponse)
@legacy_router.post("/settings", response_model=PluginSettingsResponse)
def update_plugin_settings_legacy(body: PluginSettingsUpdateRequest) -> PluginSettingsResponse:
    return update_plugin_settings(body)
