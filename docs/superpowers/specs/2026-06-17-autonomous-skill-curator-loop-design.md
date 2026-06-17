# Autonomous Daily Skill Curator Loop Design

## Goal

Build a fully automated daily loop that improves `livingcolor-skills` and then updates `livingcolor-plugin` to consume the validated skills version without human intervention.

The loop runs every day at `00:00 UTC` from `livingcolor-evolution`. It may make additive or heavy changes to skills, including prompt rewrites, renames, merges, and archives, but only if automated gates prove the resulting skill set is non-regressive and the plugin can consume it safely.

## Non-Goals

- Do not let `livingcolor-plugin` mutate skills at runtime.
- Do not require human review before merging generated PRs.
- Do not auto-merge a skills change if the plugin lock bump cannot be validated.
- Do not bypass machine-readable audit reports for destructive operations such as merges, renames, or archives.

## Current Context

`livingcolor-plugin` already consumes external skills from `Tamsi/livingcolor-skills` through `livingcolor.skills.lock.json`. The lock records both the requested ref and the exact resolved commit. Runtime prompt enrichment is cache-only and read-only, so a broken or missing cache disables external guidance rather than blocking delivery.

`livingcolor-skills` already has the foundation for versioned skill maintenance: a registry, manifests, bundles, examples, tests, validation, changelog, and evaluator packages.

`livingcolor-evolution` already acts as a curator pipeline. It can fetch official sources, normalize knowledge, audit skills, generate patches, evaluate changes, open PRs against `livingcolor-skills`, and open lock-bump PRs against `livingcolor-plugin`.

The missing piece is an autonomous daily promotion loop that removes human approval from both repositories while adding stronger gates, reports, rollback state, and machine-readable decisions.

## Architecture

`livingcolor-evolution` is the only orchestrator of the daily loop.

At `00:00 UTC`, GitHub Actions checks out:

- `livingcolor-evolution`
- `livingcolor-skills`
- `livingcolor-plugin`

The curator then runs against the `livingcolor-skills` registry using official sources and any usage-signal artifact available to the workflow. The plugin remains a passive consumer. It is only updated after a skills commit has passed gates and been merged.

The loop has two promotion targets:

1. `livingcolor-skills`: receives generated skill changes.
2. `livingcolor-plugin`: receives the exact lock bump to the validated merged skills commit.

## Daily Workflow

The daily workflow runs on this schedule:

```yaml
schedule:
  - cron: "0 0 * * *"
```

Execution flow:

1. Checkout `livingcolor-evolution`, `livingcolor-skills`, and `livingcolor-plugin`.
2. Run the curator against the skills registry.
3. Produce audits, patch decisions, and evaluation gates.
4. If no valid patch exists, publish a no-op report and stop.
5. If valid patches exist, commit them on `curator/daily-YYYY-MM-DD`.
6. Open a `livingcolor-skills` PR.
7. Enable auto-merge for the skills PR.
8. Wait for the skills PR to merge.
9. Resolve the final merged skills commit.
10. Update `livingcolor.skills.lock.json` in `livingcolor-plugin`.
11. Warm the plugin external skills cache against the merged skills commit.
12. Run plugin tests that cover external skills lock parsing, cache materialization, bundle resolution, and prompt injection.
13. Open a `livingcolor-plugin` PR for the lock bump.
14. Enable auto-merge for the plugin PR.
15. Wait for the plugin PR to merge.
16. Publish the final report.

## Automated Gates

Because the loop has no human review gate, automated gates must be strict.

For `livingcolor-skills`, the loop must pass:

- package install
- build
- lint, if configured
- unit tests
- registry validation
- bundle validation
- tests and examples for every touched skill
- before/after evaluations for every touched skill

For each touched skill:

- the post-change score must be greater than or equal to the pre-change score
- no required manifest field may be removed
- the `code-review-pipeline` bundle must remain valid
- any changed output contract must have matching tests

For destructive or structural changes:

- renames must produce a `renameMap`
- archives must produce an `archiveMap`
- merges must describe source skills, destination skill, moved files, and rewritten relative paths
- no rename, archive, or merge may auto-merge without a machine-readable decision record

