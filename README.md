# LivingColor — Hermes Agent Plugin

Autonomous delivery platform (Work Orders, readiness queue, human-approved
gates) plus a Jira PM dashboard, packaged as a Hermes plugin.

## Install

    git clone <repo-url> ~/.hermes/plugins/livingcolor
    hermes plugins enable livingcolor

Restart the Hermes dashboard. A "LivingColor" tab appears; the API mounts at
`/api/plugins/livingcolor/`. No build step required (`dashboard/dist/` ships
prebuilt).

## Prerequisites

- Jira and GitLab MCP servers configured in Hermes
- A project mapping in `~/.hermes/livingcolor/project_mapping.yaml`

## LLM provider

LivingColor uses whatever provider and model you configured in Hermes
(`~/.hermes/config.yaml` → `model.provider` / `model.default`). The plugin
does not bundle or override OpenRouter credentials.

## MCP (Jira / GitLab)

Configure MCP servers yourself via Hermes (`hermes mcp` or dashboard MCP
settings). LivingColor only reads connection status and scopes per-project
configs after you explicitly save credentials in Project → Integrations.

## Workspaces

**Personal (default)** — 100% local. Delivery state lives in
`~/.hermes/livingcolor/runtime.db`. No account required; choose **Continue
locally** on the welcome screen.

**Team** — shared projects via Firebase (`livingcolor-app`). Choose **Sign in
to collaborate** on the welcome screen (Google or email). Team data is
accessed through `https://api-livingcolor.visualq.ai`; users never install a
Firebase service account locally.

Public Firebase web client config is embedded in the plugin (safe to expose).
Security is enforced by Firebase Auth, Firestore rules, and verified ID tokens
on the cloud API.

## Agent surfaces

- Slash command: `/delivery status|scan <PROJECT>|queue|promote <id>|gates`
- Model toolset `livingcolor`: `delivery_overview`, `delivery_scan_readiness`,
  `delivery_promote`, `delivery_gate_decision`, `delivery_work_order_status`

## Data

Everything lives under `~/.hermes/livingcolor/` (follows `HERMES_HOME`).

## Development

    uv venv .venv && source .venv/bin/activate
    uv pip install -e /path/to/hermes-agent pytest httpx
    pytest tests -x -q
    cd ui && npm install && npx vite build   # rebuilds dashboard/dist

## Provenance

One-shot port of the LivingColor product from the agent-lc fork
(spec: agent-lc `docs/superpowers/specs/2026-06-12-livingcolor-hermes-plugin-design.md`).
Upstream platform: Hermes Agent (MIT, Nous Research attribution preserved).
