# LivingColor Server (`livingcolor_server/`)

> Parent: [`../AGENTS.md`](../AGENTS.md) · Delivery domain: [`../delivery_runtime/AGENTS.md`](../delivery_runtime/AGENTS.md)

The **LivingColor Server** is the delivery orchestration host. It owns execution,
persistence, and external integrations. The desktop app is Mission Control only.

## Scope

**Owns:**

- Server bootstrap and service wiring (`bootstrap.py`, `factory.py`)
- Jira readiness integration (`integrations/jira_readiness.py`)
- Agent runtime adapters (`agent_bridge/hermes_runtime.py`)
- Project automation provisioning (`provisioning/`)
- Future GitLab/Jira write integrations for delivery execution

**Does not own:**

- Delivery domain models and persistence → `delivery_runtime/`
- HTTP route definitions → `delivery_runtime/api/routes.py` (mounted by server host)
- Hermes agent loop internals → `agent/`, `run_agent.py`
- Desktop UI → `apps/desktop/src/app/delivery/`

## Architecture

```text
Desktop (Mission Control)
  ⇄ HTTP /api/delivery/*
LivingColor Server (this package)
  ⇄ delivery_runtime/
  ⇄ agent_bridge/ → Hermes (replaceable)
  ⇄ integrations/ → Jira MCP (via Hermes tooling today)
```

## Load-bearing entry points

| Path | Role |
| --- | --- |
| `bootstrap.py` | Wire `delivery_runtime.api.deps` at server startup |
| `factory.py` | Construct readiness/work-order/gate services |
| `integrations/jira_readiness.py` | Jira issue fetch for readiness scans |
| `agent_bridge/hermes_runtime.py` | Hermes-backed `AgentRuntimeBridge` |
| `agent_bridge/hermes_developer.py` | Hermes `AIAgent` loop for patch generation |
| `agent_bridge/hermes_analyst.py` | Hermes `AIAgent` loop for readiness analysis |
| `agent_bridge/developer_backend.py` | Selects Hermes vs heuristic developer backend |
| `provisioning/provisioner.py` | Writes per-project agent manifests and automation state |
| `provisioning/prerequisites.py` | Validates Jira/GitLab/MCP prerequisites before setup |
| `provisioning/gitlab_discovery.py` | Discovers GitLab repos for a Jira project key |
| `provisioning/template_renderer.py` | Renders bundled agent templates (`agent_templates/v1/`) |
| `provisioning/upgrade.py` | Auto-upgrades stale manifest template versions |

## Invariants

- Only this package (and deeper Hermes layers) may import `hermes_cli` or `tools` for delivery.
- `delivery_runtime/` must remain Hermes-free.
- Product data lives under `~/.livingcolor/` via `livingcolor_constants.get_livingcolor_home()`.

## Server host

During development the server runs inside `hermes_cli/web_server.py`, which calls
`bootstrap_livingcolor_server()` before mounting `/api/delivery/*`.

## Project automation provisioning

Provisioning is triggered via `POST /api/delivery/projects/{projectKey}/setup-automation`
(routes live in `delivery_runtime/api/routes.py`; execution is delegated here).

**Prerequisites** (checked by `provisioning/prerequisites.py`):

- Jira project mapping exists in `~/.livingcolor/project_mapping.yaml`
- Jira and GitLab MCP servers configured for the project
- GitLab discovery returns at least one repo (or a default repo is set)

On success, `ProjectAutomationProvisioner` writes:

```text
~/.livingcolor/projects/{PROJECT_KEY}/
  automation.yaml          # provisioned state (status, templateVersion, provisionedAt)
  agents/
    orchestrator.yaml        # AgentManifest for orchestrator role (declarative v1; not executed — see docs below)
    analyst.yaml             # AgentManifest for readiness analysis
    developer.yaml           # AgentManifest for patch generation
```

Manifest schema and registry live in `delivery_runtime/agents/` (Hermes-free).
Templates are bundled under `livingcolor_server/agent_templates/v1/`.

**Orchestrator vs OrchestrationEngine:** v1 workflow is driven by `OrchestrationEngine`
(Python), not the orchestrator manifest. Before building an LLM orchestrator, read
[`docs/delivery/orchestrator-llm-decision-guide.md`](../docs/delivery/orchestrator-llm-decision-guide.md).

**API surface:**

| Endpoint | Role |
| --- | --- |
| `POST /api/delivery/projects/{key}/setup-automation` | Provision manifests; `?force=true` re-renders |
| `GET /api/delivery/projects/{key}/automation` | Read provisioned state and per-role manifest summary |

Returns `400` with `{ error: "prerequisites_missing", missing: [...] }` when setup
cannot proceed. Returns `404` on GET when automation was never provisioned.

Agent bridges (`hermes_analyst.py`, `hermes_developer.py`) load manifests via
`AgentManifestRegistry` when automation is ready; they fall back to legacy
prompts when manifests are absent (backward compatibility).
