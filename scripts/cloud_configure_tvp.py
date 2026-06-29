#!/usr/bin/env python3
"""Configure TVP cloud sandbox: Stripe billing from env + active sprint.

Reads STRIPE_TEST_CUSTOMER_ID and optional STRIPE_DAILY_RATE_CENTS from the
environment (or ~/.hermes/livingcolor/.env). Never prints secret values.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DEFAULT_DAILY_RATE_CENTS = 80_000
_DEFAULT_PROJECT_KEY = "TVP"


def _log(message: str) -> None:
    print(f"[cloud-configure-tvp] {message}")


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    from lc_server.integrations.mcp_env_bootstrap import hydrate_cloud_credentials

    hydrate_cloud_credentials()

    project_key = (os.environ.get("LIVINGCOLOR_TEST_PROJECT_KEY") or _DEFAULT_PROJECT_KEY).strip().upper()

    from delivery_runtime.persistence.db import init_db

    init_db()

    customer_id = (os.environ.get("STRIPE_TEST_CUSTOMER_ID") or "").strip()
    daily_rate_raw = (os.environ.get("STRIPE_DAILY_RATE_CENTS") or "").strip()
    daily_rate_cents = _DEFAULT_DAILY_RATE_CENTS
    if daily_rate_raw:
        try:
            daily_rate_cents = max(1, int(daily_rate_raw))
        except ValueError:
            _log(f"invalid STRIPE_DAILY_RATE_CENTS; using default {_DEFAULT_DAILY_RATE_CENTS}")

    if customer_id:
        from lc_server.integrations.plugin_billing import persist_plugin_billing_settings

        persist_plugin_billing_settings(
            stripe_customer_id=customer_id,
            daily_rate_cents=daily_rate_cents,
            currency="eur",
            invoice_mode="draft",
            approval_required=False,
            max_invoice_cents=None,
        )
        _log(f"stripe_customer_id=configured daily_rate_cents={daily_rate_cents}")
    else:
        _log("STRIPE_TEST_CUSTOMER_ID=missing (phase H billing will be blocked)")

    from delivery_runtime.pm_inbox.sprint_report import build_sprint_report_snapshot
    from delivery_runtime.pm_inbox.sprint_reset import reset_sprint

    if build_sprint_report_snapshot(project_key=project_key) is None:
        payload = reset_sprint(
            project_key=project_key,
            repopulate_tickets=False,
            publish_report=False,
        )
        sprint_name = payload.get("sprintName") or "LivingColor Sprint"
        _log(f"active_sprint=started project={project_key} name={sprint_name}")
    else:
        _log(f"active_sprint=already_set project={project_key}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
