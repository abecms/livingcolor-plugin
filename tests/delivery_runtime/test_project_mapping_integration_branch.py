"""Tests for per-project integration branch resolution."""

import delivery_runtime.readiness.project_mapping as project_mapping
from delivery_runtime.readiness.project_mapping import resolve_configured_integration_branch


def test_returns_configured_branch(monkeypatch):
    monkeypatch.setattr(
        project_mapping,
        "load_project_mapping",
        lambda: {"TVP": {"default_repo": "tv5mondeplus-front", "integration_branch": "develop"}},
    )
    assert resolve_configured_integration_branch("TVP") == "develop"


def test_returns_none_when_absent(monkeypatch):
    monkeypatch.setattr(
        project_mapping,
        "load_project_mapping",
        lambda: {"TVP": {"default_repo": "tv5mondeplus-front"}},
    )
    assert resolve_configured_integration_branch("TVP") is None


def test_case_insensitive_project_key(monkeypatch):
    monkeypatch.setattr(
        project_mapping,
        "load_project_mapping",
        lambda: {"TVP": {"integration_branch": "develop"}},
    )
    assert resolve_configured_integration_branch("tvp") == "develop"


def test_unknown_project_returns_none(monkeypatch):
    monkeypatch.setattr(project_mapping, "load_project_mapping", lambda: {})
    assert resolve_configured_integration_branch("XYZ") is None
