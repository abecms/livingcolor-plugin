# LivingColor — Hermes Agent Plugin

<video src="docs/livingcolor-demo.mp4" controls width="100%"></video>

Autonomous delivery platform (Work Orders, readiness queue, human-approved
gates) plus a Jira PM dashboard, packaged as a [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin.

Repository: [github.com/abecms/livingcolor-plugin](https://github.com/abecms/livingcolor-plugin)

## Quick install

**Requirements:** [Hermes Agent](https://github.com/NousResearch/hermes-agent) installed (`hermes` in your PATH) and **Git** available (Hermes clones the plugin from GitHub).

```bash
hermes plugins install abecms/livingcolor-plugin --enable
hermes gateway restart
```

No build step is required — `dashboard/dist/` ships prebuilt.

Alternative forms:

```bash
# Full Git URL
hermes plugins install https://github.com/abecms/livingcolor-plugin.git --enable

# Install without enabling (activate later)
hermes plugins install abecms/livingcolor-plugin
hermes plugins enable livingcolor
hermes gateway restart
```

After restart, open the Hermes dashboard. A **LivingColor** tab appears at
`/livingcolor`; the API mounts at `/api/plugins/livingcolor/`.

### Update or remove

```bash
hermes plugins update livingcolor
hermes gateway restart

hermes plugins remove livingcolor
hermes gateway restart
```

### Manual install (development)

```bash
git clone https://github.com/abecms/livingcolor-plugin.git ~/.hermes/plugins/livingcolor
hermes plugins enable livingcolor
hermes gateway restart
```

## Prerequisites

Before delivery workflows can run, configure:

1. **LLM provider in Hermes** — LivingColor uses your Hermes model
   (`~/.hermes/config.yaml` → `model.provider` / `model.default`). The plugin
   does not bundle or override API keys.
2. **Jira MCP** — connect via `hermes mcp` or the dashboard MCP settings.
3. **GitLab or GitHub MCP** — choose the VCS provider used by each project.
   GitLab projects publish **Merge Requests**; GitHub projects publish **Pull
   Requests**. Connect the matching MCP server before delivery work.
4. **Project mapping** — create `~/.hermes/livingcolor/project_mapping.yaml`
   (see [Project mapping](#project-mapping) below).

LivingColor reads MCP connection status and per-project credentials only after
you explicitly save them in **Project → Integrations** in the dashboard.

### External LivingColor Skills

LivingColor can enrich delivery prompts with external guidance from the
`Tamsi/livingcolor-skills` repository. The integration is pinned by
`livingcolor.skills.lock.json`, which records both the requested `ref` and the
exact `resolvedCommit`. GitHub archive downloads use `resolvedCommit`, not a
moving branch or tag, so each warmed cache points at one immutable source
revision.

The cache materializer expands those skills under
`~/.hermes/livingcolor/skills-cache/livingcolor-skills/<resolvedCommit>/`.
Runtime prompt enrichment is cache-only: if the lock file, cache, or registry is
missing or invalid, LivingColor continues delivery for that run with external
guidance disabled. Prompt enrichment does not block on a GitHub download at
runtime.

After changing `livingcolor.skills.lock.json`, materialize the pinned cache
explicitly before running delivery:

```bash
python -m lc_server warm-skills-cache
```

The command exits non-zero when the cache cannot be materialized, so release and
automation scripts can fail fast while runtime prompt enrichment remains
cache-only.

External skills are rendered as read-only model guidance. They do not grant new
tool permissions, change delivery tool response contracts, or alter the
human-gated workflow. The `code-review-pipeline` bundle includes
`sprint-reporter` for end-of-sprint retrospectives posted to Hermes messaging.
To roll back, restore `livingcolor.skills.lock.json` to a previous known-good
`resolvedCommit`, then re-materialize or warm that cache before running delivery
again.

## First-time setup

### 1. Open the dashboard

Launch or refresh the Hermes dashboard, then click the **LivingColor** tab.

If you see *"LivingColor backend is not mounted"*, enable the plugin and restart:

```bash
hermes plugins enable livingcolor
hermes gateway restart
```

### 2. Choose a workspace mode

**Personal (default)** — 100% local. Delivery state lives in
`~/.hermes/livingcolor/runtime.db`. No account required; choose **Continue
locally** on the welcome screen.

**Team** — shared projects via Firebase (`livingcolor-app`). Choose **Sign in
to collaborate** (Google or email). Team data is served by
`https://api-livingcolor.visualq.ai`; users never install a Firebase service
account locally. Public Firebase web client config is embedded in the plugin;
security is enforced by Firebase Auth, Firestore rules, and verified ID tokens
on the cloud API.

### 3. Project mapping

Create `~/.hermes/livingcolor/project_mapping.yaml` with one block per Jira
project key:

```yaml
MYPROJ:
  default_repo: gitlab.com/org/my-service
  integration_branch: main          # optional review-request target branch
  conventions:
    - Add tests for API contract changes
  repos:
    gitlab.com/org/my-service:
      checkout_path: /path/to/local/clone   # optional; managed checkout if omitted
```

For GitHub projects, set `vcs: github` and use a GitHub repository path:

```yaml
MYPROJ:
  vcs: github
  default_repo: github.com/org/my-service
  integration_branch: main
```

Keys are matched case-insensitively. `default_repo` is required for readiness
scoring and development; label-based `rules` can override the repo per ticket.

### GitLab vs GitHub project setup

Each Jira project key can target **GitLab** (default) or **GitHub**:

| Provider | MCP requirement | Published review request | Dashboard labels |
| --- | --- | --- | --- |
| GitLab (default) | GitLab MCP + personal access token | Merge Request (MR) | MR / Merge Request |
| GitHub | GitHub MCP + personal access token | Pull Request (PR) | PR / Pull Request |

In the dashboard, open **Project → Integrations**, choose the VCS provider,
connect the matching MCP credentials, and pick the default repository. GitHub
projects require a GitHub token with repository access; GitLab projects require
a GitLab token with API scope. You can also set `vcs` in
`project_mapping.yaml` as shown above.

Install or update the plugin with:

```bash
hermes plugins install abecms/livingcolor-plugin --enable
hermes gateway restart
```

### 4. Connect integrations

In the dashboard, open a project → **Integrations** and connect Jira plus the
project's VCS provider (GitLab or GitHub). LivingColor never writes MCP config
silently — you opt in per project.

### GitLab MCP (setup & troubleshooting)

LivingColor connects to GitLab through a **Hermes MCP stdio server** (not through
Cursor, Claude Desktop, or VS Code MCP settings). Credentials are saved to
`~/.hermes/config.yaml` when you click **Connect GitLab** in the dashboard.

#### Prerequisites on the machine running the Hermes gateway

| Requirement | Why |
| --- | --- |
| **Node.js 18+** | The official GitLab MCP server is a Node package |
| **`npx` on the gateway `PATH`** | Default launch command used by the dashboard |
| **GitLab personal access token** | Scope `api` on your instance (e.g. `gitlab.com` or self-hosted) |

#### Connect via the dashboard (recommended)

1. Open **Project → Integrations**.
2. Set **VCS provider** to **GitLab**.
3. Click **Connect GitLab**.
4. Enter:
   - **Instance URL** — e.g. `https://gitlab.com` or `https://gitlab.example.com`
     (do not append `/api/v4`; LivingColor normalizes it).
   - **Personal access token** — `glpat-…` with API scope.
5. Click **Connect**. LivingColor saves the MCP entry and runs a connection test.

The saved MCP config looks like this (you normally do not edit it by hand):

```yaml
mcp_servers:
  gitlab:
    command: npx
    args:
      - -y
      - "@modelcontextprotocol/server-gitlab"
    connect_timeout: 120
    env:
      GITLAB_API_URL: https://gitlab.example.com/api/v4/
      GITLAB_PERSONAL_ACCESS_TOKEN: glpat-...
```

#### Error: `Server rejected: suspicious command/args configuration`

This message comes from **Hermes security** when saving MCP config through
LivingColor (`PUT /api/plugins/livingcolor/mcp/servers/gitlab`). It is **not**
returned by GitLab or by Cursor.

Hermes blocks only a narrow pattern: a **shell interpreter** (`bash`, `sh`, `zsh`,
…) whose `args` look like network exfiltration (`curl`, `wget`, `POST`, etc.).
The default `npx` GitLab config is allowed.

If you see this error:

1. **Inspect the existing entry** — a leftover manual config may still use `bash`/`sh`:

   ```bash
   grep -A15 gitlab ~/.hermes/config.yaml
   hermes mcp list
   ```

   `command` must be `npx` or `mcp-server-gitlab`, not `bash` or `sh`.

2. **Remove the bad entry** and reconnect from the dashboard:

   ```bash
   hermes mcp remove gitlab   # or your custom server name, e.g. gitlab-tv5
   ```

3. **Reconnect** via **Project → Integrations → Connect GitLab**.

After a plugin update, the API may return a more specific rejection reason (e.g.
*shell interpreter 'bash' with network egress in args*).

#### Alternative: install the MCP server globally (no `npx` at runtime)

Use this when the gateway process cannot find `npx` (systemd service, minimal
`PATH`, air-gapped install after a one-time `npm install`).

```bash
npm install -g @modelcontextprotocol/server-gitlab
```

Then either edit `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  gitlab:
    command: mcp-server-gitlab
    connect_timeout: 120
    env:
      GITLAB_API_URL: https://gitlab.example.com/api/v4/
      GITLAB_PERSONAL_ACCESS_TOKEN: ${GITLAB_PERSONAL_ACCESS_TOKEN}
```

and store the token in `~/.hermes/.env`:

```bash
# ~/.hermes/.env
GITLAB_PERSONAL_ACCESS_TOKEN=glpat-...
```

or add via CLI:

```bash
hermes mcp add gitlab \
  --command npx \
  --args -y \
  --args @modelcontextprotocol/server-gitlab
```

Restart the gateway after manual config changes:

```bash
hermes gateway restart
```

#### CLI checks

```bash
hermes mcp list
hermes mcp test gitlab
```

In the dashboard, **Integrations** should show GitLab as **Connected** with a
non-zero tool count.

#### Security notes

- Create a dedicated PAT per machine or user; revoke it when offboarding.
- Prefer `${GITLAB_PERSONAL_ACCESS_TOKEN}` in `config.yaml` plus `~/.hermes/.env`
  when configuring servers manually.
- Never commit tokens to git or paste them into chat logs.

### Sprint Stripe invoices

On install, LivingColor automatically installs the **Stripe Python SDK** and
creates `~/.hermes/livingcolor/.env` with setup hints. End-of-sprint reports can
create a **Stripe Billing invoice** from delivered tickets
(`estimatedDays × dailyRate`).

**One-time setup (about 2 minutes):**

1. In the dashboard, open **Project Settings → Stripe billing** and set:
   - Stripe secret key (`sk_test_...` or `sk_live_...`)
   - Stripe customer ID (`cus_...`)
   - Daily rate (EUR)
2. Click **Save settings**.

The secret key is stored in `~/.hermes/livingcolor/.env` (plugin config). You can
also set `STRIPE_SECRET_KEY` in `~/.hermes/.env` if you prefer Hermes env files.

You can also edit `billing:` in `project_mapping.yaml` if you prefer files over
the UI. Invoice creation runs when the sprint report is published; billing
failures appear as warnings in the report but do not block publication.

### 5. Enable agent tools (optional)

In Hermes, add the `livingcolor` toolset to your session or platform config so
the model can call delivery tools (see [Agent surfaces](#agent-surfaces)).

## How to use

### Dashboard (Mission Control)

The LivingColor tab is the primary UI:

| Area | Purpose |
| --- | --- |
| **Project dashboard** | Work Orders, readiness queue, gate reviews, delivery status |
| **Settings** | Per-project delivery configuration, sprint reset, sprint report |
| **Integrations** | Jira / GitLab / GitHub MCP scopes for the project |

Typical flow:

1. **Scan readiness** — pull Jira issues into the readiness queue for a project.
2. **Review & promote** — promote a readiness record to a Work Order (explicit human action).
3. **Gates** — approve or reject paused gates (analysis plan, code review, MR/PR review, etc.).
4. **Track** — follow Work Order stages until completion or review-request publication.

All orchestration state is stored under `~/.hermes/livingcolor/` (respects
`HERMES_HOME`).

### Agent surfaces (CLI / gateway)

When the plugin is enabled, Hermes exposes:

**Slash command**

```
/delivery status
/delivery scan <PROJECT>
/delivery queue
/delivery promote <id>
/delivery gates
```

**Model toolset `livingcolor`**

| Tool | Description |
| --- | --- |
| `delivery_overview` | Snapshot of work orders, readiness queue, pending gates |
| `delivery_scan_readiness` | Scan a Jira project into the readiness queue (read-only on Jira) |
| `delivery_promote` | Promote a readiness record to a Work Order |
| `delivery_gate_decision` | Approve or reject a paused gate |
| `delivery_work_order_status` | Fetch a Work Order's stage and metadata |

Enable the toolset in your Hermes platform or session tool configuration
alongside your usual toolsets.

## Data layout

| Path | Contents |
| --- | --- |
| `~/.hermes/livingcolor/runtime.db` | Delivery SQLite database |
| `~/.hermes/livingcolor/project_mapping.yaml` | Jira project → repo mapping |
| `~/.hermes/livingcolor/projects/{KEY}/` | Per-project agent manifests and automation state |

## Development

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e /path/to/hermes-agent pytest httpx
pytest tests -x -q
cd ui && npm install && npx vite build   # rebuilds dashboard/dist — commit dist/ after UI changes
```

Point Hermes at a local clone:

```bash
git clone https://github.com/abecms/livingcolor-plugin.git ~/.hermes/plugins/livingcolor
hermes plugins enable livingcolor
hermes gateway restart
```

## Provenance

One-shot port of the LivingColor product from the agent-lc fork
(spec: agent-lc `docs/superpowers/specs/2026-06-12-livingcolor-hermes-plugin-design.md`).
Upstream platform: Hermes Agent (MIT, Nous Research attribution preserved).
