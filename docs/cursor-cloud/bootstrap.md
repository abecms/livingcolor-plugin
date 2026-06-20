# LivingColor Cloud Bootstrap

Guide for Cursor Cloud agents running the TVP workflow FRT against live sandbox integrations.

## Quick start

```bash
unset LIVINGCOLOR_SHADOW_MODE
export LIVINGCOLOR_SYNC_ORCHESTRATOR=1
export LIVINGCOLOR_DEVELOPER_BACKEND=heuristic
export LIVINGCOLOR_PLANNER_BACKEND=heuristic
export LIVINGCOLOR_ANALYST_BACKEND=heuristic
export LIVINGCOLOR_PUBLISHER_BACKEND=heuristic
export LIVINGCOLOR_SPRINT_REPORTER_BACKEND=heuristic
export PATH="${HOME}/.local/bin:${PATH}"

./scripts/cloud-bootstrap.sh
```

Run `scripts/cloud-preflight.sh` after bootstrap to fail fast when Automation secrets or the Hermes gateway are missing.

## Security (public repository)

This repository is **public**. That is safe because:

- **No secrets in git** — bootstrap code only reads `os.environ` at runtime and writes to the local Hermes home (`~/.hermes/`), which is never committed.
- **Cursor Cloud secrets** stay in the Automation secrets UI; they are injected into the agent VM environment, not stored in the repo.
- **Ephemeral cloud VMs** — `~/.hermes/config.yaml` and `~/.hermes/livingcolor/.env` exist only for the duration of the run.
- **No logging of values** — scripts and `mcp_env_bootstrap` report `configured` / `missing` only, never token contents.

Do not commit `.env` files, paste tokens into PRs, or add secrets to `project_mapping.yaml`.

## Required Cursor Cloud secrets

Configure these on the **Automation** (not only IDE MCP connections):

| Variable | Purpose |
|----------|---------|
| `JIRA_URL` | Atlassian site (e.g. `https://livingcolor.atlassian.net`) |
| `JIRA_USERNAME` | Jira API user email |
| `JIRA_API_TOKEN` | Jira API token |
| `GITHUB_TOKEN` | GitHub sandbox write access (`abecms/tv5mondeplus-front`) |
| `GH_TOKEN` | Required for `gh pr create` on `livingcolor-plugin` heal PRs |
| `STRIPE_SECRET_KEY` | Stripe test mode (`sk_test_*`) |
| `OPENROUTER_API_KEY` | Optional when heuristic backends are active |

Optional: `STRIPE_TEST_CUSTOMER_ID`, `GITLAB_PERSONAL_ACCESS_TOKEN`, `GITLAB_API_URL`.

**IDE MCP connections are not enough.** Cursor chat MCP servers do not populate the Cloud Agent process environment or Hermes `config.yaml`. The automation must inject the variables above.

If secrets are missing, Hermes bootstrap may still pass but workflow phases C–H will fail with `not_configured` / `blocked`.

## Hermes gate (mandatory)

1. Install Hermes CLI: `pip install --user hermes-agent mcp`
2. Sync plugin: `./scripts/sync-hermes-plugin.sh && hermes plugins enable livingcolor`
3. Start dashboard (not gateway-only in cloud): `hermes dashboard --skip-build --no-open --port 9119`
4. Set a known session token before start: `export HERMES_DASHBOARD_SESSION_TOKEN=<token>`
5. Verify: `curl -H "X-Hermes-Session-Token: <token>" http://127.0.0.1:9119/api/plugins/livingcolor/delivery/overview`

**Forbidden:** pytest `TestClient`, standalone `uvicorn`, or direct `lc_server` import as workflow FRT substitute.

## MCP auto-provisioning from environment

`setup-automation` requires Jira and GitHub MCP entries in Hermes config. On a fresh cloud VM, `~/.hermes/config.yaml` is empty even when secrets are injected.

The plugin bridges env → MCP automatically:

- **At server startup** (`bootstrap_livingcolor_server`)
- **Before `setup-automation`** (`check_provisioning_prerequisites`)
- **Via** `./scripts/cloud-bootstrap.sh` → `python3 -m lc_server.integrations.mcp_env_bootstrap`

Mappings:

- **jira**: `uvx mcp-atlassian` with `JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN`
- **github**: `npx @modelcontextprotocol/server-github` with `GITHUB_TOKEN` or `GH_TOKEN`

## API authentication

Hermes dashboard protects `/api/*` with `X-Hermes-Session-Token`. Export a fixed token before starting the dashboard so `curl`/HTTP calls can authenticate.

## TVP project mapping

Written to `~/.hermes/livingcolor/project_mapping.yaml` by `cloud-bootstrap.sh`:

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

## Workflow API headers

```
X-Hermes-Session-Token: <token>
X-LC-Project-Key: TVP
```

Base path: `/api/plugins/livingcolor/delivery/`

## Shadow mode

Never set `LIVINGCOLOR_SHADOW_MODE`. Sandbox Jira/GitHub writes are required for a passing FRT.

## Two PRs per run

| PR | Repository | Branch |
|----|------------|--------|
| Plugin heal | `abecms/livingcolor-plugin` | `cursor/livingcolor-cloud-heal-{run_id}` |
| TVP sandbox | `abecms/tv5mondeplus-front` | `feature/TVP-*` → `preprod` |
