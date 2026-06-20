# Cursor Cloud Multi-Agent Plugin Improvement Design

**Date:** 2026-06-20  
**Status:** Revised after scope clarification  
**Target repository:** `livingcolor-plugin`  
**Execution owner:** Cursor Cloud Agents  
**Primary output:** `docs/cloud-agent-runs/YYYY-MM-DD-HHMM-result.md`

## Goal

Build a fully automated Cursor Cloud workflow that continuously tests, audits, fixes, and improves `livingcolor-plugin`.

The workflow is managed 10000% by Cursor Cloud Agents and subagents. The agents are not implemented inside `livingcolor-plugin`, are not packaged with the plugin, and are not runtime dependencies of the plugin. They operate from Cursor Cloud, read the plugin repository, run checks, use MCP integrations, run VisualQ FRT/VRT, find fixes and improvements, and open pull requests against the plugin repository when safe.

`livingcolor-plugin` remains the target product, not the orchestrator host.

## Non-Goals

- Do not add orchestrator code to `livingcolor-plugin`.
- Do not add cloud test runner code to `livingcolor-plugin`.
- Do not add fixer/improver agent code to `livingcolor-plugin`.
- Do not bind the Cloud Agents to the plugin runtime.
- Do not require the plugin to know that Cursor Cloud Agents exist.
- Do not push directly to `main`.
- Do not mutate Jira, Stripe, GitLab, GitHub, or VisualQ through MCP except for safe VisualQ test-runner actions.
- Do not expose secrets in reports, logs, PRs, commits, screenshots, or final messages.

## Core Principle

The plugin repository is a target and evidence store only.

Allowed Cloud Agent outputs in `livingcolor-plugin`:

- code fixes to the plugin
- tests for plugin fixes
- documentation changes directly related to plugin behavior
- `docs/cloud-agent-runs/YYYY-MM-DD-HHMM-result.md`
- pull requests containing safe fixes and the report

Disallowed Cloud Agent outputs in `livingcolor-plugin`:

- an orchestrator package
- a generic cloud runner
- local replicas of Cloud Agent prompts as required runtime code
- a self-healing framework embedded in the plugin
- credentials or generated secret files

## Cloud Topology

A Cursor Automation triggers on push to `main` in `livingcolor-plugin`.

That Automation starts one Cursor Cloud Orchestrator Agent. The orchestrator dispatches specialized Cloud subagents:

1. **Context Collector Agent**
2. **Hermes Setup Agent**
3. **Integration Audit Agent**
4. **Test Agent**
5. **VisualQ FRT/VRT Agent**
6. **Fix Planner Agent**
7. **Self-Healing Agent**
8. **Report Writer Agent**

The orchestrator coordinates the workflow, but the workflow definition lives in Cursor Cloud configuration and Automation prompts, not in plugin source code.

## Repository Roles

### `livingcolor-plugin`

Primary target repository.

Cloud Agents may:

- read all source, docs, tests, and prior reports
- run test commands
- modify plugin code when a safe fix is found
- add or update tests for plugin fixes
- create a branch `cursor/livingcolor-cloud-heal-{run_id}`
- open a PR toward `main`
- write `docs/cloud-agent-runs/YYYY-MM-DD-HHMM-result.md`

Cloud Agents may not:

- add themselves to the plugin
- implement the orchestrator inside the plugin
- make the plugin depend on Cursor Cloud

### `livingcolor-skills`

Read-only context repository.

Used for:

- understanding external skill contracts
- validating `livingcolor.skills.lock.json`
- detecting skill-related plugin regressions

### `livingcolor-evolution`

Read-only context repository for this workflow unless separately authorized.

Used for:

- curator-loop patterns
- report patterns
- autonomous improvement conventions

It may later become the versioned home for Automation prompts, but the current design does not require `livingcolor-plugin` to host the agents.

## TVP Test Context

The TVP project uses Jira on the LivingColor Atlassian site and GitHub as the VCS provider.

Canonical settings:

```yaml
TVP:
  jira_project_key: TVP
  jira_board_url: "https://livingcolor.atlassian.net/jira/software/c/projects/TVP/boards/234"
  jira_site_url: "https://livingcolor.atlassian.net"
  vcs: github
  default_repo: "github.com/abecms/tv5mondeplus-front"
  integration_branch: "preprod"
```

`jira_site_url` is used for Jira MCP authentication. `jira_board_url` is project context for reporting and user workflow validation.

GitLab remains plugin compatibility coverage. It is not the primary TVP path.

## Agent Responsibilities

### Context Collector Agent

Reads:

- `README.md`
- `plugin.yaml`
- `livingcolor.skills.lock.json`
- `dashboard/plugin_api.py`
- `agent_surfaces.py`
- `delivery_runtime/AGENTS.md`
- `lc_server/AGENTS.md`
- `docs/superpowers/specs/`
- `docs/superpowers/plans/`
- recent commits
- prior cloud run reports
- `livingcolor-skills`
- `livingcolor-evolution`
- Hermes documentation snapshot

Returns a concise context pack for the other agents.

### Hermes Setup Agent

Attempts to validate the plugin in a Cursor Cloud environment.

It checks:

- Hermes CLI availability
- Hermes config viability
- plugin installation or mountability
- dashboard availability
- plugin API smoke behavior

If Hermes is unavailable, it marks Hermes validation `blocked` or `partial` and continues the run.

### Integration Audit Agent

Uses scoped secrets and MCP access to validate:

- Jira read access to `https://livingcolor.atlassian.net`
- TVP project and board availability
- GitHub access to `abecms/tv5mondeplus-front`
- GitLab compatibility access when configured
- Stripe test mode access
- VisualQ readiness

It must not write to Jira, Stripe, GitLab, or GitHub through MCP.

### Test Agent

Runs:

```bash
pytest tests/test_e2e_smoke.py -q
pytest tests -x -q
cd ui && npm test
cd ui && npm run build
python -m lc_server warm-skills-cache
```

It records commands, exit codes, durations, concise outputs, and ignored pytest suites.

### VisualQ FRT/VRT Agent

Runs workflow-level validation against a Hermes dashboard URL with LivingColor mounted.

Required flows:

- open Hermes dashboard
- navigate to LivingColor
- validate overview loading
- select or validate TVP
- inspect readiness queue
- open project settings
- validate integration settings
- validate Stripe billing settings in test mode
- inspect work orders and gates
- verify blocked/partial states render clearly when dependencies are missing

If no dashboard URL exists, VisualQ is `blocked`, but the whole run still produces `result.md`.

### Fix Planner Agent

Turns all failures and improvement opportunities into ranked findings.

Each finding includes:

- stable id
- severity
- evidence
- affected files
- suggested fix
- verification command
- whether self-healing is safe

The planner does not edit code.

### Self-Healing Agent

Implements only safe plugin changes.

Allowed:

- focused bug fixes
- missing tests for those fixes
- small docs corrections directly tied to plugin behavior
- report file creation

Disallowed:

- orchestrator implementation inside the plugin
- broad architecture rewrites
- Jira writes
- Stripe live changes
- VisualQ approvals
- direct `main` pushes

When fixes are made:

```text
branch: cursor/livingcolor-cloud-heal-{run_id}
target: main
```

The agent opens a PR with the code changes, verification summary, and `result.md`.

### Report Writer Agent

Writes a report with YAML frontmatter and Markdown sections.

If a PR is opened, the report is committed in that PR. If no PR is opened, the report remains a Cursor Cloud artifact. A report-only PR is allowed only if the automation policy explicitly enables it.

## Credentials

Required Cursor Cloud secrets:

```text
OPENROUTER_API_KEY
JIRA_URL=https://livingcolor.atlassian.net
JIRA_USERNAME
JIRA_API_TOKEN
GITHUB_TOKEN
STRIPE_SECRET_KEY
VISUALQ_TEST_RUNNER_TOKEN
```

Optional:

```text
GITLAB_PERSONAL_ACCESS_TOKEN
GITLAB_API_URL
STRIPE_TEST_CUSTOMER_ID
VISUALQ_PROJECT_ID
LIVINGCOLOR_TEST_PROJECT_KEY=TVP
LIVINGCOLOR_TEST_GITHUB_REPO=abecms/tv5mondeplus-front
```

Any credential pasted into chat, logs, PRs, issues, or reports is treated as compromised and should be rotated.

## `result.md` Contract

Path:

```text
docs/cloud-agent-runs/YYYY-MM-DD-HHMM-result.md
```

Frontmatter:

```yaml
---
schema_version: "1.0"
run_id: "YYYY-MM-DD-HHMM-main-shortsha"
trigger:
  type: "push_main"
  repo: "livingcolor-plugin"
  branch: "main"
  commit: "shortsha"
mode:
  audit: true
  fix_proposal: true
  self_healing: true
status: "partial"
created_pr: null
repos:
  primary: "livingcolor-plugin"
  context:
    - "livingcolor-skills"
    - "livingcolor-evolution"
credentials:
  jira: "available_read_only"
  github: "available_branch_pr"
  stripe: "available_test_mode"
  visualq: "available_test_runner"
top_findings:
  []
---
```

Mandatory sections:

- `Executive Summary`
- `Environment And Context`
- `Installation Result`
- `Configuration Result`
- `Integration Result`
- `Test Results`
- `VisualQ FRT/VRT Results`
- `Findings`
- `Self-Healing Changes`
- `Next Agent Instructions`
- `Appendix`

The report must be usable by a later Cloud Agent without this chat history.

## Status Classification

- `passed`: all required checks and critical VisualQ flows pass
- `failed`: required code checks or critical FRT flows fail
- `partial`: useful checks ran but Hermes, VisualQ, or optional integrations were unavailable
- `blocked`: the run could not collect context or could not produce a report

## Success Criteria

The system is successful when:

- push to `main` triggers Cursor Cloud
- Cursor Cloud agents run the full workflow
- no orchestrator implementation is added to `livingcolor-plugin`
- agents find fixes or improvement opportunities automatically
- safe fixes become PRs against `livingcolor-plugin`
- `result.md` is produced for every run
- VisualQ FRT/VRT validates the plugin user workflow when Hermes dashboard is available
- external systems are not mutated beyond safe test-runner actions
- secrets never appear in outputs
