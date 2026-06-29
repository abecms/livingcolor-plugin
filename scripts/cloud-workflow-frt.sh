#!/usr/bin/env bash
# TVP delivery workflow FRT via Hermes-mounted LivingColor API.
# Never prints secret values. Writes evidence to /tmp/lc-frt-evidence.jsonl
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${HOME}/.local/bin:${PATH}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

# shellcheck disable=SC1091
source "${ROOT}/scripts/cloud-load-credentials.sh"

unset LIVINGCOLOR_SHADOW_MODE
export LIVINGCOLOR_SYNC_ORCHESTRATOR=1
export LIVINGCOLOR_DEVELOPER_BACKEND=heuristic
export LIVINGCOLOR_PLANNER_BACKEND=heuristic
export LIVINGCOLOR_ANALYST_BACKEND=heuristic
export LIVINGCOLOR_PUBLISHER_BACKEND=heuristic
export LIVINGCOLOR_SPRINT_REPORTER_BACKEND=heuristic

HERMES_PORT="${HERMES_PORT:-9119}"
BASE="http://127.0.0.1:${HERMES_PORT}/api/plugins/livingcolor/delivery"
TOKEN="${HERMES_DASHBOARD_SESSION_TOKEN:-cloud-agent-session-token}"
EVIDENCE="/tmp/lc-frt-evidence.jsonl"
SUMMARY="/tmp/lc-frt-summary.json"

log() { echo "[workflow-frt] $*"; }
record() { printf '%s\n' "$1" >>"${EVIDENCE}"; }

api() {
  local method="$1" path="$2" body="${3:-}"
  local url="${BASE}${path}"
  local tmp http
  tmp="$(mktemp)"
  if [ -n "${body}" ]; then
    http=$(curl -sS -w '\n%{http_code}' -X "${method}" "${url}" \
      -H "X-Hermes-Session-Token: ${TOKEN}" \
      -H "X-LC-Project-Key: TVP" \
      -H "Content-Type: application/json" \
      -d "${body}")
  else
    http=$(curl -sS -w '\n%{http_code}' -X "${method}" "${url}" \
      -H "X-Hermes-Session-Token: ${TOKEN}" \
      -H "X-LC-Project-Key: TVP")
  fi
  printf '%s' "${http}" >"${tmp}"
  local code
  code=$(tail -1 "${tmp}")
  local resp
  resp=$(sed '$d' "${tmp}")
  rm -f "${tmp}"
  record "$(python3 -c "import json,sys; print(json.dumps({'method':'${method}','path':'${path}','http':int('${code}'),'body_preview':sys.stdin.read()[:500]}))" <<<"${resp}")"
  printf '%s\n%s' "${code}" "${resp}"
}

# curl -w appends HTTP code on its own line; split into API_HTTP + API_BODY globals.
api_call() {
  local raw
  raw=$(api "$@")
  API_HTTP=$(printf '%s' "${raw}" | head -1)
  API_BODY=$(printf '%s' "${raw}" | tail -n +2)
}

