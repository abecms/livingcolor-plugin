"""Scope Contract generation for Phase 3E execution containment."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

DEFAULT_FORBIDDEN_PATHS: tuple[str, ...] = (
    "dist",
    "build",
    "public/assets",
    "node_modules",
    ".next",
    "coverage",
    "vendor",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
)

DEFAULT_MAX_FILES_TOUCHED = 5
DEFAULT_MAX_LINES_CHANGED = 200

# Paths that test/build tooling may touch incidentally — not intentional developer edits.
EPHEMERAL_SIDE_EFFECT_PREFIXES: tuple[str, ...] = (
    "node_modules/",
    "dist/",
    "build/",
    ".next/",
    "coverage/",
    ".cache/",
    "vendor/",
)

TEST_PATH_MARKERS = ("/tests/", "/test/", ".test.", ".spec.", "_test.", "/__tests__/")


@dataclass(frozen=True)
class ScopeContract:
    work_order_id: str
    allowed_files: list[str] = field(default_factory=list)
    allowed_directories: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    max_files_touched: int = DEFAULT_MAX_FILES_TOUCHED
    max_lines_changed: int = DEFAULT_MAX_LINES_CHANGED
    workspace_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "workOrderId": self.work_order_id,
            "allowedFiles": self.allowed_files,
            "allowedDirectories": self.allowed_directories,
            "forbiddenPaths": self.forbidden_paths,
            "maxFilesTouched": self.max_files_touched,
            "maxLinesChanged": self.max_lines_changed,
            "workspaceOnly": self.workspace_only,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ScopeContract:
        return cls(
            work_order_id=str(payload.get("workOrderId") or ""),
            allowed_files=[str(item) for item in payload.get("allowedFiles") or []],
            allowed_directories=[str(item) for item in payload.get("allowedDirectories") or []],
            forbidden_paths=[str(item) for item in payload.get("forbiddenPaths") or []],
            max_files_touched=int(payload.get("maxFilesTouched") or DEFAULT_MAX_FILES_TOUCHED),
            max_lines_changed=int(payload.get("maxLinesChanged") or DEFAULT_MAX_LINES_CHANGED),
            workspace_only=bool(payload.get("workspaceOnly")),
        )


def build_scope_contract(
    work_order_id: str,
    approved_plan: dict[str, Any],
    *,
    max_files_touched: int = DEFAULT_MAX_FILES_TOUCHED,
    max_lines_changed: int = DEFAULT_MAX_LINES_CHANGED,
) -> ScopeContract:
    """Derive a Scope Contract from an approved Gate 1 plan."""
    target_files = _normalize_paths(approved_plan.get("likelyImpactedFiles") or [])
    candidate_tests = _candidate_test_files(approved_plan, target_files)
    allowed_files = _dedupe_preserve_order(target_files + candidate_tests)
    allowed_directories = _derive_allowed_directories(allowed_files)

    return ScopeContract(
        work_order_id=work_order_id,
        allowed_files=allowed_files,
        allowed_directories=allowed_directories,
        forbidden_paths=list(DEFAULT_FORBIDDEN_PATHS),
        max_files_touched=max_files_touched,
        max_lines_changed=max_lines_changed,
    )


def build_runtime_scope_contract(
    work_order_id: str,
    stored: dict[str, Any] | ScopeContract | None,
    *,
    workspace_only: bool,
) -> ScopeContract | None:
    """Scope guard used during Hermes development.

    Managed LivingColor checkouts run in workspace-only mode: the agent may touch
    any path inside the repository checkout. Gate-time scope contracts remain
    stored for review metrics but are not hard-enforced at tool-call time.
    """
    if not stored and not workspace_only:
        return None
    if isinstance(stored, ScopeContract):
        base = stored
    elif stored:
        base = ScopeContract.from_dict(stored)
    else:
        base = ScopeContract(work_order_id=work_order_id)
    if not workspace_only:
        return base
    return ScopeContract(
        work_order_id=base.work_order_id or work_order_id,
        allowed_files=[],
        allowed_directories=[],
        forbidden_paths=[],
        max_files_touched=base.max_files_touched,
        max_lines_changed=base.max_lines_changed,
        workspace_only=True,
    )


def predicted_files_from_plan(approved_plan: dict[str, Any]) -> list[str]:
    return _normalize_paths(approved_plan.get("likelyImpactedFiles") or [])


def is_ephemeral_side_effect_path(path: str) -> bool:
    """True for generated/vendor paths that npm test or build may touch accidentally."""
    normalized = _normalize_path(path)
    for prefix in EPHEMERAL_SIDE_EFFECT_PREFIXES:
        bare = prefix.rstrip("/")
        if normalized == bare or normalized.startswith(prefix):
            return True
    return False


def _candidate_test_files(approved_plan: dict[str, Any], target_files: list[str]) -> list[str]:
    explicit = _normalize_paths(approved_plan.get("candidateTests") or [])
    if explicit:
        return explicit

    plan_text = str(approved_plan.get("implementationPlan") or "")
    discovered: list[str] = []
    for token in plan_text.replace("`", " ").split():
        normalized = _normalize_path(token)
        if normalized and _looks_like_test_path(normalized):
            discovered.append(normalized)

    for path in target_files:
        sibling = _guess_test_path(path)
        if sibling:
            discovered.append(sibling)

    return _dedupe_preserve_order(discovered)


def _guess_test_path(source_path: str) -> str | None:
    path = PurePosixPath(source_path)
    if path.suffix in {".tsx", ".ts", ".jsx", ".js"}:
        if path.parts[0] == "admin" and path.parts[1:2] == ("src",):
            rel = path.relative_to("admin")
            return f"admin/tests/{rel.with_suffix('.test' + path.suffix)}".replace("/src/", "/")
        return f"tests/{path.with_suffix('.test' + path.suffix)}"
    if path.suffix == ".py":
        stem = path.stem
        return str(path.with_name(f"test_{stem}.py"))
    return None


def _looks_like_test_path(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in TEST_PATH_MARKERS) or lowered.startswith("tests/")


def _derive_allowed_directories(allowed_files: list[str]) -> list[str]:
    directories: list[str] = []
    for path in allowed_files:
        parent = str(PurePosixPath(path).parent)
        if parent and parent != ".":
            directories.append(parent)
        top = path.split("/", 1)[0]
        if top and top not in directories:
            directories.append(top)
    return _dedupe_preserve_order(directories)


def _normalize_paths(paths: list[Any]) -> list[str]:
    return _dedupe_preserve_order(_normalize_path(str(item)) for item in paths if str(item).strip())


def _normalize_path(path: str) -> str:
    cleaned = path.strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned.lstrip("/")


def _dedupe_preserve_order(items) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered
