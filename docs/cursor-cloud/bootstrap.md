# LivingColor Cloud Bootstrap

Guide for Cursor Cloud agents running the TVP workflow FRT against live sandbox integrations.

## Quick start

```bash
unset LIVINGCOLOR_SHADOW_MODE
export PATH="${HOME}/.local/bin:${PATH}"

# Option A — credentials in Automation Secrets (already in os.environ):
./scripts/cloud-start.sh

# Option B — credentials in the automation prompt (pipe KEY=VALUE lines):
./scripts/cloud-start.sh <<'CREDS'
JIRA_URL=https://livingcolor.atlassian.net
JIRA_USERNAME=you@example.com
JIRA_API_TOKEN=...
GITHUB_TOKEN=...
GH_TOKEN=...
STRIPE_SECRET_KEY=sk_test_...
CREDS
```

`cloud-start.sh` writes `~/.hermes/livingcolor/.env`, loads it, provisions Jira/GitHub MCP, then runs `cloud-bootstrap.sh` (Hermes + plugin + dashboard).

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

### Prompt credentials are not environment variables

Cursor does **not** copy credential lines from the automation prompt into `os.environ`. If values appear in the prompt text, the agent must provision them **before** bootstrap:

```bash
# Step 0 — mandatory when credentials are in the prompt (never echo values in logs)
python3 scripts/cloud_write_credentials.py <<'CREDS'
JIRA_URL=https://livingcolor.atlassian.net
JIRA_USERNAME=you@example.com
JIRA_API_TOKEN=...
GITHUB_TOKEN=...
GH_TOKEN=...
STRIPE_SECRET_KEY=sk_test_...
CREDS

set -a && source scripts/cloud-load-credentials.sh && set +a
./scripts/cloud-preflight.sh
```

Priority:

1. Variables already in `os.environ` (Automation Secrets UI) — use as-is
2. Values in the automation prompt — write with `cloud_write_credentials.py`, then `source cloud-load-credentials.sh`
3. Missing — mark integration `blocked` in `result.md`

The `.env` file lives at `~/.hermes/livingcolor/.env` (chmod 600, never committed). `cloud-bootstrap.sh` loads it automatically.

If secrets are missing after step 0, Hermes bootstrap may still pass but workflow phases C–H will fail with `not_configured` / `blocked`.

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
