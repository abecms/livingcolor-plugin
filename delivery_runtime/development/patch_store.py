"""Persist generated patch artifacts for Work Orders."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from delivery_runtime.shadow.paths import get_work_order_artifact_root


@dataclass(frozen=True)
class PatchArtifactPaths:
    patch_path: Path
    report_path: Path


def save_patch_artifact(
    work_order_id: str,
    *,
    diff_text: str,
    execution_report: dict[str, Any],
) -> PatchArtifactPaths:
    root = get_work_order_artifact_root(work_order_id) / "patches"
    root.mkdir(parents=True, exist_ok=True)
    patch_path = root / "latest.patch"
    report_path = root / "latest.report.json"
    patch_path.write_text(diff_text, encoding="utf-8")
    report_path.write_text(json.dumps(execution_report, indent=2, sort_keys=True), encoding="utf-8")
    return PatchArtifactPaths(patch_path=patch_path, report_path=report_path)


def load_patch_artifact(work_order_id: str) -> tuple[str, dict[str, Any]] | None:
    root = get_work_order_artifact_root(work_order_id) / "patches"
    patch_path = root / "latest.patch"
    report_path = root / "latest.report.json"
    if not patch_path.exists() or not report_path.exists():
        return None
    return patch_path.read_text(encoding="utf-8"), json.loads(report_path.read_text(encoding="utf-8"))
