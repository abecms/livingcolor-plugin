# Sprint Stripe Invoice Design

## Goal

Add end-of-sprint Stripe invoice generation to LivingColor so Hermes can close a sprint, build a client-ready invoice from delivered work, create or finalize it in Stripe, and include the hosted invoice URL in the sprint report.

This is designed for the Hermes Agent Accelerated Business Hackathon story: an autonomous delivery agent should not only plan and execute work, but also turn completed operations into billable business output.

## Scope

In scope:

- Generate one Stripe invoice per published sprint report and project.
- Build invoice content with an LLM-backed Hermes billing agent.
- Bill only tickets delivered during the sprint.
- Compute amounts from delivered ticket estimates and a configured daily rate.
- Validate the LLM proposal with deterministic guardrails before any Stripe write.
- Store invoice metadata in sprint memory for deduplication and reporting.
- Include the Stripe `hosted_invoice_url` in the end-of-sprint report.
- Document how Hermes payments skills fit into the billing workflow and safety model.

Out of scope for the first implementation:

- Subscription billing.
- Usage-based metering with Metronome.
- Multi-customer split invoices for one sprint.
- Automatic tax registration or tax liability decisions.
- Editing invoices from the Mission Control UI after creation.
- Charging cards directly outside the Stripe invoice flow.

## Existing Context

LivingColor already has a sprint report path:

- `delivery_runtime/pm_inbox/sprint_report.py` builds a sprint snapshot, composes a retrospective through `HermesSprintReporterAgent`, sends it to Hermes messaging, and records `lastSprintReportKey`.
- `delivery_runtime/pm_inbox/sprint_reset.py` calls `maybe_publish_sprint_report_before_reset()` before rolling the sprint forward.
- `delivery_runtime/api/routes.py` exposes `POST /sprint/report`.
- `delivery_runtime/api/schemas.py` returns `SprintReportResponse`.
- The sprint report deduplication key is `sprint_number:sprint_end_date`.

The invoice feature should extend this path rather than create a separate end-of-sprint workflow.

## User Decisions

- The output should be a real Stripe invoice, not a mock link or Checkout-only payment link.
- The amount should be based on delivered tickets: `estimatedDays * dailyRate`.
- Each project should map explicitly to a configured Stripe customer ID.
- Invoice creation should happen when the sprint report is published.
- The LLM must participate in constructing the invoice.
- Hermes payments skills should be considered part of the agent capability and safety story.

## Architecture

The sprint report flow becomes:

```text
Sprint snapshot
-> Hermes Sprint Billing Agent
-> LLM invoice proposal JSON
-> deterministic billing validator
-> Stripe Billing invoice creation/finalization
-> hosted_invoice_url
-> enriched sprint report snapshot
-> Hermes Sprint Reporter Agent
-> messaging channel
```

The LLM builds the invoice proposal. The backend validates and executes it.

The LLM is responsible for:

- Selecting clear line-item descriptions.
- Grouping delivered tickets into sensible invoice lines when appropriate.
- Writing a concise invoice memo.
- Explaining warnings when data is incomplete.
- Producing structured JSON that can be validated.

The deterministic backend is responsible for:

- Selecting the allowed delivered ticket set.
- Computing expected amounts.
- Rejecting invented or inconsistent ticket keys.
- Enforcing limits and approval rules.
- Calling Stripe.
- Persisting deduplication metadata.

The LLM should not receive Stripe secret keys and should not call Stripe directly for the first implementation.

## Hermes Payments Skills

Hermes payments skills should be installed and documented for the hackathon environment:

```bash
hermes skills install official/payments/stripe-projects
hermes skills install official/payments/mpp-agent
hermes skills install official/payments/stripe-link-cli
```

Their role in this design:

- `stripe-projects` can support provisioning or verifying supporting SaaS resources for the demo environment.
- `mpp-agent` can let Hermes use pay-per-call APIs if the delivery workflow needs them.
- `stripe-link-cli` can let Hermes buy services on the open web when the agent needs operational resources.

These skills do not appear to be the primary API for issuing a B2B customer invoice. Stripe invoice creation should use a dedicated Stripe Billing integration unless Hermes adds an invoice-specific skill. The design should still follow the payments skills safety model:

- Primary credentials stay out of agent transcripts.
- Agent actions have configurable limits.
- Human approval gates are available for sensitive actions.
- One-time credentials are cleaned up after use.
- Every billing attempt is audited.

## Configuration

Add project-level billing configuration to the existing delivery automation config model:

- `stripeCustomerId`: Stripe customer ID for the project.
- `billingDailyRateCents`: daily delivery rate in minor currency units.
- `billingCurrency`: invoice currency, defaulting to `eur`.
- `billingInvoiceMode`: `draft` or `finalize`, defaulting to `draft`; finalization requires explicit project opt-in.
- `billingApprovalRequired`: whether the system should stop at draft creation and return `pending_approval` instead of finalizing.
- `billingMaxInvoiceCents`: hard safety cap for a sprint invoice.

Stripe credentials must not be stored in project automation files or prompts. Use environment configuration or a Hermes-managed credential mechanism. The billing agent should only receive non-secret identifiers and business configuration.

## Invoice Proposal Contract

The Hermes Sprint Billing Agent should return a structured proposal similar to:

```json
{
  "currency": "eur",
  "customerId": "cus_example",
  "lineItems": [
    {
      "description": "Delivered BN-123: Improve sprint readiness analysis",
      "ticketKeys": ["BN-123"],
      "quantityDays": 2.5,
      "unitAmountCents": 80000
    }
  ],
  "memo": "Sprint 12 delivery invoice",
  "warnings": []
}
```

