"""Tests for Jira attachment extraction."""

from __future__ import annotations


def test_extract_text_attachment(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "lc_constants.get_livingcolor_home",
        lambda: tmp_path,
    )

    def fake_preview(issue_key, *, attachment_id="", name=""):
        assert issue_key == "TVP-1489"
        return b"Expected: live title visible\nActual: blank page", "text/plain"

    monkeypatch.setattr(
        "hermes_cli.jira_dashboard.fetch_jira_attachment_preview",
        fake_preview,
    )

    from lc_server.integrations.jira_attachment_extract import extract_jira_attachment_context

    extracts = extract_jira_attachment_context(
        "TVP-1489",
        [{"id": "1", "name": "repro.txt", "mimeType": "text/plain"}],
    )

    assert extracts[0]["extractKind"] == "text"
    assert "Expected: live title visible" in extracts[0]["content"]


def test_enrich_snapshot_is_idempotent():
    snapshot = {
        "key": "TVP-1489",
        "attachments": [{"id": "1", "name": "shot.png", "mimeType": "image/png"}],
        "attachmentExtracts": [{"name": "shot.png", "extractKind": "image_description", "content": "done"}],
    }

    from lc_server.integrations.jira_attachment_extract import enrich_snapshot_with_attachment_extracts

    enriched = enrich_snapshot_with_attachment_extracts(snapshot)
    assert enriched["attachmentExtracts"][0]["content"] == "done"


def test_enrich_snapshot_retries_after_failed_extracts(monkeypatch, tmp_path):
    monkeypatch.setattr("lc_constants.get_livingcolor_home", lambda: tmp_path)
    monkeypatch.setattr(
        "hermes_cli.jira_dashboard.fetch_jira_attachment_preview",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(Exception("mcp failed")),
    )
    monkeypatch.setattr(
        "lc_server.integrations.jira_attachment_extract._download_attachment_via_jira_api",
        lambda _url: b"- Slide 1: Rendering issue",
    )

    from lc_server.integrations.jira_attachment_extract import enrich_snapshot_with_attachment_extracts

    snapshot = {
        "key": "TVP-1489",
        "attachments": [
            {
                "name": "notes.txt",
                "mimeType": "text/plain",
                "url": "https://example.test/content/1",
            }
        ],
        "attachmentExtracts": [{"name": "notes.txt", "extractKind": "error", "content": "", "error": "old"}],
    }
    enriched = enrich_snapshot_with_attachment_extracts(snapshot)
    assert "Rendering issue" in enriched["attachmentExtracts"][0]["content"]


def test_merge_attachment_context_into_pack_enriches_developer_context(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "lc_constants.get_livingcolor_home",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "hermes_cli.jira_dashboard.fetch_jira_attachment_preview",
        lambda *_args, **_kwargs: (b"bug screenshot details", "text/plain"),
    )

    from lc_server.integrations.jira_attachment_extract import merge_attachment_context_into_pack

    pack = merge_attachment_context_into_pack(
        {"jira_ticket": {"key": "TVP-1489", "summary": "Live page"}},
        {
            "key": "TVP-1489",
            "description": "See attachment",
            "attachments": [{"id": "9", "name": "notes.txt", "mimeType": "text/plain"}],
        },
    )

    assert pack["jira_attachment_extracts"][0]["content"] == "bug screenshot details"
    assert pack["jira_ticket"]["description"] == "See attachment"


def test_build_attachment_prompt_section_renders_extracts():
    from delivery_runtime.readiness.attachment_prompt import build_attachment_prompt_section

    section = build_attachment_prompt_section(
        [
            {
                "name": "capture.png",
                "mimeType": "image/png",
                "extractKind": "image_description",
                "content": "Player shows offline banner on live page.",
            }
        ]
    )

    assert "Jira attachments" in section
    assert "Player shows offline banner" in section


def test_analyst_prompt_includes_attachment_section():
    from delivery_runtime.readiness.analyst_prompt import build_analyst_user_prompt

    prompt = build_analyst_user_prompt(
        {
            "key": "TVP-1489",
            "projectKey": "TVP",
            "summary": "Live direct name",
            "description": "See screenshot",
            "attachments": [{"name": "capture.png", "mimeType": "image/png"}],
            "attachmentExtracts": [
                {
                    "name": "capture.png",
                    "extractKind": "image_description",
                    "content": "Title missing on live player.",
                }
            ],
        }
    )

    assert "Title missing on live player" in prompt


def test_developer_prompt_includes_jira_description_and_attachments():
    from delivery_runtime.development.prompt_context import build_developer_user_prompt

    prompt = build_developer_user_prompt(
        work_order_id="WO-49",
        jira_key="TVP-1489",
        approved_plan={"implementationPlan": "Fix title rendering", "likelyImpactedFiles": ["assets/js/live.js"]},
        context_pack={
            "jira_ticket": {"summary": "Live direct name", "description": "See PJ"},
            "jira_attachment_extracts": [
                {
                    "name": "capture.png",
                    "extractKind": "image_description",
                    "content": "Expected title ABC, observed empty string.",
                }
            ],
        },
        reviewer_feedback=[],
        test_command=["npm", "test"],
    )

    assert "See PJ" in prompt
    assert "Expected title ABC" in prompt


def test_run_async_works_inside_running_event_loop():
    import asyncio

    from lc_server.integrations.jira_attachment_extract import _run_async

    async def work() -> str:
        return "vision-ok"

    async def outer() -> str:
        return _run_async(work())

    assert asyncio.run(outer()) == "vision-ok"
