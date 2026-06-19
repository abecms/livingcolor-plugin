# LivingColor — Human-Gated Autonomous Delivery (Remake)

## Narrative Arc
- **Misconception corrected**: autonomous delivery means agents run unchecked.
- **Aha moment**: LivingColor automates the work, but humans approve every risky state change.
- **Visual metaphor**: one Jira ticket travels across an assembly line. At each station, an agent transforms it and a gate controls the next mutation.
- **Language**: English only.
- **Length**: ~90–110s.

## Visual Language
- Background: `#0A0A0A`
- Cyan: LivingColor/plugin/flow
- Magenta: analysis/planning
- Green: development/success
- Purple: QA/quality
- Orange: human validation gates
- White: primary text
- Grey: context/secondary

## Scene 1 — The Promise
Hook: “What if a Jira ticket could deliver itself — without giving up control?”
Visual: LivingColor title; ticket capsule enters a glowing pipeline.

## Scene 2 — The Ecosystem
Visual: three orbiting nodes around LivingColor:
- livingcolor-plugin: runtime, dashboard, gates
- livingcolor-skills: analyst, architect, QA, security guidance
- livingcolor-evolution: updates pinned skill versions

## Scene 3 — Readiness & Ticket Quality
Visual: Jira ticket scanned like a passport.
Checks:
- comments read
- acceptance criteria
- reproduction steps / URLs
- repo mapping
- blockers
Score appears: Readiness 85%, confidence 0.85.
Human promotion: “Promote to Work Order.”

## Scene 4 — Analyst + Planner Station
Visual: ticket becomes a plan.
Agent outputs:
- ticket understanding
- impacted files
- risks
- estimated effort
- confidence 0.92
Gate 1: “Approve analysis plan?”
On approval: Scope Contract + OriginalEstimate writeback.

## Scene 5 — Developer Station
Visual: isolated workspace bubble.
Branch appears: fix/BN-123-login.
Code diff grows; tests pass.
Developer confidence 0.88.
Gate 2 begins with code review.

## Scene 6 — QA Overlay
Visual: three lenses scan the diff:
- code-architect
- qa-reviewer
- security-auditor
Result: QA PASS.
Human approves code review → MR Draft.

## Scene 7 — Publisher & MR Validation
Visual: branch pushed into GitLab/GitHub MR card.
Publisher:
- deterministic commit
- git push
- create MR via MCP
- verify MR exists via API
- validate MR comment/description
Gate 3: approve Jira update.

## Scene 8 — Jira Writeback & Recap
Visual: pipeline zooms out.
Jira comment posted, ticket transitioned to To Test, closed.
Final recap:
- 4 agents: Analyst/Planner, Developer, QA, Publisher
- 3 gates: analysis, code review, Jira update
- validations: comments, quality, confidence, scope, QA, MR verification, Jira movement
Tagline: “Automation does the work. Humans keep control.”