wait_wo_status() {
  local wo_id="$1" want="$2" tries="${3:-60}"
  local i code resp status
  for i in $(seq 1 "${tries}"); do
    api_call GET "/work-orders/${wo_id}"
    code="${API_HTTP}"
    resp="${API_BODY}"
    status=$(python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" <<<"${resp}")
    if [ "${status}" = "${want}" ]; then
      echo "${status}"
      return 0
    fi
    sleep 2
  done
  echo "timeout:${status:-unknown}"
  return 1
}

tick_orchestrator() {
  local wo_id="$1" tries="${2:-90}"
  local i code resp
  for i in $(seq 1 "${tries}"); do
    api_call POST "/work-orders/${wo_id}/resume" '{}'
    code="${API_HTTP}"
    resp="${API_BODY}"
    sleep 2
    api_call GET "/work-orders/${wo_id}"
    code="${API_HTTP}"
    resp="${API_BODY}"
    local status
    status=$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status',''), d.get('currentStage',''))" <<<"${resp}")
    log "tick ${i}: ${status}"
    if echo "${status}" | grep -qE 'awaiting_gate|completed|failed'; then
      return 0
    fi
  done
}

: >"${EVIDENCE}"

log "Phase B: setup-automation"
api_call POST "/projects/TVP/setup-automation" '{}'
setup_code="${API_HTTP}"
setup_resp="${API_BODY}"
log "setup-automation HTTP ${setup_code}"

log "Phase C: integration probes"
# Ensure Jira MCP is connected inside the Hermes dashboard process
jconn_code=$(curl -sS -o /tmp/jira-connect.json -w '%{http_code}' -X POST \
  "http://127.0.0.1:${HERMES_PORT}/api/plugins/livingcolor/jira/connect" \
  -H "X-Hermes-Session-Token: ${TOKEN}" \
  -H "Content-Type: application/json" -d '{}')
log "jira connect HTTP ${jconn_code}"

# Jira writable probe
jira_code=$(curl -sS -o /tmp/jira-probe.json -w '%{http_code}' \
  -u "${JIRA_USERNAME}:${JIRA_API_TOKEN}" \
  "${JIRA_URL}/rest/api/3/project/TVP")
log "Jira TVP HTTP ${jira_code}"

gh_code=$(curl -sS -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  "https://api.github.com/repos/abecms/tv5mondeplus-front")
log "GitHub repo HTTP ${gh_code}"

stripe_code=$(curl -sS -o /tmp/stripe-probe.json -w '%{http_code}' \
  -u "${STRIPE_SECRET_KEY}:" \
  "https://api.stripe.com/v1/balance")
stripe_live=$(python3 -c "import json; print(json.load(open('/tmp/stripe-probe.json')).get('livemode', 'unknown'))" 2>/dev/null || echo unknown)
log "Stripe balance HTTP ${stripe_code} livemode=${stripe_live}"

log "Phase D: readiness scan"
api_call POST "/readiness/scan" '{"projectKey":"TVP"}'
scan_code="${API_HTTP}"
scan_resp="${API_BODY}"
log "readiness scan HTTP ${scan_code}"

api_call GET "/readiness?projectKey=TVP&status=ready"
list_code="${API_HTTP}"
list_resp="${API_BODY}"
record_id=$(python3 -c "
import json,sys
d=json.load(sys.stdin)
items=d.get('items') or d.get('records') or []
ready=[x for x in items if x.get('readinessStatus')=='ready' or x.get('readiness_status')=='ready']
print(ready[0]['id'] if ready else (items[0]['id'] if items else ''))
" <<<"${list_resp}")
jira_key=$(python3 -c "
import json,sys
d=json.load(sys.stdin)
items=d.get('items') or d.get('records') or []
for x in items:
    if x.get('id')=='${record_id}':
        print(x.get('jiraKey') or x.get('jira_key') or '')
        break
" <<<"${list_resp}")
log "selected readiness record ${record_id} jira=${jira_key}"

if [ -z "${record_id}" ]; then
  log "ERROR: no readiness record found"
  exit 1
fi

api_call POST "/readiness/${record_id}/promote" '{"actor":"cloud-agent:test"}'
prom_code="${API_HTTP}"
prom_resp="${API_BODY}"
wo_id=$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('workOrderId') or d.get('work_order_id') or d.get('id',''))" <<<"${prom_resp}")
log "promote HTTP ${prom_code} wo=${wo_id}"

log "Phase E: gate approvals"
gate_ids=()
while true; do
  api_call GET "/work-orders/${wo_id}"
  wo_code="${API_HTTP}"
  wo_resp="${API_BODY}"
  status=$(python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" <<<"${wo_resp}")
  pending=$(python3 -c "
import json,sys
d=json.load(sys.stdin)
for g in d.get('gates') or []:
    if g.get('status') in ('pending','awaiting_approval','open'):
        print(g['id'])
        break
" <<<"${wo_resp}")
  if [ -z "${pending}" ]; then
    if [ "${status}" = "completed" ]; then break; fi
    tick_orchestrator "${wo_id}" 30 || true
    api_call GET "/work-orders/${wo_id}"
  wo_code="${API_HTTP}"
  wo_resp="${API_BODY}"
    pending=$(python3 -c "
import json,sys
d=json.load(sys.stdin)
for g in d.get('gates') or []:
    if g.get('status') in ('pending','awaiting_approval','open'):
        print(g['id'])
        break
" <<<"${wo_resp}")
    [ -n "${pending}" ] || { log "no pending gate, status=${status}"; break; }
  fi
  log "approving gate ${pending}"
  api_call POST "/gates/${pending}/approve" '{"approvedBy":"cloud-agent:test"}'
  appr_code="${API_HTTP}"
  appr_resp="${API_BODY}"
  gate_ids+=("${pending}")
  tick_orchestrator "${wo_id}" 60 || true
done

log "Phase F: delivery verification"
api_call GET "/work-orders/${wo_id}"
final_code="${API_HTTP}"
final_resp="${API_BODY}"
final_status=$(python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" <<<"${final_resp}")
pr_url=$(python3 -c "
import json,sys
d=json.load(sys.stdin)
for n in d.get('nodes') or []:
    out=n.get('output') or {}
    if out.get('prUrl') or out.get('pullRequestUrl'):
        print(out.get('prUrl') or out.get('pullRequestUrl'))
        break
else:
    print('')
" <<<"${final_resp}")
branch=$(python3 -c "
import json,sys
d=json.load(sys.stdin)
for n in d.get('nodes') or []:
    out=n.get('output') or {}
    if out.get('branch'):
        print(out['branch'])
        break
else:
    print('')
" <<<"${final_resp}")
log "final WO status=${final_status} pr=${pr_url} branch=${branch}"

log "Phase G: sprint report"
api_call POST "/sprint/report" '{}'
sr_code="${API_HTTP}"
sr_resp="${API_BODY}"
log "sprint report HTTP ${sr_code}"

log "Phase H: stripe invoice (if configured)"
if api_call POST "/sprint/reset" '{}' 2>/dev/null; then
  inv_code="${API_HTTP}"
  inv_resp="${API_BODY}"
else
  inv_code="000"
  inv_resp="{}"
fi

python3 - <<'PY' "${SUMMARY}" "${jira_key}" "${wo_id}" "${final_status}" "${pr_url}" "${branch}" "${jira_code}" "${gh_code}" "${stripe_code}" "${stripe_live}" "${setup_code}" "${scan_code}" "${prom_code}" "${sr_code}"
import json, sys
out = {
    "jira_key": sys.argv[2],
    "work_order_id": sys.argv[3],
    "final_status": sys.argv[4],
    "sandbox_pr_url": sys.argv[5],
    "branch": sys.argv[6],
    "integrations": {
        "jira_http": int(sys.argv[7]),
        "github_http": int(sys.argv[8]),
        "stripe_http": int(sys.argv[9]),
        "stripe_livemode": sys.argv[10],
    },
    "http": {
        "setup_automation": int(sys.argv[11]),
        "readiness_scan": int(sys.argv[12]),
        "promote": int(sys.argv[13]),
        "sprint_report": int(sys.argv[14]),
    },
}
with open(sys.argv[1], "w") as f:
    json.dump(out, f, indent=2)
print(json.dumps(out, indent=2))
PY

log "FRT complete — summary at ${SUMMARY}"
