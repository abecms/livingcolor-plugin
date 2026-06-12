"""Tests for Hermes-backed LivingColor Developer Agent."""

from __future__ import annotations

from pathlib import Path

import pytest

from delivery_runtime.persistence.paths import get_work_orders_root
from lc_server.agent_bridge.hermes_developer import HermesDeveloperAgent


class _FakeAgent:
    def __init__(self, workspace: Path):
        self.workspace = workspace

    def run_conversation(self, prompt: str, task_id: str | None = None) -> dict:
        target = self.workspace / "src/auth/oauth_callback.ts"
        target.parent.mkdir(parents=True, exist_ok=True)
        body = target.read_text(encoding="utf-8") if target.exists() else ""
        target.write_text(body + "\nexport function hermesDeliveryPatch() { return 'ok'; }\n", encoding="utf-8")
        return {
            "final_response": (
                "Implemented OAuth callback persistence.\n"
                "```json\n"
                '{"summary": "Persist OAuth tokens after callback.", "confidence": 0.84, "risks": []}\n'
                "```"
            ),
            "completed": True,
        }


def test_hermes_developer_agent_runs_against_workspace(_isolate_hermes_home, tmp_path: Path):
    checkout = tmp_path / "repo"
    checkout.mkdir()
    (checkout / "src" / "auth").mkdir(parents=True)
    (checkout / "src" / "auth" / "oauth_callback.ts").write_text(
        "export function handleCallback() {}\n",
        encoding="utf-8",
    )
    (checkout / "package.json").write_text('{"scripts":{"test":"node -e \\"process.exit(0)\\""}}', encoding="utf-8")

    def factory(**kwargs):
        workspace = get_work_orders_root() / kwargs["work_order_id"] / "workspace"
        return _FakeAgent(workspace)

    agent = HermesDeveloperAgent(agent_factory=factory)
    result = agent.execute(
        "WO-HERMES-1",
        {
            "workOrder": {"jiraKey": "AAC-99"},
            "approvedAnalysisPlan": {
                "targetRepo": "gitlab.com/org/app",
                "implementationPlan": "1. Persist OAuth tokens in src/auth/oauth_callback.ts",
                "likelyImpactedFiles": ["src/auth/oauth_callback.ts"],
            },
            "contextPack": {
                "identified_repo": "gitlab.com/org/app",
                "repo_checkout_path": str(checkout),
                "acceptance_criteria": ["Persist OAuth tokens after callback."],
            },
        },
    )

    assert result["backend"] == "hermes"
    assert result["deliveryBranch"] == "feature/AAC-99"
    assert "src/auth/oauth_callback.ts" in result["filesModified"] + result["filesCreated"]
    assert result["diffPreview"]
    assert result["testRun"]["passed"] is True
    assert result["confidence"] >= 0.8
    assert Path(result["patchArtifactPath"]).exists()


def test_hermes_developer_requires_checkout(_isolate_hermes_home):
    agent = HermesDeveloperAgent(agent_factory=lambda **kwargs: _FakeAgent(Path(".")))
    with pytest.raises(ValueError, match="checkout"):
        agent.execute(
            "WO-HERMES-2",
            {
                "approvedAnalysisPlan": {
                    "likelyImpactedFiles": ["src/main.py"],
                },
                "contextPack": {},
            },
        )
