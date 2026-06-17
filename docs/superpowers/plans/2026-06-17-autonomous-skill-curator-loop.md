# Autonomous Skill Curator Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully automated daily `00:00 UTC` curator loop that improves `livingcolor-skills`, auto-merges validated changes, then auto-merges a validated `livingcolor-plugin` skills lock bump.

**Architecture:** `livingcolor-evolution` remains the single orchestrator. It records structured decisions, applies skill changes, gates them, promotes the skills PR with auto-merge, validates the exact merged commit in `livingcolor-plugin`, then promotes or rolls back the plugin lock. The plugin remains a passive runtime consumer through `livingcolor.skills.lock.json`.

**Tech Stack:** TypeScript, pnpm workspaces, Vitest, GitHub REST API, GitHub Actions, `livingcolor-skills` registry/evaluator, `livingcolor-plugin` Python skill-cache checks.

---

## File Structure

Create focused units in `livingcolor-evolution`:

- `packages/core/src/application/curator-state.ts` owns `known-good-skills.json` and `last-run.json` read/write logic.
- `packages/core/src/application/decision-contracts.ts` owns validation for `PatchDecision`, rename maps, archive maps, and promotion records.
- `packages/github/src/auto-merge.ts` owns GitHub auto-merge, PR polling, and merged commit resolution.
- `packages/github/src/skills-promotion.ts` owns skills branch creation, patch commits, PR creation, auto-merge, and merge result.
- `packages/github/src/plugin-rollback.ts` owns plugin lock rollback PR creation.
- `packages/scheduler/src/plugin-validation.ts` owns local plugin lock/cache validation commands.
- `packages/scheduler/src/daily-autonomous.ts` owns the daily end-to-end workflow composition.

Modify existing files:

- `packages/core/src/domain/types.ts` adds structured report, decision, promotion, and state types.
- `packages/core/src/ports/index.ts` exposes ports for state, skills promotion, auto-merge, plugin validation, and rollback.
- `packages/core/src/application/report-writer.ts` writes date-based report paths and includes decisions/promotions.
- `packages/refactoring/src/index.ts` emits structured `PatchDecision[]` alongside `GitPatch[]`.
- `packages/evaluation/src/index.ts` validates non-regressive gates and exposes gate details.
- `packages/github/src/index.ts` exports the new GitHub services.
- `packages/github/src/plugin-lock-bump.ts` auto-merges validated plugin lock bumps and returns a `PromotionResult`.
- `packages/scheduler/src/index.ts` wires the daily autonomous workflow and keeps existing dry-run commands working.
- `packages/cli/src/index.ts` adds `curator daily`.
- `.github/workflows/curator-weekly.yml` becomes the daily autonomous workflow with cron `0 0 * * *`.

---

### Task 1: Core Decision And Report Contracts

**Files:**
- Modify: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/core/src/domain/types.ts`
- Modify: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/core/src/ports/index.ts`
- Create: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/core/src/application/decision-contracts.ts`
- Test: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/core/src/application/decision-contracts.test.ts`

- [ ] **Step 1: Write decision contract tests**

Create `packages/core/src/application/decision-contracts.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import {
  assertDestructiveDecisionsHaveMaps,
  buildNoopPromotionResult,
} from './decision-contracts.js';
import type { PatchDecision } from '../domain/types.js';

describe('decision contracts', () => {
  it('allows additive patch decisions without rename or archive maps', () => {
    const decisions: PatchDecision[] = [
      {
        kind: 'patch',
        skill: 'ticket-analyst',
        rationale: 'Add missing readiness guidance from audit.',
        files: ['registry/ticket-analyst/prompt.md'],
      },
    ];

    expect(() =>
      assertDestructiveDecisionsHaveMaps(decisions, { renameMap: {}, archiveMap: {} }),
    ).not.toThrow();
  });

  it('rejects rename decisions without a rename map entry', () => {
    const decisions: PatchDecision[] = [
      {
        kind: 'rename',
        skill: 'ticket-analyst',
        targetSkill: 'delivery-ticket-analyst',
        rationale: 'Align skill name with delivery domain.',
        files: ['registry/ticket-analyst/skill.yaml'],
      },
    ];

    expect(() =>
      assertDestructiveDecisionsHaveMaps(decisions, { renameMap: {}, archiveMap: {} }),
    ).toThrow(/renameMap/i);
  });

  it('rejects archive decisions without an archive map entry', () => {
    const decisions: PatchDecision[] = [
      {
        kind: 'archive',
        skill: 'old-skill',
        rationale: 'Unused and superseded.',
        files: ['registry/old-skill'],
      },
    ];

    expect(() =>
      assertDestructiveDecisionsHaveMaps(decisions, { renameMap: {}, archiveMap: {} }),
    ).toThrow(/archiveMap/i);
  });

  it('builds a no-op promotion result with stable fields', () => {
    expect(buildNoopPromotionResult('skills')).toEqual({
      target: 'skills',
      status: 'skipped',
      pullRequest: null,
      mergedCommit: null,
      reason: 'No valid changes to promote.',
    });
  });
});
```

- [ ] **Step 2: Run the new test and verify failure**

Run:

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
pnpm --filter @curator/core test -- decision-contracts.test.ts
```

Expected: FAIL because `decision-contracts.ts` and the new types do not exist.

- [ ] **Step 3: Add core domain types**

In `packages/core/src/domain/types.ts`, add these types after `GitPatch`:

```ts
export type PatchDecisionKind = 'keep' | 'patch' | 'merge' | 'rename' | 'archive';

export interface PatchDecision {
  kind: PatchDecisionKind;
  skill: string;
  rationale: string;
  files: string[];
  targetSkill?: string;
  sourceSkills?: string[];
}

export type GateStatus = 'passed' | 'failed';

export interface RenameMapEntry {
  from: string;
  to: string;
  reason: string;
}

export interface ArchiveMapEntry {
  skill: string;
  archivePath: string;
  reason: string;
}

export interface CuratorDecisionMaps {
  renameMap: Record<string, RenameMapEntry>;
  archiveMap: Record<string, ArchiveMapEntry>;
}

export type PromotionStatus = 'skipped' | 'opened' | 'merged' | 'failed' | 'rolled_back';
export type PromotionTarget = 'skills' | 'plugin';

export interface PromotionPullRequest {
  url: string;
  branch: string;
  number: number;
}

export interface PromotionResult {
  target: PromotionTarget;
  status: PromotionStatus;
  pullRequest: PromotionPullRequest | null;
  mergedCommit: string | null;
  reason: string;
}

export interface KnownGoodSkillsState {
  skillsRepo: 'Tamsi/livingcolor-skills';
  resolvedCommit: string;
  validatedAt: string;
  pluginRepo: 'Tamsi/livingcolor-plugin';
  pluginCommit: string;
}

export interface LastRunState {
  runId: string;
  startedAt: string;
  completedAt: string;
  status: 'success' | 'failed' | 'noop';
  reportJsonPath: string;
  reportMarkdownPath: string;
}
```

Extend `CuratorRunReport`:

```ts
export interface CuratorRunReport {
  runId: string;
  startedAt: string;
  completedAt: string;
  findingsCount: number;
  knowledgeCount: number;
  audits: AuditReport[];
  patchDecisions: PatchDecision[];
  patches: GitPatch[];
  evaluationGates: EvaluationGate[];
  renameMap: Record<string, RenameMapEntry>;
  archiveMap: Record<string, ArchiveMapEntry>;
  skillsPromotion: PromotionResult;
  pluginPromotion: PromotionResult;
  rollback: PromotionResult | null;
  markdownPath: string;
  jsonPath: string;
}
```

- [ ] **Step 4: Add decision contract helpers**

Create `packages/core/src/application/decision-contracts.ts`:

```ts
import type {
  CuratorDecisionMaps,
  PatchDecision,
  PromotionResult,
  PromotionTarget,
} from '../domain/types.js';

