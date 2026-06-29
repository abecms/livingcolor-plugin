# LivingColor MoA Delivery Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provision Hermes MoA presets for analyst, planner, and developer delivery agents (standard + premium tiers) and wire LivingColor manifests/defaults to use them.

**Architecture:** Bundled presets in `lc_server/moa/presets.yaml` are idempotently merged into `~/.hermes/config.yaml` at bootstrap with semver. Agent bridges resolve `provider: moa` + preset name via existing `resolve_delivery_inference()`.

**Tech Stack:** Python, PyYAML, Hermes CLI config, LivingColor agent manifests, pytest.

**Spec:** `docs/superpowers/specs/2026-06-28-livingcolor-moa-delivery-design.md`

---

## File map

| File | Responsibility |
| --- | --- |
| `lc_server/moa/presets.yaml` | Bundled MoA preset definitions (6 presets) |
| `lc_server/moa/loader.py` | Load presets + semver metadata |
| `lc_server/integrations/moa_bootstrap.py` | Idempotent merge into Hermes config |
| `lc_server/bootstrap.py` | Call bootstrap at startup |
| `lc_server/model_defaults.py` | MoA preset names, tier env var |
| `lc_server/agent_bridge/inference_config.py` | Optional fallback when preset disabled |
| `lc_server/agent_templates/v1/*.yaml.tmpl` | `provider: moa` on analyst/planner/developer |
| `lc_server/agent_templates/v1/manifest.json` | Version 1.8.0 |
| `tests/lc_server/test_moa_bootstrap.py` | Bootstrap merge tests |
| `tests/lc_server/test_inference_config.py` | MoA provider resolution |

---

### Task 1: Bundled preset loader

**Files:**
- Create: `lc_server/moa/__init__.py`
- Create: `lc_server/moa/presets.yaml`
- Create: `lc_server/moa/loader.py`
- Test: `tests/lc_server/test_moa_loader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/lc_server/test_moa_loader.py
from lc_server.moa.loader import load_bundled_presets, bundled_preset_version


def test_load_bundled_presets_contains_standard_and_premium():
    presets = load_bundled_presets()
    assert "lc-analyst" in presets
    assert "lc-developer-premium" in presets
    assert presets["lc-developer"]["aggregator"]["model"] == "deepseek/deepseek-v4-pro"
    assert presets["lc-developer-premium"]["aggregator"]["model"] == "anthropic/claude-opus-4.8"
    assert bundled_preset_version() == "1.0.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/lc_server/test_moa_loader.py -v`  
Expected: FAIL — module not found

- [ ] **Step 3: Implement loader + presets.yaml**

Create `lc_server/moa/presets.yaml` with all 6 presets per spec (standard + premium), including `livingcolor.presetVersion`, `role`, `tier`, `managed`.

```python
# lc_server/moa/loader.py
from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

_BUNDLE_VERSION = "1.0.0"


@lru_cache(maxsize=1)
def load_bundled_presets() -> dict[str, dict[str, Any]]:
    raw = files("lc_server.moa").joinpath("presets.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    presets = data.get("presets") or {}
    if not isinstance(presets, dict):
        raise ValueError("Invalid moa presets bundle")
    return presets


def bundled_preset_version() -> str:
    return _BUNDLE_VERSION
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/lc_server/test_moa_loader.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lc_server/moa/ tests/lc_server/test_moa_loader.py
git commit -m "feat: add bundled LivingColor MoA preset definitions"
```

---

### Task 2: MoA bootstrap merge

**Files:**
- Create: `lc_server/integrations/moa_bootstrap.py`
- Test: `tests/lc_server/test_moa_bootstrap.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/lc_server/test_moa_bootstrap.py
import yaml
import pytest
from lc_server.integrations.moa_bootstrap import ensure_moa_presets_from_bundle, _parse_version


def test_parse_version():
    assert _parse_version("1.0.0") == (1, 0, 0)


def test_bootstrap_creates_presets(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("model:\n  provider: openrouter\n", encoding="utf-8")
    monkeypatch.setattr(
        "lc_server.integrations.moa_bootstrap.default_hermes_root",
        lambda: tmp_path,
    )
    changed = ensure_moa_presets_from_bundle()
    assert "lc-analyst" in changed
    saved = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert saved["moa"]["presets"]["lc-analyst"]["livingcolor"]["managed"] is True


def test_bootstrap_skips_newer_local(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump({
            "moa": {
                "presets": {
                    "lc-analyst": {
                        "enabled": True,
                        "aggregator": {"provider": "openrouter", "model": "custom/model"},
                        "livingcolor": {"presetVersion": "9.0.0", "managed": True},
                    }
                }
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "lc_server.integrations.moa_bootstrap.default_hermes_root",
        lambda: tmp_path,
    )
    changed = ensure_moa_presets_from_bundle()
    assert "lc-analyst" not in changed
    saved = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert saved["moa"]["presets"]["lc-analyst"]["aggregator"]["model"] == "custom/model"
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/lc_server/test_moa_bootstrap.py -v`

- [ ] **Step 3: Implement moa_bootstrap.py**

Key functions:
- `_parse_version(s) -> tuple[int, ...]`
- `_should_upgrade(existing: dict, bundled: dict) -> bool`
- `_merge_presets_into_config(data: dict, bundled: dict) -> list[str]`
- `ensure_moa_presets_from_bundle() -> list[str]` — returns names changed

