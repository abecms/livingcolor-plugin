# LivingColor Repository Interconnection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `livingcolor-plugin` consume a pinned, validated `livingcolor-skills` bundle for delivery-quality enrichment, and let `livingcolor-evolution` open follow-up plugin lock bump pull requests after skills updates are validated.

**Architecture:** Add a small skills integration boundary in the plugin that reads `livingcolor.skills.lock.json`, materializes a pinned GitHub archive into LivingColor-managed state, validates the `code-review-pipeline` bundle, and renders read-only prompt guidance for existing agents. Keep developer and publisher safety rules owned by the plugin. Extend `livingcolor-evolution` with a second GitHub PR workflow that bumps only the plugin lock file after a validated skills commit is ready.

**Tech Stack:** Python 3.13, pytest, Pydantic-free dataclasses, urllib, zipfile, PyYAML, FastAPI-adjacent plugin services, TypeScript 5.7, pnpm, Vitest, GitHub REST API.

---

## File Structure

### `livingcolor-plugin`

- Create `livingcolor.skills.lock.json`: root lock file pinning `Tamsi/livingcolor-skills`.
- Create `lc_server/integrations/skills/__init__.py`: package exports.
- Create `lc_server/integrations/skills/lock.py`: lock dataclass, validation, and default path loader.
- Create `lc_server/integrations/skills/cache.py`: cache paths, archive extraction, and cache status.
- Create `lc_server/integrations/skills/source.py`: GitHub archive downloader with a testable source protocol.
- Create `lc_server/integrations/skills/registry.py`: bundle and skill validation for the extracted registry.
- Create `lc_server/integrations/skills/guidance.py`: render external skill prompts into read-only guidance sections.
- Create `delivery_runtime/context/skills_context.py`: render the `Project Stack / Ticket Tracker / VCS / Delivery Context` markdown contract from a `ContextPack`.
- Modify `delivery_runtime/context/models.py`: add `vcs_provider` and `skills_context_markdown` to `ContextPack`.
- Modify `delivery_runtime/context/pack_builder.py`: compute `vcs_provider` and `skills_context_markdown`.
- Modify `delivery_runtime/context/planner_prompt.py`: include external skills context in planner prompts.
- Modify `lc_server/agent_bridge/hermes_analyst.py`: append ticket-analyst guidance to analyst prompts when available.
- Modify `lc_server/agent_bridge/hermes_planner.py`: rely on the enriched context pack prompt for code-architect context.
- Modify `lc_server/agent_bridge/hermes_developer.py`: append `code-review-pipeline` guidance only during `code_quality_review`.
- Modify `README.md`: document the pinned skills integration and rollback.
- Test `tests/lc_server/test_external_skills_lock.py`.
- Test `tests/lc_server/test_external_skills_cache.py`.
- Test `tests/lc_server/test_external_skills_registry.py`.
- Test `tests/delivery_runtime/test_skills_context.py`.
- Test `tests/lc_server/test_external_skills_prompt_injection.py`.

### `livingcolor-evolution`

These changes are implemented in `Tamsi/livingcolor-evolution`, not in this plugin repository.

- Modify `packages/core/src/domain/types.ts`: add plugin lock bump types.
- Modify `packages/core/src/ports/index.ts`: add a plugin lock pull request port.
- Create `packages/github/src/plugin-lock-bump.ts`: create a plugin lock bump PR through GitHub REST.
- Modify `packages/github/src/index.ts`: export the plugin bump service.
- Modify `packages/scheduler/src/index.ts`: add a plugin bump pipeline entry.
- Modify `packages/cli/src/index.ts`: add `curator plugin-bump`.
- Modify `.github/workflows/curator-weekly.yml`: add a `plugin-lock-bump` job that runs after the curator job when a validated skills ref is provided through workflow inputs.
- Test `packages/github/src/__tests__/plugin-lock-bump.test.ts`.
- Test `packages/scheduler/src/__tests__/plugin-bump.test.ts`.

## Scope Notes

This plan deliberately avoids a direct runtime dependency on `@hermes/runner` inside the plugin. The first plugin slice materializes external skills and uses their prompts as read-only guidance for existing Hermes agents. That keeps permissions and delivery ownership unchanged.

The `livingcolor-evolution` slice is a separate repository change. Implement it after the plugin lock format and validation tests exist, so the evolution-side bump generator can target a real contract.

## Task 1: Plugin Lock File And Validation

**Files:**
- Create: `livingcolor.skills.lock.json`
- Create: `lc_server/integrations/skills/__init__.py`
- Create: `lc_server/integrations/skills/lock.py`
- Test: `tests/lc_server/test_external_skills_lock.py`

- [ ] **Step 1: Write failing lock validation tests**

Create `tests/lc_server/test_external_skills_lock.py`:

```python
from __future__ import annotations

import json

import pytest


VALID_LOCK = {
    "repo": "Tamsi/livingcolor-skills",
    "ref": "v0.1.0",
    "resolvedCommit": "fdf1be62d61ef74b51d91ae81ed718350dce20d5",
    "bundle": "code-review-pipeline",
    "skills": ["ticket-analyst", "code-architect", "qa-reviewer", "security-auditor"],
    "updatedBy": "livingcolor-evolution",
}


def test_parse_valid_external_skills_lock():
    from lc_server.integrations.skills.lock import parse_external_skills_lock

    lock = parse_external_skills_lock(VALID_LOCK)

    assert lock.repo == "Tamsi/livingcolor-skills"
    assert lock.ref == "v0.1.0"
    assert lock.resolved_commit == "fdf1be62d61ef74b51d91ae81ed718350dce20d5"
    assert lock.bundle == "code-review-pipeline"
    assert lock.skills == ("ticket-analyst", "code-architect", "qa-reviewer", "security-auditor")
    assert lock.updated_by == "livingcolor-evolution"


def test_lock_rejects_unapproved_repo():
    from lc_server.integrations.skills.lock import parse_external_skills_lock

    payload = {**VALID_LOCK, "repo": "Other/livingcolor-skills"}

    with pytest.raises(ValueError, match="Unsupported skills repo"):
        parse_external_skills_lock(payload)


def test_lock_rejects_moving_main_ref():
    from lc_server.integrations.skills.lock import parse_external_skills_lock

    payload = {**VALID_LOCK, "ref": "main"}

    with pytest.raises(ValueError, match="must not be a moving branch"):
        parse_external_skills_lock(payload)


def test_lock_rejects_short_resolved_commit():
    from lc_server.integrations.skills.lock import parse_external_skills_lock

    payload = {**VALID_LOCK, "resolvedCommit": "abc123"}

    with pytest.raises(ValueError, match="resolvedCommit"):
        parse_external_skills_lock(payload)


def test_load_external_skills_lock_from_root(tmp_path):
    from lc_server.integrations.skills.lock import load_external_skills_lock

    path = tmp_path / "livingcolor.skills.lock.json"
    path.write_text(json.dumps(VALID_LOCK), encoding="utf-8")

    lock = load_external_skills_lock(path)

    assert lock.bundle == "code-review-pipeline"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/lc_server/test_external_skills_lock.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lc_server.integrations.skills'`.

- [ ] **Step 3: Add the root lock file**

Create `livingcolor.skills.lock.json`:

```json
{
  "repo": "Tamsi/livingcolor-skills",
  "ref": "v0.1.0",
  "resolvedCommit": "fdf1be62d61ef74b51d91ae81ed718350dce20d5",
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

The commit SHA above is the current `Tamsi/livingcolor-skills` `main` commit observed while this plan was written.

- [ ] **Step 4: Add the skills integration package**

Create `lc_server/integrations/skills/__init__.py`:

```python
"""External LivingColor skills integration boundary."""

