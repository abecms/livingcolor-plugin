"""Tests for Phase 3F hard Scope Contract enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest

from delivery_runtime.development.command_policy import evaluate_terminal_command
from delivery_runtime.development.scope_contract import ScopeContract, build_scope_contract, build_runtime_scope_contract
from delivery_runtime.development.scope_enforcement import (
    SCOPE_VIOLATION_BLOCKED,
    ScopeEnforcementGuard,
    check_delivery_tool_scope,
    clear_scope_guard,
    guard_from_context,
    register_scope_guard,
)


def _sample_plan() -> dict:
    return {
        "implementationPlan": "Edit component and add test.",
        "likelyImpactedFiles": ["admin/src/components/CriteresAutomatiquesInput.tsx"],
        "candidateTests": ["admin/tests/CriteresAutomatiquesInput.tsx.test.ts"],
    }


def test_command_policy_blocks_dependency_install():
    result = evaluate_terminal_command("npm install lodash")
    assert result.decision == "deny"


def test_command_policy_allows_tests():
    result = evaluate_terminal_command("npm run test -- --runInBand")
    assert result.decision == "allow"


def test_command_policy_blocks_git_push():
    result = evaluate_terminal_command("git push origin feature/bn-516")
    assert result.decision == "deny"


def test_command_policy_allows_git_commit_when_merge_conflict_resolution():
    result = evaluate_terminal_command("git commit -m 'resolve merge'", allow_git_write=True)
    assert result.decision == "allow"


def test_git_push_denied_by_default():
    result = evaluate_terminal_command("git push -u origin feature/TVP-1489")
    assert result.decision == "deny"


def test_git_push_allowed_with_push_flag():
    result = evaluate_terminal_command(
        "git push -u origin feature/TVP-1489", allow_git_push=True
    )
    assert result.decision == "allow"


def test_git_commit_still_denied_with_push_flag():
    result = evaluate_terminal_command("git commit -m 'x'", allow_git_push=True)
    assert result.decision == "deny"


def test_git_push_still_allowed_with_git_write_flag():
    result = evaluate_terminal_command(
        "git push origin HEAD", allow_git_write=True
    )
    assert result.decision == "allow"


def test_force_push_denied_even_with_push_flag():
    result = evaluate_terminal_command(
        "git push --force origin x", allow_git_push=True
    )
    assert result.decision == "deny"
    assert "force push" in result.reason


def test_short_force_push_denied_even_with_git_write_flag():
    result = evaluate_terminal_command("git push -f origin x", allow_git_write=True)
    assert result.decision == "deny"


def test_force_with_lease_push_denied():
    result = evaluate_terminal_command(
        "git push --force-with-lease=main:abc origin main", allow_git_push=True
    )
    assert result.decision == "deny"


def test_plain_push_still_allowed_with_push_flag():
    result = evaluate_terminal_command("git push -u origin x", allow_git_push=True)
    assert result.decision == "allow"


def test_branch_name_containing_f_is_not_force_push():
    result = evaluate_terminal_command(
        "git push -u origin feature/x-f", allow_git_push=True
    )
    assert result.decision == "allow"


def test_guard_allows_git_merge_when_merge_conflict_resolution(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    task_id = "delivery-dev-WO-99"
    guard_from_context(
        task_id=task_id,
        workspace=workspace,
        baseline_ref=None,
        scope_contract=build_scope_contract("WO-99", _sample_plan()).to_dict(),
        allow_git_write=True,
    )
    message = check_delivery_tool_scope(task_id, "terminal", {"command": "git merge --continue"})
    assert message is None
    clear_scope_guard(task_id)


def test_guard_blocks_forbidden_write_file(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    contract = build_scope_contract("WO-99", _sample_plan())
    guard = ScopeEnforcementGuard(contract=contract, workspace=workspace, baseline_ref=None)
    message = guard.check_write_path("admin/package-lock.json")
    assert message is not None
    assert "Scope expansion required" in message
    assert guard.blocked is True


def test_guard_allows_in_scope_write(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    contract = build_scope_contract("WO-99", _sample_plan())
    guard = ScopeEnforcementGuard(contract=contract, workspace=workspace, baseline_ref=None)
    allowed = "admin/src/components/CriteresAutomatiquesInput.tsx"
    assert guard.check_write_path(allowed) is None


def test_guard_allows_dev_null_in_terminal_commands(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    contract = build_scope_contract("WO-99", _sample_plan())
    guard = ScopeEnforcementGuard(contract=contract, workspace=workspace, baseline_ref=None)
    for command in (
        "npm test 2>/dev/null",
        "command -v node >/dev/null 2>&1",
        "npm ci &>/dev/null",
    ):
        guard = ScopeEnforcementGuard(contract=contract, workspace=workspace, baseline_ref=None)
        assert guard.check_terminal_before(command) is None
        assert guard.blocked is False


def test_delivery_tool_scope_blocks_patch_paths(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    task_id = "delivery-dev-WO-99"
    guard_from_context(
        task_id=task_id,
        workspace=workspace,
        baseline_ref=None,
        scope_contract=build_scope_contract("WO-99", _sample_plan()).to_dict(),
    )
    message = check_delivery_tool_scope(
        task_id,
        "patch",
        {"mode": "replace", "path": "public/assets/index.js", "old_string": "a", "new_string": "b"},
    )
    assert message is not None
    clear_scope_guard(task_id)


def test_guard_rollback_removes_forbidden_git_changes(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "admin").mkdir(parents=True)
    (workspace / "admin" / "package-lock.json").write_text('{"name":"demo"}', encoding="utf-8")
    (workspace / "admin" / "src").mkdir(parents=True)
    (workspace / "admin" / "src" / "allowed.ts").write_text("export const ok = 1;\n", encoding="utf-8")

    import subprocess

    from delivery_runtime.shadow.context import allow_internal_git

    with allow_internal_git():
        subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=workspace, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "baseline"],
            cwd=workspace,
            check=True,
            capture_output=True,
        )
        baseline = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        (workspace / "admin" / "package-lock.json").write_text('{"name":"changed"}', encoding="utf-8")

    contract = ScopeContract(
        work_order_id="WO-99",
        allowed_files=["admin/src/allowed.ts"],
        allowed_directories=["admin/src"],
        forbidden_paths=["package-lock.json", "public/assets"],
    )
    guard = ScopeEnforcementGuard(contract=contract, workspace=workspace, baseline_ref=baseline)
    blocked = guard.post_terminal_after("npm install")
    assert blocked is not None
    assert guard.blocked is True
    assert guard.block_outcome == SCOPE_VIOLATION_BLOCKED


def test_terminal_allows_workspace_root_path(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "tests").mkdir(parents=True)
    (workspace / "tests" / "sample.test.js").write_text("test('ok', () => {});\n", encoding="utf-8")
    contract = build_scope_contract(
        "WO-99",
        {
            "likelyImpactedFiles": ["tests/sample.test.js"],
            "implementationPlan": "Update tests/sample.test.js",
        },
    )
    guard = ScopeEnforcementGuard(contract=contract, workspace=workspace, baseline_ref=None)
    workspace_text = str(workspace.resolve())
    assert guard.check_terminal_before(f"cd {workspace_text} && ls") is None
    assert guard.check_write_path("tests/sample.test.js") is None
    assert guard.blocked is False


def test_post_terminal_ignores_node_modules_test_side_effects(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "tests").mkdir(parents=True)
    (workspace / "tests" / "sample.test.js").write_text("test('ok', () => {});\n", encoding="utf-8")
    node_bin = workspace / "node_modules" / ".bin"
    node_bin.mkdir(parents=True)
    jest = node_bin / "jest"
    jest.write_text("#!/usr/bin/env node\n", encoding="utf-8")

    import subprocess

    from delivery_runtime.shadow.context import allow_internal_git

    with allow_internal_git():
        subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=workspace, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "baseline"],
            cwd=workspace,
            check=True,
            capture_output=True,
        )
        baseline = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        jest.write_text("#!/usr/bin/env node\nconsole.log('touched');\n", encoding="utf-8")

    contract = build_scope_contract(
        "WO-99",
        {
            "likelyImpactedFiles": ["tests/sample.test.js"],
            "implementationPlan": "Update tests/sample.test.js",
        },
    )
    guard = ScopeEnforcementGuard(contract=contract, workspace=workspace, baseline_ref=baseline)
    assert guard.post_terminal_after("npm test -- tests/sample.test.js") is None
    assert guard.blocked is False


def test_terminal_allows_inspecting_node_modules_jest_binary(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    jest = workspace / "node_modules" / ".bin" / "jest"
    jest.parent.mkdir(parents=True)
    jest.write_text("#!/usr/bin/env node\n", encoding="utf-8")
    contract = build_scope_contract(
        "WO-99",
        {
            "likelyImpactedFiles": ["tests/unit/live-direct-name.test.js"],
            "implementationPlan": "Update tests/unit/live-direct-name.test.js",
        },
    )
    guard = ScopeEnforcementGuard(contract=contract, workspace=workspace, baseline_ref=None)
    workspace_text = str(workspace.resolve())
    command = f"cd {workspace_text} && ls node_modules/.bin/jest 2>/dev/null"
    assert guard.check_terminal_before(command) is None
    assert guard.blocked is False


def test_workspace_only_scope_allows_node_modules_paths(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    contract = build_runtime_scope_contract("WO-99", build_scope_contract("WO-99", _sample_plan()).to_dict(), workspace_only=True)
    assert contract is not None
    guard = ScopeEnforcementGuard(contract=contract, workspace=workspace, baseline_ref=None)
    command = f"cd {workspace.resolve()} && ls node_modules/.bin/jest 2>/dev/null"
    assert guard.check_terminal_before(command) is None
    assert guard.check_write_path("node_modules/.bin/jest") is None
    assert guard.blocked is False
