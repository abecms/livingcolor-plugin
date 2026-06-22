#!/usr/bin/env bash
# Bootstrap Hermes + LivingColor for Cursor Cloud TVP workflow FRT.
# Idempotent: safe to re-run. Never prints secret values.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${HOME}/.local/bin:${PATH}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

# Credentials from Automation Secrets or agent-written ~/.hermes/livingcolor/.env
# shellcheck disable=SC1091
source "${ROOT}/scripts/cloud-load-credentials.sh"

HERMES_PORT="${HERMES_PORT:-9119}"
SESSION_TOKEN="${HERMES_DASHBOARD_SESSION_TOKEN:-cloud-agent-session-token}"
LOG_FILE="${HERMES_DASHBOARD_LOG:-/tmp/hermes-dashboard.log}"

log() { echo "[cloud-bootstrap] $*"; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "ERROR: missing command: $1"
    exit 1
  fi
}

install_hermes() {
  if command -v hermes >/dev/null 2>&1; then
    log "Hermes already installed: $(hermes --version 2>/dev/null | head -1)"
    return 0
  fi
  log "Installing hermes-agent..."
  pip install --user hermes-agent mcp
}

install_uvx() {
  if command -v uvx >/dev/null 2>&1; then
    log "uvx already installed"
    return 0
  fi
  log "Installing uv (provides uvx for mcp-atlassian)..."
  pip install --user uv
}

sync_plugin() {
  log "Syncing LivingColor plugin from ${ROOT}"
  "${ROOT}/scripts/sync-hermes-plugin.sh"
  hermes plugins enable livingcolor 2>/dev/null || true
}

write_project_mapping() {
  local mapping_dir="${HOME}/.hermes/livingcolor"
  mkdir -p "${mapping_dir}"
  cat > "${mapping_dir}/project_mapping.yaml" <<'EOF'
TVP:
  jira_project_key: TVP
  vcs: github
  default_repo: github.com/abecms/tv5mondeplus-front
  integration_branch: preprod
  communication_language: fr
  sprint:
    duration_days: 7
    capacity_days: 2.0
EOF
  log "Wrote ${mapping_dir}/project_mapping.yaml"
}

configure_mcp_from_env() {
  log "Provisioning Hermes MCP entries from environment (no values logged)"
  python3 -m lc_server.integrations.mcp_env_bootstrap
}

write_livingcolor_env() {
  local env_path="${HOME}/.hermes/livingcolor/.env"
  mkdir -p "$(dirname "${env_path}")"
  local tmp
  tmp="$(mktemp)"
  : >"${tmp}"
  for key in JIRA_URL JIRA_USERNAME JIRA_API_TOKEN GITHUB_TOKEN GH_TOKEN STRIPE_SECRET_KEY \
    STRIPE_TEST_CUSTOMER_ID OPENROUTER_API_KEY GITLAB_PERSONAL_ACCESS_TOKEN GITLAB_API_URL \
    LIVINGCOLOR_TEST_PROJECT_KEY LIVINGCOLOR_TEST_GITHUB_REPO; do
    if [ -n "${!key:-}" ]; then
      printf '%s=%s\n' "${key}" "${!key}" >>"${tmp}"
    fi
  done
  if [ -s "${tmp}" ]; then
    python3 "${ROOT}/scripts/cloud_write_credentials.py" <"${tmp}" >/dev/null
    log "Synced in-process credentials to ${env_path}"
  fi
  rm -f "${tmp}"
}

start_dashboard() {
  local already_up=0
  if curl -sf -H "X-Hermes-Session-Token: ${SESSION_TOKEN}" \
    "http://127.0.0.1:${HERMES_PORT}/api/plugins/livingcolor/delivery/overview" >/dev/null 2>&1; then
    log "Dashboard already responding on port ${HERMES_PORT}"
    already_up=1
  fi

  if [ "${already_up}" = "1" ]; then
    return 0
  fi

  log "Starting Hermes dashboard on port ${HERMES_PORT}"
  export HERMES_DASHBOARD_SESSION_TOKEN="${SESSION_TOKEN}"
  unset LIVINGCOLOR_SHADOW_MODE
  export LIVINGCOLOR_SYNC_ORCHESTRATOR=1
  export LIVINGCOLOR_DEVELOPER_BACKEND=heuristic
  export LIVINGCOLOR_PLANNER_BACKEND=heuristic
  export LIVINGCOLOR_ANALYST_BACKEND=heuristic
  export LIVINGCOLOR_PUBLISHER_BACKEND=heuristic
  export LIVINGCOLOR_SPRINT_REPORTER_BACKEND=heuristic

  nohup hermes dashboard --skip-build --no-open --port "${HERMES_PORT}" >"${LOG_FILE}" 2>&1 &
  for _ in $(seq 1 30); do
    if curl -sf -H "X-Hermes-Session-Token: ${SESSION_TOKEN}" \
      "http://127.0.0.1:${HERMES_PORT}/api/plugins/livingcolor/delivery/overview" >/dev/null 2>&1; then
      log "Dashboard ready: http://127.0.0.1:${HERMES_PORT}"
      return 0
    fi
    sleep 1
  done
  log "ERROR: dashboard did not become ready; see ${LOG_FILE}"
  tail -20 "${LOG_FILE}" 2>/dev/null || true
  exit 1
}

verify_mount() {
  local code
  code=$(curl -sS -o /dev/null -w '%{http_code}' \
    -H "X-Hermes-Session-Token: ${SESSION_TOKEN}" \
    "http://127.0.0.1:${HERMES_PORT}/api/plugins/livingcolor/delivery/overview")
  if [ "${code}" = "200" ]; then
    log "LivingColor API mount OK (HTTP 200)"
  else
    log "ERROR: overview returned HTTP ${code}"
    exit 1
  fi
}

warmup_jira_mcp() {
  log "Warming up Jira MCP connection (mcp-atlassian via uvx)..."
  if ! python3 - <<'PY'
import json
import sys
from jira_dashboard.mcp_compat import install_mcp_tool_shims
install_mcp_tool_shims()
from jira_dashboard.service import connect_jira_mcp
result = connect_jira_mcp()
if not result.get("ok"):
    print(result.get("message") or "Jira MCP warmup failed", file=sys.stderr)
    sys.exit(1)
print(f"toolCount={result.get('toolCount', 0)}")
PY
  then
    log "WARNING: Jira MCP warmup failed in bootstrap shell; Hermes process may need dashboard restart"
    return 1
  fi
}

restart_dashboard() {
  log "Restarting Hermes dashboard to load MCP runtime with uvx available"
  pkill -f "hermes dashboard" 2>/dev/null || true
  sleep 2
  start_dashboard
}

main() {
  require_cmd python3
  install_hermes
  install_uvx
  sync_plugin
  write_project_mapping
  configure_mcp_from_env
  write_livingcolor_env
  start_dashboard
  verify_mount
  warmup_jira_mcp || restart_dashboard
  verify_mount
  log "Credential scan:"
  python3 -c "from lc_server.integrations.mcp_env_bootstrap import credential_env_status; [print(f'{k}={v}') for k, v in credential_env_status().items()]"
  log "Bootstrap complete"
}

main "$@"
