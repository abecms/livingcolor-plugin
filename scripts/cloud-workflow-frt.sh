#!/usr/bin/env bash
# Hermes-mounted TVP workflow FRT driver (phases A–H).
# Requires: ./scripts/cloud-bootstrap.sh (or running Hermes dashboard).
# Never prints secret values. Exits non-zero on critical workflow failures.
set -euo pipefail

export PATH="${HOME}/.local/bin:${PATH}"
unset LIVINGCOLOR_SHADOW_MODE

HERMES_PORT="${HERMES_PORT:-9119}"
SESSION_TOKEN="${HERMES_DASHBOARD_SESSION_TOKEN:-cloud-agent-session-token}"
PROJECT_KEY="${LIVINGCOLOR_TEST_PROJECT_KEY:-TVP}"
BASE="http://127.0.0.1:${HERMES_PORT}/api/plugins/livingcolor/delivery"
HDR=(-H "X-Hermes-Session-Token: ${SESSION_TOKEN}" -H "Content-Type: application/json" -H "X-LC-Project-Key: ${PROJECT_KEY}")

log() { echo "[cloud-workflow-frt] $*"; }
failures=0
record() { log "PHASE $1 | $2 | $3"; [ "$3" = "pass" ] || failures=$((failures + 1)); }

# Phase A — Hermes mount
code=$(curl -sS -o /dev/null -w '%{http_code}' -H "X-Hermes-Session-Token: ${SESSION_TOKEN}" "${BASE}/overview" 2>/dev/null || echo "000")
if [ "${code}" = "200" ]; then record A "overview" pass; else record A "overview" "fail HTTP_${code}"; fi

# Phase B — setup + settings
setup_body=$(curl -sS -w '\n%{http_code}' -X POST "${HDR[@]}" "${BASE}/projects/${PROJECT_KEY}/setup-automation" 2>/dev/null || echo -e '\n000')
setup_code="${setup_body##*$'\n'}"
if [ "${setup_code}" = "200" ]; then
  record B "setup-automation" pass
elif echo "${setup_body}" | grep -q prerequisites_missing; then
  record B "setup-automation" "blocked prerequisites_missing"
else
  record B "setup-automation" "fail HTTP_${setup_code}"
fi

cfg_code=$(curl -sS -o /dev/null -w '%{http_code}' -X PUT "${HDR[@]}" "${BASE}/project-config" \
  -d "{\"projectKey\":\"${PROJECT_KEY}\",\"sprintDurationDays\":7,\"sprintCapacityDays\":2.0,\"communicationLanguage\":\"fr\",\"defaultRepo\":\"github.com/abecms/tv5mondeplus-front\",\"jiraProjectKey\":\"${PROJECT_KEY}\",\"integrationBranch\":\"preprod\",\"vcs\":\"github\"}" 2>/dev/null || echo "000")
[ "${cfg_code}" = "200" ] && record B "project-config" pass || record B "project-config" "fail HTTP_${cfg_code}"

# Phase C — integrations
jira_code=$(curl -sS -o /dev/null -w '%{http_code}' "${HDR[@]}" "${BASE}/projects/${PROJECT_KEY}/jira-projects" 2>/dev/null || echo "000")
if [ "${jira_code}" = "200" ]; then record C "jira" pass
elif [ "${jira_code}" = "400" ]; then record C "jira" blocked
else record C "jira" "fail HTTP_${jira_code}"; fi

vcs_code=$(curl -sS -o /dev/null -w '%{http_code}' "${HDR[@]}" "${BASE}/projects/${PROJECT_KEY}/vcs-repos" 2>/dev/null || echo "000")
if [ "${vcs_code}" = "200" ]; then record C "github" pass
elif [ "${vcs_code}" = "400" ]; then record C "github" blocked
else record C "github" "fail HTTP_${vcs_code}"; fi

# Phase D — readiness (skip promote if scan blocked)
scan_body=$(curl -sS -w '\n%{http_code}' -X POST "${HDR[@]}" "${BASE}/readiness/scan" -d "{\"projectKey\":\"${PROJECT_KEY}\"}" 2>/dev/null || echo -e '\n000')
scan_code="${scan_body##*$'\n'}"
if [ "${scan_code}" = "200" ]; then
  record D "readiness-scan" pass
  record_id=$(echo "${scan_body}" | sed '$d' | python3 -c "import sys,json; d=json.load(sys.stdin); items=d.get('items') or []; print(items[0]['id'] if items else '')" 2>/dev/null || true)
  if [ -n "${record_id:-}" ]; then
    prom_code=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "${HDR[@]}" "${BASE}/readiness/${record_id}/promote" 2>/dev/null || echo "000")
    [ "${prom_code}" = "200" ] && record D "promote" pass || record D "promote" "fail HTTP_${prom_code}"
  else
    record D "promote" blocked
  fi
else
  record D "readiness-scan" blocked
  record D "promote" blocked
fi

# Phases E–H require live integrations; mark blocked when credentials missing
if [ "${jira_code}" != "200" ] || [ "${vcs_code}" != "200" ]; then
  record E "gates" blocked
  record F "delivery" blocked
  record G "jira-writeback" blocked
  record G "github-publication" blocked
  record H "sprint-report" blocked
  record H "stripe" blocked
else
  log "Phases E–H require gate approval loop — run manually or extend this script."
  record E "gates" "manual"
  record F "delivery" "manual"
fi

log "Workflow FRT complete (${failures} failure(s))"
exit "${failures}"