The prompt must instruct the agent to output only JSON and to use only data from the sprint billing snapshot.

The billing snapshot should include:

- Project key and project name.
- Sprint number, name, start date, and end date.
- Delivered ticket keys.
- Delivered ticket titles.
- Estimated days per delivered ticket.
- Configured daily rate and currency.
- Stripe customer ID.
- Safety limits.
- Any missing-estimate warnings already detected by the backend.

## Guardrails

The validator must reject a proposal if:

- A line references a ticket that was not delivered in the sprint.
- A delivered ticket is billed more than once.
- A delivered ticket with a known estimate is omitted without an explicit allowed reason.
- `quantityDays` differs from the expected estimate or grouped estimate sum.
- `unitAmountCents` differs from the configured daily rate.
- Currency differs from the configured currency.
- Customer ID differs from the configured customer ID.
- Any line amount is negative or zero.
- The total exceeds `billingMaxInvoiceCents`.
- Required billing config is missing.
- The same sprint report deduplication key already has a finalized invoice.

If any delivered ticket is missing an estimate, the first implementation must skip Stripe invoice creation and let the sprint report publish with an invoice warning. The LLM must never invent billable quantities.

## Stripe Billing Integration

Create a small integration layer owned by the server side under `lc_server/integrations/stripe_billing.py`.

The integration should:

- Initialize Stripe with the latest Stripe SDK/API version available in the project environment.
- Prefer restricted API keys for production usage.
- Create invoice items from validated line items.
- Create an invoice for the configured customer.
- Finalize the invoice only when `billingInvoiceMode == "finalize"` and `billingApprovalRequired` is false.
- Return invoice ID, status, total, currency, hosted invoice URL, and PDF URL when available.

Do not pass `payment_method_types` in Stripe API calls.

For the default draft-first rollout, the report should include the invoice URL if Stripe returns one; if not, it should include a clear "invoice draft created" status with the invoice ID. When `billingApprovalRequired` is true, the created draft invoice should be returned with `billingStatus == "pending_approval"`.

## Sprint Memory

Store invoice metadata in sprint memory using the same deduplication key as the report:

```json
{
  "lastSprintInvoiceKey": "12:2026-06-30",
  "lastSprintInvoiceId": "in_example",
  "lastSprintInvoiceUrl": "https://invoice.stripe.com/example",
  "lastSprintInvoicePdfUrl": "https://pay.stripe.com/invoice/example/pdf",
  "lastSprintInvoiceStatus": "open",
  "lastSprintInvoiceTotalCents": 240000,
  "lastSprintInvoiceCurrency": "eur"
}
```

If `publish_sprint_report(force=True)` is called for a sprint that already has invoice metadata, it should reuse the existing invoice metadata by default instead of creating a duplicate invoice. A future explicit "regenerate invoice" command can be designed separately.

## Events

Add audit events for billing:

- `SPRINT_INVOICE_PROPOSED`: LLM proposal was generated.
- `SPRINT_INVOICE_CREATED`: Stripe invoice was created or finalized.
- `SPRINT_INVOICE_SKIPPED`: invoice creation was skipped because config or estimates were missing.
- `SPRINT_INVOICE_FAILED`: billing failed after the report flow started.

Events must include non-secret metadata only:

- Project key.
- Sprint report deduplication key.
- Invoice ID when available.
- Invoice status.
- Total and currency.
- Error class/message when safe.

## Error Handling

The sprint report should still be publishable when billing fails. The report snapshot should include a billing status such as:

- `created`
- `draft_created`
- `skipped`
- `failed`
- `pending_approval`
- `already_exists`

The reporter prompt should instruct Hermes to include the invoice link when available, or a short factual warning when billing did not complete.

Stripe failures should not mark `lastSprintReportKey` unless the message was successfully delivered. Invoice creation and report publication are related but not the same success condition.

## API Surface

The first implementation can keep the existing API:

- `POST /sprint/report?force=false`

`SprintReportResponse` should be extended with optional billing fields:

- `invoiceUrl`
- `invoiceId`
- `invoiceStatus`
- `invoiceTotalCents`
- `invoiceCurrency`
- `billingStatus`
- `billingWarning`

A separate endpoint is not required for the first version.

## Testing Plan

Unit tests should cover:

- Sprint billing snapshot includes only delivered sprint tickets.
- Missing billing config skips invoice creation with a clear status.
- Billing agent mock returns a valid proposal.
- Validator accepts a valid proposal.
- Validator rejects unknown tickets.
- Validator rejects duplicate ticket billing.
- Validator rejects arbitrary amounts.
- Validator rejects total above `billingMaxInvoiceCents`.
- Stripe integration mock returns `hosted_invoice_url`.
- Sprint memory stores invoice metadata.
- Re-publishing the same sprint reuses existing invoice metadata.
- Stripe failure still allows the sprint report to publish with a billing warning.
- The sprint reporter prompt includes invoice URL/status in the snapshot.

Targeted test files:

- `tests/delivery_runtime/test_sprint_report.py`
- `tests/delivery_runtime/test_sprint_invoice.py`
- `tests/lc_server/test_stripe_billing.py`
- `tests/lc_server/test_hermes_sprint_billing_agent.py`

## Rollout

1. Add billing config fields with safe defaults and no behavior change when unset.
2. Add the LLM billing proposal contract and validator with mocked agent tests.
3. Add Stripe Billing integration behind config and tests with a mocked Stripe client.
4. Enrich sprint report snapshot with billing result.
5. Update reporter prompt/tests so the invoice link appears in the final message.
6. Document Hermes payments skill installation for the hackathon demo.
