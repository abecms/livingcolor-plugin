"""Phase 3G.2 workspace escape audit simulation and trace tests."""

from __future__ import annotations

from pathlib import Path

from delivery_runtime.development.workspace_access_audit import (
    WORKSPACE_ACCESS_ALLOWED,
    WORKSPACE_ACCESS_BLOCKED,
    get_workspace_access_trace,
    reset_workspace_access_audit_log,
)
from delivery_runtime.development.workspace_confinement import (
    WorkspaceConfinementGuard,
    activate_workspace_runtime,
    check_delivery_workspace_tool,
    clear_workspace_confinement,
    deactivate_workspace_runtime,
)


def _layout(tmp_path: Path, work_order_id: str = "WO-99") -> tuple[Path, Path]:
    artifact = tmp_path / work_order_id
    workspace = artifact / "workspace"
    workspace.mkdir(parents=True)
    src = workspace / "src"
    src.mkdir()
    (src / "file.ts").write_text("export const ok = true;\n", encoding="utf-8")
    return artifact, workspace


def test_terminal_escape_emits_blocked_trace(tmp_path: Path):
    reset_workspace_access_audit_log()
    _, workspace = _layout(tmp_path)
    task_id = "delivery-dev-WO-99"
    guard = WorkspaceConfinementGuard(workspace_root=workspace, task_id=task_id)
    message = guard.check_terminal_before("cd ../../agent-lc")
    assert message is not None
    trace = get_workspace_access_trace(task_id)
    assert len(trace) == 1
    assert trace[0]["event"] == WORKSPACE_ACCESS_BLOCKED
    assert trace[0]["tool"] == "terminal"
    assert trace[0]["reason"] == "shell_parent_escape"
    assert "agent-lc" in trace[0]["path"]


def test_terminal_in_workspace_emits_allowed_trace(tmp_path: Path):
    reset_workspace_access_audit_log()
    _, workspace = _layout(tmp_path)
    task_id = "delivery-dev-WO-99"
    guard = WorkspaceConfinementGuard(workspace_root=workspace, task_id=task_id)
    assert guard.check_terminal_before("cat ./src/file.ts") is None
    trace = get_workspace_access_trace(task_id)
    assert len(trace) == 1
    assert trace[0]["event"] == WORKSPACE_ACCESS_ALLOWED
    assert trace[0]["tool"] == "terminal"
    assert trace[0]["path"] == "./src/file.ts"
    assert trace[0]["reason"] == "inside_workspace"
    assert trace[0]["resolved_path"].endswith("/src/file.ts")


def test_file_tool_emits_allowed_trace(tmp_path: Path):
    reset_workspace_access_audit_log()
    _, workspace = _layout(tmp_path)
    task_id = "delivery-dev-WO-99"
    activate_workspace_runtime(task_id, workspace)
    assert check_delivery_workspace_tool(task_id, "read_file", {"path": "src/file.ts"}) is None
    trace = get_workspace_access_trace(task_id)
    assert trace[-1]["event"] == WORKSPACE_ACCESS_ALLOWED
    assert trace[-1]["tool"] == "file"
    deactivate_workspace_runtime(task_id, previous_terminal_cwd=None, session_token=None)
    clear_workspace_confinement(task_id)


def test_file_tool_emits_blocked_trace_for_agent_lc(tmp_path: Path):
    reset_workspace_access_audit_log()
    _, workspace = _layout(tmp_path)
    task_id = "delivery-dev-WO-99"
    activate_workspace_runtime(task_id, workspace)
    message = check_delivery_workspace_tool(
        task_id,
        "read_file",
        {"path": "/Users/me/programmation/side-projects/agent-lc/AGENTS.md"},
    )
    assert message is not None
    trace = get_workspace_access_trace(task_id)
    assert trace[-1]["event"] == WORKSPACE_ACCESS_BLOCKED
    assert trace[-1]["tool"] == "file"
    assert trace[-1]["reason"] == "hard_blocked_path"
    deactivate_workspace_runtime(task_id, previous_terminal_cwd=None, session_token=None)
    clear_workspace_confinement(task_id)


def test_simulated_escape_matrix(tmp_path: Path):
    reset_workspace_access_audit_log()
    _, workspace = _layout(tmp_path)
    task_id = "delivery-dev-WO-99"

    scenarios = [
        ("cd ../../agent-lc", WORKSPACE_ACCESS_BLOCKED),
        ("cat ./src/file.ts", WORKSPACE_ACCESS_ALLOWED),
        ("grep -r pattern /**", None),
        ("cat /etc/passwd", WORKSPACE_ACCESS_BLOCKED),
    ]

    for command, expected_event in scenarios:
        before = len(get_workspace_access_trace(task_id))
        guard = WorkspaceConfinementGuard(workspace_root=workspace, task_id=task_id)
        guard.check_terminal_before(command)
        trace = get_workspace_access_trace(task_id)
        if expected_event is None:
            assert len(trace) == before
            continue
        assert trace[-1]["event"] == expected_event
