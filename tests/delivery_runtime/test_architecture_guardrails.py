"""Guardrails for delivery_runtime Hermes isolation."""

from __future__ import annotations

import ast
from pathlib import Path


def _iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if path.name == "__pycache__":
            continue
        yield path


def test_delivery_runtime_has_no_hermes_imports():
    root = Path(__file__).resolve().parents[2] / "delivery_runtime"
    offenders: list[str] = []

    for path in _iter_python_files(root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in {"hermes_cli", "hermes_state", "hermes_constants", "tools"}:
                        offenders.append(f"{path}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.split(".")[0] in {"hermes_cli", "hermes_state", "hermes_constants", "tools"}:
                    offenders.append(f"{path}: from {module} import ...")

    assert not offenders, "delivery_runtime must not import Hermes:\n" + "\n".join(offenders)
