#!/usr/bin/env bash
# Single cloud entrypoint: provision credentials, bootstrap Hermes, verify integrations.
# Safe to re-run. Never prints secret values.
#
# Usage:
#   A) Credentials already in os.environ (Automation Secrets):
#        ./scripts/cloud-start.sh
#   B) Pipe KEY=VALUE lines from the automation prompt (stdin):
#        ./scripts/cloud-start.sh <<'CREDS'
#        JIRA_URL=...
#        JIRA_API_TOKEN=...
#        GITHUB_TOKEN=...
#        CREDS
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${HOME}/.local/bin:${PATH}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

unset LIVINGCOLOR_SHADOW_MODE
export LIVINGCOLOR_SYNC_ORCHESTRATOR="${LIVINGCOLOR_SYNC_ORCHESTRATOR:-1}"
export LIVINGCOLOR_DEVELOPER_BACKEND="${LIVINGCOLOR_DEVELOPER_BACKEND:-heuristic}"
export LIVINGCOLOR_PLANNER_BACKEND="${LIVINGCOLOR_PLANNER_BACKEND:-heuristic}"
export LIVINGCOLOR_ANALYST_BACKEND="${LIVINGCOLOR_ANALYST_BACKEND:-heuristic}"
export LIVINGCOLOR_PUBLISHER_BACKEND="${LIVINGCOLOR_PUBLISHER_BACKEND:-heuristic}"
export LIVINGCOLOR_SPRINT_REPORTER_BACKEND="${LIVINGCOLOR_SPRINT_REPORTER_BACKEND:-heuristic}"
export LIVINGCOLOR_SPRINT_BILLING_BACKEND="${LIVINGCOLOR_SPRINT_BILLING_BACKEND:-heuristic}"

log() { echo "[cloud-start] $*"; }

# 1) Existing ~/.hermes/livingcolor/.env from a prior step in this run
# shellcheck disable=SC1091
source "${ROOT}/scripts/cloud-load-credentials.sh"

# 2) Fresh credentials piped on stdin (agent extracts values from the prompt)
if [ ! -t 0 ]; then
  log "Writing credentials from stdin to ~/.hermes/livingcolor/.env"
  python3 "${ROOT}/scripts/cloud_write_credentials.py"
  # shellcheck disable=SC1091
  source "${ROOT}/scripts/cloud-load-credentials.sh"
fi

# 3) Hydrate + MCP provision (also loads .env inside Python for API handlers)
log "Hydrating credentials and provisioning MCP from environment"
python3 -m lc_server.integrations.mcp_env_bootstrap

missing_required=0
for key in JIRA_URL JIRA_API_TOKEN GITHUB_TOKEN; do
  if [ -z "${!key:-}" ] && [ "${key}" = "GITHUB_TOKEN" ] && [ -n "${GH_TOKEN:-}" ]; then
    export GITHUB_TOKEN="${GH_TOKEN}"
  fi
  if [ -z "${!key:-}" ]; then
    log "${key}=missing (required for TVP workflow)"
    missing_required=$((missing_required + 1))
  else
    log "${key}=configured"
  fi
done

if [ "${missing_required}" -gt 0 ]; then
  log "ERROR: ${missing_required} required credential(s) missing."
  log "Pipe KEY=VALUE lines on stdin or configure Cursor Automation Secrets."
  exit 1
fi

# 4) Hermes + LivingColor plugin + dashboard (re-runs MCP bootstrap with loaded env)
"${ROOT}/scripts/cloud-bootstrap.sh"

log "Cloud start complete — proceed with workflow FRT phases B–H"
log "Run: python3 scripts/cloud-workflow-frt.py  (preferred) or ./scripts/cloud-workflow-frt.sh"
