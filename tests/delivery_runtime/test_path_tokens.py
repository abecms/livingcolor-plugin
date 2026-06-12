"""Tests for shared delivery path token helpers."""

from __future__ import annotations

from pathlib import Path

from delivery_runtime.development.path_tokens import (
    extract_command_path_arguments,
    is_allowed_readonly_skill_path,
    is_allowed_work_order_artifact_path,
    is_glob_only_token,
    is_hard_blocked_path,
    is_path_like_command_token,
    is_shell_device_path,
    should_ignore_path_token,
    terminal_path_access,
)


def test_glob_tokens_are_ignored():
    assert is_glob_only_token("/**") is True
    assert is_glob_only_token("*") is True
    assert is_glob_only_token(".") is True
    assert should_ignore_path_token("./") is True
    assert is_path_like_command_token("/**") is False


def test_hard_blocked_paths():
    assert is_hard_blocked_path("/Users/me/programmation/side-projects/agent-lc") is True
    assert is_hard_blocked_path("../../agent-lc") is True
    assert is_hard_blocked_path("/etc/passwd") is True
    assert is_hard_blocked_path("~/.ssh/id_rsa") is True
    assert is_hard_blocked_path("../evaluation.json") is False


def test_extract_command_paths_only_from_path_verbs():
    assert extract_command_path_arguments("grep -r pattern /**") == []
    assert extract_command_path_arguments("git checkout -- .") == []
    paths = extract_command_path_arguments("cat admin/src/foo.ts")
    assert paths == ["admin/src/foo.ts"]
    redirect_paths = extract_command_path_arguments("npm test > reports/out.txt")
    assert redirect_paths == ["reports/out.txt"]


def test_shell_device_paths_are_ignored():
    assert is_shell_device_path("/dev/null") is True
    assert is_shell_device_path("/dev/tty") is True
    assert is_shell_device_path("/dev/fd/2") is True
    assert should_ignore_path_token("/dev/null") is True
    assert extract_command_path_arguments("npm test 2>/dev/null") == ["/dev/null"]
    assert extract_command_path_arguments("npm ci &>/dev/null") == ["/dev/null"]
    assert should_ignore_path_token("2>/dev/null") is True


def test_ls_node_modules_jest_not_scope_blocked(tmp_path):
    """Inspecting test runner binaries under node_modules must not trip scope guard."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    jest = workspace / "node_modules" / ".bin" / "jest"
    jest.parent.mkdir(parents=True)
    jest.write_text("#!/usr/bin/env node\n", encoding="utf-8")

    from delivery_runtime.development.scope_contract import build_scope_contract
    from delivery_runtime.development.scope_enforcement import ScopeEnforcementGuard

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


def test_readonly_skill_paths(tmp_path: Path, monkeypatch):
    skills_root = tmp_path / "skills"
    skill_file = skills_root / "active" / "thermo-nuclear-code-quality-review.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("# skill\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    assert is_allowed_readonly_skill_path(str(skill_file)) is True
    assert is_allowed_readonly_skill_path(str(tmp_path / "other.txt")) is False
    assert terminal_path_access(f"cat {skill_file}", str(skill_file)) == "read"
    assert terminal_path_access(f"cp {skill_file} /tmp/x", str(skill_file)) == "write"


def test_allowed_work_order_artifact_path(tmp_path: Path):
    artifact = tmp_path / "WO-42"
    workspace = artifact / "workspace"
    workspace.mkdir(parents=True)
    evaluation = artifact / "evaluation.json"
    evaluation.write_text("{}", encoding="utf-8")
    assert is_allowed_work_order_artifact_path(evaluation.resolve(), workspace) is True
    outside = tmp_path / "agent-lc" / "README.md"
    outside.parent.mkdir()
    outside.write_text("nope", encoding="utf-8")
    assert is_allowed_work_order_artifact_path(outside.resolve(), workspace) is False
