# LivingColor Plugin — Multi-Agent Delivery for Hermes

## Narrative arc

The LivingColor plugin turns Hermes into a multi-agent delivery platform. It connects Jira, GitLab, and GitHub to a Kanban board where an **Orchestrator** decomposes work and dispatches it to specialist **Workers** — each a Hermes profile with its own model and tools. External coding agents (Claude Code, Codex, OpenCode) can be delegated to from within the worker. The result: a fully autonomous pipeline from ticket to merged PR.

**The aha moment:** One cron job kicks off a chain: analyst reads Jira → picks the most urgent ticket → delegates to dev worker → code gets committed and a GitLab MR appears. Zero human touch.

## Scenes (4 scenes, ~35 seconds total)

### Scene 1 — Plugin Connection (6s)
- Hermes logo/shell appears
- LivingColor plugin tabs into the shell
- "Plugin running inside Hermes" subtitle
- Colors: Classic 3B1B dark background

### Scene 2 — Agent Hierarchy (12s)
- "Orchestrator" node at top — "Decomposes & Routes"
- Three Worker nodes below: Analyst (deepseek), Developer (kimi), Reviewer
- Arrows from Orchestrator → Workers
- "Kanban Board" label connecting all
- Subtitle: "One orchestrator dispatches to specialist agents"

### Scene 3 — External Coding Agents (8s)
- A Worker node expands to show: Claude Code, Codex CLI, OpenCode
- Icons/logos for each
- "Delegates to external coding agents" subtitle

### Scene 4 — Full Pipeline (9s)
- Left to right flow: Cron Job → Orchestrator → bibnum-analyst → bibnum-dev → GitLab MR
- Each step lights up sequentially
- Title: "Fully Autonomous Delivery"
- Subtitle: "From Jira ticket to merged PR — zero human touch"

## Color Palette
Classic 3B1B dark: BG #1C1C1C, PRIMARY #58C4DD, SECONDARY #83C167, ACCENT #FFFF00

## Fonts
Menlo for all Text (monospace on macOS)
No LaTeX needed — text-only video.