For `livingcolor-plugin`, the lock bump must pass:

- `livingcolor.skills.lock.json` schema validation
- cache warmup against the exact merged skills commit
- external bundle resolution
- prompt enrichment tests
- focused plugin tests that cover skills-dependent agent behavior

## Auto-Merge Policy

The curator may auto-merge any type of skills change when all gates pass:

- additive prompt guidance
- examples and tests
- prompt rewrites
- manifest changes
- skill renames
- skill merges
- skill archives

No change is auto-merged if:

- a gate fails
- the report cannot be written
- a decision record is missing
- the plugin lock bump cannot be validated
- the final merged skills commit cannot be resolved exactly

The plugin lock bump must point to the final merged skills commit, not the pre-merge branch head.

## Rollback And Known-Good State

`livingcolor-evolution` maintains a known-good state file:

```text
.curator/state/known-good-skills.json
```

It records the last `livingcolor-skills` commit that passed the full skills gates and was successfully consumed by `livingcolor-plugin`.

If the skills PR merges but the plugin bump fails validation, the plugin remains on the previous lock and the run reports the failure.

If the plugin PR merges but post-merge verification fails, the workflow creates an automatic rollback PR that restores `livingcolor.skills.lock.json` to the last known-good skills commit.

Archived skills are moved to `registry/_archive/` before physical deletion is considered. This keeps rollback simple and makes destructive changes auditable.

## Data Contracts

The loop writes stable structured artifacts.

Daily report:

```text
.curator/reports/YYYY-MM-DD.json
.curator/reports/YYYY-MM-DD.md
```

State:

```text
.curator/state/known-good-skills.json
.curator/state/last-run.json
```

The JSON report includes:

- `runId`
- `startedAt`
- `completedAt`
- `findingsCount`
- `knowledgeCount`
- `audits`
- `patchDecisions`
- `patches`
- `evaluationGates`
- `renameMap`
- `archiveMap`
- `skillsPromotion`
- `pluginPromotion`
- `rollback`

Core decision types:

```text
PatchDecision = keep | patch | merge | rename | archive
GateResult = passed | failed
PromotionResult = skipped | opened | merged | failed | rolled_back
```

`livingcolor.skills.lock.json` remains the plugin runtime contract and must continue to include:

- `repo`
- `ref`
- `resolvedCommit`
- `bundle`
- `skills`

## Error Handling

If the curator finds no useful change, the workflow publishes a no-op report and exits successfully.

If skill gates fail, no skills PR is auto-merged. The run publishes a failed report with gate details.

If the skills PR cannot merge, the plugin bump is skipped.

If the plugin cache warmup or tests fail, the plugin PR is not auto-merged and the known-good state is unchanged.

If a post-merge plugin verification fails, the workflow creates a rollback PR against `livingcolor-plugin`.

If GitHub API operations fail, the run records the failure and leaves both repositories at their last merged state.

## Testing Strategy

`livingcolor-evolution` tests:

- daily workflow schedule is `0 0 * * *`
- no-op curator runs produce a report and no PR
- valid patches create a skills PR
- failing skill gates block auto-merge
- non-regressive scores allow promotion
- destructive changes require `renameMap` or `archiveMap`
- plugin lock bump targets the exact merged skills commit
- plugin validation failure blocks bump auto-merge
- rollback restores the last known-good skills commit

`livingcolor-skills` tests:

- registry validation
- bundle validation
- examples and tests for touched skills
- before/after skill evaluation
- rename and archive map validation

`livingcolor-plugin` tests:

- lock parsing
- external skills cache materialization
- bundle resolution
- prompt enrichment
- skills-dependent agent prompt tests

## Success Criteria

Every day at `00:00 UTC`, the loop either:

- improves `livingcolor-skills`, auto-merges the validated skills change, auto-merges the plugin lock bump, and updates known-good state; or
- produces a no-op or failed report without changing the plugin runtime lock.

The system is considered successful when:

- no human approval is required for successful runs
- every merged change has machine-readable audit evidence
- no plugin lock bump points to an unvalidated skills commit
- destructive skill operations are reversible through maps and archive state
- failed runs leave both repositories in a known-good runtime state
