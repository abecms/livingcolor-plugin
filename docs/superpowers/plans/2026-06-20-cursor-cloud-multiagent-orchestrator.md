# Cursor Cloud Autonomous Plugin Improvement Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure a fully automated Cursor Cloud workflow where Cloud Agents audit, test, improve, and open PRs against `livingcolor-plugin` without implementing the orchestrator inside the plugin repository.

**Architecture:** Cursor Cloud owns the orchestration. A Cursor Automation triggered by push to `main` starts a Cloud Orchestrator Agent, which dispatches Cloud subagents for context collection, Hermes setup, integration audit, tests, VisualQ FRT/VRT, fix planning, self-healing, and report writing. `livingcolor-plugin` is only the target repository: it is read, tested, modified through PRs, and receives `docs/cloud-agent-runs/...-result.md`.

**Tech Stack:** Cursor Cloud Agents, Cursor Automations, Cursor-managed secrets, MCP servers, GitHub PRs, VisualQ MCP, Hermes CLI/runtime when available in cloud, pytest, Vitest, Vite.

---

## Critical Boundary

Do not add orchestrator code, test runner code, fixer code, or cloud agent implementation code to `livingcolor-plugin`.

Allowed changes in `livingcolor-plugin` are limited to:

- plugin fixes found by Cloud Agents
- plugin improvements found by Cloud Agents
- tests for those plugin fixes
- generated run reports under `docs/cloud-agent-runs/`
- lightweight docs that explain how to interpret those reports

The agent workflow itself lives in Cursor Cloud configuration and automation prompts, not in the plugin codebase.

## Cloud Agent Topology

The Cursor Automation creates one Cloud Orchestrator Agent.

The orchestrator dispatches these subagents:

1. **Context Collector Agent**: reads `livingcolor-plugin`, `livingcolor-skills`, `livingcolor-evolution`, Hermes docs snapshot, recent commits, open PRs, and prior reports.
2. **Hermes Setup Agent**: prepares or verifies Hermes in Cursor Cloud, installs/enables the plugin when possible, and reports blockers when Hermes is unavailable.
3. **Integration Audit Agent**: checks Jira, GitHub, GitLab compatibility, Stripe test mode, and VisualQ readiness using scoped secrets/MCP access.
4. **Test Agent**: runs pytest, Vitest, Vite build, skills cache warmup, and targeted smoke tests.
5. **VisualQ Agent**: runs FRT/VRT against the Hermes dashboard with LivingColor mounted.
6. **Fix Planner Agent**: converts failures and improvement opportunities into ranked findings.
7. **Self-Healing Agent**: implements safe fixes/improvements in a branch on `livingcolor-plugin` and opens a PR.
8. **Report Writer Agent**: writes `docs/cloud-agent-runs/YYYY-MM-DD-HHMM-result.md` with YAML frontmatter and action-ready instructions for the next agent.

## Task 1: Configure Cursor Cloud Automation

**Files:**
- No required repository file changes.
- Cursor Cloud configuration: create or update the Automation in Cursor.

- [ ] **Step 1: Create the Automation trigger**

Configure a Cursor Automation with:

```text
Name: LivingColor Plugin Autonomous Improvement
Trigger: Git push
Repository: abecms/livingcolor-plugin
Branch: main
Execution: Cursor Cloud Agent
```

Expected behavior: every push to `main` starts a new Cloud Orchestrator Agent run.

- [ ] **Step 2: Configure the primary and context repositories**

Configure the Cloud Agent run with:

```text
Primary target repository:
- abecms/livingcolor-plugin

Context repositories:
- livingcolor-skills
- livingcolor-evolution

Do not treat context repositories as write targets.
```

Expected behavior: the orchestrator can read all three repositories, but only opens plugin fix PRs against `abecms/livingcolor-plugin`.

- [ ] **Step 3: Set the Automation prompt**

Use this prompt as the Automation prompt:

```markdown
You are the Cursor Cloud Orchestrator Agent for LivingColor.

Your mission is to fully automate testing, diagnosis, fixing, and improvement discovery for `abecms/livingcolor-plugin`.

Repository boundaries:

- `abecms/livingcolor-plugin` is the only target repository.
- `livingcolor-skills` and `livingcolor-evolution` are read-only context repositories.
- Do not implement the orchestrator in `livingcolor-plugin`.
- Do not add Cloud Agent runner code to `livingcolor-plugin`.

Trigger:

- This run was triggered by a push to `main`.

Required subagents:

1. Context Collector Agent
2. Hermes Setup Agent
3. Integration Audit Agent
4. Test Agent
5. VisualQ FRT/VRT Agent
6. Fix Planner Agent
7. Self-Healing Agent
8. Report Writer Agent

TVP configuration:

- Jira site: `https://livingcolor.atlassian.net`
- Jira board: `https://livingcolor.atlassian.net/jira/software/c/projects/TVP/boards/234`
- Jira project key: `TVP`
- VCS provider: GitHub
- Target repository: `github.com/abecms/tv5mondeplus-front`
- Integration branch: `preprod`

Validation matrix:

- `pytest tests/test_e2e_smoke.py -q`
- `pytest tests -x -q`
- `cd ui && npm test`
- `cd ui && npm run build`
- `python -m lc_server warm-skills-cache`
- Hermes plugin install/mount smoke when Hermes is available in Cursor Cloud
- VisualQ FRT/VRT against the Hermes dashboard with LivingColor mounted when a dashboard URL is available

Self-healing rules:

- Never push directly to `main`.
- Create a branch named `cursor/livingcolor-cloud-heal-{run_id}` for safe fixes.
- Open a PR against `main` when changes are made.
- Commit `docs/cloud-agent-runs/YYYY-MM-DD-HHMM-result.md` in the same PR.
- If no safe fix is made, still produce the report as the run artifact.
- Do not mutate Jira, Stripe, GitLab, GitHub, or VisualQ through MCP except for safe VisualQ test-runner actions.
- Do not approve VisualQ results.
- Do not expose secrets in logs, commits, PRs, screenshots, or reports.

Report requirements:

- Write Markdown with YAML frontmatter.
- Include status: `passed`, `failed`, `partial`, or `blocked`.
- Include install, config, integration, test, VisualQ, findings, self-healing, and next-agent sections.
- Include exact commands, exit codes, and concise outputs.
- Include clear next steps for a later Cloud Agent.

Final response:

- Return the report path.
- Return the PR URL if one was created.
- State the final run status.
```

Expected behavior: Cursor Cloud owns the orchestration, and no repo-local orchestrator code is needed.

## Task 2: Configure Secrets And Permissions

**Files:**
- No required repository file changes.
- Cursor Cloud secrets configuration.

- [ ] **Step 1: Add required secrets**

Configure these secrets in Cursor Cloud:

```text
OPENROUTER_API_KEY
JIRA_URL=https://livingcolor.atlassian.net
JIRA_USERNAME
JIRA_API_TOKEN
GITHUB_TOKEN
STRIPE_SECRET_KEY
VISUALQ_TEST_RUNNER_TOKEN
```

Expected behavior: Cloud Agents can test Hermes/LLM paths, read Jira, read/write plugin branches and PRs, validate Stripe test mode, and run VisualQ FRT/VRT.

- [ ] **Step 2: Add optional secrets when available**

Configure these only if needed:

```text
GITLAB_PERSONAL_ACCESS_TOKEN
GITLAB_API_URL
STRIPE_TEST_CUSTOMER_ID
VISUALQ_PROJECT_ID
LIVINGCOLOR_TEST_PROJECT_KEY=TVP
LIVINGCOLOR_TEST_GITHUB_REPO=abecms/tv5mondeplus-front
```

Expected behavior: the orchestrator performs deeper compatibility checks without blocking basic plugin validation when optional secrets are missing.

- [ ] **Step 3: Enforce permission boundaries**

Set permissions so that:

```text
GitHub: write only for branch/PR on abecms/livingcolor-plugin
Jira: read-only
GitLab: read-only
Stripe: test mode only
VisualQ: test runner + read reports, no approvals
```

Expected behavior: Cloud Agents can improve the plugin but cannot mutate external production systems.

## Task 3: Define Subagent Contracts In Cursor Cloud

**Files:**
- No required repository file changes.
- Cursor Cloud subagent definitions or prompt sections.

- [ ] **Step 1: Define Context Collector Agent**

Use this subagent instruction:

```markdown
Collect context for the LivingColor plugin improvement run.

