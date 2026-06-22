#!/usr/bin/env bash
# Credential and Hermes preflight for Cursor Cloud TVP workflow FRT.
# Prints configured/missing status only — never secret values.
set -euo pipefail

export PATH="${HOME}/.local/bin:${PATH}"
HERMES_PORT="${HERMES_PORT:-9119}"
SESSION_TOKEN="${HERMES_DASHBOARD_SESSION_TOKEN:-cloud-agent-session-token}"

log() { echo "[cloud-preflight] $*"; }

critical_missing=0

check_env() {
  local name="$1"
  local required="${2:-1}"
  if [ -n "${!name:-}" ]; then
    log "${name}=configured"
    return 0
  fi
  if [ "${required}" = "1" ]; then
    log "${name}=missing (required)"
    critical_missing=$((critical_missing + 1))
  else
    log "${name}=missing (optional)"
  fi
  return 1
}

log "=== Credential scan ==="
check_env JIRA_URL || true
check_env JIRA_USERNAME || true
check_env JIRA_API_TOKEN || true
check_env GITHUB_TOKEN || true
check_env GH_TOKEN 0 || true
check_env STRIPE_SECRET_KEY 0 || true
check_env OPENROUTER_API_KEY 0 || true

if [ -z "${GITHUB_TOKEN:-}" ] && [ -n "${GH_TOKEN:-}" ]; then
  log "GITHUB_TOKEN=configured (via GH_TOKEN)"
  critical_missing=$((critical_missing > 0 ? critical_missing - 1 : 0))
fi

log "=== Hermes gate ==="
if command -v hermes >/dev/null 2>&1; then
  log "hermes=$(hermes --version 2>/dev/null | head -1)"
else
  log "hermes=missing"
  critical_missing=$((critical_missing + 1))
fi

if [ -d "${HOME}/.hermes/plugins/livingcolor" ]; then
  log "livingcolor_plugin=installed"
else
  log "livingcolor_plugin=missing"
  critical_missing=$((critical_missing + 1))
fi

code=$(curl -sS -o /dev/null -w '%{http_code}' \
  -H "X-Hermes-Session-Token: ${SESSION_TOKEN}" \
  "http://127.0.0.1:${HERMES_PORT}/api/plugins/livingcolor/delivery/overview" 2>/dev/null || echo "000")
if [ "${code}" = "200" ]; then
  log "gateway_overview=HTTP_200"
else
  log "gateway_overview=HTTP_${code}"
  critical_missing=$((critical_missing + 1))
fi

if [ "${critical_missing}" -gt 0 ]; then
  log "Preflight: ${critical_missing} blocker(s). Configure Cursor Automation secrets (see docs/cursor-cloud/bootstrap.md)."
  exit 1
fi

log "Preflight OK"
exit 0