from lc_server.integrations.skills.lock import ExternalSkillsLock, load_external_skills_lock

__all__ = ["ExternalSkillsLock", "load_external_skills_lock"]
```

- [ ] **Step 5: Implement lock parsing**

Create `lc_server/integrations/skills/lock.py`:

```python
"""Validated lock-file contract for external LivingColor skills."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APPROVED_SKILLS_REPO = "Tamsi/livingcolor-skills"
DEFAULT_LOCK_PATH = Path(__file__).resolve().parents[3] / "livingcolor.skills.lock.json"
FORBIDDEN_MOVING_REFS = {"main", "master", "develop", "dev"}
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class ExternalSkillsLock:
    repo: str
    ref: str
    resolved_commit: str
    bundle: str
    skills: tuple[str, ...]
    updated_by: str

    @property
    def cache_key(self) -> str:
        return self.resolved_commit


def load_external_skills_lock(path: str | Path | None = None) -> ExternalSkillsLock:
    lock_path = Path(path) if path is not None else DEFAULT_LOCK_PATH
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    return parse_external_skills_lock(payload)


def parse_external_skills_lock(payload: dict[str, Any]) -> ExternalSkillsLock:
    repo = _require_str(payload, "repo")
    if repo != APPROVED_SKILLS_REPO:
        raise ValueError(f"Unsupported skills repo: {repo}")

    ref = _require_str(payload, "ref")
    if ref.lower() in FORBIDDEN_MOVING_REFS:
        raise ValueError("External skills ref must not be a moving branch")

    resolved_commit = _require_str(payload, "resolvedCommit").lower()
    if not FULL_SHA_RE.fullmatch(resolved_commit):
        raise ValueError("resolvedCommit must be a full 40-character lowercase git SHA")

    bundle = _require_str(payload, "bundle")
    raw_skills = payload.get("skills")
    if not isinstance(raw_skills, list) or not raw_skills:
        raise ValueError("skills must be a non-empty list")
    skills = tuple(str(item).strip() for item in raw_skills if str(item).strip())
    if len(skills) != len(raw_skills):
        raise ValueError("skills must contain only non-empty strings")

    return ExternalSkillsLock(
        repo=repo,
        ref=ref,
        resolved_commit=resolved_commit,
        bundle=bundle,
        skills=skills,
        updated_by=str(payload.get("updatedBy") or "").strip(),
    )


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()
```

- [ ] **Step 6: Run lock tests**

Run:

```bash
pytest tests/lc_server/test_external_skills_lock.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```bash
git add livingcolor.skills.lock.json lc_server/integrations/skills/__init__.py lc_server/integrations/skills/lock.py tests/lc_server/test_external_skills_lock.py
git commit -m "feat: add external skills lock contract"
```

## Task 2: Skills Cache And GitHub Archive Materialization

**Files:**
- Create: `lc_server/integrations/skills/cache.py`
- Create: `lc_server/integrations/skills/source.py`
- Modify: `lc_server/integrations/skills/__init__.py`
- Test: `tests/lc_server/test_external_skills_cache.py`

- [ ] **Step 1: Write failing cache tests**

Create `tests/lc_server/test_external_skills_cache.py`:

```python
from __future__ import annotations

import io
import zipfile
from pathlib import Path


class InMemoryArchiveSource:
    def __init__(self, archive: bytes) -> None:
        self.archive = archive
        self.calls: list[tuple[str, str, str]] = []

    def fetch_archive(self, *, repo: str, ref: str, resolved_commit: str) -> bytes:
        self.calls.append((repo, ref, resolved_commit))
        return self.archive


def _skills_archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        prefix = "livingcolor-skills-0123456/"
        zf.writestr(prefix + "registry/bundles/code-review-pipeline/bundle.yaml", "name: code-review-pipeline\nskills:\n  - ticket-analyst\n")
        zf.writestr(prefix + "registry/ticket-analyst/skill.yaml", "name: ticket-analyst\nversion: 2.0.0\n")
        zf.writestr(prefix + "registry/ticket-analyst/prompt.md", "# Ticket Analyst\n")
    return buffer.getvalue()


def _lock():
    from lc_server.integrations.skills.lock import ExternalSkillsLock

    return ExternalSkillsLock(
        repo="Tamsi/livingcolor-skills",
        ref="v0.1.0",
        resolved_commit="0123456789abcdef0123456789abcdef01234567",
        bundle="code-review-pipeline",
        skills=("ticket-analyst",),
        updated_by="livingcolor-evolution",
    )


def test_materialize_skills_archive_under_livingcolor_cache(livingcolor_home):
    from lc_server.integrations.skills.cache import materialize_external_skills

    source = InMemoryArchiveSource(_skills_archive())
    result = materialize_external_skills(_lock(), source=source)

    assert result.available is True
    assert result.registry_path == livingcolor_home / "skills-cache" / "livingcolor-skills" / _lock().resolved_commit / "registry"
    assert (result.registry_path / "ticket-analyst" / "prompt.md").is_file()
    assert source.calls == [("Tamsi/livingcolor-skills", "v0.1.0", _lock().resolved_commit)]


def test_materialize_reuses_existing_cache(livingcolor_home):
    from lc_server.integrations.skills.cache import materialize_external_skills

    source = InMemoryArchiveSource(_skills_archive())
    first = materialize_external_skills(_lock(), source=source)
    second = materialize_external_skills(_lock(), source=source)

    assert first.registry_path == second.registry_path
    assert len(source.calls) == 1


def test_materialize_reports_fetch_error(livingcolor_home):
    from lc_server.integrations.skills.cache import materialize_external_skills

    class BrokenSource:
        def fetch_archive(self, *, repo: str, ref: str, resolved_commit: str) -> bytes:
            raise RuntimeError("network unavailable")

    result = materialize_external_skills(_lock(), source=BrokenSource())

    assert result.available is False
    assert "network unavailable" in result.error
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/lc_server/test_external_skills_cache.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `lc_server.integrations.skills.cache`.

- [ ] **Step 3: Implement the GitHub source**

Create `lc_server/integrations/skills/source.py`:

```python
"""Download source archives for pinned external skills."""

from __future__ import annotations

import urllib.request
from typing import Protocol


class SkillsArchiveSource(Protocol):
    def fetch_archive(self, *, repo: str, ref: str, resolved_commit: str) -> bytes:
        ...


class GitHubArchiveSkillsSource:
    """Fetch public GitHub repository archives without embedding credentials."""

    def fetch_archive(self, *, repo: str, ref: str, resolved_commit: str) -> bytes:
        del resolved_commit
        url = f"https://github.com/{repo}/archive/{ref}.zip"
        request = urllib.request.Request(url, headers={"User-Agent": "livingcolor-plugin"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
```

- [ ] **Step 4: Implement cache extraction**

Create `lc_server/integrations/skills/cache.py`:

```python
"""Materialize pinned external skills under LivingColor-managed cache paths."""

from __future__ import annotations

import io
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lc_constants import ensure_livingcolor_home_layout, get_livingcolor_home
from lc_server.integrations.skills.lock import ExternalSkillsLock
from lc_server.integrations.skills.source import GitHubArchiveSkillsSource, SkillsArchiveSource


@dataclass(frozen=True)
class ExternalSkillsCacheResult:
    available: bool
    registry_path: Path
    cache_path: Path
    source_ref: str
    resolved_commit: str
    error: str = ""


def external_skills_cache_root() -> Path:
    ensure_livingcolor_home_layout()
    root = get_livingcolor_home() / "skills-cache" / "livingcolor-skills"
    root.mkdir(parents=True, exist_ok=True)
    return root


def materialize_external_skills(
    lock: ExternalSkillsLock,
    *,
    source: SkillsArchiveSource | None = None,
) -> ExternalSkillsCacheResult:
    cache_path = external_skills_cache_root() / lock.resolved_commit
    registry_path = cache_path / "registry"
    if registry_path.is_dir():
        return ExternalSkillsCacheResult(
            available=True,
            registry_path=registry_path,
            cache_path=cache_path,
            source_ref=lock.ref,
            resolved_commit=lock.resolved_commit,
        )

    try:
        archive_source = source or GitHubArchiveSkillsSource()
        archive = archive_source.fetch_archive(
            repo=lock.repo,
            ref=lock.ref,
            resolved_commit=lock.resolved_commit,
        )
        _extract_archive(archive, cache_path)
    except Exception as exc:
        return ExternalSkillsCacheResult(
            available=False,
            registry_path=registry_path,
            cache_path=cache_path,
            source_ref=lock.ref,
            resolved_commit=lock.resolved_commit,
            error=str(exc),
        )

    return ExternalSkillsCacheResult(
        available=registry_path.is_dir(),
        registry_path=registry_path,
        cache_path=cache_path,
        source_ref=lock.ref,
        resolved_commit=lock.resolved_commit,
        error="" if registry_path.is_dir() else "archive did not contain registry/",
    )


def _extract_archive(archive: bytes, destination: Path) -> None:
    temp_path = destination.with_suffix(".tmp")
    if temp_path.exists():
        shutil.rmtree(temp_path)
    temp_path.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        zf.extractall(temp_path)

    roots = [path for path in temp_path.iterdir() if path.is_dir()]
    source_root = roots[0] if len(roots) == 1 else temp_path
    if destination.exists():
        shutil.rmtree(destination)
    shutil.move(str(source_root), destination)
    if temp_path.exists():
        shutil.rmtree(temp_path)
```

- [ ] **Step 5: Update package exports**

Modify `lc_server/integrations/skills/__init__.py`:

```python
"""External LivingColor skills integration boundary."""

from lc_server.integrations.skills.cache import ExternalSkillsCacheResult, materialize_external_skills
from lc_server.integrations.skills.lock import ExternalSkillsLock, load_external_skills_lock

__all__ = [
    "ExternalSkillsCacheResult",
    "ExternalSkillsLock",
    "load_external_skills_lock",
    "materialize_external_skills",
]
```

- [ ] **Step 6: Run cache tests**

Run:

```bash
pytest tests/lc_server/test_external_skills_cache.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add lc_server/integrations/skills/__init__.py lc_server/integrations/skills/cache.py lc_server/integrations/skills/source.py tests/lc_server/test_external_skills_cache.py
git commit -m "feat: cache pinned external skills"
```

## Task 3: Registry Validation And Read-Only Guidance Rendering

**Files:**
- Create: `lc_server/integrations/skills/registry.py`
- Create: `lc_server/integrations/skills/guidance.py`
- Modify: `lc_server/integrations/skills/__init__.py`
- Test: `tests/lc_server/test_external_skills_registry.py`

- [ ] **Step 1: Write failing registry tests**

Create `tests/lc_server/test_external_skills_registry.py`:

```python
from __future__ import annotations


def _write_registry(root):
    bundle_dir = root / "bundles" / "code-review-pipeline"
    bundle_dir.mkdir(parents=True)
    bundle_dir.joinpath("bundle.yaml").write_text(
        "name: code-review-pipeline\nskills:\n  - ticket-analyst\n  - code-architect\n",
        encoding="utf-8",
    )
    for name, prompt in {
        "ticket-analyst": "# Ticket Analyst\nAssess readiness.",
        "code-architect": "# Code Architect\nAssess architecture.",
    }.items():
        skill_dir = root / name
        skill_dir.mkdir()
        skill_dir.joinpath("skill.yaml").write_text(f"name: {name}\nversion: 2.0.0\n", encoding="utf-8")
        skill_dir.joinpath("prompt.md").write_text(prompt, encoding="utf-8")


def test_resolve_valid_external_bundle(tmp_path):
    from lc_server.integrations.skills.registry import resolve_external_bundle

    registry = tmp_path / "registry"
    registry.mkdir()
    _write_registry(registry)

    bundle = resolve_external_bundle(
        registry_path=registry,
        bundle_name="code-review-pipeline",
        required_skills=("ticket-analyst", "code-architect"),
        resolved_commit="0123456789abcdef0123456789abcdef01234567",
    )

    assert bundle.available is True
    assert bundle.bundle_name == "code-review-pipeline"
    assert [skill.name for skill in bundle.skills] == ["ticket-analyst", "code-architect"]
    assert bundle.skills[0].prompt.startswith("# Ticket Analyst")


def test_resolve_external_bundle_reports_missing_skill(tmp_path):
    from lc_server.integrations.skills.registry import resolve_external_bundle

    registry = tmp_path / "registry"
    registry.mkdir()
    _write_registry(registry)

    bundle = resolve_external_bundle(
        registry_path=registry,
        bundle_name="code-review-pipeline",
        required_skills=("ticket-analyst", "security-auditor"),
        resolved_commit="0123456789abcdef0123456789abcdef01234567",
    )

    assert bundle.available is False
    assert "security-auditor" in bundle.error


def test_guidance_renders_selected_skills(tmp_path):
    from lc_server.integrations.skills.guidance import render_external_guidance
    from lc_server.integrations.skills.registry import resolve_external_bundle

    registry = tmp_path / "registry"
    registry.mkdir()
    _write_registry(registry)
    bundle = resolve_external_bundle(
        registry_path=registry,
        bundle_name="code-review-pipeline",
        required_skills=("ticket-analyst", "code-architect"),
        resolved_commit="0123456789abcdef0123456789abcdef01234567",
    )

    guidance = render_external_guidance(bundle, skill_names=("code-architect",))

    assert "External LivingColor Skills Guidance" in guidance
    assert "Source commit: 0123456789abcdef0123456789abcdef01234567" in guidance
    assert "# Code Architect" in guidance
    assert "# Ticket Analyst" not in guidance
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/lc_server/test_external_skills_registry.py -v
```

Expected: FAIL with missing `registry` and `guidance` modules.

- [ ] **Step 3: Implement registry validation**

Create `lc_server/integrations/skills/registry.py`:

```python
"""Validate extracted LivingColor skills registries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ExternalSkill:
    name: str
    version: str
    root_path: Path
    prompt: str


@dataclass(frozen=True)
class ExternalSkillsBundle:
    available: bool
    bundle_name: str
    resolved_commit: str
    skills: tuple[ExternalSkill, ...] = ()
    error: str = ""


def resolve_external_bundle(
    *,
    registry_path: Path,
    bundle_name: str,
    required_skills: tuple[str, ...],
    resolved_commit: str,
) -> ExternalSkillsBundle:
    bundle_path = registry_path / "bundles" / bundle_name / "bundle.yaml"
    if not bundle_path.is_file():
        return _unavailable(bundle_name, resolved_commit, f"bundle not found: {bundle_name}")

    try:
        bundle_payload = yaml.safe_load(bundle_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return _unavailable(bundle_name, resolved_commit, f"invalid bundle yaml: {exc}")

    listed_skills = tuple(str(item).strip() for item in (bundle_payload.get("skills") or []) if str(item).strip())
    missing_from_bundle = [skill for skill in required_skills if skill not in listed_skills]
    if missing_from_bundle:
        return _unavailable(bundle_name, resolved_commit, f"bundle missing required skills: {', '.join(missing_from_bundle)}")

    skills: list[ExternalSkill] = []
    for skill_name in required_skills:
        loaded = _load_skill(registry_path, skill_name)
        if isinstance(loaded, str):
            return _unavailable(bundle_name, resolved_commit, loaded)
        skills.append(loaded)

    return ExternalSkillsBundle(
        available=True,
        bundle_name=bundle_name,
        resolved_commit=resolved_commit,
        skills=tuple(skills),
    )


def _load_skill(registry_path: Path, skill_name: str) -> ExternalSkill | str:
    root = registry_path / skill_name
    manifest_path = root / "skill.yaml"
    prompt_path = root / "prompt.md"
    if not manifest_path.is_file():
        return f"skill manifest not found: {skill_name}"
    if not prompt_path.is_file():
        return f"skill prompt not found: {skill_name}"
    try:
        manifest: dict[str, Any] = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return f"invalid skill yaml for {skill_name}: {exc}"
    name = str(manifest.get("name") or "").strip()
    if name != skill_name:
        return f"skill name mismatch: expected {skill_name}, got {name or '(missing)'}"
    version = str(manifest.get("version") or "").strip()
    return ExternalSkill(
        name=skill_name,
        version=version,
        root_path=root,
        prompt=prompt_path.read_text(encoding="utf-8"),
    )


def _unavailable(bundle_name: str, resolved_commit: str, error: str) -> ExternalSkillsBundle:
    return ExternalSkillsBundle(
        available=False,
        bundle_name=bundle_name,
        resolved_commit=resolved_commit,
        error=error,
    )
```

- [ ] **Step 4: Implement guidance rendering**

Create `lc_server/integrations/skills/guidance.py`:

```python
"""Render external skill prompts as read-only guidance for LivingColor agents."""

from __future__ import annotations

from lc_server.integrations.skills.registry import ExternalSkillsBundle


def render_external_guidance(
    bundle: ExternalSkillsBundle,
    *,
    skill_names: tuple[str, ...],
) -> str:
    if not bundle.available:
        return ""

    selected = [skill for skill in bundle.skills if skill.name in skill_names]
    if not selected:
        return ""

    lines = [
        "## External LivingColor Skills Guidance",
        "",
        f"Source commit: {bundle.resolved_commit}",
        "Use this as read-only role guidance. It does not change your tool permissions.",
        "",
    ]
    for skill in selected:
        lines.extend(
            [
                f"### {skill.name} ({skill.version or 'unversioned'})",
                "",
                skill.prompt.strip(),
                "",
            ]
        )
    return "\n".join(lines).strip()
```

- [ ] **Step 5: Update package exports**

Modify `lc_server/integrations/skills/__init__.py`:

```python
"""External LivingColor skills integration boundary."""

from lc_server.integrations.skills.cache import ExternalSkillsCacheResult, materialize_external_skills
from lc_server.integrations.skills.guidance import render_external_guidance
from lc_server.integrations.skills.lock import ExternalSkillsLock, load_external_skills_lock
from lc_server.integrations.skills.registry import ExternalSkillsBundle, resolve_external_bundle

__all__ = [
    "ExternalSkillsBundle",
    "ExternalSkillsCacheResult",
    "ExternalSkillsLock",
    "load_external_skills_lock",
    "materialize_external_skills",
    "render_external_guidance",
    "resolve_external_bundle",
]
```

- [ ] **Step 6: Run registry tests**

Run:

```bash
pytest tests/lc_server/test_external_skills_registry.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add lc_server/integrations/skills/__init__.py lc_server/integrations/skills/registry.py lc_server/integrations/skills/guidance.py tests/lc_server/test_external_skills_registry.py
git commit -m "feat: validate external skills registry"
```

## Task 4: Delivery Context Contract Markdown

**Files:**
- Create: `delivery_runtime/context/skills_context.py`
- Modify: `delivery_runtime/context/models.py`
- Modify: `delivery_runtime/context/pack_builder.py`
- Modify: `delivery_runtime/context/planner_prompt.py`
- Test: `tests/delivery_runtime/test_skills_context.py`
- Test: `tests/delivery_runtime/test_context_engine.py`

- [ ] **Step 1: Write failing context tests**

Create `tests/delivery_runtime/test_skills_context.py`:

```python
from __future__ import annotations


def test_render_skills_context_contains_stack_tracker_vcs_and_delivery_context():
    from delivery_runtime.context.models import ContextPack
    from delivery_runtime.context.skills_context import render_skills_context_markdown

    pack = ContextPack(
        jira_key="BN-42",
        jira_ticket={
            "key": "BN-42",
            "summary": "Fix search result rendering",
            "description": "Acceptance criteria: results render without duplicate cards.",
            "projectKey": "BN",
            "issueType": "Bug",
        },
        acceptance_criteria=["results render without duplicate cards."],
        identified_repo="github.com/acme/search-ui",
        repo_structure=["package.json", "src/search/results.tsx", "tests/search/results.test.tsx"],
        candidate_files=["src/search/results.tsx"],
        project_conventions=["Use React Testing Library for component tests"],
        git_history=[{"file": "src/search/results.tsx", "sha": "abcdef123456", "message": "fix search layout"}],
        repo_architecture={
            "summary": "github.com/acme/search-ui uses Node.js, React, TypeScript.",
            "stack": ["Node.js", "React", "TypeScript", "Vitest"],
            "topLevelDirectories": [{"path": "src/", "role": "Application source code"}],
            "entryPoints": ["src/main.tsx"],
            "testDirectories": ["tests/"],
            "architectureNotes": ["Application routes live under src/search."],
        },
        vcs_provider="github",
    )

    rendered = render_skills_context_markdown(pack)

    assert "## Project Stack" in rendered
    assert "Node.js, React, TypeScript, Vitest" in rendered
    assert "## Ticket Tracker" in rendered
    assert "tracker: jira" in rendered
    assert "## VCS" in rendered
    assert "vcs: github" in rendered
    assert "## Delivery Context" in rendered
    assert "BN-42" in rendered
    assert "`src/search/results.tsx`" in rendered


def test_pack_builder_populates_skills_context_and_vcs(_isolate_hermes_home):
    from delivery_runtime.context.pack_builder import ContextPackBuilder
    from delivery_runtime.validation.mapping_setup import install_phase25_project_mapping

    install_phase25_project_mapping()

    pack = ContextPackBuilder().build(
        {
            "workOrder": {"jiraKey": "MAM-324", "title": "Render shows media offline"},
            "jiraSnapshot": {
                "key": "MAM-324",
                "summary": "Render shows media offline",
                "description": "Acceptance criteria: no media offline on valid renders.",
                "projectKey": "MAM",
                "issueType": "Bug",
            },
            "recommendedRepos": ["gitlab.com/afp/mam-iris-panel"],
        }
    )

    assert pack.vcs_provider == "gitlab"
    assert "## Project Stack" in pack.skills_context_markdown
    assert "tracker: jira" in pack.skills_context_markdown
    assert "vcs: gitlab" in pack.skills_context_markdown
```

- [ ] **Step 2: Run context tests and verify they fail**

Run:

```bash
pytest tests/delivery_runtime/test_skills_context.py -v
```

Expected: FAIL because `delivery_runtime.context.skills_context` does not exist and `ContextPack` has no `vcs_provider`.

- [ ] **Step 3: Add fields to `ContextPack`**

Modify `delivery_runtime/context/models.py`:

```python
@dataclass
class ContextPack:
    """Structured context assembled before any implementation planning."""

    jira_key: str
    jira_ticket: dict[str, Any]
    jira_comments: list[dict[str, Any]] = field(default_factory=list)
    jira_attachment_extracts: list[dict[str, Any]] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    epic: dict[str, Any] | None = None
    linked_tickets: list[dict[str, Any]] = field(default_factory=list)
    identified_repo: str | None = None
    repo_checkout_path: str | None = None
    repo_structure: list[str] = field(default_factory=list)
    candidate_files: list[str] = field(default_factory=list)
    project_conventions: list[str] = field(default_factory=list)
    git_history: list[dict[str, Any]] = field(default_factory=list)
    repo_architecture: dict[str, Any] = field(default_factory=dict)
    vcs_provider: str = "gitlab"
    skills_context_markdown: str = ""
    rejection_feedback: str = ""
    resolved_repo_override: str | None = None
    build_notes: list[str] = field(default_factory=list)
```

Preserve the existing `repo_resolved` property and `to_dict()` method below this block.

- [ ] **Step 4: Implement context markdown rendering**

Create `delivery_runtime/context/skills_context.py`:

```python
"""Render the external skills context contract for generic role skills."""

from __future__ import annotations

from delivery_runtime.context.models import ContextPack


def render_skills_context_markdown(pack: ContextPack) -> str:
    ticket = pack.jira_ticket
    architecture = pack.repo_architecture or {}
    stack = architecture.get("stack") or []
    stack_text = ", ".join(str(item) for item in stack) or "Unknown stack"
    summary = str(architecture.get("summary") or "").strip()

    lines = [
        "## Project Stack",
        "",
        f"Stack: {stack_text}",
    ]
    if summary:
        lines.append(f"Summary: {summary}")

    _append_list(lines, "Architecture notes", architecture.get("architectureNotes") or [])
    _append_list(lines, "Repository structure", pack.repo_structure[:20], code=True)
    _append_list(lines, "Project conventions", pack.project_conventions[:8])

    lines.extend(
        [
            "",
            "## Ticket Tracker",
            "",
            "tracker: jira",
            "",
            "## VCS",
            "",
            f"vcs: {pack.vcs_provider or 'gitlab'}",
            "",
            "## Delivery Context",
            "",
            f"Ticket: {pack.jira_key or ticket.get('key') or 'unknown'}",
            f"Summary: {ticket.get('summary') or '(missing)'}",
            f"Issue type: {ticket.get('issueType') or '(missing)'}",
            f"Target repository: {pack.identified_repo or '(unresolved)'}",
        ]
    )
    _append_list(lines, "Acceptance criteria", pack.acceptance_criteria)
    _append_list(lines, "Candidate files", pack.candidate_files[:12], code=True)
    _append_git_history(lines, pack.git_history[:5])
    return "\n".join(lines).strip()


def _append_list(lines: list[str], title: str, values, *, code: bool = False) -> None:
    items = [str(item).strip() for item in values if str(item).strip()] if isinstance(values, list) else []
    if not items:
        return
    lines.extend(["", f"### {title}"])
    for item in items:
        lines.append(f"- `{item}`" if code else f"- {item}")


def _append_git_history(lines: list[str], values: list[dict]) -> None:
    if not values:
        return
    lines.extend(["", "### Relevant git history"])
    for item in values:
        file_path = str(item.get("file") or "").strip()
        sha = str(item.get("sha") or "")[:8]
        message = str(item.get("message") or "").strip()
        if file_path:
            lines.append(f"- `{file_path}` — {sha} {message}".strip())
```

- [ ] **Step 5: Populate context in the pack builder**

Modify imports in `delivery_runtime/context/pack_builder.py`:

```python
from delivery_runtime.context.skills_context import render_skills_context_markdown
from delivery_runtime.readiness.project_settings import load_project_vcs_provider
```

Before creating `ContextPack`, compute:

```python
        vcs_provider = load_project_vcs_provider(project_key)
```

Set the new field while constructing `ContextPack`:

```python
            vcs_provider=vcs_provider,
```

After the `ContextPack(...)` call and before returning:

```python
        pack.skills_context_markdown = render_skills_context_markdown(pack)
        return pack
```

Remove the existing immediate `return pack` line so the rendered markdown is stored first.

- [ ] **Step 6: Add skills context to planner prompt**

Modify `delivery_runtime/context/planner_prompt.py` after the repository architecture section:

```python
    if pack.skills_context_markdown:
        sections.extend(
            [
                "",
                "## External skills context",
                "Use this context when applying generic LivingColor role skills.",
                "",
                pack.skills_context_markdown,
            ]
        )
```

- [ ] **Step 7: Run context tests**

Run:

```bash
pytest tests/delivery_runtime/test_skills_context.py tests/delivery_runtime/test_context_engine.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

```bash
git add delivery_runtime/context/models.py delivery_runtime/context/pack_builder.py delivery_runtime/context/planner_prompt.py delivery_runtime/context/skills_context.py tests/delivery_runtime/test_skills_context.py tests/delivery_runtime/test_context_engine.py
git commit -m "feat: render external skills context"
```

## Task 5: Resolve External Bundle For Agent Prompt Enrichment

**Files:**
- Create: `lc_server/integrations/skills/resolver.py`
- Modify: `lc_server/integrations/skills/__init__.py`
- Modify: `lc_server/agent_bridge/hermes_analyst.py`
- Modify: `lc_server/agent_bridge/hermes_developer.py`
- Test: `tests/lc_server/test_external_skills_prompt_injection.py`

- [ ] **Step 1: Write failing prompt injection tests**

Create `tests/lc_server/test_external_skills_prompt_injection.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CapturingAgent:
    final_response: str
    prompts: list[str]

    def run_conversation(self, prompt: str, *, task_id: str):
        self.prompts.append(prompt)
        return {"final_response": self.final_response}


def test_analyst_prompt_appends_ticket_analyst_guidance(monkeypatch):
    from lc_server.agent_bridge.hermes_analyst import HermesAnalystAgent

    prompts: list[str] = []
    final = """```json
{"readinessScore": 90, "readinessStatus": "ready", "analysisSummary": "Ready", "blockers": [], "recommendedRepos": ["group/app"], "confidence": 0.8, "estimatedDays": 1}
```"""

    monkeypatch.setattr(
        "lc_server.agent_bridge.hermes_analyst.external_guidance_for_skills",
        lambda names: "## External LivingColor Skills Guidance\n# Ticket Analyst",
    )

    agent = HermesAnalystAgent(
        agent_factory=lambda **kwargs: CapturingAgent(final_response=final, prompts=prompts)
    )

    agent.analyze(
        {
            "key": "BN-1",
            "summary": "Improve ticket",
            "description": "Acceptance criteria: estimate work.",
            "projectKey": "BN",
        },
        "BN",
    )

    assert "External LivingColor Skills Guidance" in prompts[0]
    assert "# Ticket Analyst" in prompts[0]


def test_code_quality_review_prompt_appends_pipeline_guidance(monkeypatch, tmp_path):
    from lc_server.agent_bridge.hermes_developer import _append_external_code_review_guidance

    monkeypatch.setattr(
        "lc_server.agent_bridge.hermes_developer.external_guidance_for_skills",
        lambda names: "## External LivingColor Skills Guidance\n# Code Architect\n# QA Reviewer",
    )

    prompt = _append_external_code_review_guidance("base prompt", developer_phase="code_quality_review")

    assert "base prompt" in prompt
    assert "# Code Architect" in prompt
    assert "# QA Reviewer" in prompt


def test_implementation_prompt_does_not_append_external_review_guidance(monkeypatch):
    from lc_server.agent_bridge.hermes_developer import _append_external_code_review_guidance

    monkeypatch.setattr(
        "lc_server.agent_bridge.hermes_developer.external_guidance_for_skills",
        lambda names: "SHOULD NOT APPEAR",
    )

    prompt = _append_external_code_review_guidance("base prompt", developer_phase="implement")

    assert prompt == "base prompt"
```

- [ ] **Step 2: Run prompt tests and verify they fail**

Run:

```bash
pytest tests/lc_server/test_external_skills_prompt_injection.py -v
```

Expected: FAIL because `external_guidance_for_skills` and `_append_external_code_review_guidance` do not exist.

- [ ] **Step 3: Implement resolver facade**

Create `lc_server/integrations/skills/resolver.py`:

```python
"""High-level external skills resolver used by agent bridges."""

from __future__ import annotations

import logging

from lc_server.integrations.skills.cache import materialize_external_skills
from lc_server.integrations.skills.guidance import render_external_guidance
from lc_server.integrations.skills.lock import load_external_skills_lock
from lc_server.integrations.skills.registry import resolve_external_bundle

logger = logging.getLogger(__name__)


def external_guidance_for_skills(skill_names: tuple[str, ...]) -> str:
    try:
        lock = load_external_skills_lock()
        cache = materialize_external_skills(lock)
        if not cache.available:
            logger.info("External skills unavailable: %s", cache.error)
            return ""
        bundle = resolve_external_bundle(
            registry_path=cache.registry_path,
            bundle_name=lock.bundle,
            required_skills=lock.skills,
            resolved_commit=lock.resolved_commit,
        )
        if not bundle.available:
            logger.info("External skills bundle unavailable: %s", bundle.error)
            return ""
        return render_external_guidance(bundle, skill_names=skill_names)
    except FileNotFoundError:
        return ""
    except Exception as exc:
        logger.info("External skills guidance disabled: %s", exc)
        return ""
```

- [ ] **Step 4: Export resolver facade**

Modify `lc_server/integrations/skills/__init__.py`:

```python
from lc_server.integrations.skills.resolver import external_guidance_for_skills
```

Add `"external_guidance_for_skills"` to `__all__`.

- [ ] **Step 5: Append guidance to analyst prompts**

Modify imports in `lc_server/agent_bridge/hermes_analyst.py`:

```python
from lc_server.integrations.skills.resolver import external_guidance_for_skills
```

Modify `HermesAnalystAgent.analyze()` after `prompt = build_analyst_user_prompt(snapshot)`:

```python
        guidance = external_guidance_for_skills(("ticket-analyst",))
        if guidance:
            prompt = f"{prompt}\n\n{guidance}"
```

- [ ] **Step 6: Add code-review-only developer prompt guidance**

Modify imports in `lc_server/agent_bridge/hermes_developer.py`:

```python
from lc_server.integrations.skills.resolver import external_guidance_for_skills
```

After `prompt = build_developer_user_prompt(...)` in `HermesDeveloperAgent.execute()`, add:

```python
        prompt = _append_external_code_review_guidance(prompt, developer_phase=developer_phase)
```

Add this helper near the other module-level helpers:

```python
def _append_external_code_review_guidance(prompt: str, *, developer_phase: str) -> str:
    if developer_phase != DEVELOPER_PHASE_CODE_QUALITY_REVIEW:
        return prompt
    guidance = external_guidance_for_skills(
        ("code-architect", "qa-reviewer", "security-auditor")
    )
    if not guidance:
        return prompt
    return f"{prompt}\n\n{guidance}"
```

- [ ] **Step 7: Run prompt injection tests**

Run:

```bash
pytest tests/lc_server/test_external_skills_prompt_injection.py tests/lc_server/test_hermes_developer_manifest.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit Task 5**

```bash
git add lc_server/integrations/skills/__init__.py lc_server/integrations/skills/resolver.py lc_server/agent_bridge/hermes_analyst.py lc_server/agent_bridge/hermes_developer.py tests/lc_server/test_external_skills_prompt_injection.py
git commit -m "feat: inject external skills guidance"
```

## Task 6: Documentation And Plugin Verification

**Files:**
- Modify: `README.md`
- Test: all plugin tests touched by this plan

- [ ] **Step 1: Update README**

Add this section after the current prerequisites section in `README.md`:

```markdown
### External LivingColor Skills

LivingColor can enrich delivery analysis and review with generic role skills from
`Tamsi/livingcolor-skills`. The consumed version is pinned in
`livingcolor.skills.lock.json`; the plugin never follows the moving `main`
branch at runtime.

On startup or first use, the plugin materializes the pinned skills registry under
`~/.hermes/livingcolor/skills-cache/`. If the lock is missing, invalid, or cannot
be fetched, delivery continues with the bundled delivery skills and external
skills are disabled for that run.

Rollback is a lock-file revert to a previous `resolvedCommit`.
```

- [ ] **Step 2: Run focused plugin verification**

Run:

```bash
pytest tests/lc_server/test_external_skills_lock.py tests/lc_server/test_external_skills_cache.py tests/lc_server/test_external_skills_registry.py tests/lc_server/test_external_skills_prompt_injection.py tests/delivery_runtime/test_skills_context.py tests/delivery_runtime/test_context_engine.py tests/lc_server/test_hermes_developer_manifest.py -v
```

Expected: PASS.

- [ ] **Step 3: Run fast development smoke if available**

Run:

```bash
LIVINGCOLOR_FAST_DEV=true scripts/run_fast_dev_smoke.sh
```

Expected: PASS. If this script is unavailable in the execution environment, record the missing script as a verification limitation in the final handoff.

- [ ] **Step 4: Commit Task 6**

```bash
git add README.md
git commit -m "docs: document external skills integration"
```

## Task 7: Evolution Plugin Lock Bump Contract

**Repository:** `Tamsi/livingcolor-evolution`

**Files:**
- Modify: `packages/core/src/domain/types.ts`
- Modify: `packages/core/src/ports/index.ts`
- Create: `packages/github/src/plugin-lock-bump.ts`
- Modify: `packages/github/src/index.ts`
- Modify: `packages/scheduler/src/index.ts`
- Modify: `packages/cli/src/index.ts`
- Test: `packages/github/src/__tests__/plugin-lock-bump.test.ts`
- Test: `packages/scheduler/src/__tests__/plugin-bump.test.ts`

- [ ] **Step 1: Write GitHub plugin bump tests in `livingcolor-evolution`**

Create `packages/github/src/__tests__/plugin-lock-bump.test.ts` in `livingcolor-evolution`:

```typescript
import { describe, expect, it, vi } from 'vitest';
import { GitHubPluginLockBumpService } from '../plugin-lock-bump.js';

describe('GitHubPluginLockBumpService', () => {
  it('creates a plugin lock bump pull request that only changes the lock file', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url.endsWith('/git/ref/heads/main')) {
        return Response.json({ object: { sha: 'base-sha' } });
      }
      if (url.endsWith('/git/refs')) {
        return Response.json({ ref: 'refs/heads/curator/skills-lock-bump' });
      }
      if (url.endsWith('/contents/livingcolor.skills.lock.json')) {
        return Response.json({ content: Buffer.from(JSON.stringify({
          repo: 'Tamsi/livingcolor-skills',
          ref: 'v0.1.0',
          resolvedCommit: '0000000000000000000000000000000000000000',
          bundle: 'code-review-pipeline',
          skills: ['ticket-analyst', 'code-architect', 'qa-reviewer', 'security-auditor'],
          updatedBy: 'livingcolor-evolution',
        })).toString('base64'), sha: 'file-sha' });
      }
      if (url.includes('/contents/livingcolor.skills.lock.json')) {
        return Response.json({ content: { path: 'livingcolor.skills.lock.json' } });
      }
      if (url.endsWith('/pulls')) {
        return Response.json({ html_url: 'https://github.com/Tamsi/livingcolor-plugin/pull/12', number: 12 });
      }
      return Response.json({});
    });

    const service = new GitHubPluginLockBumpService(
      {
        token: 'gh-test',
        owner: 'Tamsi',
        repo: 'livingcolor-plugin',
        baseBranch: 'main',
        lockPath: 'livingcolor.skills.lock.json',
      },
      fetchMock,
    );

    const result = await service.create({
      skillsRepo: 'Tamsi/livingcolor-skills',
      skillsRef: 'v0.2.0',
      resolvedCommit: '0123456789abcdef0123456789abcdef01234567',
      bundle: 'code-review-pipeline',
      skills: ['ticket-analyst', 'code-architect', 'qa-reviewer', 'security-auditor'],
      dryRun: false,
    });

    assert(result);
    expect(result.url).toBe('https://github.com/Tamsi/livingcolor-plugin/pull/12');
    const updateCall = calls.find((call) => call.url.includes('/contents/livingcolor.skills.lock.json') && call.init?.method === 'PUT');
    expect(updateCall).toBeTruthy();
    const body = JSON.parse(String(updateCall?.init?.body));
    expect(body.message).toBe('chore: bump livingcolor skills lock');
    expect(body.branch).toMatch(/^curator\/skills-lock-/);
  });
});

