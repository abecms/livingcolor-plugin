"""Stripe Billing adapter for sprint invoices."""

from __future__ import annotations

from typing import Any


class StripeBillingError(RuntimeError):
    """Raised when Stripe invoice creation fails."""


def _resolve_stripe_api_key() -> str:
    from lc_server.env_loader import prepare_delivery_agent_environment
    from lc_server.integrations.plugin_secrets import load_stripe_secret_key

    prepare_delivery_agent_environment()
    value = load_stripe_secret_key()
    if value:
        return value
    raise StripeBillingError(
        "Stripe API key is not configured (set it in LivingColor plugin settings or STRIPE_SECRET_KEY)"
    )


def _default_stripe_client() -> Any:
    try:
        import stripe
    except ImportError as exc:
        raise StripeBillingError("Stripe SDK is not installed in this environment") from exc
    stripe.api_key = _resolve_stripe_api_key()
    return stripe


def _invoice_payload(invoice: Any) -> dict[str, Any]:
    getter = invoice.get if isinstance(invoice, dict) else lambda key, default=None: getattr(invoice, key, default)
    return {
        "invoiceId": getter("id"),
        "invoiceStatus": getter("status"),
        "invoiceTotalCents": getter("total"),
        "invoiceCurrency": getter("currency"),
        "invoiceUrl": getter("hosted_invoice_url"),
        "invoicePdfUrl": getter("invoice_pdf"),
    }


def create_sprint_invoice(
    validated_invoice: dict[str, Any],
    *,
    invoice_mode: str,
    stripe_client: Any | None = None,
) -> dict[str, Any]:
    from lc_server.env_loader import prepare_delivery_agent_environment

    prepare_delivery_agent_environment()
    client = stripe_client or _default_stripe_client()
    customer_id = str(validated_invoice["customerId"])
    currency = str(validated_invoice["currency"])

    for line in validated_invoice.get("lineItems") or []:
        client.InvoiceItem.create(
            customer=customer_id,
            currency=currency,
            amount=int(line["amountCents"]),
            description=str(line["description"]),
            metadata={"ticketKeys": ",".join(line.get("ticketKeys") or [])},
        )

    invoice = client.Invoice.create(
        customer=customer_id,
        description=str(validated_invoice.get("memo") or ""),
        auto_advance=False,
        pending_invoice_items_behavior="include",
        metadata={"source": "livingcolor_sprint_report"},
    )

    if invoice_mode == "finalize":
        invoice_id = invoice["id"] if isinstance(invoice, dict) else invoice.id
        invoice = client.Invoice.finalize_invoice(invoice_id)
    else:
        invoice_id = invoice["id"] if isinstance(invoice, dict) else invoice.id
        invoice = client.Invoice.retrieve(invoice_id)

    return _invoice_payload(invoice)
