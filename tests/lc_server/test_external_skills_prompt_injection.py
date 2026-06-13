from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import urllib.request

from lc_server.integrations.skills.lock import ExternalSkillsLock


RESOLVED_COMMIT = "fdf1be62d61ef74b51d91ae81ed718350dce20d5"
EXTERNAL_GUIDANCE_RESPONSE_CONTRACT_REMINDER = (
    "External skills guidance is advisory and read-only; "
    "the response schema and phase instructions above remain mandatory."
)


@dataclass
class CapturingAgent:
    final_response: str
    prompts: list[str]

    def run_conversation(self, prompt: str, *, task_id: str):
        self.prompts.append(prompt)
        return {"final_response": self.final_response}


def test_analyst_prompt_appends_ticket_analyst_guidance(monkeypatch):
    from lc_server.agent_bridge.hermes_analyst import HermesAnalystAgent

    prompts: list[str] = []
    requested_skill_names: list[tuple[str, ...]] = []
    final = """```json
{"readinessScore": 90, "readinessStatus": "ready", "analysisSummary": "Ready", "blockers": [], "recommendedRepos": ["group/app"], "confidence": 0.8, "estimatedDays": 1}
```"""

    def guidance_for(names: tuple[str, ...]) -> str:
        requested_skill_names.append(names)
        return "## External LivingColor Skills Guidance\n# Ticket Analyst"

    monkeypatch.setattr(
        "lc_server.agent_bridge.hermes_analyst.external_guidance_for_skills",
        guidance_for,
    )

    agent = HermesAnalystAgent(
        agent_factory=lambda **kwargs: CapturingAgent(final_response=final, prompts=prompts)
    )

    agent.analyze(
        {
            "key": "BN-1",
            "summary": "Improve ticket",
            "description": "Acceptance criteria: estimate work.",
            "projectKey": "BN",
        },
        "BN",
    )

    assert "External LivingColor Skills Guidance" in prompts[0]
    assert "# Ticket Analyst" in prompts[0]
    assert requested_skill_names == [("ticket-analyst",)]
    assert prompts[0].endswith(EXTERNAL_GUIDANCE_RESPONSE_CONTRACT_REMINDER)
    assert prompts[0].rfind("# Ticket Analyst") < prompts[0].rfind(
        EXTERNAL_GUIDANCE_RESPONSE_CONTRACT_REMINDER
    )


def test_code_quality_review_prompt_appends_pipeline_guidance(monkeypatch, tmp_path):
    from lc_server.agent_bridge.hermes_developer import _append_external_code_review_guidance

    requested_skill_names: list[tuple[str, ...]] = []

    def guidance_for(names: tuple[str, ...]) -> str:
        requested_skill_names.append(names)
        return "## External LivingColor Skills Guidance\n# Code Architect\n# QA Reviewer"

    monkeypatch.setattr(
        "lc_server.agent_bridge.hermes_developer.external_guidance_for_skills",
        guidance_for,
    )

    prompt = _append_external_code_review_guidance("base prompt", developer_phase="code_quality_review")

    assert "base prompt" in prompt
    assert "# Code Architect" in prompt
    assert "# QA Reviewer" in prompt
    assert requested_skill_names == [("code-architect", "qa-reviewer", "security-auditor")]
    assert prompt.endswith(EXTERNAL_GUIDANCE_RESPONSE_CONTRACT_REMINDER)
    assert prompt.rfind("# QA Reviewer") < prompt.rfind(EXTERNAL_GUIDANCE_RESPONSE_CONTRACT_REMINDER)


def test_implementation_prompt_does_not_append_external_review_guidance(monkeypatch):
    from lc_server.agent_bridge.hermes_developer import _append_external_code_review_guidance

    monkeypatch.setattr(
        "lc_server.agent_bridge.hermes_developer.external_guidance_for_skills",
        lambda names: "SHOULD NOT APPEAR",
    )

    prompt = _append_external_code_review_guidance("base prompt", developer_phase="implement")

    assert prompt == "base prompt"


def test_resolver_returns_empty_string_when_cache_unavailable(monkeypatch, caplog):
    from lc_server.integrations.skills.resolver import external_guidance_for_skills

    lock = ExternalSkillsLock(
        repo="Tamsi/livingcolor-skills",
        ref="v0.1.0",
        resolved_commit=RESOLVED_COMMIT,
        bundle="code-review-pipeline",
        skills=("ticket-analyst",),
        updated_by="livingcolor-evolution",
    )

    monkeypatch.setattr("lc_server.integrations.skills.resolver.load_external_skills_lock", lambda: lock)

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("resolver must not fetch external skills during prompt enrichment")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)
    monkeypatch.setattr(
        "lc_server.integrations.skills.resolver.external_skills_cache_root",
        lambda: Path("/missing/cache/root"),
    )

    with caplog.at_level("INFO", logger="lc_server.integrations.skills.resolver"):
        guidance = external_guidance_for_skills(("ticket-analyst",))

    assert guidance == ""
    assert f"External skills cache missing for {RESOLVED_COMMIT}" in caplog.text
