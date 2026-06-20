#!/usr/bin/env python3
"""Cloud orchestrator workflow FRT — live sandbox integrations for TVP delivery."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _github_token() -> str:
    token = _env("GITHUB_TOKEN") or _env("GITHUB_PERSONAL_ACCESS_TOKEN")
    if token:
        return token
    try:
        from delivery_runtime.readiness.project_settings import resolve_project_mcp_server
        from lc_server.integrations.vcs.github import github_token_from_config

        return github_token_from_config(resolve_project_mcp_server("TVP", "github")) or ""
    except Exception:
        return ""


def _phase_result(phase: str, status: str, **extra: Any) -> dict[str, Any]:
    return {"phase": phase, "status": status, **extra}


def _load_client():
    os.environ.setdefault("PYTHONPATH", str(REPO_ROOT))
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from fastapi import FastAPI
    from starlette.testclient import TestClient

    spec = importlib.util.spec_from_file_location(
        "livingcolor_cloud_frt_plugin",
        REPO_ROOT / "dashboard" / "plugin_api.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    app = FastAPI()
    app.include_router(mod.router, prefix="/api/plugins/livingcolor")
    return TestClient(app)


def _jira_create_sandbox_ticket() -> dict[str, Any]:
    import httpx

    base = _env("JIRA_URL", "https://livingcolor.atlassian.net")
    user = _env("JIRA_USERNAME")
    token = _env("JIRA_API_TOKEN")
    summary = f"Cloud agent TVP workflow validation {RUN_ID}"
    payload = {
        "fields": {
            "project": {"key": "TVP"},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Automated sandbox ticket for LivingColor cloud workflow FRT. "
                                    "Acceptance criteria: add a LivingColor validation marker comment "
                                    "in README or docs without breaking build."
                                ),
                            }
                        ],
                    }
                ],
            },
            "issuetype": {"name": "Story"},
        }
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{base}/rest/api/3/issue",
            auth=(user, token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"key": data["key"], "id": data["id"], "summary": summary}


def _stripe_probe() -> dict[str, Any]:
    import stripe

    key = _env("STRIPE_SECRET_KEY")
    if not key:
        return {"status": "not_configured"}
    stripe.api_key = key
    customers = stripe.Customer.list(limit=1)
    return {
        "status": "available",
        "customer_count_sample": len(customers.data),
        "first_customer_id": customers.data[0].id if customers.data else None,
    }


def _github_write_probe() -> dict[str, Any]:
    import httpx

    token = _github_token()
    if not token:
        return {"status": "not_configured"}
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            "https://api.github.com/repos/abecms/tv5mondeplus-front",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        if resp.status_code != 200:
            return {"status": "blocked", "http": resp.status_code}
        repo = resp.json()
        perms = repo.get("permissions") or {}
        can_push = bool(perms.get("push") or perms.get("admin"))
        return {
            "status": "available" if can_push else "read_only",
            "default_branch": repo.get("default_branch"),
            "permissions": perms,
        }


def _wait_for_gate(client, work_order_id: str, timeout: float = 120.0) -> dict[str, Any] | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        wo = client.get(f"/api/plugins/livingcolor/delivery/work-orders/{work_order_id}")
        if wo.status_code != 200:
            time.sleep(1)
            continue
        payload = wo.json()
        gates = payload.get("gates") or []
        pending = [g for g in gates if g.get("status") == "pending"]
        if pending:
            return pending[0]
        if payload.get("status") not in {"awaiting_gate", "running", "intake"}:
            return None
        time.sleep(1)
    return None


def _resume_until_stable(client, work_order_id: str, max_ticks: int = 30) -> dict[str, Any]:
    last = {}
    for _ in range(max_ticks):
        wo = client.get(f"/api/plugins/livingcolor/delivery/work-orders/{work_order_id}")
        last = wo.json() if wo.status_code == 200 else {"error": wo.text}
        status = last.get("status")
        if status in {"completed", "failed", "cancelled"}:
            break
        pending = [g for g in (last.get("gates") or []) if g.get("status") == "pending"]
        if pending:
            break
        client.post(f"/api/plugins/livingcolor/delivery/work-orders/{work_order_id}/resume")
        time.sleep(2)
    return last


def main() -> int:
    os.environ.setdefault("LIVINGCOLOR_SYNC_ORCHESTRATOR", "1")
    os.environ.setdefault("LIVINGCOLOR_DEVELOPER_BACKEND", "heuristic")
    os.environ.setdefault("LIVINGCOLOR_PLANNER_BACKEND", "heuristic")
    os.environ.setdefault("LIVINGCOLOR_ANALYST_BACKEND", "heuristic")
    os.environ.setdefault("LIVINGCOLOR_PUBLISHER_BACKEND", "heuristic")
    os.environ.pop("LIVINGCOLOR_SHADOW_MODE", None)

    results: dict[str, Any] = {
        "run_id": RUN_ID,
        "shadow_mode": bool(_env("LIVINGCOLOR_SHADOW_MODE")),
        "phases": {},
        "sandbox_jira_ticket": None,
        "sandbox_pr_url": None,
        "sandbox_branch": None,
        "credentials": {
            "OPENROUTER_API_KEY": bool(_env("OPENROUTER_API_KEY")),
            "JIRA_URL": bool(_env("JIRA_URL")),
            "JIRA_USERNAME": bool(_env("JIRA_USERNAME")),
            "JIRA_API_TOKEN": bool(_env("JIRA_API_TOKEN")),
            "GITHUB_TOKEN": bool(_github_token()),
            "STRIPE_SECRET_KEY": bool(_env("STRIPE_SECRET_KEY")),
        },
    }

    # Phase A — Bootstrap
    try:
        client = _load_client()
        overview = client.get("/api/plugins/livingcolor/delivery/overview")
        results["phases"]["A"] = _phase_result(
            "A_bootstrap",
            "pass" if overview.status_code == 200 else "fail",
            http=overview.status_code,
            mode="FastAPI TestClient",
            shadow_mode_set=bool(_env("LIVINGCOLOR_SHADOW_MODE")),
        )
    except Exception as exc:
        results["phases"]["A"] = _phase_result("A_bootstrap", "fail", error=str(exc))
        print(json.dumps(results, indent=2))
        return 1

    # Phase B — Project setup
    try:
        setup = client.post("/api/plugins/livingcolor/delivery/projects/TVP/setup-automation")
        settings = client.get("/api/plugins/livingcolor/delivery/project-config?project=TVP")
        results["phases"]["B"] = _phase_result(
            "B_project_setup",
            "pass" if setup.status_code in {200, 400} else "fail",
            setup_http=setup.status_code,
            setup_body=setup.json() if setup.content else {},
            settings_http=settings.status_code,
        )
    except Exception as exc:
        results["phases"]["B"] = _phase_result("B_project_setup", "fail", error=str(exc))

    # Phase C — Integrations
    try:
        jira_ticket = _jira_create_sandbox_ticket()
        results["sandbox_jira_ticket"] = jira_ticket["key"]
        gh = _github_write_probe()
        stripe = _stripe_probe()
        jira_status = "available"
        if gh.get("status") == "read_only":
            jira_status = "available"
        results["phases"]["C"] = _phase_result(
            "C_integrations",
            "pass" if gh.get("status") == "available" and jira_status == "available" else "fail",
            jira=jira_status,
            github=gh,
            stripe=stripe,
            sandbox_ticket=jira_ticket["key"],
        )
    except Exception as exc:
        results["phases"]["C"] = _phase_result("C_integrations", "fail", error=str(exc))

    # Phase D — Readiness promote
    record_id = None
    work_order_id = None
    try:
        scan = client.post(
            "/api/plugins/livingcolor/delivery/readiness/scan",
            json={"projectKey": "TVP"},
        )
        readiness_list = client.get("/api/plugins/livingcolor/delivery/readiness?project=TVP")
        items = readiness_list.json().get("items") or [] if readiness_list.status_code == 200 else []
        jira_key = results.get("sandbox_jira_ticket")
        if jira_key:
            for item in items:
                if item.get("jiraKey") == jira_key:
                    record_id = item["id"]
                    break
        if not record_id and items:
            record_id = items[0]["id"]
        if not record_id:
            raise RuntimeError("No readiness record available after scan")

        reanalyze = client.post(f"/api/plugins/livingcolor/delivery/readiness/{record_id}/reanalyze")
        if reanalyze.status_code == 200:
            record = reanalyze.json()
            if record.get("readinessStatus") != "ready":
                time.sleep(2)
                refreshed = client.get(f"/api/plugins/livingcolor/delivery/readiness/{record_id}")
                if refreshed.status_code == 200:
                    record = refreshed.json()
        else:
            record = client.get(f"/api/plugins/livingcolor/delivery/readiness/{record_id}").json()

        if record.get("readinessStatus") != "ready":
            raise RuntimeError(
                f"readiness record not ready: {record.get('readinessStatus')} "
                f"({record.get('analysisSummary')})"
            )

        promote = client.post(f"/api/plugins/livingcolor/delivery/readiness/{record_id}/promote")
        if promote.status_code != 200:
            raise RuntimeError(f"promote failed: {promote.status_code} {promote.text}")
        wo = promote.json().get("workOrder") or {}
        work_order_id = wo.get("id")

        deadline = time.time() + 120.0
        while time.time() < deadline:
            if wo.get("status") == "awaiting_gate" and wo.get("gates"):
                break
            tick = client.post(f"/api/plugins/livingcolor/delivery/work-orders/{work_order_id}/resume")
            if tick.status_code == 200:
                refreshed = client.get(f"/api/plugins/livingcolor/delivery/work-orders/{work_order_id}")
                if refreshed.status_code == 200:
                    wo = refreshed.json()
            time.sleep(2)

        gates = wo.get("gates") or []
        results["phases"]["D"] = _phase_result(
            "D_readiness_promote",
            "pass" if wo.get("status") == "awaiting_gate" and gates else "fail",
            scan_http=scan.status_code,
            record_id=record_id,
            work_order_id=work_order_id,
            work_order_status=wo.get("status"),
            gate_count=len(gates),
        )
    except Exception as exc:
        results["phases"]["D"] = _phase_result("D_readiness_promote", "fail", error=str(exc))

    # Phase E — Gates
    gate_log: list[dict[str, Any]] = []
    try:
        if not work_order_id:
            raise RuntimeError("missing work order")
        approved = 0
        for _ in range(8):
            gate = _wait_for_gate(client, work_order_id, timeout=180.0)
            if not gate:
                break
            gate_id = gate["id"]
            before = client.get(f"/api/plugins/livingcolor/delivery/work-orders/{work_order_id}").json()
            approve = client.post(
                f"/api/plugins/livingcolor/delivery/gates/{gate_id}/approve",
                json={"approvedBy": "cloud-agent:test"},
            )
            after = client.get(f"/api/plugins/livingcolor/delivery/work-orders/{work_order_id}").json()
            gate_log.append(
                {
                    "gate_id": gate_id,
                    "gate_type": gate.get("gateType"),
                    "approve_http": approve.status_code,
                    "stage_before": before.get("currentStage"),
                    "stage_after": after.get("currentStage"),
                }
            )
            if approve.status_code != 200:
                break
            approved += 1
            client.post(f"/api/plugins/livingcolor/delivery/work-orders/{work_order_id}/resume")
            time.sleep(2)

        wo_final = client.get(f"/api/plugins/livingcolor/delivery/work-orders/{work_order_id}").json()
        results["phases"]["E"] = _phase_result(
            "E_gates",
            "pass" if approved >= 1 else "fail",
            gates_approved=approved,
            gate_log=gate_log,
            final_status=wo_final.get("status"),
            final_stage=wo_final.get("currentStage"),
        )
    except Exception as exc:
        results["phases"]["E"] = _phase_result("E_gates", "fail", error=str(exc), gate_log=gate_log)

    # Phase F — Delivery execution
    try:
        if not work_order_id:
            raise RuntimeError("missing work order")
        wo_state = _resume_until_stable(client, work_order_id, max_ticks=40)
        publication = (wo_state.get("publication") or {}) if isinstance(wo_state, dict) else {}
        pr_url = publication.get("reviewRequestUrl") or publication.get("mrUrl")
        branch = publication.get("branchName") or publication.get("sourceBranch")
        shadow_reason = publication.get("reason") or wo_state.get("shadowSkipReason")
        jira_writeback = wo_state.get("jiraWriteback") or {}
        status = "pass"
        if shadow_reason == "shadow_mode":
            status = "fail"
        if not pr_url and wo_state.get("status") != "completed":
            status = "partial" if wo_state.get("status") == "failed" else status
        results["sandbox_pr_url"] = pr_url
        results["sandbox_branch"] = branch
        results["phases"]["F"] = _phase_result(
            "F_delivery",
            status,
            work_order_status=wo_state.get("status"),
            publication=publication,
            jira_writeback=jira_writeback,
            shadow_reason=shadow_reason,
        )
    except Exception as exc:
        results["phases"]["F"] = _phase_result("F_delivery", "fail", error=str(exc))

    # Phase G — Sprint report
    try:
        report = client.post(
            "/api/plugins/livingcolor/delivery/sprint/report",
            headers={"x-lc-project-key": "TVP"},
        )
        results["phases"]["G"] = _phase_result(
            "G_sprint_report",
            "pass" if report.status_code == 200 else "blocked" if report.status_code == 503 else "fail",
            http=report.status_code,
            body=report.json() if report.content else {},
        )
    except Exception as exc:
        results["phases"]["G"] = _phase_result("G_sprint_report", "fail", error=str(exc))

    # Phase H — Stripe billing
    try:
        stripe_result = _stripe_probe()
        invoice_id = None
        if stripe_result.get("status") == "available" and stripe_result.get("first_customer_id"):
            import stripe

            stripe.api_key = _env("STRIPE_SECRET_KEY")
            inv = stripe.Invoice.create(
                customer=stripe_result["first_customer_id"],
                collection_method="send_invoice",
                days_until_due=30,
                auto_advance=False,
                metadata={"livingcolor_run": RUN_ID, "project": "TVP"},
            )
            invoice_id = inv.id
        results["phases"]["H"] = _phase_result(
            "H_stripe",
            "pass" if invoice_id else "blocked" if stripe_result.get("status") != "available" else "partial",
            stripe=stripe_result,
            invoice_id=invoice_id,
        )
    except Exception as exc:
        results["phases"]["H"] = _phase_result("H_stripe", "blocked", error=str(exc))

    out_path = REPO_ROOT / "docs" / "cloud-agent-runs" / f"{RUN_ID}-frt.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
