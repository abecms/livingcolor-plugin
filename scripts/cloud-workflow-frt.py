#!/usr/bin/env python3
"""TVP delivery workflow FRT via Hermes-mounted LivingColor API.

Never prints secret values. Writes summary to /tmp/lc-frt-summary.json
and evidence to /tmp/lc-frt-evidence.jsonl.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load credentials from ~/.hermes/livingcolor/.env
from lc_server.integrations.mcp_env_bootstrap import hydrate_cloud_credentials

hydrate_cloud_credentials()

PORT = int(os.environ.get("HERMES_PORT", "9119"))
BASE = f"http://127.0.0.1:{PORT}/api/plugins/livingcolor"
TOKEN = os.environ.get("HERMES_DASHBOARD_SESSION_TOKEN", "cloud-agent-session-token")
EVIDENCE = Path("/tmp/lc-frt-evidence.jsonl")
SUMMARY = Path("/tmp/lc-frt-summary.json")
APPROVER = "cloud-agent:test"


def log(msg: str) -> None:
    print(f"[workflow-frt] {msg}", flush=True)


def record(entry: dict[str, Any]) -> None:
    with EVIDENCE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    prefix: str = "/delivery",
) -> tuple[int, Any]:
    url = f"{BASE}{prefix}{path}"
    data = None
    headers = {
        "X-Hermes-Session-Token": TOKEN,
        "X-LC-Project-Key": "TVP",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read().decode("utf-8")
            code = resp.status
    except urllib.error.HTTPError as exc:
        code = exc.code
        raw = exc.read().decode("utf-8", errors="replace")
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {"raw": raw[:500]}
    record({"method": method, "path": path, "http": code, "body_preview": raw[:500]})
    return code, parsed


def curl_probe(url: str, headers: dict[str, str] | None = None, *, max_bytes: int = 500) -> tuple[int, str]:
    hdrs = headers or {}
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read(max_bytes).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(200).decode("utf-8", errors="replace")


def wait_for_gate_or_complete(wo_id: str, timeout_s: int = 600) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last: dict[str, Any] = {}
    while time.time() < deadline:
        _, last = request("GET", f"/work-orders/{wo_id}")
        status = last.get("status", "")
        gates = last.get("gates") or []
        pending = next(
            (g for g in gates if g.get("status") in ("pending", "awaiting_approval", "open")),
            None,
        )
        if pending:
            return last
        if status in ("completed", "failed"):
            return last
        request("POST", f"/work-orders/{wo_id}/resume", {})
        time.sleep(2)
    return last


def main() -> int:
    EVIDENCE.write_text("", encoding="utf-8")
    summary: dict[str, Any] = {
        "phases": {},
        "jira_key": "",
        "work_order_id": "",
        "sandbox_pr_url": "",
        "branch": "",
        "final_status": "",
    }

    log("Phase B: setup-automation")
    code, setup = request("POST", "/projects/TVP/setup-automation", {})
    summary["phases"]["setup"] = code == 200
    log(f"setup-automation HTTP {code}")

    log("Phase C: integration probes")
    jcode, jconn = request("POST", "/connect", {}, prefix="/jira")
    log(f"jira connect HTTP {jcode}")

    jira_url = os.environ.get("JIRA_URL", "")
    jira_user = os.environ.get("JIRA_USERNAME", "")
    jira_token = os.environ.get("JIRA_API_TOKEN", "")
    import base64

    auth = base64.b64encode(f"{jira_user}:{jira_token}".encode()).decode()
    jira_http, _ = curl_probe(
        f"{jira_url}/rest/api/3/project/TVP",
        {"Authorization": f"Basic {auth}", "Accept": "application/json"},
    )
    gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")
    gh_http, _ = curl_probe(
        "https://api.github.com/repos/abecms/tv5mondeplus-front",
        {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"},
    )
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    stripe_http, stripe_body = curl_probe(
        "https://api.stripe.com/v1/balance",
        {"Authorization": f"Bearer {stripe_key}"},
        max_bytes=4096,
    )
    stripe_live = "unknown"
    try:
        stripe_live = str(json.loads(stripe_body).get("livemode", "unknown"))
    except Exception:
        pass
    stripe_test_mode = stripe_http == 200 and stripe_live in ("False", "false", "0")
    log(f"Jira={jira_http} GitHub={gh_http} Stripe={stripe_http} livemode={stripe_live}")
    summary["phases"]["integrations"] = jira_http == 200 and gh_http == 200 and jcode == 200

    log("Phase D: readiness scan")
    code, scan = request("POST", "/readiness/scan", {"projectKey": "TVP"})
    log(f"readiness scan HTTP {code}")

    log("Phase D3: promote readiness ticket")
    _, ready_list = request("GET", "/readiness?projectKey=TVP&status=ready")
    items = ready_list.get("items") or []
    ready = [x for x in items if x.get("readinessStatus") == "ready" and not x.get("promotedWorkOrderId")]
    if not ready:
        ready = [x for x in items if x.get("readinessStatus") == "ready"]
    if not ready:
        log("ERROR: no ready readiness record")
        summary["phases"]["readiness"] = False
        SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return 1
    record_row = ready[0]
    record_id = record_row["id"]
    jira_key = record_row.get("jiraKey", "")
    summary["jira_key"] = jira_key
    log(f"selected {record_id} jira={jira_key}")

    ecode, _ = request(
        "PATCH",
        f"/tickets/{jira_key}/estimation",
        {"estimatedDays": 1.0, "complexity": "Medium", "confidence": 0.8},
    )
    log(f"ticket estimation HTTP {ecode}")

    acode, sel = request("PUT", "/sprint/selection", {"append": [jira_key]})
    log(f"sprint selection append HTTP {acode} tickets={len((sel or {}).get('tickets') or [])}")

    log("Phase D4: sprint reset (repopulate tickets, before promote)")
    rcode, reset = request("POST", "/sprint/reset", {"repopulateTickets": True})
    sprint_name = str((reset or {}).get("sprintName") or "")
    ticket_count = len((reset or {}).get("tickets") or [])
    log(f"sprint reset HTTP {rcode} sprint={sprint_name} tickets={ticket_count}")
    summary["phases"]["settings"] = rcode == 200 and bool(sprint_name)

    pcode, promote = request("POST", f"/readiness/{record_id}/promote", {"actor": APPROVER})
    wo = promote.get("workOrder") or {}
    wo_id = wo.get("id") or promote.get("workOrderId") or promote.get("id", "")
    if not wo_id:
        # Ticket may already be promoted — reuse existing WO
        _, wo_list = request("GET", "/work-orders")
        for item in wo_list.get("items") or []:
            if item.get("jiraKey") == jira_key or item.get("readinessId") == record_id:
                wo_id = item.get("id", "")
                break
    summary["work_order_id"] = wo_id
    log(f"promote HTTP {pcode} wo={wo_id}")
    summary["phases"]["readiness"] = pcode in (200, 201) and bool(wo_id)

    log("Phase E: gate approvals")
    gate_count = 0
    if not wo_id:
        log("ERROR: no work order id")
        summary["phases"]["readiness"] = False
        SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return 1
    for _ in range(20):
        wo = wait_for_gate_or_complete(wo_id, timeout_s=30)
        status = wo.get("status", "")
        gates = wo.get("gates") or []
        pending = next(
            (g for g in gates if g.get("status") in ("pending", "awaiting_approval", "open")),
            None,
        )
        if not pending:
            if status in ("completed", "failed"):
                break
            continue
        gate_id = pending["id"]
        gate_type = pending.get("gateType") or pending.get("type", "")
        log(f"approving gate {gate_id} type={gate_type}")
        acode, _ = request(
            "POST",
            f"/gates/{gate_id}/approve",
            {"approvedBy": APPROVER},
        )
        gate_count += 1
        if acode not in (200, 201):
            log(f"gate approve failed HTTP {acode}")
            break
        time.sleep(1)

    log("Phase F: delivery execution")
    final = wait_for_gate_or_complete(wo_id, timeout_s=600)
    final_status = final.get("status", "")
    summary["final_status"] = final_status
    pr_url = ""
    branch = ""
    nodes = final.get("graphNodes") or final.get("nodes") or []
    for node in nodes:
        out = node.get("output") or node.get("payload") or {}
        pr_url = pr_url or out.get("prUrl") or out.get("pullRequestUrl") or out.get("mrUrl") or out.get("reviewRequestUrl") or ""
        branch = branch or out.get("branch") or out.get("deliveryBranch") or ""
    summary["sandbox_pr_url"] = pr_url
    summary["branch"] = branch
    log(f"final status={final_status} pr={pr_url} branch={branch}")
    summary["phases"]["gates"] = gate_count >= 1
    summary["phases"]["delivery"] = final_status == "completed" and bool(pr_url)

    log("Phase G: sprint report")
    srcode, sr = request("POST", "/sprint/report?force=true", {})
    sr_status = str(sr.get("status") or "")
    sr_reason = str(sr.get("reason") or sr.get("error") or "")
    log(f"sprint report HTTP {srcode} status={sr_status} reason={sr_reason[:120]}")
    summary["sprint_report"] = {
        "http": srcode,
        "status": sr_status,
        "reason": sr_reason,
        "invoiceId": sr.get("invoiceId"),
        "billingStatus": sr.get("billingStatus"),
    }
    summary["phases"]["sprint_report"] = (
        srcode == 200
        and sr_status not in ("skipped",)
        and sr_reason != "no_active_sprint"
    )

    log("Phase H: stripe billing via sprint report")
    invoice_id = sr.get("invoiceId")
    billing_status = str(sr.get("billingStatus") or "")
    summary["stripe"] = {
        "balance_probe": stripe_test_mode,
        "invoiceId": invoice_id,
        "billingStatus": billing_status,
    }
    summary["phases"]["stripe"] = stripe_test_mode and bool(
        invoice_id or billing_status in ("draft_created", "created", "pending_approval", "skipped")
    )

    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(f"FRT complete — summary at {SUMMARY}")
    core_ok = summary["phases"].get("delivery") and summary["phases"].get("readiness")
    return 0 if core_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