export function assertDestructiveDecisionsHaveMaps(
  decisions: PatchDecision[],
  maps: CuratorDecisionMaps,
): void {
  for (const decision of decisions) {
    if (decision.kind === 'rename' && !maps.renameMap[decision.skill]) {
      throw new Error(`Missing renameMap entry for ${decision.skill}`);
    }
    if (decision.kind === 'archive' && !maps.archiveMap[decision.skill]) {
      throw new Error(`Missing archiveMap entry for ${decision.skill}`);
    }
    if (decision.kind === 'merge') {
      const sources = decision.sourceSkills ?? [];
      if (sources.length === 0 || !decision.targetSkill) {
        throw new Error(`Merge decision for ${decision.skill} must include sourceSkills and targetSkill`);
      }
    }
  }
}

export function buildNoopPromotionResult(target: PromotionTarget): PromotionResult {
  return {
    target,
    status: 'skipped',
    pullRequest: null,
    mergedCommit: null,
    reason: 'No valid changes to promote.',
  };
}
```

- [ ] **Step 5: Update ports**

In `packages/core/src/ports/index.ts`, import the new types and add:

```ts
import type {
  KnownGoodSkillsState,
  LastRunState,
  PromotionResult,
} from '../domain/types.js';

export interface CuratorStatePort {
  readKnownGood(): Promise<KnownGoodSkillsState | null>;
  writeKnownGood(state: KnownGoodSkillsState): Promise<void>;
  writeLastRun(state: LastRunState): Promise<void>;
}

export interface SkillsPromotionPort {
  promote(request: {
    branch: string;
    patches: GitPatch[];
    report: CuratorRunReport;
  }): Promise<PromotionResult>;
}

export interface PluginValidationPort {
  validate(request: {
    pluginPath: string;
    skillsPath: string;
    resolvedCommit: string;
  }): Promise<{ passed: boolean; output: string[] }>;
}

export interface PluginRollbackPort {
  rollback(request: {
    knownGood: KnownGoodSkillsState;
    reason: string;
  }): Promise<PromotionResult>;
}
```

Replace the existing `PluginLockBumpPort` return type in the same file:

```ts
export interface PluginLockBumpPort {
  create(request: PluginLockBumpRequest): Promise<PromotionResult | null>;
}
```

- [ ] **Step 6: Run core tests**

Run:

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
pnpm --filter @curator/core test -- decision-contracts.test.ts
pnpm --filter @curator/core typecheck
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
git add packages/core/src/domain/types.ts packages/core/src/ports/index.ts packages/core/src/application/decision-contracts.ts packages/core/src/application/decision-contracts.test.ts
git commit -m "feat: add autonomous curator decision contracts"
```

---

### Task 2: Curator State And Date-Based Reports

**Files:**
- Create: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/core/src/application/curator-state.ts`
- Modify: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/core/src/application/report-writer.ts`
- Modify: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/core/src/index.ts`
- Test: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/core/src/application/curator-state.test.ts`
- Test: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/core/src/application/report-writer.test.ts`

- [ ] **Step 1: Write state tests**

Create `packages/core/src/application/curator-state.test.ts`:

```ts
import { mkdtemp, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { describe, expect, it } from 'vitest';
import { JsonCuratorStateStore } from './curator-state.js';

describe('JsonCuratorStateStore', () => {
  it('returns null when known-good state is missing', async () => {
    const root = await mkdtemp(join(tmpdir(), 'curator-state-'));
    const store = new JsonCuratorStateStore(join(root, '.curator', 'state'));

    await expect(store.readKnownGood()).resolves.toBeNull();
  });

  it('writes and reads known-good state', async () => {
    const root = await mkdtemp(join(tmpdir(), 'curator-state-'));
    const store = new JsonCuratorStateStore(join(root, '.curator', 'state'));

    await store.writeKnownGood({
      skillsRepo: 'Tamsi/livingcolor-skills',
      resolvedCommit: '0123456789abcdef0123456789abcdef01234567',
      validatedAt: '2026-06-17T00:00:00.000Z',
      pluginRepo: 'Tamsi/livingcolor-plugin',
      pluginCommit: 'abcdefabcdefabcdefabcdefabcdefabcdefabcd',
    });

    await expect(store.readKnownGood()).resolves.toEqual({
      skillsRepo: 'Tamsi/livingcolor-skills',
      resolvedCommit: '0123456789abcdef0123456789abcdef01234567',
      validatedAt: '2026-06-17T00:00:00.000Z',
      pluginRepo: 'Tamsi/livingcolor-plugin',
      pluginCommit: 'abcdefabcdefabcdefabcdefabcdefabcdefabcd',
    });
  });

  it('writes last-run state with stable file name', async () => {
    const root = await mkdtemp(join(tmpdir(), 'curator-state-'));
    const stateDir = join(root, '.curator', 'state');
    const store = new JsonCuratorStateStore(stateDir);

    await store.writeLastRun({
      runId: 'run-1',
      startedAt: '2026-06-17T00:00:00.000Z',
      completedAt: '2026-06-17T00:03:00.000Z',
      status: 'success',
      reportJsonPath: '.curator/reports/2026-06-17.json',
      reportMarkdownPath: '.curator/reports/2026-06-17.md',
    });

    const raw = await readFile(join(stateDir, 'last-run.json'), 'utf8');
    expect(JSON.parse(raw)).toMatchObject({ runId: 'run-1', status: 'success' });
  });
});
```

- [ ] **Step 2: Write report writer test**

Create `packages/core/src/application/report-writer.test.ts`:

```ts
import { mkdtemp } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { describe, expect, it } from 'vitest';
import { MarkdownReportWriter } from './report-writer.js';
import type { CuratorRunReport } from '../domain/types.js';

function report(): CuratorRunReport {
  return {
    runId: 'run-1',
    startedAt: '2026-06-17T00:00:00.000Z',
    completedAt: '2026-06-17T00:02:00.000Z',
    findingsCount: 1,
    knowledgeCount: 1,
    audits: [],
    patchDecisions: [],
    patches: [],
    evaluationGates: [],
    renameMap: {},
    archiveMap: {},
    skillsPromotion: {
      target: 'skills',
      status: 'skipped',
      pullRequest: null,
      mergedCommit: null,
      reason: 'No valid changes to promote.',
    },
    pluginPromotion: {
      target: 'plugin',
      status: 'skipped',
      pullRequest: null,
      mergedCommit: null,
      reason: 'No valid changes to promote.',
    },
    rollback: null,
    markdownPath: '',
    jsonPath: '',
  };
}

describe('MarkdownReportWriter', () => {
  it('writes date-based report names and promotion fields', async () => {
    const root = await mkdtemp(join(tmpdir(), 'curator-report-'));
    const writer = new MarkdownReportWriter();

    const paths = await writer.write(report(), join(root, '.curator', 'reports'));

    expect(paths.markdownPath.endsWith('2026-06-17.md')).toBe(true);
    expect(paths.jsonPath.endsWith('2026-06-17.json')).toBe(true);
  });
});
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
pnpm --filter @curator/core test -- curator-state.test.ts report-writer.test.ts
```

Expected: FAIL because the state store does not exist and report names are still run-id based.

- [ ] **Step 4: Implement state store**

Create `packages/core/src/application/curator-state.ts`:

```ts
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import type { CuratorStatePort } from '../ports/index.js';
import type { KnownGoodSkillsState, LastRunState } from '../domain/types.js';

export class JsonCuratorStateStore implements CuratorStatePort {
  constructor(private readonly stateDir: string) {}

  async readKnownGood(): Promise<KnownGoodSkillsState | null> {
    try {
      const raw = await readFile(join(this.stateDir, 'known-good-skills.json'), 'utf8');
      return JSON.parse(raw) as KnownGoodSkillsState;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        return null;
      }
      throw error;
    }
  }

  async writeKnownGood(state: KnownGoodSkillsState): Promise<void> {
    await mkdir(this.stateDir, { recursive: true });
    await writeFile(join(this.stateDir, 'known-good-skills.json'), `${JSON.stringify(state, null, 2)}\n`, 'utf8');
  }

  async writeLastRun(state: LastRunState): Promise<void> {
    await mkdir(this.stateDir, { recursive: true });
    await writeFile(join(this.stateDir, 'last-run.json'), `${JSON.stringify(state, null, 2)}\n`, 'utf8');
  }
}
```

- [ ] **Step 5: Update report writer**

Change `packages/core/src/application/report-writer.ts` so paths use the UTC date:

```ts
const reportDate = report.startedAt.slice(0, 10);
const markdownPath = join(outputDir, `${reportDate}.md`);
const jsonPath = join(outputDir, `${reportDate}.json`);
```

Add these sections to `renderMarkdown(report)` before the final return:

```ts
lines.push(`## Promotions`, ``);
lines.push(`- **Skills:** ${report.skillsPromotion.status} — ${report.skillsPromotion.reason}`);
lines.push(`- **Plugin:** ${report.pluginPromotion.status} — ${report.pluginPromotion.reason}`);
if (report.rollback) {
  lines.push(`- **Rollback:** ${report.rollback.status} — ${report.rollback.reason}`);
}
lines.push(``);

if (report.patchDecisions.length > 0) {
  lines.push(`## Patch Decisions`, ``);
  for (const decision of report.patchDecisions) {
    lines.push(`- **${decision.kind}** \`${decision.skill}\`: ${decision.rationale}`);
  }
  lines.push(``);
}
```

- [ ] **Step 6: Export state store**

In `packages/core/src/index.ts`, export:

```ts
export { JsonCuratorStateStore } from './application/curator-state.js';
export {
  assertDestructiveDecisionsHaveMaps,
  buildNoopPromotionResult,
} from './application/decision-contracts.js';
```

- [ ] **Step 7: Run core tests**

Run:

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
pnpm --filter @curator/core test -- curator-state.test.ts report-writer.test.ts decision-contracts.test.ts
pnpm --filter @curator/core typecheck
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
git add packages/core/src/application/curator-state.ts packages/core/src/application/curator-state.test.ts packages/core/src/application/report-writer.ts packages/core/src/application/report-writer.test.ts packages/core/src/index.ts
git commit -m "feat: persist autonomous curator state"
```

---

### Task 3: Structured Patch Decisions And Destructive Maps

**Files:**
- Modify: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/refactoring/src/index.ts`
- Test: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/refactoring/src/index.test.ts`

- [ ] **Step 1: Write refactoring tests**

Create `packages/refactoring/src/index.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import type { AuditReport, SkillAuditContext } from '@curator/core';
import { AdditivePatchGenerator } from './index.js';

const skill: SkillAuditContext = {
  name: 'ticket-analyst',
  tags: ['analysis'],
  prompt: '# Ticket Analyst\n',
  version: '2.0.0',
  hasTests: true,
  hasExamples: true,
  rootPath: '/repo/registry/ticket-analyst',
};

const audit: AuditReport = {
  skill: 'ticket-analyst',
  score: {
    skill: 'ticket-analyst',
    dimensions: {
      prompt_quality: 80,
      reasoning_quality: 80,
      tool_usage: 80,
      architecture_guidance: 80,
      evaluation_coverage: 80,
      guardrails: 80,
      maintainability: 80,
    },
    overall_score: 80,
    recorded_at: '2026-06-17T00:00:00.000Z',
  },
  issues: [
    {
      type: 'missing',
      severity: 'medium',
      message: 'Missing readiness semantics.',
      recommendation: 'Document ready, not_ready, needs_clarification, and not_development.',
    },
  ],
  recommendations: ['Document readiness statuses.'],
};

describe('AdditivePatchGenerator', () => {
  it('returns patches with matching patch decisions', () => {
    const result = new AdditivePatchGenerator().generateWithDecisions([audit], [skill]);

    expect(result.patches).toHaveLength(1);
    expect(result.decisions).toEqual([
      {
        kind: 'patch',
        skill: 'ticket-analyst',
        rationale: 'Add 1 knowledge gap section(s) from curator audit',
        files: ['registry/ticket-analyst/prompt.md'],
      },
    ]);
    expect(result.renameMap).toEqual({});
    expect(result.archiveMap).toEqual({});
  });

  it('keeps existing generate API returning only patches', () => {
    const patches = new AdditivePatchGenerator().generate([audit], [skill]);
    expect(patches).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
pnpm --filter @curator/refactoring test -- index.test.ts
```

Expected: FAIL because `generateWithDecisions` does not exist.

- [ ] **Step 3: Add structured generation result**

In `packages/refactoring/src/index.ts`, import the new types:

```ts
import type {
  ArchiveMapEntry,
  AuditReport,
  GitPatch,
  PatchDecision,
  RenameMapEntry,
  SkillAuditContext,
} from '@curator/core';
```

Add:

```ts
export interface PatchGenerationResult {
  patches: GitPatch[];
  decisions: PatchDecision[];
  renameMap: Record<string, RenameMapEntry>;
  archiveMap: Record<string, ArchiveMapEntry>;
}
```

Refactor `generate` to delegate:

```ts
generate(reports: AuditReport[], skills: SkillAuditContext[]): GitPatch[] {
  return this.generateWithDecisions(reports, skills).patches;
}
```

Add `generateWithDecisions`:

```ts
generateWithDecisions(reports: AuditReport[], skills: SkillAuditContext[]): PatchGenerationResult {
  const patches: GitPatch[] = [];
  const decisions: PatchDecision[] = [];
  const skillMap = new Map(skills.map((s) => [s.name, s]));

  for (const report of reports) {
    if (report.issues.length === 0) continue;
    const skill = skillMap.get(report.skill);
    if (!skill) continue;

    const missing = report.issues.filter((i) => i.type === 'missing' && i.recommendation);
    if (missing.length === 0) continue;

    const section = buildAdditionSection(missing.map((m) => m.recommendation as string));
    const diff = buildUnifiedDiff('prompt.md', skill.prompt, `${skill.prompt.trim()}\n\n${section}`);
    const summary = `Add ${String(missing.length)} knowledge gap section(s) from curator audit`;

    patches.push({
      skill: report.skill,
      filePath: 'prompt.md',
      diff,
      summary,
    });
    decisions.push({
      kind: 'patch',
      skill: report.skill,
      rationale: summary,
      files: [`registry/${report.skill}/prompt.md`],
    });
  }

  return { patches, decisions, renameMap: {}, archiveMap: {} };
}
```

- [ ] **Step 4: Run refactoring tests**

Run:

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
pnpm --filter @curator/refactoring test -- index.test.ts
pnpm --filter @curator/refactoring typecheck
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
git add packages/refactoring/src/index.ts packages/refactoring/src/index.test.ts
git commit -m "feat: emit structured curator patch decisions"
```

---

### Task 4: GitHub Auto-Merge And Skills Promotion

**Files:**
- Create: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/github/src/auto-merge.ts`
- Create: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/github/src/skills-promotion.ts`
- Modify: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/github/src/index.ts`
- Test: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/github/src/__tests__/auto-merge.test.ts`
- Test: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/github/src/__tests__/skills-promotion.test.ts`

- [ ] **Step 1: Write auto-merge tests**

Create `packages/github/src/__tests__/auto-merge.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { GitHubAutoMergeService } from '../auto-merge.js';

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('GitHubAutoMergeService', () => {
  it('enables auto-merge and returns the merged commit', async () => {
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ data: { enablePullRequestAutoMerge: { pullRequest: { number: 12 } } } }))
      .mockResolvedValueOnce(jsonResponse({ merged: false, merge_commit_sha: null }))
      .mockResolvedValueOnce(jsonResponse({ merged: true, merge_commit_sha: '0123456789abcdef0123456789abcdef01234567' }));

    const service = new GitHubAutoMergeService({
      token: 'token',
      owner: 'Tamsi',
      repo: 'livingcolor-skills',
      pollIntervalMs: 1,
      maxPolls: 2,
    }, fetchImpl);

    await expect(service.enableAndWait({
      pullRequestNumber: 12,
      pullRequestNodeId: 'PR_node_id',
    })).resolves.toEqual({
      mergedCommit: '0123456789abcdef0123456789abcdef01234567',
    });

    expect(fetchImpl).toHaveBeenCalledTimes(3);
  });
});
```

- [ ] **Step 2: Write skills promotion tests**

Create `packages/github/src/__tests__/skills-promotion.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import type { CuratorRunReport, GitPatch } from '@curator/core';
import { GitHubSkillsPromotionService } from '../skills-promotion.js';

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function report(): CuratorRunReport {
  return {
    runId: 'run-1',
    startedAt: '2026-06-17T00:00:00.000Z',
    completedAt: '2026-06-17T00:01:00.000Z',
    findingsCount: 1,
    knowledgeCount: 1,
    audits: [],
    patchDecisions: [],
    patches: [],
    evaluationGates: [],
    renameMap: {},
    archiveMap: {},
    skillsPromotion: { target: 'skills', status: 'skipped', pullRequest: null, mergedCommit: null, reason: 'No valid changes to promote.' },
    pluginPromotion: { target: 'plugin', status: 'skipped', pullRequest: null, mergedCommit: null, reason: 'No valid changes to promote.' },
    rollback: null,
    markdownPath: '',
    jsonPath: '',
  };
}

describe('GitHubSkillsPromotionService', () => {
  it('creates a branch, commits patch content, opens PR, and waits for merge', async () => {
    const patch: GitPatch = {
      skill: 'ticket-analyst',
      filePath: 'prompt.md',
      diff: '--- a/prompt.md\n+++ b/prompt.md\n@@ -1 +1 @@\n-old\n+new',
      summary: 'Update prompt',
    };
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ object: { sha: 'base-sha' } }))
      .mockResolvedValueOnce(jsonResponse({ ref: 'refs/heads/curator/daily-2026-06-17' }))
      .mockResolvedValueOnce(jsonResponse({ sha: 'existing-file-sha' }))
      .mockResolvedValueOnce(jsonResponse({ content: { sha: 'new-file-sha' } }))
      .mockResolvedValueOnce(jsonResponse({
        html_url: 'https://github.com/Tamsi/livingcolor-skills/pull/10',
        number: 10,
        node_id: 'PR_node_id',
      }))
      .mockResolvedValueOnce(jsonResponse({ data: { enablePullRequestAutoMerge: { pullRequest: { number: 10 } } } }))
      .mockResolvedValueOnce(jsonResponse({ merged: true, merge_commit_sha: 'abcdefabcdefabcdefabcdefabcdefabcdefabcd' }));

    const service = new GitHubSkillsPromotionService({
      token: 'token',
      owner: 'Tamsi',
      repo: 'livingcolor-skills',
      baseBranch: 'main',
      pollIntervalMs: 1,
      maxPolls: 1,
    }, fetchImpl);

    await expect(service.promote({
      branch: 'curator/daily-2026-06-17',
      patches: [patch],
      report: report(),
    })).resolves.toMatchObject({
      target: 'skills',
      status: 'merged',
      mergedCommit: 'abcdefabcdefabcdefabcdefabcdefabcdefabcd',
    });
  });
});
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
pnpm --filter @curator/github test -- auto-merge.test.ts skills-promotion.test.ts
```

Expected: FAIL because the services do not exist.

- [ ] **Step 4: Implement auto-merge service**

Create `packages/github/src/auto-merge.ts`:

```ts
type FetchImpl = typeof fetch;

export interface GitHubAutoMergeConfig {
  token: string;
  owner: string;
  repo: string;
  pollIntervalMs?: number;
  maxPolls?: number;
}

export class GitHubAutoMergeService {
  constructor(
    private readonly config: GitHubAutoMergeConfig,
    private readonly fetchImpl: FetchImpl = fetch,
  ) {}

  async enableAndWait(request: {
    pullRequestNumber: number;
    pullRequestNodeId: string;
  }): Promise<{ mergedCommit: string }> {
    await this.githubRequest(`https://api.github.com/graphql`, {
      method: 'POST',
      body: JSON.stringify({
        query: `
          mutation EnableAutoMerge($input: EnablePullRequestAutoMergeInput!) {
            enablePullRequestAutoMerge(input: $input) {
              pullRequest { number }
            }
          }
        `,
        variables: {
          input: {
            pullRequestId: request.pullRequestNodeId,
            mergeMethod: 'SQUASH',
          },
        },
      }),
    });

    const maxPolls = this.config.maxPolls ?? 60;
    const pollIntervalMs = this.config.pollIntervalMs ?? 10_000;
    for (let attempt = 0; attempt <= maxPolls; attempt += 1) {
      const pr = await this.githubRequest<{ merged: boolean; merge_commit_sha: string | null }>(
        `https://api.github.com/repos/${this.config.owner}/${this.config.repo}/pulls/${String(request.pullRequestNumber)}`,
      );
      if (pr.merged && pr.merge_commit_sha) {
        return { mergedCommit: pr.merge_commit_sha };
      }
      if (attempt < maxPolls) {
        await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
      }
    }
    throw new Error(`Pull request ${String(request.pullRequestNumber)} did not merge before timeout`);
  }

  private async githubRequest<T = unknown>(url: string, init?: RequestInit): Promise<T> {
    const response = await this.fetchImpl(url, {
      ...init,
      headers: {
        Authorization: `Bearer ${this.config.token}`,
        Accept: 'application/vnd.github+json',
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`GitHub API ${String(response.status)} for ${url}: ${text}`);
    }
    return (await response.json()) as T;
  }
}
```

- [ ] **Step 5: Implement skills promotion service**

Create `packages/github/src/skills-promotion.ts`:

```ts
import { Buffer } from 'node:buffer';
import type { CuratorRunReport, GitPatch, PromotionResult } from '@curator/core';
import { GitHubAutoMergeService } from './auto-merge.js';

type FetchImpl = typeof fetch;

export interface GitHubSkillsPromotionConfig {
  token?: string;
  owner: string;
  repo: string;
  baseBranch: string;
  pollIntervalMs?: number;
  maxPolls?: number;
}

interface GitHubRefResponse {
  object: { sha: string };
}

interface GitHubContentResponse {
  sha: string;
}

interface GitHubPullRequestResponse {
  html_url: string;
  number: number;
  node_id: string;
}

export class GitHubSkillsPromotionService {
  constructor(
    private readonly config: GitHubSkillsPromotionConfig,
    private readonly fetchImpl: FetchImpl = fetch,
  ) {}

  async promote(request: {
    branch: string;
    patches: GitPatch[];
    report: CuratorRunReport;
  }): Promise<PromotionResult> {
    if (request.patches.length === 0) {
      return {
        target: 'skills',
        status: 'skipped',
        pullRequest: null,
        mergedCommit: null,
        reason: 'No valid changes to promote.',
      };
    }
    if (!this.config.token) {
      return {
        target: 'skills',
        status: 'failed',
        pullRequest: null,
        mergedCommit: null,
        reason: 'Missing GitHub token for skills promotion.',
      };
    }

    const apiBase = `https://api.github.com/repos/${this.config.owner}/${this.config.repo}`;
    const baseRef = await this.githubRequest<GitHubRefResponse>(
      `${apiBase}/git/ref/heads/${this.config.baseBranch}`,
    );
    await this.githubRequest(`${apiBase}/git/refs`, {
      method: 'POST',
      body: JSON.stringify({ ref: `refs/heads/${request.branch}`, sha: baseRef.object.sha }),
    });

    for (const patch of request.patches) {
      const path = `registry/${patch.skill}/${patch.filePath}`;
      const current = await this.githubRequest<GitHubContentResponse>(
        `${apiBase}/contents/${encodePath(path)}?ref=${encodeURIComponent(this.config.baseBranch)}`,
      );
      await this.githubRequest(`${apiBase}/contents/${encodePath(path)}`, {
        method: 'PUT',
        body: JSON.stringify({
          message: patch.summary,
          content: Buffer.from(extractAddedContent(patch.diff), 'utf8').toString('base64'),
          branch: request.branch,
          sha: current.sha,
        }),
      });
    }

    const pr = await this.githubRequest<GitHubPullRequestResponse>(`${apiBase}/pulls`, {
      method: 'POST',
      body: JSON.stringify({
        title: `Autonomous skill improvements ${request.report.startedAt.slice(0, 10)}`,
        head: request.branch,
        base: this.config.baseBranch,
        body: buildSkillsPrBody(request.report, request.patches),
      }),
    });

    const merge = await new GitHubAutoMergeService({
      token: this.config.token,
      owner: this.config.owner,
      repo: this.config.repo,
      pollIntervalMs: this.config.pollIntervalMs,
      maxPolls: this.config.maxPolls,
    }, this.fetchImpl).enableAndWait({
      pullRequestNumber: pr.number,
      pullRequestNodeId: pr.node_id,
    });

    return {
      target: 'skills',
      status: 'merged',
      pullRequest: { url: pr.html_url, branch: request.branch, number: pr.number },
      mergedCommit: merge.mergedCommit,
      reason: 'Skills PR merged after all gates passed.',
    };
  }

