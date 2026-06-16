# Analyst Async Optimization Design

## Goal

Make the LivingColor Analyst daily scan faster and more reliable while keeping the analysis genuinely LLM-based.

The current daily scan analyzes in-scope Jira tickets one after another. Each ticket starts a full Hermes analyst conversation, so a small backlog can still take several minutes. Hermes now supports asynchronous subagents, which allows LivingColor to fan out independent ticket analyses while preserving per-ticket reasoning, structured outputs, and traceability.

The target outcome is a daily analysis pipeline that can analyze several Jira tickets concurrently, skip unchanged tickets on automatic runs, expose per-ticket failures without losing the whole run, and produce higher-quality readiness decisions through a prompt and schema tailored to LivingColor.

## Non-Goals

- Do not replace LLM readiness analysis with heuristics.
- Do not silently fall back to heuristic analysis when the LLM fails.
- Do not give the daily analyst write access to Jira, VCS, terminal, or filesystem tools.
- Do not require a full repository checkout or code context for daily ticket triage.
- Do not build live subagent progress UI in the first implementation.
- Do not change developer, planner, publisher, or sprint reporter execution semantics.

## Current Problems

`ReadinessScanner.scan_project()` fetches Jira issues, filters them, and calls `_analysis_runner` inside a synchronous loop. This makes the scan duration roughly `ticket_count * LLM_latency`.

The analyst backend currently uses `AIAgent.run_conversation()` for each ticket. That is appropriate for multi-step agents with tools, but the daily analyst has no toolsets and only needs a structured readiness JSON result. Starting a full agent loop for every ticket adds overhead and makes failures harder to isolate.

Automatic and manual daily runs currently behave similarly. They reprocess every in-scope ticket, even when the Jira snapshot has not changed since the last successful analysis. This wastes model calls and delays routine scheduled scans.

LLM output quality is also affected by prompt drift. The plugin-owned readiness model now includes `ready`, `needs_clarification`, `not_ready`, and `not_development`, while older analyst skills and schemas still emphasize `ready` / `not_ready`, story points, and formal Gherkin-style acceptance criteria. This can make the analyst classify too many implementation-ready technical tickets as `needs_clarification`.

## Selected Approach

Use a dedicated asynchronous analysis dispatcher backed by Hermes analyst subagents.

The implementation introduces a `ReadinessAnalysisDispatcher` that sits between scope filtering and database upserts. It receives in-scope snapshots, decides whether each ticket should be analyzed or reused from cache, launches up to three LLM analyses concurrently, and returns per-ticket outcomes.

The primary backend is `HermesSubagentAnalystBackend`. It launches isolated read-only analyst subagents for each ticket and validates their structured JSON output. A temporary `HermesConversationAnalystBackend` may remain available as a compatibility fallback if the Hermes subagent API is unavailable, but it must still be explicit in metrics and logs. It must not be confused with heuristic fallback.

Manual dashboard runs force re-analysis of all in-scope tickets. Automatic runs are incremental and reuse cached results when the relevant Jira input has not changed.

## Component Boundaries

### `ReadinessScanner`

The scanner remains responsible for:

- Fetching Jira issues through the configured integration.
- Applying ticket scope and excluded-ticket filters.
- Dismissing records that moved out of scope.
- Upserting successful analysis records.
- Emitting readiness events.

It should no longer own how multiple LLM calls are scheduled.

### `ReadinessAnalysisDispatcher`

The dispatcher owns:

- Stable analysis input hashing.
- Cache lookup and force-run behavior.
- Concurrency-limited fan-out with a default concurrency of `3`.
- Per-ticket timeout and failure capture.
- Aggregating outcomes into scan metrics.

The dispatcher returns structured outcomes rather than mutating the database directly. This keeps persistence rules centralized in the scanner and makes the dispatcher easier to test.

### `AnalystBackend`

The backend interface abstracts the LLM execution mechanism.

```python
class AnalystBackend(Protocol):
    async def analyze_ticket(
        self,
        snapshot: dict[str, Any],
        *,
        project_key: str,
        run_id: str,
    ) -> dict[str, Any]:
        ...
```

