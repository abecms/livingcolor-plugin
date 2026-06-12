"""Tests for Phase 3G workspace confinement."""

from __future__ import annotations

from pathlib import Path

from delivery_runtime.development.workspace_confinement import (
    WORKSPACE_VIOLATION,
    WorkspaceConfinementGuard,
    activate_workspace_runtime,
    clear_workspace_confinement,
    deactivate_workspace_runtime,
    resolve_confined_path,
)


def _artifact_layout(tmp_path: Path, work_order_id: str = "WO-42") -> tuple[Path, Path]:
    artifact = tmp_path / work_order_id
    workspace = artifact / "workspace"
    workspace.mkdir(parents=True)
    return artifact, workspace


def test_resolve_confined_path_stays_in_workspace(tmp_path: Path):
    _, workspace = _artifact_layout(tmp_path, "WO-1")
    (workspace / "AGENTS.md").write_text("# repo\n", encoding="utf-8")
    task_id = "delivery-dev-WO-1"
    activate_workspace_runtime(task_id, workspace)
    rel = resolve_confined_path("AGENTS.md", workspace, task_id)
    assert rel == "AGENTS.md"
    rel_dot = resolve_confined_path("./", workspace, task_id)
    assert rel_dot == "."
    deactivate_workspace_runtime(task_id, previous_terminal_cwd=None, session_token=None)


def test_outside_path_is_rejected(tmp_path: Path):
    _, workspace = _artifact_layout(tmp_path, "WO-2")
    guard = WorkspaceConfinementGuard(workspace_root=workspace, task_id="delivery-dev-WO-2")
    message = guard.assert_path_allowed("/Users/me/agent-lc/AGENTS.md")
    assert message is not None
    assert guard.blocked is True


def test_terminal_cd_parent_blocked(tmp_path: Path):
    _, workspace = _artifact_layout(tmp_path, "WO-3")
    guard = WorkspaceConfinementGuard(workspace_root=workspace, task_id="delivery-dev-WO-3")
    message = guard.check_terminal_before("cd .. && ls")
    assert message is not None
    assert WORKSPACE_VIOLATION in guard.violation_events[0]["outcome"]


def test_terminal_glob_path_not_blocked(tmp_path: Path):
    _, workspace = _artifact_layout(tmp_path, "WO-5")
    guard = WorkspaceConfinementGuard(workspace_root=workspace, task_id="delivery-dev-WO-5")
    message = guard.check_terminal_before("grep -r pattern /**")
    assert message is None
    assert guard.blocked is False


def test_terminal_bare_dot_not_blocked(tmp_path: Path):
    _, workspace = _artifact_layout(tmp_path, "WO-6")
    guard = WorkspaceConfinementGuard(workspace_root=workspace, task_id="delivery-dev-WO-6")
    message = guard.check_terminal_before("git checkout -- .")
    assert message is None
    assert guard.blocked is False


def test_activate_workspace_runtime_uses_confinement_root(tmp_path: Path):
    project_env = tmp_path / "TVP"
    repo = project_env / "tv5monde" / "tv5mondeplus-front"
    repo.mkdir(parents=True)
    sibling = project_env / "tv5monde" / "other-repo"
    sibling.mkdir(parents=True)
    (sibling / "README.md").write_text("ok\n", encoding="utf-8")

    task_id = "delivery-dev-WO-10"
    activate_workspace_runtime(task_id, repo, confinement_root=project_env)
    from delivery_runtime.development.workspace_confinement import get_workspace_confinement

    guard = get_workspace_confinement(task_id)
    assert guard is not None
    assert guard.assert_path_allowed(str(sibling / "README.md"), tool="file", access="read") is None
    assert guard.assert_path_allowed("/Users/me/outside", tool="file", access="read") is not None
    deactivate_workspace_runtime(task_id, previous_terminal_cwd=None, session_token=None)


def test_terminal_dev_null_redirect_not_blocked(tmp_path: Path):
    _, workspace = _artifact_layout(tmp_path, "WO-9")
    guard = WorkspaceConfinementGuard(workspace_root=workspace, task_id="delivery-dev-WO-9")
    for command in (
        "npm test 2>/dev/null",
        "command -v node >/dev/null 2>&1",
        "npm ci &>/dev/null",
    ):
        guard = WorkspaceConfinementGuard(workspace_root=workspace, task_id="delivery-dev-WO-9")
        assert guard.check_terminal_before(command) is None
        assert guard.blocked is False


def test_readonly_skill_path_allowed_for_read_file(tmp_path: Path, monkeypatch):
    _, workspace = _artifact_layout(tmp_path, "WO-10")
    hermes_home = tmp_path / "hermes"
    skill_file = hermes_home / "skills" / "active" / "thermo-nuclear-code-quality-review.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("# review\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    guard = WorkspaceConfinementGuard(workspace_root=workspace, task_id="delivery-dev-WO-10")
    assert guard.assert_path_allowed(str(skill_file), tool="file", access="read") is None
    assert guard.blocked is False

    guard = WorkspaceConfinementGuard(workspace_root=workspace, task_id="delivery-dev-WO-10b")
    assert guard.assert_path_allowed(str(skill_file), tool="file", access="write") is not None
    assert guard.blocked is True


def test_evaluation_json_in_work_order_artifact_allowed(tmp_path: Path):
    artifact, workspace = _artifact_layout(tmp_path, "WO-42")
    (artifact / "evaluation.json").write_text("{}", encoding="utf-8")
    guard = WorkspaceConfinementGuard(workspace_root=workspace, task_id="delivery-dev-WO-42")
    assert guard.assert_path_allowed("../evaluation.json") is None
    assert guard.assert_path_allowed(str(artifact / "evaluation.json")) is None


def test_arbitrary_parent_escape_still_blocked(tmp_path: Path):
    _, workspace = _artifact_layout(tmp_path, "WO-7")
    guard = WorkspaceConfinementGuard(workspace_root=workspace, task_id="delivery-dev-WO-7")
    assert guard.assert_path_allowed("../../agent-lc/README.md") is not None
    assert guard.assert_path_allowed("/etc/passwd") is not None


def test_grep_pattern_with_slash_not_inspected(tmp_path: Path):
    _, workspace = _artifact_layout(tmp_path, "WO-8")
    guard = WorkspaceConfinementGuard(workspace_root=workspace, task_id="delivery-dev-WO-8")
    assert guard.check_terminal_before("rg 'foo/bar' admin/src") is None


def test_activate_workspace_runtime_sets_terminal_cwd(tmp_path: Path, monkeypatch):
    _, workspace = _artifact_layout(tmp_path, "WO-4")
    task_id = "delivery-dev-WO-4"
    previous, token = activate_workspace_runtime(task_id, workspace)
    import os

    assert os.environ["TERMINAL_CWD"] == str(workspace.resolve())
    deactivate_workspace_runtime(task_id, previous_terminal_cwd=previous, session_token=token)
    clear_workspace_confinement(task_id)