  private async githubRequest<T>(url: string, init?: RequestInit): Promise<T> {
    const response = await this.fetchImpl(url, {
      ...init,
      headers: {
        Authorization: `Bearer ${this.config.token ?? ''}`,
        Accept: 'application/vnd.github+json',
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`GitHub API ${String(response.status)} for ${url}: ${text}`);
    }
    return (await response.json()) as T;
  }
}

function extractAddedContent(diff: string): string {
  return diff
    .split('\n')
    .filter((line) => line.startsWith('+') && !line.startsWith('+++'))
    .map((line) => line.slice(1))
    .join('\n');
}

function buildSkillsPrBody(report: CuratorRunReport, patches: GitPatch[]): string {
  return [
    '## Summary',
    '',
    'Automated LivingColor skill improvements from the daily curator loop.',
    '',
    '## Patches',
    '',
    ...patches.map((patch) => `- **${patch.skill}**: ${patch.summary}`),
    '',
    '## Gates',
    '',
    ...report.evaluationGates.map((gate) => `- **${gate.skill}**: ${gate.passed ? 'passed' : 'failed'} (${String(gate.scoreDelta)})`),
  ].join('\n');
}

function encodePath(path: string): string {
  return path.split('/').map(encodeURIComponent).join('/');
}
```

- [ ] **Step 6: Export GitHub services**

In `packages/github/src/index.ts`, add:

```ts
export { GitHubAutoMergeService } from './auto-merge.js';
export { GitHubSkillsPromotionService } from './skills-promotion.js';
export type { GitHubAutoMergeConfig } from './auto-merge.js';
export type { GitHubSkillsPromotionConfig } from './skills-promotion.js';
```

- [ ] **Step 7: Run GitHub tests**

Run:

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
pnpm --filter @curator/github test -- auto-merge.test.ts skills-promotion.test.ts plugin-lock-bump.test.ts
pnpm --filter @curator/github typecheck
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
git add packages/github/src/auto-merge.ts packages/github/src/skills-promotion.ts packages/github/src/index.ts packages/github/src/__tests__/auto-merge.test.ts packages/github/src/__tests__/skills-promotion.test.ts
git commit -m "feat: auto-merge curated skills changes"
```

---

### Task 5: Plugin Validation And Rollback Services

**Files:**
- Create: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/scheduler/src/plugin-validation.ts`
- Create: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/github/src/plugin-rollback.ts`
- Modify: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/github/src/plugin-lock-bump.ts`
- Modify: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/github/src/index.ts`
- Test: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/scheduler/src/__tests__/plugin-validation.test.ts`
- Test: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/github/src/__tests__/plugin-rollback.test.ts`
- Test: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/github/src/__tests__/plugin-lock-bump.test.ts`

- [ ] **Step 1: Write plugin validation tests**

Create `packages/scheduler/src/__tests__/plugin-validation.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { LocalPluginValidationService } from '../plugin-validation.js';

describe('LocalPluginValidationService', () => {
  it('runs cache warmup and focused plugin tests', async () => {
    const calls: string[] = [];
    const service = new LocalPluginValidationService(async (command, args, options) => {
      calls.push(`${command} ${args.join(' ')} @ ${options.cwd}`);
      return { exitCode: 0, stdout: 'ok', stderr: '' };
    });

    await expect(service.validate({
      pluginPath: '/repo/livingcolor-plugin',
      skillsPath: '/repo/livingcolor-skills',
      resolvedCommit: '0123456789abcdef0123456789abcdef01234567',
    })).resolves.toEqual({ passed: true, output: ['ok', 'ok'] });

    expect(calls).toEqual([
      'python -m lc_server warm-skills-cache @ /repo/livingcolor-plugin',
      'python -m pytest tests/lc_server/test_external_skills_lock.py tests/lc_server/test_external_skills_prompt_injection.py -q @ /repo/livingcolor-plugin',
    ]);
  });

  it('returns failed when any command exits non-zero', async () => {
    const service = new LocalPluginValidationService(async () => ({
      exitCode: 1,
      stdout: '',
      stderr: 'cache failed',
    }));

    await expect(service.validate({
      pluginPath: '/repo/livingcolor-plugin',
      skillsPath: '/repo/livingcolor-skills',
      resolvedCommit: '0123456789abcdef0123456789abcdef01234567',
    })).resolves.toEqual({ passed: false, output: ['cache failed'] });
  });
});
```

- [ ] **Step 2: Write rollback tests**

Create `packages/github/src/__tests__/plugin-rollback.test.ts`:

```ts
import { Buffer } from 'node:buffer';
import { describe, expect, it, vi } from 'vitest';
import { GitHubPluginRollbackService } from '../plugin-rollback.js';

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('GitHubPluginRollbackService', () => {
  it('opens a rollback PR to the known-good skills commit', async () => {
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ object: { sha: 'base-sha' } }))
      .mockResolvedValueOnce(jsonResponse({ ref: 'refs/heads/curator/rollback-skills-01234567' }))
      .mockResolvedValueOnce(jsonResponse({ sha: 'existing-lock-sha' }))
      .mockResolvedValueOnce(jsonResponse({ content: { sha: 'new-lock-sha' } }))
      .mockResolvedValueOnce(jsonResponse({ html_url: 'https://github.com/Tamsi/livingcolor-plugin/pull/44', number: 44 }));

    const service = new GitHubPluginRollbackService({
      token: 'token',
      owner: 'Tamsi',
      repo: 'livingcolor-plugin',
      baseBranch: 'main',
      lockPath: 'livingcolor.skills.lock.json',
    }, fetchImpl);

    const result = await service.rollback({
      knownGood: {
        skillsRepo: 'Tamsi/livingcolor-skills',
        resolvedCommit: '0123456789abcdef0123456789abcdef01234567',
        validatedAt: '2026-06-17T00:00:00.000Z',
        pluginRepo: 'Tamsi/livingcolor-plugin',
        pluginCommit: 'abcdefabcdefabcdefabcdefabcdefabcdefabcd',
      },
      reason: 'Post-merge plugin validation failed.',
    });

    expect(result.status).toBe('opened');
    const putBody = JSON.parse(String(fetchImpl.mock.calls[3]?.[1]?.body)) as { content: string };
    const lock = JSON.parse(Buffer.from(putBody.content, 'base64').toString('utf8')) as { resolvedCommit: string };
    expect(lock.resolvedCommit).toBe('0123456789abcdef0123456789abcdef01234567');
  });
});
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
pnpm --filter @curator/scheduler test -- plugin-validation.test.ts
pnpm --filter @curator/github test -- plugin-rollback.test.ts
```

Expected: FAIL because services do not exist.

- [ ] **Step 4: Implement plugin validation**

Create `packages/scheduler/src/plugin-validation.ts`:

```ts
import { spawn } from 'node:child_process';
import type { PluginValidationPort } from '@curator/core';

export type CommandRunner = (
  command: string,
  args: string[],
  options: { cwd: string; env: NodeJS.ProcessEnv },
) => Promise<{ exitCode: number; stdout: string; stderr: string }>;

export class LocalPluginValidationService implements PluginValidationPort {
  constructor(private readonly runner: CommandRunner = runCommand) {}

  async validate(request: {
    pluginPath: string;
    skillsPath: string;
    resolvedCommit: string;
  }): Promise<{ passed: boolean; output: string[] }> {
    const env = {
      ...process.env,
      LIVINGCOLOR_SKILLS_RESOLVED_COMMIT: request.resolvedCommit,
      LIVINGCOLOR_SKILLS_PATH: request.skillsPath,
    };
    const commands: Array<[string, string[]]> = [
      ['python', ['-m', 'lc_server', 'warm-skills-cache']],
      ['python', ['-m', 'pytest', 'tests/lc_server/test_external_skills_lock.py', 'tests/lc_server/test_external_skills_prompt_injection.py', '-q']],
    ];
    const output: string[] = [];
    for (const [command, args] of commands) {
      const result = await this.runner(command, args, { cwd: request.pluginPath, env });
      output.push(result.stdout || result.stderr);
      if (result.exitCode !== 0) {
        return { passed: false, output };
      }
    }
    return { passed: true, output };
  }
}

