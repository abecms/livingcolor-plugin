from __future__ import annotations

import json

import pytest


VALID_LOCK = {
    "repo": "Tamsi/livingcolor-skills",
    "ref": "v0.2.0",
    "resolvedCommit": "316e3ba0f98aacff910c3f79e64f21e058d11baa",
    "bundle": "code-review-pipeline",
    "skills": [
        "ticket-analyst",
        "code-architect",
        "qa-reviewer",
        "security-auditor",
        "sprint-reporter",
    ],
    "updatedBy": "livingcolor-evolution",
}


def test_parse_valid_external_skills_lock():
    from lc_server.integrations.skills.lock import parse_external_skills_lock

    lock = parse_external_skills_lock(VALID_LOCK)

    assert lock.repo == "Tamsi/livingcolor-skills"
    assert lock.ref == "v0.2.0"
    assert lock.resolved_commit == "316e3ba0f98aacff910c3f79e64f21e058d11baa"
    assert lock.bundle == "code-review-pipeline"
    assert lock.skills == (
        "ticket-analyst",
        "code-architect",
        "qa-reviewer",
        "security-auditor",
        "sprint-reporter",
    )
    assert lock.updated_by == "livingcolor-evolution"


def test_lock_rejects_unapproved_repo():
    from lc_server.integrations.skills.lock import parse_external_skills_lock

    payload = {**VALID_LOCK, "repo": "Other/livingcolor-skills"}

    with pytest.raises(ValueError, match="Unsupported skills repo"):
        parse_external_skills_lock(payload)


def test_lock_rejects_moving_main_ref():
    from lc_server.integrations.skills.lock import parse_external_skills_lock

    payload = {**VALID_LOCK, "ref": "main"}

    with pytest.raises(ValueError, match="must not be a moving branch"):
        parse_external_skills_lock(payload)


def test_lock_rejects_heads_main_ref():
    from lc_server.integrations.skills.lock import parse_external_skills_lock

    payload = {**VALID_LOCK, "ref": "refs/heads/main"}

    with pytest.raises(ValueError, match="must not be a moving branch"):
        parse_external_skills_lock(payload)


def test_lock_rejects_branch_like_ref():
    from lc_server.integrations.skills.lock import parse_external_skills_lock

    payload = {**VALID_LOCK, "ref": "feature/foo"}

    with pytest.raises(ValueError, match="must not be a moving branch"):
        parse_external_skills_lock(payload)


def test_lock_rejects_short_resolved_commit():
    from lc_server.integrations.skills.lock import parse_external_skills_lock

    payload = {**VALID_LOCK, "resolvedCommit": "abc123"}

    with pytest.raises(ValueError, match="resolvedCommit"):
        parse_external_skills_lock(payload)


def test_lock_rejects_uppercase_resolved_commit():
    from lc_server.integrations.skills.lock import parse_external_skills_lock

    payload = {**VALID_LOCK, "resolvedCommit": "FDF1BE62D61EF74B51D91AE81ED718350DCE20D5"}

    with pytest.raises(ValueError, match="resolvedCommit"):
        parse_external_skills_lock(payload)


def test_lock_rejects_non_string_skill_item():
    from lc_server.integrations.skills.lock import parse_external_skills_lock

    payload = {**VALID_LOCK, "skills": ["ticket-analyst", 123]}

    with pytest.raises(ValueError, match="skills"):
        parse_external_skills_lock(payload)


def test_load_external_skills_lock_from_root(tmp_path):
    from lc_server.integrations.skills.lock import load_external_skills_lock

    path = tmp_path / "livingcolor.skills.lock.json"
    path.write_text(json.dumps(VALID_LOCK), encoding="utf-8")

    lock = load_external_skills_lock(path)

    assert lock.bundle == "code-review-pipeline"