`HermesSubagentAnalystBackend` is the default production implementation. Test suites use deterministic fake backends that can assert concurrency and failure behavior.

## Analysis Flow

The daily run flow becomes:

1. Fetch Jira tickets.
2. Filter out invalid, excluded, and out-of-scope tickets.
3. Build an `analysis_input_hash` for every remaining ticket.
4. For automatic runs, reuse existing successful analysis records when the hash matches.
5. For manual runs, force every in-scope ticket through LLM analysis.
6. Launch LLM analyses through the dispatcher with concurrency `3`.
7. Persist successful results.
8. Preserve previous valid analysis when a forced analysis fails.
9. Mark tickets with no previous valid analysis as `analysis_failed`.
10. Rebuild execution queue, sprint backlog, and project memory from the resulting records.

The manual dashboard button remains the user's "fresh LLM read" action. Scheduled runs prioritize speed and only analyze changed tickets.

## Cache Policy

The analysis input hash is computed from a canonical JSON payload containing the fields that affect readiness:

- Jira key.
- Summary/title.
- Description.
- Issue type.
- Status and status category.
- Labels.
- Assignee display/email fields.
- Comments, including author, created timestamp, and body.
- Attachment metadata and extracted content when present.
- Project key.
- Relevant project mapping or default repo version marker.
- Analyst prompt/schema version.

The hash is stored with the readiness record or in a dedicated cache table. The first implementation can add fields to `readiness_records` if that keeps queries simple:

- `analysis_input_hash`
- `last_analysis_error`
- `last_analysis_failed_at`
- `analysis_backend`

Existing records without a hash are treated as unknown. The next automatic run analyzes them once and then benefits from caching.

## Failure Policy

The dispatcher is fail-soft.

Per-ticket outcomes are:

- `success`: LLM output validated and ready to persist.
- `cached`: existing successful analysis reused.
- `failed`: LLM, subagent, timeout, or parser failure.
- `skipped`: ticket was invalid or excluded before analysis.

A failed ticket does not fail the full daily run. Successful analyses are persisted and downstream queues are rebuilt.

If a ticket fails and has a previous valid analysis, LivingColor keeps the previous readiness status and surfaces the latest error separately. If the ticket has no previous valid analysis, the record is stored with `readiness_status = 'analysis_failed'` so the dashboard can show that the ticket exists but was not classified.

There is no silent heuristic fallback. If a compatibility backend is used because subagents are unavailable, the pipeline records `backend = 'hermes_conversation'`. If a heuristic result is ever used for a development-only emergency path, it must be explicitly labeled as non-LLM and never presented as normal LLM analysis.

## Hermes Subagent Backend

The subagent backend launches one read-only Hermes analyst subagent per ticket.

Each subagent receives:

- A stable task id such as `delivery-analyst-{JIRA_KEY}-{RUN_ID}`.
- A compact analyst system prompt.
- The normalized Jira snapshot.
- Project metadata needed for classification.
- No write-capable tools.
- A per-ticket timeout.

The backend validates final output through the plugin-owned parser before returning success. Parse failures are captured as ticket failures, not converted into heuristics.

Concurrency is fixed at `3` for the first version. This is intentionally conservative for provider rate limits and local Hermes stability. Configuration can be added later if operational data shows that higher concurrency is safe.

## Prompt And Schema

The daily analyst prompt should be short and plugin-owned.

It should define statuses in LivingColor terms:

- `ready`: enough information to implement safely.
- `needs_clarification`: missing product or QA information blocks implementation.
- `not_ready`: blocked, contradictory, or technically impossible right now.
- `not_development`: editorial, support, process-only, or otherwise outside development delivery.

The prompt must not require formal Gherkin acceptance criteria when the expected code change is clear. Technical tickets such as SEO JSON-LD, schema.org metadata, dataLayer tracking, Airship properties, BFF behavior, and frontend playback/access bugs are development work unless the ticket explicitly says otherwise.

`livingcolor-skills` remains advisory guidance. The plugin-owned prompt and schema are authoritative when older skill content conflicts with LivingColor fields. `analyst-readiness` should be aligned with the current status model and included directly in the analyst prompt or loaded into the subagent context in a deterministic way.

The schema includes the stable fields already consumed by the runtime:

```json
{
  "readinessScore": 0,
  "readinessStatus": "ready",
  "analysisSummary": "...",
  "blockers": [],
  "recommendedRepos": [],
  "confidence": 0.0,
  "estimatedDays": 1.0
}
```

Additional fields such as `classificationRationale` and `missingInformation` may be accepted and stored later, but downstream behavior must continue to depend on the stable fields above.

## API And UI

The daily analysis response keeps the existing `scan`, `qualification`, `executionQueue`, and `selectedSprint` fields for compatibility.

The daily analysis request accepts an explicit `force` boolean. The dashboard `Run analysis` button sends `force: true`. Scheduled or automation-triggered runs send `force: false` or omit the field, which defaults to incremental mode.

It adds an `analysisDispatch` block:

```json
{
  "backend": "hermes_subagent",
  "concurrency": 3,
  "success": 6,
  "cached": 1,
  "failed": 1,
  "forced": true,
  "durationMs": 74000,
  "items": [
    {
      "jiraKey": "TVP-2391",
      "status": "success",
      "backend": "hermes_subagent",
      "durationMs": 24120
    }
  ]
}
```

The dashboard completion message should report:

- Tickets in scope.
- Tickets analyzed by LLM.
- Tickets reused from cache.
- Tickets failed.
- Tickets needing clarification.

The dashboard should also expose per-ticket analysis failures. A ticket with a previous valid result can remain in the sprint backlog with a warning badge. A ticket without any valid result appears as `analysis_failed` and cannot be promoted.

Live progress is deferred. The first implementation can keep the current polling model and update the final run summary.

## Data Model

Add persistence for cache and failure metadata.

Recommended first version:

- Add nullable columns to `readiness_records`:
  - `analysis_input_hash TEXT`
  - `analysis_backend TEXT`
  - `last_analysis_error TEXT`
  - `last_analysis_failed_at TEXT`
- Allow `analysis_failed` as a readiness status in UI and queue filtering.
- Store dispatcher metrics in `daily_analysis_runs.pipeline_json`.

This avoids a second cache table until there is a need to retain historical analysis attempts.

## Testing Strategy

Backend tests:

- The dispatcher never runs more than three analyses concurrently.
- Automatic runs reuse cached analysis when the input hash matches.
- Manual runs force LLM re-analysis even when the hash matches.
- A failed ticket does not prevent successful tickets from being persisted.
- A failed ticket with a previous valid analysis keeps that previous readiness status and records the error.
- A failed ticket with no previous analysis becomes `analysis_failed`.
- No code path silently converts LLM failure into heuristic readiness analysis.
- The compact prompt classifies technical tickets such as SEO JSON-LD and dataLayer changes as development work when the change is sufficiently specified.

UI tests:

- The run summary shows analyzed, cached, and failed counts.
- `analysis_failed` tickets are visible and not promotable.
- Tickets with previous valid analysis and a latest error show a warning.
- Manual `Run analysis` sends `force: true`; scheduled runs use incremental mode.

Integration tests:

- A small TVP-like backlog with eight tickets completes through a fake async backend in bounded time.
- The daily pipeline preserves LLM analysis and does not re-run heuristic qualification over it.

## Rollout

Ship in phases:

1. Add persistence fields and parser/status support.
2. Introduce `ReadinessAnalysisDispatcher` with fake/test backend.
3. Wire scanner and daily pipeline to dispatcher.
4. Add Hermes subagent backend.
5. Add cache behavior and manual force mode.
6. Update UI summaries and failure display.
7. Remove old silent heuristic fallback from readiness scan paths.

The first production rollout should default to concurrency `3` and keep the old conversation backend available only as an explicitly labeled compatibility fallback.

## Success Criteria

- Manual daily analysis of eight TVP tickets completes substantially faster than the current serial run, with a target below two minutes under normal provider latency.
- Automatic daily analysis is near-instant when no Jira inputs changed.
- LLM failures are visible per ticket and do not erase successful analyses.
- The dashboard clearly explains what happened in a run.
- Technical TVP tickets are not downgraded solely because they lack formal Gherkin acceptance criteria.
- No result presented as LLM analysis comes from a silent heuristic fallback.
