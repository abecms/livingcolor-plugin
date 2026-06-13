# LivingColor Repository Interconnection Design

## Goal

Connect `livingcolor-plugin`, `livingcolor-skills`, and `livingcolor-evolution` without merging their responsibilities.

The first product outcome is better delivery quality inside `livingcolor-plugin`: external generic skills should enrich readiness, planning, and review with project stack, tracker, and VCS context. The second outcome is an autonomous improvement loop: `livingcolor-evolution` keeps `livingcolor-skills` current and opens a follow-up bump pull request in `livingcolor-plugin` when a validated skills version is ready to consume.

## Non-Goals

- Do not merge the three repositories into one monorepo.
- Do not make `livingcolor-plugin` depend on a sibling checkout of `livingcolor-skills`.
- Do not replace the delivery-critical developer and publisher agents in the first slice.
- Do not consume the moving `main` branch of `livingcolor-skills` at runtime.
- Do not let a skills bump modify plugin runtime code in the same pull request.
- Do not require `livingcolor-evolution` to run inside the plugin process.

## Repository Responsibilities

`livingcolor-plugin` remains the delivery runtime and product surface. It owns Work Orders, gates, Jira readiness, GitLab/GitHub VCS integration, agent provisioning, the Hermes dashboard, and the local runtime state.

`livingcolor-skills` becomes the versioned knowledge dependency. It provides generic, tested role skills such as `ticket-analyst`, `code-architect`, `qa-reviewer`, `security-auditor`, and the `code-review-pipeline` bundle.

`livingcolor-evolution` remains an external automation. It monitors role-aligned sources, audits and updates `livingcolor-skills`, runs evaluations, opens skills pull requests, and then opens a plugin pull request that bumps the pinned skills reference.

## Selected Approach

Use a pinned GitHub source with a validated bundle.

`livingcolor-plugin` reads a lock file that points to an explicit `Tamsi/livingcolor-skills` commit or tag. It materializes that version into a local cache and exposes a stable skill view to agent provisioning and gate execution. In development and production, the lock file is the source of truth.

This keeps plugin behavior reproducible and lets `livingcolor-evolution` update skills through reviewable pull requests rather than implicit runtime updates.

## Plugin Skills Boundary

Add a small integration boundary under `lc_server/integrations/skills/`.

Responsibilities:

- Read and validate `livingcolor.skills.lock.json`.
- Resolve the configured GitHub repo and pinned ref to a commit.
- Materialize the pinned registry into a cache under the LivingColor home, for example `~/.hermes/livingcolor/skills-cache/`.
- Validate that required skills and bundles exist.
- Convert or expose external skill content in the format the current Hermes agent provisioning can consume.
- Report availability and provenance to logs, API responses, and future UI surfaces.

The boundary should not know delivery gate internals. It should return a neutral resolved bundle object, including skill names, prompt paths, source ref, resolved commit, and validation status.

## Lock File

Create a root-level lock file in `livingcolor-plugin`. The example below uses a tag-like ref and a shortened example commit for readability; the real file stores the full resolved commit SHA.

```json
{
  "repo": "Tamsi/livingcolor-skills",
  "ref": "v0.1.0",
  "resolvedCommit": "0123456789abcdef0123456789abcdef01234567",
  "bundle": "code-review-pipeline",
  "skills": [
    "ticket-analyst",
    "code-architect",
    "qa-reviewer",
    "security-auditor"
  ],
  "updatedBy": "livingcolor-evolution"
}
```

Rules:

- `repo`, `ref`, `resolvedCommit`, `bundle`, and `skills` are required.
- `repo` must be `Tamsi/livingcolor-skills` in the first version.
- `ref` may be a tag or commit-like ref, but the resolver must store and verify `resolvedCommit`.
- The plugin must never fetch from an unpinned branch at runtime.
- A bump pull request should change only this lock file and, optionally, a generated changelog entry.

## Context Contract

`livingcolor-plugin` produces the context that generic skills need.

The first version should generate a markdown context block with these sections:

```markdown
## Project Stack
Languages, frameworks, versions, architecture notes, conventions, and relevant repository structure.

## Ticket Tracker
tracker: jira

## VCS
vcs: gitlab | github

## Delivery Context
Ticket key, summary, acceptance criteria, target repository, candidate files, project conventions, and relevant git history.
```

`Project Stack` is produced from the existing repository scan and architecture profile code. The output is stable enough for tests and readable enough for humans. The first implementation stores the rendered markdown under LivingColor-managed runtime state, not inside the customer repository checkout.

`Ticket Tracker` is `jira` in the first version because the current product remains Jira-first. The format should leave room for Linear, Asana, or other trackers later.

