# LivingColor Cloud Automation — Memories

Persistent facts for **LivingColor Plugin Autonomous Improvement** runs. Full spec: `docs/cursor-cloud/prompt.md`.

**Do not create a run todo or subagent for "explore repo / learn TVP / read docs".** That stable context lives here. Each run starts at **Hermes Bootstrap**.

## Mission

Primary success = **Hermes + LivingColor plugin running**, then **TVP delivery workflow E2E** with live sandbox integrations — not pytest/vitest alone.

```
Hermes install → plugin install/enable → gateway up → setup TVP → workflow A–H → diagnose → heal PR (if needed)
```

## Run checklist (per execution only)

1. Hermes Bootstrap — install, plugin sync, gateway verify
2. Project setup + integration audit — Jira, GitHub, Stripe
3. Workflow FRT phases A–H via Hermes API
4. Secondary tests — pytest, vitest, build
5. Self-healing + `result.md` + PR (if fixes)

Per-run delta only (not a checklist step): trigger commit SHA, latest `docs/cloud-agent-runs/*-result.md`, credential presence scan.

## Product context (stable — do not re-discover each run)

LivingColor = **Hermes Agent plugin** (`abecms/livingcolor-plugin`). Not a standalone app.

| What | Where |
|------|--------|
| Plugin install | `~/.hermes/plugins/livingcolor` |
| LivingColor home | `~/.hermes/livingcolor/` |
| Project mapping | `~/.hermes/livingcolor/project_mapping.yaml` |
| Runtime DB (personal) | `~/.hermes/livingcolor/runtime.db` |
| API base (Hermes) | `/api/plugins/livingcolor` |
| Dashboard tab | `/livingcolor` on Hermes dashboard |
| Sync script | `scripts/sync-hermes-plugin.sh` |
| Run reports | `docs/cloud-agent-runs/*-result.md` |
| Context repos | `livingcolor-skills`, `livingcolor-evolution` (read-only) |

Install commands (README):

```bash
hermes plugins install abecms/livingcolor-plugin --enable
hermes gateway restart
```

Dev sync from checkout: `./scripts/sync-hermes-plugin.sh && hermes plugins enable livingcolor`

**Do not** implement Cloud orchestrator/runner/fixer code in the plugin repo.

## TVP `project_mapping.yaml` template

```yaml
TVP:
  jira_project_key: TVP
  vcs: github
  default_repo: github.com/abecms/tv5mondeplus-front
  integration_branch: preprod
  communication_language: fr
  sprint:
    duration_days: 7
    capacity_days: 2.0
```

## Workflow API map (stable)

| Step | Endpoint / action |
|------|-------------------|
| Overview | `GET /delivery/overview` |
| Setup automation | `POST /delivery/projects/TVP/setup-automation` |
| Readiness scan | readiness API for project `TVP` |
| Promote | `POST /readiness/{id}/promote` |
| Approve gate | `POST /gates/{gate_id}/approve` |
| Orchestration | sync tick via `LIVINGCOLOR_SYNC_ORCHESTRATOR=1` |

Gates **must pause**; advance only via explicit approve. Approver: `cloud-agent:test`.

## Secondary test commands (stable)

```bash
python3 -m pytest tests/test_e2e_smoke.py -q
python3 -m pytest tests/delivery_runtime/test_orchestration_phase2.py -q
python3 -m pytest tests/delivery_runtime/test_delivery_api.py -q
python3 -m pytest tests/lc_server/test_stripe_billing.py -q
cd ui && npm test && npm run build
python3 -m lc_server warm-skills-cache
```

List ignored suites from `pytest.ini` when reporting.

## Hermes — MANDATORY (hard gate)

LivingColor is a **Hermes Agent plugin**. No Hermes = nothing to test.

The agent **must**:
1. Install Hermes CLI (`hermes --version`)
2. Install/sync + enable plugin (`./scripts/sync-hermes-plugin.sh` or `hermes plugins install abecms/livingcolor-plugin --enable`)
3. `hermes gateway restart`
4. Verify `GET /api/plugins/livingcolor/delivery/overview` → HTTP 2xx

**Forbidden:** pytest `TestClient`, standalone `uvicorn`, or direct `lc_server` import as workflow FRT substitute.

Hermes bootstrap failure → status `blocked` (still write `result.md`).

## Repos

| Role | Repository |
|------|------------|
| Target (PR only) | `abecms/livingcolor-plugin` |
| Context (read-only) | `livingcolor-skills`, `livingcolor-evolution` |
| TVP VCS sandbox (real writes) | `abecms/tv5mondeplus-front` (branch `preprod`) |

Never implement orchestrator/runner/fixer code in the plugin. Never push to `main` on `livingcolor-plugin`.

**Two distinct PRs:**
- **Plugin heal PR** → `livingcolor-plugin`, branch `cursor/livingcolor-cloud-heal-{run_id}`
- **TVP sandbox PR** → `tv5mondeplus-front` (workflow publication)

## TVP canonical

- Jira: `livingcolor.atlassian.net`, project `TVP`, board `/boards/234` — **dedicated sandbox, real writes**
- GitHub: `abecms/tv5mondeplus-front`, branch `preprod` — **dedicated sandbox, real PRs**
- Stripe: test mode only (`sk_test_*`)
- Fixtures: `abecms/`, not `tv5monde/` GitLab paths

## Shadow mode — OFF

Never set `LIVINGCOLOR_SHADOW_MODE`. `reason: shadow_mode` on writeback/publication = critical failure.

## Runtime

```bash
unset LIVINGCOLOR_SHADOW_MODE
export LIVINGCOLOR_SYNC_ORCHESTRATOR=1
export LIVINGCOLOR_DEVELOPER_BACKEND=heuristic
export LIVINGCOLOR_PLANNER_BACKEND=heuristic
export PATH="/home/ubuntu/.local/bin:$PATH"
```

Gates: must pause; advance only via `POST .../gates/{id}/approve`.

## Out of scope

- VisualQ FRT/VRT
- Stripe live mode
- Writes outside TVP sandbox

## Credential discovery (per run — lightweight, not a todo phase)

Scan env/MCP for presence only (names in `result.md`, never values): `JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`, `STRIPE_SECRET_KEY`, optional `STRIPE_TEST_CUSTOMER_ID`, optional `OPENROUTER_API_KEY`.

Never ask user mid-run. Missing → `blocked` / `not_configured` on that integration.

**PR blocker history:** plugin heal PR needs `GH_TOKEN` + write on `abecms`.

## Artifacts

`docs/cloud-agent-runs/*-result.md` every run. Include `hermes_version`, `hermes_plugin_enabled`, `hermes_gateway_ok`.

## Status

- `blocked` — Hermes/plugin/gateway not up
- `failed` — Hermes OK but workflow critical failure
- `partial` — workflow OK; messaging/Stripe blocked
- `passed` — Hermes + workflow A–H + live Jira/GitHub verified

## Security

Never commit or print secrets.