Use `default_hermes_root()` from `mcp_config_bridge`. Write YAML with `sort_keys=False`.

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/lc_server/test_moa_bootstrap.py -v`

- [ ] **Step 5: Commit**

```bash
git add lc_server/integrations/moa_bootstrap.py tests/lc_server/test_moa_bootstrap.py
git commit -m "feat: idempotent Hermes MoA preset bootstrap with semver"
```

---

### Task 3: Bootstrap hook

**Files:**
- Modify: `lc_server/bootstrap.py`

- [ ] **Step 1: Add bootstrap call after MCP env bootstrap**

```python
    try:
        from lc_server.integrations.moa_bootstrap import ensure_moa_presets_from_bundle

        ensure_moa_presets_from_bundle()
    except Exception as exc:
        logger.warning("MoA preset bootstrap skipped: %s", exc)
```

- [ ] **Step 2: Smoke test**

Run: `pytest tests/lc_server/test_moa_bootstrap.py tests/lc_server/test_moa_loader.py -v`  
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add lc_server/bootstrap.py
git commit -m "feat: bootstrap LivingColor MoA presets at server startup"
```

---

### Task 4: model_defaults + tier env

**Files:**
- Modify: `lc_server/model_defaults.py`
- Test: `tests/lc_server/test_inference_config.py`

- [ ] **Step 1: Write failing test**

```python
def test_moa_tier_premium(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_MOA_TIER", "premium")
    from importlib import reload
    import lc_server.model_defaults as md
    reload(md)
    assert md.LIVINGCOLOR_DEVELOPER_MODEL == "lc-developer-premium"
    assert md.LIVINGCOLOR_DEVELOPER_PROVIDER == "moa"
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/lc_server/test_inference_config.py::test_moa_tier_premium -v`

- [ ] **Step 3: Update model_defaults.py**

```python
import os

LIVINGCOLOR_MOA_PROVIDER = "moa"

def _moa_preset(base: str) -> str:
    tier = os.getenv("LIVINGCOLOR_MOA_TIER", "standard").strip().lower()
    if tier == "premium":
        return f"{base}-premium"
    return base

LIVINGCOLOR_ANALYST_MODEL = _moa_preset("lc-analyst")
LIVINGCOLOR_ANALYST_PROVIDER = LIVINGCOLOR_MOA_PROVIDER
# ... planner, developer similarly
```

Keep single-model fallback constants for disabled-preset fallback:

```python
LIVINGCOLOR_ORCHESTRATION_FALLBACK_MODEL = "openrouter/owl-alpha"
LIVINGCOLOR_DEVELOPER_FALLBACK_MODEL = "deepseek/deepseek-v4-pro"
LIVINGCOLOR_FALLBACK_PROVIDER = "openrouter"
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/lc_server/test_inference_config.py -v`

- [ ] **Step 5: Commit**

```bash
git add lc_server/model_defaults.py tests/lc_server/test_inference_config.py
git commit -m "feat: MoA preset defaults with premium tier env override"
```

---

### Task 5: Agent manifest templates

**Files:**
- Modify: `lc_server/agent_templates/v1/analyst.yaml.tmpl`
- Modify: `lc_server/agent_templates/v1/planner.yaml.tmpl`
- Modify: `lc_server/agent_templates/v1/developer.yaml.tmpl`
- Modify: `lc_server/agent_templates/v1/manifest.json`
- Test: `tests/lc_server/test_provisioning.py`

- [ ] **Step 1: Write failing assertion**

Add to provisioning test:

```python
def test_templates_use_moa_provider():
    rendered = render_template("analyst.yaml.tmpl", ...)
    assert "provider: moa" in rendered
    assert "model: lc-analyst" in rendered
```

- [ ] **Step 2: Update templates**

Set `provider: moa` and `model: lc-{role}` on analyst, planner, developer templates. Bump manifest.json to `"version": "1.8.0"`.

- [ ] **Step 3: Run tests**

Run: `pytest tests/lc_server/test_provisioning.py -v`

- [ ] **Step 4: Commit**

```bash
git add lc_server/agent_templates/v1/
git commit -m "feat: provision delivery agent manifests with MoA presets"
```

---

### Task 6: Inference fallback for disabled presets

**Files:**
- Modify: `lc_server/agent_bridge/inference_config.py`
- Test: `tests/lc_server/test_inference_config.py`

- [ ] **Step 1: Write failing test**

Test that when Hermes config has `lc-analyst` with `enabled: false`, resolve falls back to owl-alpha.

- [ ] **Step 2: Implement optional check**

When `effective_provider == "moa"`, load Hermes config; if preset missing or `enabled: false`, return fallback model/provider for role (pass `role` kwarg or handle in agent factories).

Minimal approach: add `resolve_moa_or_fallback(model, provider, *, fallback_model, fallback_provider)` helper called from agent factories after `resolve_delivery_inference`.

- [ ] **Step 3: Run tests**

Run: `pytest tests/lc_server/test_inference_config.py -v`

- [ ] **Step 4: Commit**

```bash
git add lc_server/agent_bridge/inference_config.py tests/lc_server/test_inference_config.py
git commit -m "feat: fallback to single-model when MoA preset disabled"
```

---

### Task 7: Integration verification

- [ ] **Step 1: Run full lc_server test suite**

Run: `pytest tests/lc_server/ -v --tb=short`  
Expected: all pass

- [ ] **Step 2: Manual smoke (optional)**

Run server bootstrap in dev; verify `~/.hermes/config.yaml` contains `lc-analyst` under `moa.presets`.

- [ ] **Step 3: Final commit if any fixes**

```bash
git commit -m "test: verify MoA delivery integration"
```

---

## Spec coverage checklist

| Spec requirement | Task |
| --- | --- |
| 6 bundled presets | Task 1 |
| Semver bootstrap | Task 2 |
| Plugin startup hook | Task 3 |
| Standard + premium tiers | Task 1, 4 |
| Manifest templates moa | Task 5 |
| Fallback when disabled | Task 6 |
| Tests | Tasks 1–7 |
