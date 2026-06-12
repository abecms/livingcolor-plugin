# Delivery Runtime (`delivery_runtime/`)

> Parent: [`../AGENTS.md`](../AGENTS.md) · Server host: [`../livingcolor_server/AGENTS.md`](../livingcolor_server/AGENTS.md) · Spec: [`../docs/superpowers/specs/2026-06-09-autonomous-delivery-platform-design.md`](../docs/superpowers/specs/2026-06-09-autonomous-delivery-platform-design.md)

Instructions for AI assistants working on the **LivingColor Autonomous Delivery Platform** domain layer.

## Scope

**Owns:**

- Work Orders (primary product entity)
- Delivery Readiness Queue (A+ intake)
- Execution graphs, gates, events
- SQLite persistence under `~/.livingcolor/` (`runtime.db`, `project_mapping.yaml`)
- REST API at `/api/delivery/*` (routes only — server wires dependencies)
- Orchestration loop and agent bridge **protocol**

**Does not own:**

- Desktop Mission Control UI → `apps/desktop/src/app/delivery/`
- Hermes agent loop or MCP transport → `livingcolor_server/`, `agent/`, `tools/`
- Legacy PM dashboard → `apps/desktop/src/app/dashboard/`

## Load-bearing entry points

| Path | Role |
| --- | --- |
| `persistence/db.py` | SQLite schema + connections |
| `readiness/service.py` | Readiness queue queries |
| `work_orders/service.py` | Work Order queries |
| `events/store.py` | Append-only audit trail |
| `api/routes.py` | FastAPI router |
| `api/deps.py` | Server-injected service dependencies |
| `orchestration/engine.py` | Scheduler (Phase 2+) |
| `agent_bridge/protocol.py` | `AgentRuntimeBridge` protocol |
| `agents/schema.py` | `AgentManifest` schema and validation |
| `agents/paths.py` | Per-project manifest paths under `~/.livingcolor/projects/{KEY}/agents/` |
| `agents/registry.py` | `AgentManifestRegistry` — load/cache manifests and `automation.yaml` state |

## Invariants

- Delivery Runtime is **Hermes-free** — no imports from `hermes_cli`, `tools`, or `agent`.
- LivingColor Server owns integrations and agent runtime adapters.
- Events are append-only — never UPDATE or DELETE audit rows.
- Readiness analysis must not mutate Jira or create Work Orders automatically in MVP.
- Work Orders are created only via explicit human promotion (`POST /readiness/{id}/promote`).
- Gates pause orchestration; Jira writes happen only after human gate approval: the Original Estimate write-back fires at `analysis_plan` (Gate 1) approval (best-effort, shadow-mode-aware, never blocking); all other Jira mutations remain post-Gate 3.
- Agent runtime is replaceable via `AgentRuntimeBridge` — implementations live in `livingcolor_server/agent_bridge/`.

## FAST DEV mode

During active delivery implementation (workspace confinement, patch quality, MR draft prep):

```bash
export LIVINGCOLOR_FAST_DEV=true
scripts/run_fast_dev_smoke.sh
```

- **Do run:** targeted unit tests for touched modules, smoke suite above.
- **Do not run by default:** BN shadow evaluation, live/shadow corpus evaluation, full `tests/delivery_runtime/`, audit report generation.

Full BN evaluation is a **milestone gate** only — see [`../docs/superpowers/fast-dev-mode.md`](../docs/superpowers/fast-dev-mode.md).

Implementation: `delivery_runtime/fast_dev/`.

## Related docs

- [`../docs/superpowers/plans/2026-06-09-autonomous-delivery-platform.md`](../docs/superpowers/plans/2026-06-09-autonomous-delivery-platform.md)
- [`../apps/desktop/src/app/dashboard/AGENTS.md`](../apps/desktop/src/app/dashboard/AGENTS.md) — legacy PM dashboard
