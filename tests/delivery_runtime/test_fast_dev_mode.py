"""Tests for LivingColor FAST DEV evaluation gate."""

from __future__ import annotations

import pytest

from delivery_runtime.fast_dev.evaluation_gate import assert_full_evaluation_allowed
from delivery_runtime.fast_dev.mode import is_fast_dev_mode
from delivery_runtime.fast_dev.smoke import FAST_DEV_SMOKE_TEST_PATHS


def test_fast_dev_mode_reads_env(monkeypatch):
    monkeypatch.delenv("LIVINGCOLOR_FAST_DEV", raising=False)
    assert is_fast_dev_mode() is False
    monkeypatch.setenv("LIVINGCOLOR_FAST_DEV", "true")
    assert is_fast_dev_mode() is True


def test_assert_full_evaluation_allowed_when_fast_dev_disabled(monkeypatch):
    monkeypatch.delenv("LIVINGCOLOR_FAST_DEV", raising=False)
    assert_full_evaluation_allowed(script_name="run_shadow_evaluation.py")


def test_assert_full_evaluation_blocked_when_fast_dev_enabled(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_FAST_DEV", "true")
    with pytest.raises(SystemExit) as exc:
        assert_full_evaluation_allowed(script_name="run_shadow_evaluation.py")
    assert exc.value.code == 3


def test_force_full_eval_override(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_FAST_DEV", "true")
    assert_full_evaluation_allowed(script_name="run_shadow_evaluation.py", force=True)


def test_smoke_paths_are_curated():
    assert len(FAST_DEV_SMOKE_TEST_PATHS) >= 4
    assert all(path.startswith("tests/delivery_runtime/") for path in FAST_DEV_SMOKE_TEST_PATHS)