function runCommand(
  command: string,
  args: string[],
  options: { cwd: string; env: NodeJS.ProcessEnv },
): Promise<{ exitCode: number; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    const child = spawn(command, args, { cwd: options.cwd, env: options.env });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk: Buffer) => {
      stdout += chunk.toString('utf8');
    });
    child.stderr.on('data', (chunk: Buffer) => {
      stderr += chunk.toString('utf8');
    });
    child.on('close', (code) => {
      resolve({ exitCode: code ?? 1, stdout, stderr });
    });
  });
}
```

- [ ] **Step 5: Implement plugin rollback**

Create `packages/github/src/plugin-rollback.ts` with the same GitHub request pattern as `plugin-lock-bump.ts`, but build the lock from `knownGood.resolvedCommit` and use:

```ts
const branch = `curator/rollback-skills-${request.knownGood.resolvedCommit.slice(0, 8)}`;
const title = `Rollback LivingColor skills lock to known-good ${request.knownGood.resolvedCommit.slice(0, 8)}`;
```

Return:

```ts
return {
  target: 'plugin',
  status: 'opened',
  pullRequest: { url: pr.html_url, branch, number: pr.number },
  mergedCommit: null,
  reason: request.reason,
};
```

- [ ] **Step 6: Convert plugin lock bump to auto-merge promotion**

In `packages/github/src/plugin-lock-bump.ts`, import the auto-merge service and `PromotionResult`:

```ts
import type {
  PluginLockBumpConfig,
  PluginLockBumpPort,
  PluginLockBumpRequest,
  PromotionResult,
} from '@curator/core';
import { GitHubAutoMergeService } from './auto-merge.js';
```

Extend `GitHubPullRequestResponse`:

```ts
interface GitHubPullRequestResponse {
  html_url: string;
  number: number;
  node_id: string;
}
```

Change `create` to return `Promise<PromotionResult | null>`. After creating the PR, call auto-merge:

```ts
const merge = await new GitHubAutoMergeService({
  token,
  owner: this.config.owner,
  repo: this.config.repo,
}).enableAndWait({
  pullRequestNumber: pr.number,
  pullRequestNodeId: pr.node_id,
});

return {
  target: 'plugin',
  status: 'merged',
  pullRequest: { url: pr.html_url, branch, number: pr.number },
  mergedCommit: merge.mergedCommit,
  reason: 'Plugin lock bump merged after validation passed.',
};
```

Keep the existing dry-run and missing-token behavior returning `null`.

Update `packages/github/src/__tests__/plugin-lock-bump.test.ts`:

```ts
// Add these mock responses after PR creation:
.mockResolvedValueOnce(jsonResponse({
  data: { enablePullRequestAutoMerge: { pullRequest: { number: 42 } } },
}))
.mockResolvedValueOnce(jsonResponse({
  merged: true,
  merge_commit_sha: 'abcdefabcdefabcdefabcdefabcdefabcdefabcd',
}))
```

Update the expected result:

```ts
expect(result).toEqual({
  target: 'plugin',
  status: 'merged',
  pullRequest: {
    url: 'https://github.com/Tamsi/livingcolor-plugin/pull/42',
    branch: 'curator/skills-lock-01234567',
    number: 42,
  },
  mergedCommit: 'abcdefabcdefabcdefabcdefabcdefabcdefabcd',
  reason: 'Plugin lock bump merged after validation passed.',
});
```

Update the PR mock body to include `node_id`:

```ts
jsonResponse({
  html_url: 'https://github.com/Tamsi/livingcolor-plugin/pull/42',
  number: 42,
  node_id: 'PR_plugin_node_id',
})
```

- [ ] **Step 7: Export rollback service**

In `packages/github/src/index.ts`, add:

```ts
export { GitHubPluginRollbackService } from './plugin-rollback.js';
```

- [ ] **Step 8: Run tests**

Run:

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
pnpm --filter @curator/scheduler test -- plugin-validation.test.ts
pnpm --filter @curator/github test -- plugin-rollback.test.ts plugin-lock-bump.test.ts
pnpm --filter @curator/scheduler typecheck
pnpm --filter @curator/github typecheck
```

Expected: PASS.

- [ ] **Step 9: Commit Task 5**

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
git add packages/scheduler/src/plugin-validation.ts packages/scheduler/src/__tests__/plugin-validation.test.ts packages/github/src/plugin-rollback.ts packages/github/src/__tests__/plugin-rollback.test.ts packages/github/src/plugin-lock-bump.ts packages/github/src/__tests__/plugin-lock-bump.test.ts packages/github/src/index.ts
git commit -m "feat: validate and rollback plugin skill bumps"
```

---

### Task 6: Daily Autonomous Scheduler

**Files:**
- Create: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/scheduler/src/daily-autonomous.ts`
- Modify: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/scheduler/src/index.ts`
- Test: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/scheduler/src/__tests__/daily-autonomous.test.ts`

- [ ] **Step 1: Write daily autonomous tests**

Create `packages/scheduler/src/__tests__/daily-autonomous.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { DailyAutonomousCurator } from '../daily-autonomous.js';
import type {
  CuratorRunReport,
  PluginLockBumpRequest,
  PromotionResult,
} from '@curator/core';

function baseReport(): CuratorRunReport {
  return {
    runId: 'run-1',
    startedAt: '2026-06-17T00:00:00.000Z',
    completedAt: '2026-06-17T00:01:00.000Z',
    findingsCount: 1,
    knowledgeCount: 1,
    audits: [],
    patchDecisions: [],
    patches: [],
    evaluationGates: [],
    renameMap: {},
    archiveMap: {},
    skillsPromotion: { target: 'skills', status: 'skipped', pullRequest: null, mergedCommit: null, reason: 'No valid changes to promote.' },
    pluginPromotion: { target: 'plugin', status: 'skipped', pullRequest: null, mergedCommit: null, reason: 'No valid changes to promote.' },
    rollback: null,
    markdownPath: '',
    jsonPath: '',
  };
}

describe('DailyAutonomousCurator', () => {
  it('stops after no-op report when there are no patches', async () => {
    const state = {
      readKnownGood: vi.fn().mockResolvedValue(null),
      writeKnownGood: vi.fn(),
      writeLastRun: vi.fn(),
    };
    const curator = new DailyAutonomousCurator({
      runCurator: vi.fn().mockResolvedValue(baseReport()),
      skillsPromotion: { promote: vi.fn() },
      pluginBump: { create: vi.fn() },
      pluginValidation: { validate: vi.fn() },
      rollback: { rollback: vi.fn() },
      state,
      reportWriter: { write: vi.fn().mockResolvedValue({ markdownPath: '.curator/reports/2026-06-17.md', jsonPath: '.curator/reports/2026-06-17.json' }) },
      options: {
        projectRoot: '/repo/livingcolor-evolution',
        pluginPath: '/repo/livingcolor-plugin',
        skillsPath: '/repo/livingcolor-skills',
        reportDir: '/repo/livingcolor-evolution/.curator/reports',
      },
    });

    const result = await curator.run();

    expect(result.skillsPromotion.status).toBe('skipped');
    expect(state.writeLastRun).toHaveBeenCalledWith(expect.objectContaining({ status: 'noop' }));
  });

  it('promotes skills, validates plugin, bumps plugin, and records known-good', async () => {
    const report = {
      ...baseReport(),
      patches: [{ skill: 'ticket-analyst', filePath: 'prompt.md', diff: '+new', summary: 'Update prompt' }],
      evaluationGates: [{ passed: true, skill: 'ticket-analyst', scoreDelta: 1, regressions: [], validationValid: true }],
    };
    const skillsPromotion: PromotionResult = {
      target: 'skills',
      status: 'merged',
      pullRequest: { url: 'https://github.com/Tamsi/livingcolor-skills/pull/1', branch: 'curator/daily-2026-06-17', number: 1 },
      mergedCommit: '0123456789abcdef0123456789abcdef01234567',
      reason: 'merged',
    };
    const state = {
      readKnownGood: vi.fn().mockResolvedValue(null),
      writeKnownGood: vi.fn(),
      writeLastRun: vi.fn(),
    };
    const pluginBump = {
      create: vi.fn<(request: PluginLockBumpRequest) => Promise<PromotionResult | null>>().mockResolvedValue({
        target: 'plugin',
        status: 'merged',
        pullRequest: { url: 'https://github.com/Tamsi/livingcolor-plugin/pull/2', branch: 'curator/skills-lock-01234567', number: 2 },
        mergedCommit: 'abcdefabcdefabcdefabcdefabcdefabcdefabcd',
        reason: 'merged',
      }),
    };
    const curator = new DailyAutonomousCurator({
      runCurator: vi.fn().mockResolvedValue(report),
      skillsPromotion: { promote: vi.fn().mockResolvedValue(skillsPromotion) },
      pluginBump,
      pluginValidation: { validate: vi.fn().mockResolvedValue({ passed: true, output: ['ok'] }) },
      rollback: { rollback: vi.fn() },
      state,
      reportWriter: { write: vi.fn().mockResolvedValue({ markdownPath: '.curator/reports/2026-06-17.md', jsonPath: '.curator/reports/2026-06-17.json' }) },
      options: {
        projectRoot: '/repo/livingcolor-evolution',
        pluginPath: '/repo/livingcolor-plugin',
        skillsPath: '/repo/livingcolor-skills',
        reportDir: '/repo/livingcolor-evolution/.curator/reports',
      },
    });

    await curator.run();

    expect(pluginBump.create).toHaveBeenCalledWith(expect.objectContaining({
      resolvedCommit: '0123456789abcdef0123456789abcdef01234567',
    }));
    expect(state.writeKnownGood).toHaveBeenCalledWith(expect.objectContaining({
      resolvedCommit: '0123456789abcdef0123456789abcdef01234567',
    }));
  });
});
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
pnpm --filter @curator/scheduler test -- daily-autonomous.test.ts
```

