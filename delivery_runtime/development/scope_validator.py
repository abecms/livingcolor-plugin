"""Scope Contract validation for developer patches (Phase 3E)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Literal

from delivery_runtime.development.scope_contract import ScopeContract, predicted_files_from_plan, build_scope_contract, is_ephemeral_side_effect_path

ScopeOutcome = Literal["PASS", "SCOPE_VIOLATION", "SCOPE_EXPLOSION"]


@dataclass(frozen=True)
class ScopeValidationResult:
    outcome: ScopeOutcome
    predicted_files: list[str]
    touched_files: list[str]
    scope_precision: float
    scope_recall: float
    reason: str = ""
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "reason": self.reason,
            "predictedFiles": self.predicted_files,
            "touchedFiles": self.touched_files,
            "scopePrecision": round(self.scope_precision, 3),
            "scopeRecall": round(self.scope_recall, 3),
            "violations": self.violations,
        }


def validate_dev_result_scope(
    *,
    context: dict[str, Any],
    files_modified: list[str],
    files_created: list[str],
    files_deleted: list[str],
    patch_stats: dict[str, Any],
) -> dict[str, Any]:
    approved_plan = context.get("approvedAnalysisPlan") or {}
    scope_payload = context.get("scopeContract") or {}
    if not scope_payload:
        contract = build_scope_contract(
            str((context.get("workOrder") or {}).get("id") or "WO-UNKNOWN"),
            approved_plan,
        )
    elif context.get("runtimeWorkspaceOnly"):
        from delivery_runtime.development.scope_contract import build_runtime_scope_contract

        contract = build_runtime_scope_contract(
            str((context.get("workOrder") or {}).get("id") or "WO-UNKNOWN"),
            scope_payload,
            workspace_only=True,
        ) or build_scope_contract(
            str((context.get("workOrder") or {}).get("id") or "WO-UNKNOWN"),
            approved_plan,
        )
    else:
        contract = ScopeContract.from_dict(scope_payload)
    result = validate_patch_scope(
        contract=contract,
        approved_plan=approved_plan,
        files_modified=files_modified,
        files_created=files_created,
        files_deleted=files_deleted,
        patch_stats=patch_stats,
    )
    return result.to_dict()


def is_workspace_nav_path(path: str) -> bool:
    """True for repo-root tokens — navigation, not intentional file edits."""
    normalized = _normalize_path(path)
    return not normalized or normalized == "."


def check_path_against_contract(path: str, contract: ScopeContract) -> str | None:
    """Return a violation message when a path is forbidden or outside scope."""
    if contract.workspace_only:
        return None
    normalized = _normalize_path(path)
    if is_workspace_nav_path(normalized):
        return None
    if _matches_forbidden(normalized, contract.forbidden_paths):
        return f"Modified forbidden path: {normalized}"
    if not _is_allowed(normalized, contract):
        return f"Modified file outside approved scope: {normalized}"
    return None


def validate_patch_scope(
    *,
    contract: ScopeContract,
    approved_plan: dict[str, Any],
    files_modified: list[str],
    files_created: list[str],
    files_deleted: list[str] | None = None,
    patch_stats: dict[str, Any] | None = None,
) -> ScopeValidationResult:
    touched = _normalize_paths((files_modified or []) + (files_created or []) + (files_deleted or []))
    touched = [path for path in touched if not is_ephemeral_side_effect_path(path)]
    predicted = predicted_files_from_plan(approved_plan)
    precision, recall = compute_scope_metrics(predicted, touched)
    violations: list[str] = []

    if contract.workspace_only:
        return ScopeValidationResult(
            outcome="PASS",
            reason="Managed checkout — runtime scope is workspace-only.",
            predicted_files=predicted,
            touched_files=touched,
            scope_precision=precision,
            scope_recall=recall,
            violations=[],
        )

    for path in touched:
        if _matches_forbidden(path, contract.forbidden_paths):
            violations.append(f"Modified forbidden path: {path}")

    for path in touched:
        if _matches_forbidden(path, contract.forbidden_paths):
            continue
        if not _is_allowed(path, contract):
            violations.append(f"Modified file outside approved scope: {path}")

    if violations:
        return ScopeValidationResult(
            outcome="SCOPE_VIOLATION",
            reason=violations[0],
            predicted_files=predicted,
            touched_files=touched,
            scope_precision=precision,
            scope_recall=recall,
            violations=violations,
        )

    if len(touched) > contract.max_files_touched:
        reason = (
            f"Touched {len(touched)} files; limit is {contract.max_files_touched}"
        )
        return ScopeValidationResult(
            outcome="SCOPE_EXPLOSION",
            reason=reason,
            predicted_files=predicted,
            touched_files=touched,
            scope_precision=precision,
            scope_recall=recall,
            violations=[reason],
        )

    lines_changed = _lines_changed(patch_stats)
    if lines_changed > contract.max_lines_changed:
        reason = f"Changed {lines_changed} lines; limit is {contract.max_lines_changed}"
        return ScopeValidationResult(
            outcome="SCOPE_EXPLOSION",
            reason=reason,
            predicted_files=predicted,
            touched_files=touched,
            scope_precision=precision,
            scope_recall=recall,
            violations=[reason],
        )

    return ScopeValidationResult(
        outcome="PASS",
        reason="Patch stayed within the Scope Contract.",
        predicted_files=predicted,
        touched_files=touched,
        scope_precision=precision,
        scope_recall=recall,
        violations=[],
    )


def compute_scope_metrics(predicted: list[str], touched: list[str]) -> tuple[float, float]:
    predicted_set = set(_normalize_paths(predicted))
    touched_set = set(_normalize_paths(touched))
    if not touched_set:
        precision = 1.0 if not predicted_set else 0.0
    else:
        precision = len(predicted_set & touched_set) / len(touched_set)
    if not predicted_set:
        recall = 1.0 if not touched_set else 0.0
    else:
        recall = len(predicted_set & touched_set) / len(predicted_set)
    return precision, recall


def _is_allowed(path: str, contract: ScopeContract) -> bool:
    normalized = _normalize_path(path)
    if normalized in {_normalize_path(item) for item in contract.allowed_files}:
        return True
    parent = str(PurePosixPath(normalized).parent)
    for directory in contract.allowed_directories:
        allowed_dir = _normalize_path(directory)
        if not allowed_dir:
            continue
        if normalized == allowed_dir or normalized.startswith(f"{allowed_dir}/"):
            return True
        if parent == allowed_dir or parent.startswith(f"{allowed_dir}/"):
            return True
    return False


def _matches_forbidden(path: str, forbidden_paths: list[str]) -> bool:
    normalized = _normalize_path(path)
    for forbidden in forbidden_paths:
        blocked = _normalize_path(forbidden)
        if not blocked:
            continue
        if normalized == blocked or normalized.endswith(f"/{blocked}"):
            return True
        if normalized.startswith(f"{blocked}/"):
            return True
        if PurePosixPath(normalized).name == blocked:
            return True
    return False


def _lines_changed(patch_stats: dict[str, Any] | None) -> int:
    if not patch_stats:
        return 0
    explicit = int(patch_stats.get("linesChanged") or 0)
    if explicit:
        return explicit
    return int(patch_stats.get("linesAdded") or 0) + int(patch_stats.get("linesRemoved") or 0)


def _normalize_paths(paths: list[str]) -> list[str]:
    normalized = [_normalize_path(path) for path in paths if path.strip()]
    return list(dict.fromkeys(normalized))


def _normalize_path(path: str) -> str:
    cleaned = path.strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned.lstrip("/")
