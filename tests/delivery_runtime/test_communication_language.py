"""Tests for project communication language settings."""

from __future__ import annotations

import pytest

from delivery_runtime.communication.language import (
    get_clarification_comment_template,
    get_mr_labels,
    get_not_development_comment_template,
    normalize_communication_language,
)
from delivery_runtime.mr_drafts.generator import generate_mr_draft_content
from delivery_runtime.pm_inbox.analyst import analyze_for_daily_delivery


def test_normalize_communication_language_defaults_to_french():
    assert normalize_communication_language(None) == "fr"
    assert normalize_communication_language("fr-FR") == "fr"
    assert normalize_communication_language("en-US") == "en"
    assert normalize_communication_language("de") == "fr"


def test_comment_templates_switch_language():
    assert "reproduction steps" in get_clarification_comment_template("en").lower()
    assert "étapes de reproduction" in get_clarification_comment_template("fr").lower()
    assert "non-development" in get_not_development_comment_template("en").lower()
    assert "non-développement" in get_not_development_comment_template("fr").lower()


def test_generate_mr_draft_content_uses_french_section_headers():
    content = generate_mr_draft_content(
        jira_key="BN-1",
        work_order_title="Fix redirect",
        jira_snapshot={"summary": "Fix redirect", "description": "Acceptance criteria: user lands on home"},
        approved_plan={"implementationPlan": "Update callback handler"},
        context_pack={},
        code_review_payload={
            "summary": "Adjusted OAuth callback",
            "filesModified": ["src/auth/callback.ts"],
        },
        communication_language="fr",
    )

    assert "### Contexte" in content["description"]
    assert "### Modifications" in content["description"]
    assert "Critères d'acceptation" in content["ticketSummary"]