function assert(value: unknown): asserts value {
  expect(value).toBeTruthy();
}
```

- [ ] **Step 2: Write scheduler plugin bump test in `livingcolor-evolution`**

Create `packages/scheduler/src/__tests__/plugin-bump.test.ts`:

```typescript
import { describe, expect, it, vi } from 'vitest';

vi.mock('@curator/github', () => ({
  GitHubPluginLockBumpService: class {
    constructor(private readonly config: { owner: string; repo: string; lockPath: string }) {}

    create(request: { resolvedCommit: string }) {
      return Promise.resolve({
        url: `https://github.com/${this.config.owner}/${this.config.repo}/pull/99`,
        branch: `curator/skills-lock-${request.resolvedCommit.slice(0, 8)}`,
        number: 99,
      });
    }
  },
}));

describe('runPluginLockBump', () => {
  it('delegates to the GitHub plugin lock bump service', async () => {
    const { runPluginLockBump } = await import('../index.js');

    const result = await runPluginLockBump({
      token: 'gh-test',
      pluginOwner: 'Tamsi',
      pluginRepo: 'livingcolor-plugin',
      baseBranch: 'main',
      lockPath: 'livingcolor.skills.lock.json',
      request: {
        skillsRepo: 'Tamsi/livingcolor-skills',
        skillsRef: 'v0.2.0',
        resolvedCommit: '0123456789abcdef0123456789abcdef01234567',
        bundle: 'code-review-pipeline',
        skills: ['ticket-analyst', 'code-architect', 'qa-reviewer', 'security-auditor'],
        dryRun: false,
      },
    });

    expect(result?.url).toBe('https://github.com/Tamsi/livingcolor-plugin/pull/99');
    expect(result?.branch).toBe('curator/skills-lock-01234567');
  });
});
```

- [ ] **Step 3: Run evolution tests and verify they fail**

From `livingcolor-evolution`, run:

```bash
pnpm --filter @curator/github test -- plugin-lock-bump
pnpm --filter @curator/scheduler test -- plugin-bump
```

Expected: FAIL because `packages/github/src/plugin-lock-bump.ts` and `runPluginLockBump` do not exist.

- [ ] **Step 4: Add core types**

Modify `packages/core/src/domain/types.ts` in `livingcolor-evolution`:

```typescript
export interface PluginLockBumpRequest {
  skillsRepo: 'Tamsi/livingcolor-skills';
  skillsRef: string;
  resolvedCommit: string;
  bundle: 'code-review-pipeline';
  skills: string[];
  dryRun: boolean;
}

export interface PluginLockBumpConfig {
  token?: string;
  owner: string;
  repo: string;
  baseBranch: string;
  lockPath: string;
}
```

Modify `packages/core/src/ports/index.ts`:

```typescript
import type {
  PluginLockBumpRequest,
  PullRequestResult,
} from '../domain/types.js';

export interface PluginLockBumpPort {
  create(request: PluginLockBumpRequest): Promise<PullRequestResult | null>;
}
```

Keep existing imports in `ports/index.ts`; merge the new imported type names into the existing type import block instead of creating duplicate imports.

- [ ] **Step 5: Implement plugin lock bump GitHub service**

Create `packages/github/src/plugin-lock-bump.ts` in `livingcolor-evolution`:

```typescript
import type { PluginLockBumpConfig, PluginLockBumpRequest, PullRequestResult } from '@curator/core';
import type { PluginLockBumpPort } from '@curator/core';

type FetchLike = (url: string, init?: RequestInit) => Promise<Response>;

export class GitHubPluginLockBumpService implements PluginLockBumpPort {
  constructor(
    private readonly config: PluginLockBumpConfig,
    private readonly fetchImpl: FetchLike = fetch,
  ) {}

  async create(request: PluginLockBumpRequest): Promise<PullRequestResult | null> {
    const branch = `curator/skills-lock-${request.resolvedCommit.slice(0, 8)}`;
    const title = `Bump LivingColor skills to ${request.skillsRef}`;
    const body = [
      '## Summary',
      '',
      `- Bumps \`${this.config.lockPath}\` to \`${request.skillsRepo}@${request.resolvedCommit}\``,
      '- Generated after LivingColor Skills evaluation passed',
      '',
      '## Test plan',
      '',
      '- Plugin CI validates lock parsing, cache materialization, and prompt-context fixtures',
    ].join('\n');

    if (request.dryRun || !this.config.token) {
      return null;
    }

    const apiBase = `https://api.github.com/repos/${this.config.owner}/${this.config.repo}`;
    const ref = await this.githubRequest<{ object: { sha: string } }>(
      `${apiBase}/git/ref/heads/${this.config.baseBranch}`,
    );
    await this.githubRequest(`${apiBase}/git/refs`, {
      method: 'POST',
      body: JSON.stringify({ ref: `refs/heads/${branch}`, sha: ref.object.sha }),
    });

    const existing = await this.githubRequest<{ content: string; sha: string }>(
      `${apiBase}/contents/${this.config.lockPath}?ref=${this.config.baseBranch}`,
    );
    const lock = JSON.stringify(
      {
        repo: request.skillsRepo,
        ref: request.skillsRef,
        resolvedCommit: request.resolvedCommit,
        bundle: request.bundle,
        skills: request.skills,
        updatedBy: 'livingcolor-evolution',
      },
      null,
      2,
    ) + '\n';

    await this.githubRequest(`${apiBase}/contents/${this.config.lockPath}`, {
      method: 'PUT',
      body: JSON.stringify({
        message: 'chore: bump livingcolor skills lock',
        content: Buffer.from(lock, 'utf-8').toString('base64'),
        sha: existing.sha,
        branch,
      }),
    });

    const pr = await this.githubRequest<{ html_url: string; number: number }>(`${apiBase}/pulls`, {
      method: 'POST',
      body: JSON.stringify({ title, head: branch, base: this.config.baseBranch, body }),
    });

    return { url: pr.html_url, branch, number: pr.number };
  }

