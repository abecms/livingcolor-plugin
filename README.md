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
