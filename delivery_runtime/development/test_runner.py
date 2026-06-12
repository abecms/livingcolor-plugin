"""Project test detection and execution for development workspaces."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TestRunResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "exitCode": self.exit_code,
            "passed": self.passed,
            "stdoutTail": self.stdout[-4000:],
            "stderrTail": self.stderr[-2000:],
        }


def detect_test_command(
    workspace: Path,
    context_pack: dict[str, Any] | None = None,
    *,
    target_files: list[str] | None = None,
) -> list[str] | None:
    """Best-effort test command for a repository checkout."""
    context_pack = context_pack or {}
    conventions = " ".join(str(item) for item in context_pack.get("project_conventions") or []).lower()

    package_json = workspace / "package.json"
    if package_json.exists():
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        scripts = payload.get("scripts") if isinstance(payload, dict) else {}
        if isinstance(scripts, dict) and scripts.get("test") and scripts["test"] != 'echo "Error: no test specified" && exit 1':
            targeted = _targeted_js_test_paths(workspace, target_files or [])
            if targeted:
                return ["npm", "test", "--", *targeted]
            return ["npm", "test"]

    if (workspace / "pyproject.toml").exists() or (workspace / "pytest.ini").exists() or (workspace / "setup.py").exists():
        if "npm" in conventions:
            return None
        return ["python", "-m", "pytest", "-q"]

    if (workspace / "go.mod").exists():
        return ["go", "test", "./..."]

    if (workspace / "Cargo.toml").exists():
        return ["cargo", "test"]

    return None


def _targeted_js_test_paths(workspace: Path, source_files: list[str]) -> list[str]:
    """Resolve co-located or mirrored test files for a narrow npm test run."""
    discovered: list[str] = []
    seen: set[str] = set()
    for rel in source_files:
        rel_path = Path(str(rel).strip().replace("\\", "/"))
        if not rel_path.parts:
            continue
        suffixes = [rel_path.suffix] if rel_path.suffix else [""]
        if rel_path.suffix:
            suffixes.extend([".ts", ".tsx", ".js", ".jsx"])
        stem = rel_path.stem
        parent = rel_path.parent
        candidates: list[Path] = []
        for suffix in suffixes:
            candidates.extend(
                [
                    parent / f"{stem}.test{suffix}",
                    parent / f"{stem}.spec{suffix}",
                    parent / "__tests__" / f"{stem}.test{suffix}",
                    parent / "__tests__" / f"{stem}.spec{suffix}",
                    Path("tests") / parent / f"{stem}.test{suffix}",
                    Path("tests") / parent / f"{stem}.spec{suffix}",
                    Path("test") / parent / f"{stem}.test{suffix}",
                ]
            )
        if str(rel_path).endswith(".test.ts") or str(rel_path).endswith(".spec.ts"):
            candidates.append(rel_path)
        for candidate in candidates:
            normalized = str(candidate).replace("\\", "/")
            if normalized in seen:
                continue
            if (workspace / candidate).exists():
                seen.add(normalized)
                discovered.append(normalized)
    return discovered[:5]


def run_project_tests(
    workspace: Path,
    context_pack: dict[str, Any] | None = None,
    *,
    target_files: list[str] | None = None,
) -> TestRunResult | None:
    command = detect_test_command(workspace, context_pack, target_files=target_files)
    if not command:
        return None

    completed = subprocess.run(
        command,
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return TestRunResult(
        command=command,
        exit_code=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )
