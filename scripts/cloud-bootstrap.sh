#!/usr/bin/env bash
# Bootstrap Hermes + LivingColor for Cursor Cloud TVP workflow FRT.
# Idempotent: safe to re-run. Never prints secret values.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${HOME}/.local/bin:${PATH}"

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
  python3 <<'PY'
import os
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[cloud-bootstrap] PyYAML unavailable; skipping MCP config")
    raise SystemExit(0)

cfg_path = Path.home() / ".hermes" / "config.yaml"
data = {}
if cfg_path.exists():
    loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if isinstance(loaded, dict):
        data = loaded

servers = data.get("mcp_servers")
if not isinstance(servers, dict):
    servers = {}

jira_url = (os.environ.get("JIRA_URL") or "").strip()
jira_user = (os.environ.get("JIRA_USERNAME") or "").strip()
jira_token = (os.environ.get("JIRA_API_TOKEN") or "").strip()
if jira_url and jira_token:
    servers["jira"] = {
        "command": "uvx",
        "args": ["mcp-atlassian"],
        "env": {
            "JIRA_URL": jira_url,
            "JIRA_USERNAME": jira_user,
            "JIRA_API_TOKEN": jira_token,
        },
    }
    print("[cloud-bootstrap] Configured jira MCP from environment")

github_token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
if github_token:
    servers["github"] = {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {
            "GITHUB_PERSONAL_ACCESS_TOKEN": github_token,
            "GITHUB_TOKEN": github_token,
        },
    }
    print("[cloud-bootstrap] Configured github MCP from environment")

if servers:
    data["mcp_servers"] = servers
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
else:
    print("[cloud-bootstrap] No Jira/GitHub credentials in environment; MCP not configured")
PY
}

write_livingcolor_env() {
  local env_path="${HOME}/.hermes/livingcolor/.env"
  mkdir -p "$(dirname "${env_path}")"
  if [ -n "${STRIPE_SECRET_KEY:-}" ]; then
    if ! grep -q '^STRIPE_SECRET_KEY=' "${env_path}" 2>/dev/null; then
      printf 'STRIPE_SECRET_KEY=%s\n' "${STRIPE_SECRET_KEY}" >> "${env_path}"
      chmod 600 "${env_path}" 2>/dev/null || true
      log "Wrote STRIPE_SECRET_KEY to ${env_path}"
    fi
  fi
}

start_dashboard() {
  if curl -sf -H "X-Hermes-Session-Token: ${SESSION_TOKEN}" \
    "http://127.0.0.1:${HERMES_PORT}/api/plugins/livingcolor/delivery/overview" >/dev/null 2>&1; then
    log "Dashboard already responding on port ${HERMES_PORT}"
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

credential_report() {
  for var in JIRA_URL JIRA_USERNAME JIRA_API_TOKEN GITHUB_TOKEN GH_TOKEN STRIPE_SECRET_KEY OPENROUTER_API_KEY; do
    if [ -n "${!var:-}" ]; then
      echo "${var}=configured"
    else
      echo "${var}=missing"
    fi
  done
}

main() {
  require_cmd python3
  install_hermes
  sync_plugin
  write_project_mapping
  configure_mcp_from_env
  write_livingcolor_env
  start_dashboard
  verify_mount
  log "Credential scan:"
  credential_report
  log "Bootstrap complete"
}

main "$@"