Read:

- `README.md`
- `plugin.yaml`
- `livingcolor.skills.lock.json`
- `dashboard/plugin_api.py`
- `agent_surfaces.py`
- `delivery_runtime/AGENTS.md`
- `lc_server/AGENTS.md`
- `docs/superpowers/specs/`
- `docs/superpowers/plans/`
- recent Git commits
- prior `docs/cloud-agent-runs/` reports if present
- context repositories `livingcolor-skills` and `livingcolor-evolution`
- Hermes documentation snapshot

Return:

- repository inventory
- relevant architecture summary
- known missing docs/scripts
- ignored pytest suites
- high-risk areas for this run

Do not modify files.
```

Expected behavior: other agents receive a concise context pack without rereading the whole repo.

- [ ] **Step 2: Define Test Agent**

Use this subagent instruction:

```markdown
Run the LivingColor plugin validation matrix in Cursor Cloud.

Commands:

- `pytest tests/test_e2e_smoke.py -q`
- `pytest tests -x -q`
- `cd ui && npm test`
- `cd ui && npm run build`
- `python -m lc_server warm-skills-cache`

Record:

- command
- working directory
- exit code
- duration
- concise output summary
- ignored pytest suites from `pytest.ini`

Do not fix code. Return structured test results and likely root causes.
```

Expected behavior: test failures are isolated from fixing decisions.

- [ ] **Step 3: Define VisualQ Agent**

Use this subagent instruction:

```markdown
Validate the LivingColor user workflow with VisualQ.

Target:

- Hermes dashboard URL with LivingColor mounted.

If no dashboard URL is available:

- mark VisualQ as `blocked`
- explain exactly what is missing
- do not fail the entire run by itself

When available, run:

- setup health
- FRT for opening LivingColor, selecting TVP, readiness queue, project settings, integrations, Stripe billing, work orders, and gates
- VRT for main plugin screens
- failure retrieval
- diff stats
- quality score

Return:

- VisualQ status
- run IDs
- critical FRT failures
- VRT threshold failures
- links or identifiers for reports

Do not approve VisualQ results.
```

Expected behavior: workflow-level regressions are captured separately from unit/build failures.

- [ ] **Step 4: Define Fix Planner and Self-Healing Agents**

Use this Fix Planner instruction:

```markdown
Convert test, integration, and VisualQ results into ranked plugin findings.

For each finding, include:

- id
- severity
- affected files
- evidence
- suggested fix
- verification command
- whether self-healing is safe

Do not edit code.
```

Use this Self-Healing instruction:

```markdown
Implement only safe plugin fixes in `abecms/livingcolor-plugin`.

Allowed:

- focused bug fixes
- missing tests for the fix
- stale docs directly related to the fix
- generated `docs/cloud-agent-runs/YYYY-MM-DD-HHMM-result.md`

Disallowed:

- orchestrator implementation code inside the plugin
- direct pushes to `main`
- external system mutations
- Stripe live changes
- Jira writes
- VisualQ approvals
- broad architecture rewrites

Create branch:

`cursor/livingcolor-cloud-heal-{run_id}`

