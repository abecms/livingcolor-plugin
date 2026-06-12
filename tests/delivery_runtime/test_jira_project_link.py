"""Tests for linked Jira project settings."""

from __future__ import annotations

from delivery_runtime.readiness.project_settings import (
    persist_project_jira_project_key,
    resolve_jira_project_key,
)


def test_resolve_jira_project_key_defaults_to_livingcolor_key(_isolate_hermes_home):
    assert resolve_jira_project_key("TVP") == "TVP"


def test_persist_and_resolve_linked_jira_project_key(_isolate_hermes_home):
    persist_project_jira_project_key("TV5", "TVP")
    assert resolve_jira_project_key("TV5") == "TVP"