`VCS` must use the provider selected by the project configuration. This aligns with the GitHub VCS provider boundary already being introduced in the plugin.

## Gate Integration

External generic skills should enrich delivery quality without replacing delivery-critical flows in the first slice.

Readiness:

- `ticket-analyst` enriches `analyst-readiness` output without replacing the plugin-owned readiness status model in the first version.
- The plugin keeps its own readiness JSON schema and status interpretation.
- External output is mapped into plugin-owned fields only after schema validation.

Planning:

- `planner-gate1` remains the primary planning skill.
- `code-architect` is injected as supporting context when the repository scan is available.
- The approved Gate 1 plan format remains owned by the plugin.

Code Review Gate:

- `code-review-pipeline` is the first strong integration point.
- The bundle runs architecture, QA, and security review against the delivery diff and generated context.
- Findings become structured review input for the human gate.

Developer and Publisher:

- The developer agent keeps bundled delivery skills such as `developer-workspace`, `patch-quality`, and merge-conflict skills.
- The publisher agent keeps bundled publication rules because they enforce Git, MCP, and review request safety.
- External generic skills do not get permission to push branches, modify tickets, or create review requests.

## Evolution Pipeline

`livingcolor-evolution` should run a two-pull-request pipeline.

1. Fetch role-aligned sources from its configured source list.
2. Extract, normalize, and map findings to `livingcolor-skills` roles.
3. Patch `livingcolor-skills` prompts, tests, examples, or schemas.
4. Run `@hermes/evaluator` and the repository test suite.
5. Open a pull request in `Tamsi/livingcolor-skills`.
6. After the skills change is merged or tagged, resolve the new commit.
7. Open a second pull request in `livingcolor-plugin` that bumps `livingcolor.skills.lock.json`.
8. Let plugin CI validate lock parsing, cache materialization, context generation, and gate fixtures.

The plugin does not consume the skills update until its own bump pull request is reviewed and merged.

## Failure Handling

The first version should fail open for delivery and fail closed for external skills.

- Missing lock file: continue with bundled delivery skills.
- Invalid lock file: continue with bundled delivery skills and record a visible integration warning.
- GitHub fetch failure: use the last valid cache if it matches the lock; otherwise disable external skills for the run.
- Missing bundle or skill: disable the external bundle for the run.
- Invalid external skill output: keep the human gate, mark the external analysis as unusable, and preserve raw diagnostics for debugging.
- Resolved commit mismatch: reject the external bundle and surface a provenance error.

Rollback is a lock-file revert. Returning to a previous `resolvedCommit` should restore the previous external skills behavior after cache refresh.

## Security And Provenance

- Do not log GitHub tokens or authenticated clone URLs.
- Prefer public GitHub archive downloads when the skills repo is public; authenticated fetch is only needed for private sources later.
- Cache paths must stay under LivingColor-managed state.
- External skills are read-only knowledge inputs in the first version.
- A skills bump pull request must not change plugin executable code.
- Store enough provenance to answer which skills commit influenced a gate result.

## Testing Strategy

Plugin tests:

- Lock file parsing, validation, and resolved commit checks.
- Cache materialization with fixtures.
- Missing, invalid, and stale cache fallback behavior.
- Context markdown generation from repository scan fixtures.
- Project provider context generation for GitLab and GitHub.
- Agent provisioning behavior when external skills are available or unavailable.
- Code review gate fixture tests that map external findings into plugin-owned review data.

Skills tests:

- `pnpm test`.
- `hermes validate` for changed skills.
- Evaluator cases for multiple stacks and tracker context.

Evolution tests:

- Source fetcher and role routing fixtures.
- End-to-end mock run that updates `livingcolor-skills`.
- Bump pull request generation that changes only the plugin lock file and optional changelog.

## Rollout Plan

Phase 1: add the lock file, skills resolver, cache materialization, and status reporting with no gate behavior change.

Phase 2: generate the context contract from existing repository scan data and expose it to gates.

Phase 3: integrate `code-review-pipeline` into the code review gate behind fallback behavior.

Phase 4: allow `ticket-analyst` and `code-architect` to enrich readiness and planning, while preserving plugin-owned schemas.

Phase 5: extend `livingcolor-evolution` to open plugin lock bump pull requests after successful skills changes.

## Open Extension Points

- Add tracker providers beyond Jira without changing skill prompts.
- Add GitHub Enterprise or private skills registries by extending the source resolver.
- Promote external skills from optional review input to stricter gate criteria after enough fixture coverage exists.
- Add a UI panel that shows external skills provenance for a Work Order or gate.
