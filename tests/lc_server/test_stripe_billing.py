"""Tests for Stripe invoice creation adapter."""

from __future__ import annotations

from lc_server.integrations.stripe_billing import create_sprint_invoice


class FakeStripeClient:
    def __init__(self):
        self.invoice_items: list[dict] = []
        self.created_invoices: list[dict] = []
        self.finalized: list[str] = []

    class InvoiceItem:
        @staticmethod
        def create(**kwargs):
            raise AssertionError("InvoiceItem.create must be patched")

    class Invoice:
        @staticmethod
        def create(**kwargs):
            raise AssertionError("Invoice.create must be patched")

        @staticmethod
        def finalize_invoice(invoice_id):
            raise AssertionError("Invoice.finalize_invoice must be patched")


def test_create_sprint_invoice_creates_items_and_draft():
    fake = FakeStripeClient()

    def create_item(**kwargs):
        fake.invoice_items.append(kwargs)
        return {"id": f"ii_{len(fake.invoice_items)}"}

    def create_invoice(**kwargs):
        fake.created_invoices.append(kwargs)
        return {
            "id": "in_123",
            "status": "draft",
            "total": 0,
            "currency": "eur",
        }

    def retrieve_invoice(invoice_id):
        return {
            "id": invoice_id,
            "status": "draft",
            "total": 160000,
            "currency": "eur",
            "hosted_invoice_url": "https://invoice.stripe.com/in_123",
            "invoice_pdf": "https://invoice.stripe.com/in_123.pdf",
        }

    fake.InvoiceItem.create = staticmethod(create_item)
    fake.Invoice.create = staticmethod(create_invoice)
    fake.Invoice.retrieve = staticmethod(retrieve_invoice)

    result = create_sprint_invoice(
        {
            "customerId": "cus_123",
            "currency": "eur",
            "lineItems": [
                {
                    "description": "Delivered BN-1",
                    "quantityDays": 2.0,
                    "unitAmountCents": 80000,
                    "amountCents": 160000,
                    "ticketKeys": ["BN-1"],
                }
            ],
            "memo": "Sprint 12 delivery invoice",
            "totalCents": 160000,
        },
        invoice_mode="draft",
        stripe_client=fake,
    )

    assert fake.invoice_items == [
        {
            "customer": "cus_123",
            "currency": "eur",
            "amount": 160000,
            "description": "Delivered BN-1",
            "metadata": {"ticketKeys": "BN-1"},
        }
    ]
    assert fake.created_invoices[0]["customer"] == "cus_123"
    assert fake.created_invoices[0]["description"] == "Sprint 12 delivery invoice"
    assert fake.created_invoices[0]["pending_invoice_items_behavior"] == "include"
    assert result["invoiceId"] == "in_123"
    assert result["invoiceStatus"] == "draft"
    assert result["invoiceUrl"] == "https://invoice.stripe.com/in_123"


def test_create_sprint_invoice_finalizes_when_requested():
    fake = FakeStripeClient()
    fake.InvoiceItem.create = staticmethod(lambda **kwargs: {"id": "ii_123"})
    fake.Invoice.create = staticmethod(
        lambda **kwargs: {"id": "in_123", "status": "draft", "total": 0, "currency": "eur"}
    )
    fake.Invoice.retrieve = staticmethod(
        lambda invoice_id: {
            "id": invoice_id,
            "status": "draft",
            "total": 160000,
            "currency": "eur",
            "hosted_invoice_url": "https://invoice.stripe.com/in_123",
            "invoice_pdf": "https://invoice.stripe.com/in_123.pdf",
        }
    )
    fake.Invoice.finalize_invoice = staticmethod(
        lambda invoice_id: {
            "id": invoice_id,
            "status": "open",
            "total": 160000,
            "currency": "eur",
            "hosted_invoice_url": "https://invoice.stripe.com/in_123",
            "invoice_pdf": "https://invoice.stripe.com/in_123.pdf",
        }
    )

    result = create_sprint_invoice(
        {
            "customerId": "cus_123",
            "currency": "eur",
            "lineItems": [
                {
                    "description": "Delivered BN-1",
                    "quantityDays": 2.0,
                    "unitAmountCents": 80000,
                    "amountCents": 160000,
                    "ticketKeys": ["BN-1"],
                }
            ],
            "memo": "Sprint 12 delivery invoice",
            "totalCents": 160000,
        },
        invoice_mode="finalize",
        stripe_client=fake,
    )

    assert result["invoiceStatus"] == "open"
    assert result["invoiceUrl"] == "https://invoice.stripe.com/in_123"