Open a PR toward `main` with the fixes and report.
```

Expected behavior: the self-healing agent improves the plugin without becoming part of the plugin.

## Task 4: Define `result.md` Contract For Cloud Agents

**Files:**
- Optional plugin report destination: `docs/cloud-agent-runs/YYYY-MM-DD-HHMM-result.md`

- [ ] **Step 1: Use this YAML frontmatter**

Every report starts with:

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

Expected behavior: a later agent can parse the report without reading the chat history.

- [ ] **Step 2: Use these Markdown sections**

Every report contains:

```markdown
## Executive Summary
## Environment And Context
## Installation Result
## Configuration Result
## Integration Result
## Test Results
## VisualQ FRT/VRT Results
## Findings
## Self-Healing Changes
## Next Agent Instructions
## Appendix
```

Expected behavior: reports stay consistent across runs.

- [ ] **Step 3: Redact secrets**

The Report Writer Agent must redact:

```text
ghp_
github_pat_
glpat-
sk_test_
sk_live_
sk-or-v1-
ATATT
xoxb-
xapp-
password=
secret=
token=
```

Expected behavior: no secret appears in the report, PR body, commit message, or final response.

## Task 5: Configure Self-Healing PR Behavior

**Files:**
- No required repository file changes unless the agent finds a safe plugin fix.

- [ ] **Step 1: Require branch-per-run**

Every self-healing run uses:

```text
cursor/livingcolor-cloud-heal-{run_id}
```

Expected behavior: fixes are isolated from `main`.

- [ ] **Step 2: Require PR content**

Every PR opened by a Cloud Agent includes:

```markdown
## Summary
- What the agent fixed or improved
- Link/path to `result.md`

## Verification
- Exact commands run
- VisualQ run IDs when available

## Safety
- Confirmation that no external systems were mutated
- Confirmation that secrets were redacted
```

Expected behavior: maintainers can review the PR without reading cloud logs.

- [ ] **Step 3: Require no-op reporting**

If no safe fix exists:

```text
Do not create a code PR only to change nothing.
Still preserve `result.md` as a Cursor Cloud artifact.
If Git write is available and policy allows report-only PRs, open a report-only PR.
```

Expected behavior: every run has a useful handoff, but the repo is not spammed with empty fixes.

## Task 6: First Cloud Run Verification

**Files:**
- No planned local file changes.
- Cloud Agents may open a PR against `livingcolor-plugin` if safe fixes are found.

- [ ] **Step 1: Trigger the automation**

Trigger by pushing to `main` or using the Automation's manual test trigger if available.

Expected behavior: Cursor Cloud starts the orchestrator.

- [ ] **Step 2: Verify subagent execution**

Confirm the run includes outputs from:

```text
Context Collector Agent
Hermes Setup Agent
Integration Audit Agent
Test Agent
VisualQ Agent
Fix Planner Agent
Report Writer Agent
Self-Healing Agent, if fixes are safe
```

Expected behavior: no single agent performs the whole workflow monolithically.

- [ ] **Step 3: Verify report output**

Confirm either:

```text
docs/cloud-agent-runs/YYYY-MM-DD-HHMM-result.md committed in the PR
```

or:

```text
result.md preserved as a Cursor Cloud artifact when no PR is opened
```

Expected behavior: the next Cloud Agent can use the report as its starting point.

- [ ] **Step 4: Verify external safety**

Confirm:

```text
No Jira writes
No Stripe live mutations
No VisualQ approvals
No direct main push
No secrets in logs/report/PR
```

Expected behavior: the automation is safe enough to keep enabled on push to `main`.

## Self-Review

Spec coverage:

- Fully automated Cursor Cloud execution is covered by the Automation prompt.
- Agents and subagents manage the full workflow.
- `livingcolor-plugin` is only the target repo, not the orchestrator home.
- `result.md` remains the handoff contract for later agents.
- Self-healing creates PRs in the plugin repo without binding the agents to the repo.
- VisualQ FRT/VRT is included as a dedicated Cloud subagent responsibility.

Boundary check:

- No step asks to add orchestrator code to `livingcolor-plugin`.
- No step asks to add a local Python runner to the plugin.
- No step asks to make external MCP write mutations except VisualQ test runs.

Placeholder scan:

- This plan does not use deferred markers, incomplete sections, or ambiguous implementation steps.
