"""Tests for workspace reuse across developer phases."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from unittest.mock import patch

import pytest

from delivery_runtime.context.repo_checkout import is_managed_repo_checkout
from delivery_runtime.development.workspace import prepare_development_workspace
from delivery_runtime.shadow.context import allow_internal_git
from delivery_runtime.shadow.paths import get_work_order_artifact_root


def test_prepare_development_workspace_reuses_existing_checkout(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "module.py").write_text("value = 1\n", encoding="utf-8")

    work_order_id = "WO-REUSE-1"
    artifact_root = get_work_order_artifact_root(work_order_id)
    if artifact_root.exists():
        shutil.rmtree(artifact_root)

    workspace, baseline = prepare_development_workspace(work_order_id, str(source), jira_key="TVP-1")
    assert workspace.exists()
    assert baseline

    marker = "# reused marker"
    (workspace / "module.py").write_text((workspace / "module.py").read_text() + marker, encoding="utf-8")

    reused, reused_baseline = prepare_development_workspace(
        work_order_id,
        str(source),
        reuse_existing=True,
        baseline_ref=baseline,
    )
    assert reused == workspace
    assert reused_baseline == baseline
    assert marker in (workspace / "module.py").read_text(encoding="utf-8")

    shutil.rmtree(artifact_root, ignore_errors=True)


def test_managed_checkout_uses_source_path_without_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LIVINGCOLOR_HOME", str(tmp_path / "livingcolor"))
    managed_root = tmp_path / "livingcolor" / "TVP" / "org" / "demo-repo"
    managed_root.mkdir(parents=True)
    (managed_root / "module.py").write_text("value = 1\n", encoding="utf-8")
    with allow_internal_git():
        subprocess.run(["git", "init", "-b", "main"], cwd=managed_root, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=managed_root, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "baseline"],
            cwd=managed_root,
            check=True,
            capture_output=True,
        )

    assert is_managed_repo_checkout(managed_root)

    work_order_id = "WO-MANAGED-1"
    artifact_root = get_work_order_artifact_root(work_order_id)
    if artifact_root.exists():
        shutil.rmtree(artifact_root)

    with patch("delivery_runtime.development.workspace.fetch_managed_checkout") as fetch_mock:
        fetch_mock.return_value = True
        workspace, baseline = prepare_development_workspace(
            work_order_id,
            str(managed_root),
            jira_key="TVP-99",
        )
    fetch_mock.assert_called_once_with(managed_root.resolve())
    assert workspace == managed_root.resolve()
    assert baseline
    assert not (artifact_root / "workspace").exists()

    marker = "# managed marker"
    (managed_root / "module.py").write_text((managed_root / "module.py").read_text() + marker, encoding="utf-8")

    work_order_id_2 = "WO-MANAGED-2"
    artifact_root_2 = get_work_order_artifact_root(work_order_id_2)
    workspace_2, _ = prepare_development_workspace(
        work_order_id_2,
        str(managed_root),
        reuse_existing=True,
        baseline_ref=baseline,
    )
    assert workspace_2 == managed_root.resolve()
    assert marker in (managed_root / "module.py").read_text(encoding="utf-8")

    shutil.rmtree(artifact_root, ignore_errors=True)
    shutil.rmtree(artifact_root_2, ignore_errors=True)
