"""Targeted smoke tests for FAST DEV iteration loops."""

from __future__ import annotations

FAST_DEV_SMOKE_TEST_PATHS: tuple[str, ...] = (
    "tests/delivery_runtime/test_path_tokens.py",
    "tests/delivery_runtime/test_workspace_confinement.py",
    "tests/delivery_runtime/test_workspace_escape_audit.py",
    "tests/delivery_runtime/test_scope_enforcement.py",
    "tests/delivery_runtime/test_scope_validator.py",
    "tests/delivery_runtime/test_orchestration_phase3a.py",
    "tests/delivery_runtime/test_delivery_api.py",
)