  private async githubRequest<T>(url: string, init?: RequestInit): Promise<T> {
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
      throw new Error(`GitHub API ${String(response.status)}: ${await response.text()}`);
    }
    return (await response.json()) as T;
  }
}
```

- [ ] **Step 6: Export the service**

Modify `packages/github/src/index.ts`:

```typescript
export { GitHubPluginLockBumpService } from './plugin-lock-bump.js';
```

Keep the existing `GitHubPullRequestService` export behavior intact.

- [ ] **Step 7: Add scheduler and CLI entry points**

Modify `packages/scheduler/src/index.ts`:

```typescript
import { GitHubPluginLockBumpService } from '@curator/github';
import type { PluginLockBumpRequest, PullRequestResult } from '@curator/core';

export async function runPluginLockBump(options: {
  token?: string;
  pluginOwner: string;
  pluginRepo: string;
  baseBranch: string;
  lockPath: string;
  request: PluginLockBumpRequest;
}): Promise<PullRequestResult | null> {
  const service = new GitHubPluginLockBumpService({
    token: options.token,
    owner: options.pluginOwner,
    repo: options.pluginRepo,
    baseBranch: options.baseBranch,
    lockPath: options.lockPath,
  });
  return service.create(options.request);
}
```

Modify `packages/cli/src/index.ts` imports:

```typescript
import { CuratorPipeline, resolveDefaultPaths, runPluginLockBump } from '@curator/scheduler';
```

Add a command before `program.parse()`:

```typescript
program
  .command('plugin-bump')
  .description('Open a livingcolor-plugin PR that bumps livingcolor.skills.lock.json')
  .requiredOption('--skills-ref <ref>', 'Validated livingcolor-skills ref')
  .requiredOption('--resolved-commit <sha>', 'Resolved livingcolor-skills commit SHA')
  .option('--dry-run', 'Do not call GitHub API')
  .action(async (options: { skillsRef: string; resolvedCommit: string; dryRun?: boolean }) => {
    const target = process.env['CURATOR_PLUGIN_TARGET_REPO'] ?? 'Tamsi/livingcolor-plugin';
    const [owner = 'Tamsi', repo = 'livingcolor-plugin'] = target.split('/');
    const result = await runPluginLockBump({
      token: process.env['GITHUB_TOKEN'],
      pluginOwner: owner,
      pluginRepo: repo,
      baseBranch: process.env['CURATOR_PLUGIN_BASE_BRANCH'] ?? 'main',
      lockPath: process.env['CURATOR_PLUGIN_LOCK_PATH'] ?? 'livingcolor.skills.lock.json',
      request: {
        skillsRepo: 'Tamsi/livingcolor-skills',
        skillsRef: options.skillsRef,
        resolvedCommit: options.resolvedCommit,
        bundle: 'code-review-pipeline',
        skills: ['ticket-analyst', 'code-architect', 'qa-reviewer', 'security-auditor'],
        dryRun: options.dryRun ?? !process.env['GITHUB_TOKEN'],
      },
    });
    console.log(result ? `Plugin PR: ${result.url}` : 'Plugin PR dry-run complete.');
  });
