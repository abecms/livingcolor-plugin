"""Tests for developer post-run test detection."""

from __future__ import annotations

from pathlib import Path

from delivery_runtime.development.test_runner import detect_test_command


def test_detect_test_command_prefers_targeted_js_tests(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    src = workspace / "src" / "components"
    src.mkdir(parents=True)
    (src / "Button.tsx").write_text("export const Button = () => null;\n", encoding="utf-8")
    (src / "Button.test.tsx").write_text("test('button', () => {});\n", encoding="utf-8")
    (workspace / "package.json").write_text(
        '{"scripts": {"test": "vitest run"}}',
        encoding="utf-8",
    )

    command = detect_test_command(workspace, target_files=["src/components/Button.tsx"])
    assert command == ["npm", "test", "--", "src/components/Button.test.tsx"]
