# LivingColor MoA Delivery Agents Design

**Date:** 2026-06-28  
**Status:** Approved (2026-06-28 — user validated)  
**Branch:** `feature/livingcolor-moa-delivery`  
**Hermes reference:** [Mixture of Agents](https://hermes-agent.nousresearch.com/docs/user-guide/features/mixture-of-agents)

## Summary

Wire LivingColor delivery agents (analyst, planner, developer) through **native Hermes MoA presets** instead of single-model inference. LivingColor bundles and idempotently provisions named presets into `~/.hermes/config.yaml` at plugin startup, with semver-gated upgrades. Agent manifests point at `provider: moa` and a preset name.

Two quality tiers ship in v1:

- **Standard** (default) — best quality/price for daily volume.
- **Premium** — Opus 4.8 aggregators for maximum quality on analyst, planner, and developer.

Publisher and reporter remain single-model (out of scope).

## Goals

- Improve output quality on analyst readiness, Gate 1 planning, and developer patch generation.
- Use Hermes MoA natively so tool calls, session persistence, prompt caching, and the agent loop stay unchanged.
- Reproducible, versioned preset definitions under LivingColor control.
- Idempotent bootstrap that never clobbers user-owned non-`lc-*` presets.

## Non-Goals

- Custom multi-call aggregation in LivingColor Python (no duplicate Hermes MoA loop).
- MoA on publisher, reporter, or orchestrator in v1.
- Automatic cost-based routing between tiers (manual/env/manifest selection only in v1).
- Upstream Hermes changes.

## Brainstorming Decisions

| Topic | Decision |
| --- | --- |
| Primary objective | Output quality |
| Scope | analyst → planner → developer |
| Implementation | Native Hermes MoA presets |
| Composition | Fixed per role, LivingColor-versioned |
| Provisioning | Idempotent merge at plugin startup |
| Upgrade policy | Semver — overwrite only when bundled version > installed `livingcolor.presetVersion` |
| Developer references | `owl-alpha`, `claude-sonnet-4.6`, `glm-5.2` (no gpt-5.5 on standard dev) |
| Best quality tier | Opus 4.8 aggregators on all three roles |

---

## Architecture

```text
bootstrap_livingcolor_server()
  └─ ensure_moa_presets_from_bundle()
       └─ read lc_server/moa/presets.yaml
       └─ merge lc-* / lc-*-premium into ~/.hermes/config.yaml (semver)

HermesRuntimeBridge → agent bridges (analyst | planner | developer)
  └─ resolve_delivery_inference(manifest, role_defaults)
       └─ provider: moa, model: lc-{role}[-premium]
            └─ Hermes AIAgent
                 1. reference_models (no tools, trimmed transcript)
                 2. aggregator (full system prompt + tools + JSON completion)
```

### MoA roles (Hermes)

| Role | Responsibility |
| --- | --- |
| **Reference models** | Parallel advisory analysis on user/assistant text only |
| **Aggregator** | Acting model — writes the response, emits tool calls, produces structured JSON |

---

## Preset Catalog

All presets use `provider: openrouter` unless noted. Temperature defaults: `reference_temperature: 0.6`, `aggregator_temperature: 0.4`, `max_tokens: 4096`, `enabled: true`.

### Standard tier (default)

| Preset | Aggregator | Reference models | Rationale |
| --- | --- | --- | --- |
| `lc-analyst` | `openrouter/owl-alpha` | `deepseek/deepseek-v4-pro`, `openai/gpt-5.5` | Readiness synthesis + technical + reasoning perspectives |
| `lc-planner` | `openrouter/owl-alpha` | `deepseek/deepseek-v4-pro`, `openai/gpt-5.5` | Gate 1 plan quality before developer handoff |
| `lc-developer` | `deepseek/deepseek-v4-pro` | `openrouter/owl-alpha`, `anthropic/claude-sonnet-4.6`, `z-ai/glm-5.2` | Code execution aggregator; architecture, code review, frontend references |

### Premium tier (best quality)

| Preset | Aggregator | Reference models | Rationale |
| --- | --- | --- | --- |
| `lc-analyst-premium` | `anthropic/claude-opus-4.8` | `openai/gpt-5.5`, `deepseek/deepseek-v4-pro`, `anthropic/claude-sonnet-4.6` | Maximum readiness reasoning |
| `lc-planner-premium` | `anthropic/claude-opus-4.8` | `openai/gpt-5.5`, `deepseek/deepseek-v4-pro`, `openrouter/owl-alpha` | Highest-leverage Gate 1 quality |
| `lc-developer-premium` | `anthropic/claude-opus-4.8` | `deepseek/deepseek-v4-pro`, `anthropic/claude-sonnet-4.6`, `z-ai/glm-5.2`, `openai/gpt-5.5` | Opus tool loop with code + UI + alt-architecture references |

Each preset includes metadata:

```yaml
livingcolor:
  presetVersion: "1.0.0"
  role: analyst | planner | developer
  tier: standard | premium
  managed: true
```

Bundled source of truth: `lc_server/moa/presets.yaml`.

---

## Bootstrap & Semver

New module: `lc_server/integrations/moa_bootstrap.py`

Behavior (mirrors `mcp_env_bootstrap.py` patterns):

1. Load bundled presets from `lc_server/moa/presets.yaml`.
2. Load `~/.hermes/config.yaml` (via `default_hermes_root()`).
3. For each LivingColor-managed preset (`lc-*` with `livingcolor.managed: true`):
   - **Missing** → insert preset.
   - **Present, bundled version newer** → replace entire preset dict.
   - **Present, local version ≥ bundled** → skip (preserve user tweaks).
   - **Present, no `livingcolor` metadata** → treat as version `0.0.0`, upgrade if bundled > 0.
4. Never modify presets that are not LivingColor-managed.
5. Log `INFO` on create/upgrade, `DEBUG` on skip.

Hook: call `ensure_moa_presets_from_bundle()` from `bootstrap_livingcolor_server()` after MCP bootstrap.

---

## LivingColor Wiring

### `model_defaults.py`

Standard tier defaults:

```python
LIVINGCOLOR_ANALYST_MODEL = "lc-analyst"
LIVINGCOLOR_ANALYST_PROVIDER = "moa"
LIVINGCOLOR_PLANNER_MODEL = "lc-planner"
LIVINGCOLOR_PLANNER_PROVIDER = "moa"
LIVINGCOLOR_DEVELOPER_MODEL = "lc-developer"
LIVINGCOLOR_DEVELOPER_PROVIDER = "moa"
```

Premium override via environment (optional v1):

```bash
LIVINGCOLOR_MOA_TIER=premium   # switches role defaults to lc-*-premium
```

### Agent manifest templates

Update `analyst.yaml.tmpl`, `planner.yaml.tmpl`, `developer.yaml.tmpl`:

```yaml
runtime:
  type: hermes
  provider: moa
  model: lc-analyst   # or lc-planner / lc-developer
```

Bump `manifest.json` version to `1.8.0` so `upgrade_all_project_manifests()` refreshes provisioned projects.

### `resolve_delivery_inference()`

No signature change. Must correctly pass through `provider: moa` and preset name to `AIAgent` / `resolve_runtime_provider`.

**Fallback:** when a preset has `enabled: false`, fall back to the role's single-model pair:

| Role | Fallback model | Fallback provider |
| --- | --- | --- |
| analyst | `openrouter/owl-alpha` | `openrouter` |
| planner | `openrouter/owl-alpha` | `openrouter` |
| developer | `deepseek/deepseek-v4-pro` | `openrouter` |

Log at `INFO` when fallback activates.

---

## Data Flow

### Analyst

1. User prompt = Jira snapshot (via `build_analyst_user_prompt`).
2. References score readiness from multiple angles.
3. Aggregator produces JSON → `parse_analyst_completion`.

### Planner

1. User prompt = context pack (via `build_planner_user_prompt`).
2. References challenge file lists and risks.
3. Aggregator produces Gate 1 JSON → `parse_planner_completion`.

### Developer

1. User prompt = approved plan + workspace context.
2. References review scope, code approach, UI impact.
3. Aggregator runs file/terminal/skills tools → JSON completion block.

---

## Error Handling

| Condition | Behavior |
| --- | --- |
| Reference credential failure | Hermes continues with successful references (native MoA behavior); LivingColor logs warning |
| Preset missing after bootstrap | `is_delivery_llm_available()` false; prerequisites surface clear error |
| Preset `enabled: false` | Fallback single-model for that role |
| Aggregator parse failure | Existing role-specific errors (`AnalystParseError`, `PlannerParseError`) unchanged |

---

## Cost Notes

MoA multiplies LLM calls per agent iteration:

| Role | Calls per iteration (standard) |
| --- | --- |
| analyst | 3 (2 ref + 1 agg) |
| planner | 3 (2 ref + 1 agg) |
| developer | 4 (3 ref + 1 agg) |
| developer-premium | 5 (4 ref + 1 agg) |

Premium tier with Opus aggregator is intentionally expensive — use via `LIVINGCOLOR_MOA_TIER=premium` or per-project manifest override.

---

## Testing

| Test | Assertion |
| --- | --- |
| `test_moa_bootstrap_creates_presets` | All 6 presets written when absent |
| `test_moa_bootstrap_skips_newer_local` | Local v1.1.0 not downgraded by bundled v1.0.0 |
| `test_moa_bootstrap_upgrades_older` | Local v1.0.0 upgraded to bundled v1.1.0 |
| `test_moa_bootstrap_never_touches_custom` | Non-`lc-*` presets unchanged |
| `test_inference_config_moa_provider` | Resolves `moa` + `lc-planner` |
| `test_moa_tier_env_premium` | `LIVINGCOLOR_MOA_TIER=premium` → `lc-developer-premium` |
| `test_provisioning_templates_moa` | Rendered manifests use `provider: moa` |
| Existing analyst/planner/developer tests | Pass with mocked agent factory |

---

## Deliverables

1. `lc_server/moa/presets.yaml` — bundled preset definitions
2. `lc_server/moa/loader.py` — load and validate bundled presets
3. `lc_server/integrations/moa_bootstrap.py` — idempotent Hermes config merge
4. `lc_server/bootstrap.py` — hook bootstrap call
5. `lc_server/model_defaults.py` — MoA preset names + tier env support
6. `lc_server/agent_templates/v1/{analyst,planner,developer}.yaml.tmpl` — `provider: moa`
7. `lc_server/agent_templates/v1/manifest.json` — version bump to 1.8.0
8. `tests/lc_server/test_moa_bootstrap.py`
9. Updates to `tests/lc_server/test_inference_config.py`, `test_provisioning.py`

---

## Future (out of v1 scope)

- Auto-route to premium tier based on analyst `confidenceLevel`, `estimatedDays`, or ticket labels.
- Dashboard toggle for MoA tier per project.
- Per-role premium overrides in project manifests.