```

- [ ] **Step 8: Add the workflow input job**

Modify `.github/workflows/curator-weekly.yml`:

```yaml
name: LivingColor Evolution Weekly

on:
  schedule:
    - cron: '0 4 * * 0'
  workflow_dispatch:
    inputs:
      plugin_skills_ref:
        description: 'Validated livingcolor-skills ref to pin in livingcolor-plugin'
        required: false
        type: string
      plugin_skills_commit:
        description: 'Resolved livingcolor-skills commit SHA to pin in livingcolor-plugin'
        required: false
        type: string

jobs:
  curator:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/checkout@v4
        with:
          repository: Tamsi/livingcolor-skills
          path: livingcolor-skills
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: pnpm

      - name: Install livingcolor-skills dependencies
        working-directory: livingcolor-skills
        run: pnpm install --frozen-lockfile

      - name: Build livingcolor-skills
        working-directory: livingcolor-skills
        run: pnpm build

      - name: Install curator
        run: pnpm install --frozen-lockfile

      - name: Build curator
        run: pnpm build

      - name: Run curator pipeline
        env:
          CURATOR_SKILLS_PATH: ${{ github.workspace }}/livingcolor-skills/registry
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          CURATOR_TARGET_REPO: Tamsi/livingcolor-skills
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          HERMES_LLM_PROVIDER: anthropic
          CURATOR_MOCK_LLM: ${{ secrets.ANTHROPIC_API_KEY == '' && 'true' || '' }}
        run: pnpm curator pr

  plugin-lock-bump:
    if: ${{ github.event_name == 'workflow_dispatch' && inputs.plugin_skills_ref != '' && inputs.plugin_skills_commit != '' }}
    needs: curator
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: pnpm

      - name: Install curator
        run: pnpm install --frozen-lockfile

      - name: Build curator
        run: pnpm build

      - name: Open plugin lock bump PR
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          CURATOR_PLUGIN_TARGET_REPO: Tamsi/livingcolor-plugin
        run: pnpm curator plugin-bump --skills-ref "${{ inputs.plugin_skills_ref }}" --resolved-commit "${{ inputs.plugin_skills_commit }}"
```

- [ ] **Step 9: Run evolution verification**

From `livingcolor-evolution`, run:

```bash
pnpm --filter @curator/github test -- plugin-lock-bump
pnpm --filter @curator/scheduler test -- plugin-bump
pnpm build
pnpm test
```

Expected: PASS.

- [ ] **Step 10: Commit Task 7 in `livingcolor-evolution`**

```bash
git add packages/core/src/domain/types.ts packages/core/src/ports/index.ts packages/github/src/plugin-lock-bump.ts packages/github/src/index.ts packages/scheduler/src/index.ts packages/cli/src/index.ts packages/github/src/__tests__/plugin-lock-bump.test.ts packages/scheduler/src/__tests__/plugin-bump.test.ts .github/workflows/curator-weekly.yml
git commit -m "feat: add plugin skills lock bump"
```

## Task 8: End-To-End Handoff Checks

**Files:**
- Modify: `docs/superpowers/specs/2026-06-13-livingcolor-repos-interconnection-design.md` only if implementation reveals a design correction.
- Modify: `docs/superpowers/plans/2026-06-13-livingcolor-repos-interconnection.md` only if a task changes during execution.

- [ ] **Step 1: Verify plugin working tree**

From `livingcolor-plugin`, run:

```bash
git status --short
```

Expected: only intended implementation files are modified or untracked.

- [ ] **Step 2: Run plugin focused test set**

From `livingcolor-plugin`, run:

```bash
pytest tests/lc_server/test_external_skills_lock.py tests/lc_server/test_external_skills_cache.py tests/lc_server/test_external_skills_registry.py tests/lc_server/test_external_skills_prompt_injection.py tests/delivery_runtime/test_skills_context.py tests/delivery_runtime/test_context_engine.py tests/lc_server/test_hermes_developer_manifest.py -v
```

Expected: PASS.

- [ ] **Step 3: Run plugin smoke suite**

From `livingcolor-plugin`, run:

```bash
LIVINGCOLOR_FAST_DEV=true scripts/run_fast_dev_smoke.sh
```

Expected: PASS.

- [ ] **Step 4: Verify evolution working tree**

From `livingcolor-evolution`, run:

```bash
git status --short
```

Expected: only intended evolution implementation files are modified or untracked.

- [ ] **Step 5: Run evolution focused test set**

From `livingcolor-evolution`, run:

```bash
pnpm --filter @curator/github test -- plugin-lock-bump
pnpm build
pnpm test
```

Expected: PASS.

- [ ] **Step 6: Document verification results**

In the final implementation handoff, include:

- Plugin commit hashes for Tasks 1-6.
- Evolution commit hash for Task 7.
- Exact test commands run.
- Any unavailable commands or environment limitations.
- The external skills commit pinned in `livingcolor.skills.lock.json`.