Expected: FAIL because `daily-autonomous.ts` does not exist.

- [ ] **Step 3: Implement daily orchestrator**

Create `packages/scheduler/src/daily-autonomous.ts`:

```ts
import type {
  CuratorRunReport,
  CuratorStatePort,
  PluginLockBumpPort,
  PluginRollbackPort,
  PluginValidationPort,
  PromotionResult,
  ReportWriterPort,
  SkillsPromotionPort,
} from '@curator/core';

export interface DailyAutonomousCuratorOptions {
  projectRoot: string;
  pluginPath: string;
  skillsPath: string;
  reportDir: string;
}

export interface DailyAutonomousCuratorDeps {
  runCurator: () => Promise<CuratorRunReport>;
  skillsPromotion: SkillsPromotionPort;
  pluginBump: PluginLockBumpPort;
  pluginValidation: PluginValidationPort;
  rollback: PluginRollbackPort;
  state: CuratorStatePort;
  reportWriter: ReportWriterPort;
  options: DailyAutonomousCuratorOptions;
}

export class DailyAutonomousCurator {
  constructor(private readonly deps: DailyAutonomousCuratorDeps) {}

  async run(): Promise<CuratorRunReport> {
    const report = await this.deps.runCurator();
    if (report.patches.length === 0) {
      report.skillsPromotion = {
        target: 'skills',
        status: 'skipped',
        pullRequest: null,
        mergedCommit: null,
        reason: 'No valid changes to promote.',
      };
      report.pluginPromotion = {
        target: 'plugin',
        status: 'skipped',
        pullRequest: null,
        mergedCommit: null,
        reason: 'No skills change was promoted.',
      };
      await this.finish(report, 'noop');
      return report;
    }

    if (report.evaluationGates.some((gate) => !gate.passed)) {
      report.skillsPromotion = {
        target: 'skills',
        status: 'failed',
        pullRequest: null,
        mergedCommit: null,
        reason: 'One or more evaluation gates failed.',
      };
      await this.finish(report, 'failed');
      return report;
    }

    report.skillsPromotion = await this.deps.skillsPromotion.promote({
      branch: `curator/daily-${report.startedAt.slice(0, 10)}`,
      patches: report.patches,
      report,
    });
    if (report.skillsPromotion.status !== 'merged' || !report.skillsPromotion.mergedCommit) {
      await this.finish(report, 'failed');
      return report;
    }

    const validation = await this.deps.pluginValidation.validate({
      pluginPath: this.deps.options.pluginPath,
      skillsPath: this.deps.options.skillsPath,
      resolvedCommit: report.skillsPromotion.mergedCommit,
    });
    if (!validation.passed) {
      report.pluginPromotion = {
        target: 'plugin',
        status: 'failed',
        pullRequest: null,
        mergedCommit: null,
        reason: validation.output.join('\n'),
      };
      await this.finish(report, 'failed');
      return report;
    }

    const pluginPromotion = await this.deps.pluginBump.create({
      skillsRepo: 'Tamsi/livingcolor-skills',
      skillsRef: `refs/tags/curator-${report.skillsPromotion.mergedCommit.slice(0, 8)}`,
      resolvedCommit: report.skillsPromotion.mergedCommit,
      bundle: 'code-review-pipeline',
      skills: ['ticket-analyst', 'code-architect', 'qa-reviewer', 'security-auditor', 'sprint-reporter'],
      dryRun: false,
    });
    report.pluginPromotion = normalizePluginPromotion(pluginPromotion);

    if (report.pluginPromotion.status === 'merged' && report.pluginPromotion.mergedCommit) {
      await this.deps.state.writeKnownGood({
        skillsRepo: 'Tamsi/livingcolor-skills',
        resolvedCommit: report.skillsPromotion.mergedCommit,
        validatedAt: new Date().toISOString(),
        pluginRepo: 'Tamsi/livingcolor-plugin',
        pluginCommit: report.pluginPromotion.mergedCommit,
      });
      await this.finish(report, 'success');
      return report;
    }

    const knownGood = await this.deps.state.readKnownGood();
    if (knownGood) {
      report.rollback = await this.deps.rollback.rollback({
        knownGood,
        reason: 'Plugin promotion failed after skills promotion.',
      });
    }
    await this.finish(report, 'failed');
    return report;
  }

  private async finish(report: CuratorRunReport, status: 'success' | 'failed' | 'noop'): Promise<void> {
    const paths = await this.deps.reportWriter.write(report, this.deps.options.reportDir);
    report.markdownPath = paths.markdownPath;
    report.jsonPath = paths.jsonPath;
    await this.deps.state.writeLastRun({
      runId: report.runId,
      startedAt: report.startedAt,
      completedAt: report.completedAt,
      status,
      reportJsonPath: report.jsonPath,
      reportMarkdownPath: report.markdownPath,
    });
  }
}

function normalizePluginPromotion(result: PromotionResult | null): PromotionResult {
  return result ?? {
    target: 'plugin',
    status: 'failed',
    pullRequest: null,
    mergedCommit: null,
    reason: 'Plugin lock bump did not return a promotion result.',
  };
}
```

- [ ] **Step 4: Wire exports in scheduler**

In `packages/scheduler/src/index.ts`, export:

```ts
export { DailyAutonomousCurator } from './daily-autonomous.js';
export { LocalPluginValidationService } from './plugin-validation.js';
```

- [ ] **Step 5: Run scheduler tests**

Run:

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
pnpm --filter @curator/scheduler test -- daily-autonomous.test.ts plugin-validation.test.ts plugin-bump.test.ts
pnpm --filter @curator/scheduler typecheck
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
git add packages/scheduler/src/daily-autonomous.ts packages/scheduler/src/__tests__/daily-autonomous.test.ts packages/scheduler/src/index.ts
git commit -m "feat: orchestrate daily autonomous curator"
```

---

### Task 7: CLI Command And GitHub Actions Daily Workflow

**Files:**
- Modify: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/cli/src/index.ts`
- Modify: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/.github/workflows/curator-weekly.yml`
- Test: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/cli/src/index.test.ts`
- Test: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/scheduler/src/__tests__/workflow-schedule.test.ts`

- [ ] **Step 1: Write workflow schedule test**

Create `packages/scheduler/src/__tests__/workflow-schedule.test.ts`:

```ts
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('curator workflow schedule', () => {
  it('runs the autonomous curator daily at 00:00 UTC', async () => {
    const workflow = await readFile(resolve(process.cwd(), '.github/workflows/curator-weekly.yml'), 'utf8');

    expect(workflow).toContain("cron: '0 0 * * *'");
    expect(workflow).toContain('pnpm curator daily');
    expect(workflow).toContain('contents: write');
    expect(workflow).toContain('pull-requests: write');
  });
});
```

- [ ] **Step 2: Write CLI smoke test**

Create `packages/cli/src/index.test.ts`:

```ts
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('curator CLI', () => {
  it('declares the daily command', async () => {
    const source = await readFile(resolve(process.cwd(), 'packages/cli/src/index.ts'), 'utf8');

    expect(source).toContain(".command('daily')");
    expect(source).toContain('Execute the fully autonomous daily curator loop');
  });
});
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
pnpm --filter @curator/scheduler test -- workflow-schedule.test.ts
pnpm --filter @curator/cli test -- index.test.ts
```

Expected: FAIL because the daily command and daily schedule are not present.

- [ ] **Step 4: Add CLI daily command**

In `packages/cli/src/index.ts`, import:

```ts
import {
  DailyAutonomousCurator,
  LocalPluginValidationService,
} from '@curator/scheduler';
import {
  GitHubPluginLockBumpService,
  GitHubPluginRollbackService,
  GitHubSkillsPromotionService,
} from '@curator/github';
import { JsonCuratorStateStore, MarkdownReportWriter } from '@curator/core';
```

Add command:

```ts
program
  .command('daily')
  .description('Execute the fully autonomous daily curator loop')
  .action(async () => {
    const root = projectRoot();
    const paths = resolveDefaultPaths(root);
    const githubTarget = parseGithubTarget();
    const token = process.env['GITHUB_TOKEN'];
    const pluginTarget = process.env['CURATOR_PLUGIN_TARGET_REPO'] ?? 'Tamsi/livingcolor-plugin';
    const [pluginOwner = 'Tamsi', pluginRepo = 'livingcolor-plugin'] = pluginTarget.split('/');
    const pluginPath = process.env['CURATOR_PLUGIN_PATH'] ?? resolve(root, '../livingcolor-plugin');

    const pipeline = new CuratorPipeline();
    const daily = new DailyAutonomousCurator({
      runCurator: async () => {
        const { report } = await pipeline.run({
          projectRoot: root,
          skillsPath: paths.skillsPath,
          configPath: paths.configPath,
          outputDir: paths.outputDir,
          cacheDir: paths.cacheDir,
          openPr: false,
          dryRun: false,
          github: token ? { token, ...githubTarget } : { ...githubTarget },
        });
        return report;
      },
      skillsPromotion: new GitHubSkillsPromotionService({
        token,
        owner: githubTarget.owner,
        repo: githubTarget.repo,
        baseBranch: githubTarget.baseBranch,
      }),
      pluginBump: new GitHubPluginLockBumpService({
        ...(token ? { token } : {}),
        owner: pluginOwner,
        repo: pluginRepo,
        baseBranch: process.env['CURATOR_PLUGIN_BASE_BRANCH'] ?? 'main',
        lockPath: process.env['CURATOR_PLUGIN_LOCK_PATH'] ?? 'livingcolor.skills.lock.json',
      }),
      pluginValidation: new LocalPluginValidationService(),
      rollback: new GitHubPluginRollbackService({
        ...(token ? { token } : {}),
        owner: pluginOwner,
        repo: pluginRepo,
        baseBranch: process.env['CURATOR_PLUGIN_BASE_BRANCH'] ?? 'main',
        lockPath: process.env['CURATOR_PLUGIN_LOCK_PATH'] ?? 'livingcolor.skills.lock.json',
      }),
      state: new JsonCuratorStateStore(resolve(root, '.curator/state')),
      reportWriter: new MarkdownReportWriter(),
      options: {
        projectRoot: root,
        pluginPath,
        skillsPath: paths.skillsPath,
        reportDir: paths.outputDir,
      },
    });

    const report = await daily.run();
    console.log(`Daily curator complete: ${report.skillsPromotion.status}/${report.pluginPromotion.status}`);
  });
```

- [ ] **Step 5: Update workflow**

In `.github/workflows/curator-weekly.yml`, change:

```yaml
name: LivingColor Evolution Weekly
```

to:

```yaml
name: LivingColor Evolution Daily Autonomous
```

Change schedule:

```yaml
schedule:
  - cron: '0 0 * * *'
```

Add permissions at top level:

```yaml
permissions:
  contents: write
  pull-requests: write
```

In the curator job, change the run command:

```yaml
run: pnpm curator daily
```

Keep the existing `plugin-lock-bump` workflow_dispatch job for manual recovery, but do not make it the daily path.

- [ ] **Step 6: Run workflow and CLI tests**

Run:

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
pnpm --filter @curator/scheduler test -- workflow-schedule.test.ts
pnpm --filter @curator/cli test -- index.test.ts
pnpm --filter @curator/cli typecheck
```

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
git add packages/cli/src/index.ts packages/cli/src/index.test.ts .github/workflows/curator-weekly.yml packages/scheduler/src/__tests__/workflow-schedule.test.ts
git commit -m "feat: schedule daily autonomous curator"
```

---

### Task 8: End-To-End Verification And Documentation

**Files:**
- Modify: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/README.md`
- Modify: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/package.json`
- Modify only if generated by build: `/Users/tamsibesson/programmation/side-projects/livingcolor-evolution/packages/*/dist/**`

- [ ] **Step 1: Add README section**

In `livingcolor-evolution/README.md`, add:

```md
## Daily Autonomous Skill Curator

LivingColor Evolution runs a daily autonomous curator at `00:00 UTC`.

The loop:

1. audits `Tamsi/livingcolor-skills`,
2. generates non-regressive skill changes,
3. auto-merges the validated skills PR,
4. validates `Tamsi/livingcolor-plugin` against the exact merged skills commit,
5. auto-merges the plugin `livingcolor.skills.lock.json` bump,
6. records known-good state under `.curator/state/`.

Required repository secrets:

- `GITHUB_TOKEN` with `contents:write` and `pull-requests:write` for `livingcolor-skills`
- `LIVINGCOLOR_PLUGIN_PR_TOKEN` with `contents:write` and `pull-requests:write` for `livingcolor-plugin`
- `ANTHROPIC_API_KEY` for LLM-backed extraction/refactoring when mock mode is disabled

Successful runs produce `.curator/reports/YYYY-MM-DD.json` and `.curator/reports/YYYY-MM-DD.md`.
Failed runs leave `livingcolor-plugin` on the last known-good skills lock.
```

- [ ] **Step 2: Add package verification script**

In `package.json`, add:

```json
"verify": "pnpm build && pnpm typecheck && pnpm test"
```

- [ ] **Step 3: Run full test suite**

Run:

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
pnpm install --frozen-lockfile
pnpm verify
```

Expected: PASS.

- [ ] **Step 4: Run daily command in dry environment**

Run:

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
CURATOR_MOCK_LLM=true GITHUB_TOKEN= pnpm curator daily
```

Expected: command completes without GitHub writes and records a failed or no-op report under `.curator/reports/`.

- [ ] **Step 5: Check Git status**

Run:

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
git status --short
```

Expected: only intentional source, test, workflow, README, package, and build output changes remain.

- [ ] **Step 6: Commit Task 8**

```bash
cd /Users/tamsibesson/programmation/side-projects/livingcolor-evolution
git add README.md package.json packages .github/workflows/curator-weekly.yml
git commit -m "docs: document autonomous curator operations"
```

---

## Self-Review Notes

Spec coverage:

- Daily `00:00 UTC` trigger: Task 7.
- Fully automated PR + auto-merge: Tasks 4, 6, 7.
- Heavy changes allowed with strict gates: Tasks 1, 3, 6.
- Machine-readable decisions, rename maps, archive maps: Tasks 1, 3.
- Plugin lock bump to exact merged commit: Tasks 5, 6.
- Known-good and rollback: Tasks 2, 5, 6.
- Reports and last-run state: Tasks 2, 6, 8.
- No runtime mutation by plugin: preserved by architecture; plugin only validates and consumes lock.

Execution order is important. Task 1 must land before all later tasks because it defines shared types. Task 4 can be implemented before Task 5 because skills promotion does not depend on plugin validation. Task 6 ties the pieces together only after the services exist.
