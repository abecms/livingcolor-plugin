"""Tests for delivery agent inference resolution."""

from __future__ import annotations


def test_role_defaults_use_moa_presets():
    from lc_server.model_defaults import (
        LIVINGCOLOR_ANALYST_MODEL,
        LIVINGCOLOR_ANALYST_PROVIDER,
        LIVINGCOLOR_DEVELOPER_MODEL,
        LIVINGCOLOR_DEVELOPER_PROVIDER,
        LIVINGCOLOR_PLANNER_MODEL,
        LIVINGCOLOR_PLANNER_PROVIDER,
        LIVINGCOLOR_PUBLISHER_MODEL,
        LIVINGCOLOR_PUBLISHER_PROVIDER,
        LIVINGCOLOR_REPORTER_MODEL,
        LIVINGCOLOR_REPORTER_PROVIDER,
    )

    assert LIVINGCOLOR_ANALYST_PROVIDER == "moa"
    assert LIVINGCOLOR_PLANNER_PROVIDER == "moa"
    assert LIVINGCOLOR_DEVELOPER_PROVIDER == "moa"
    assert LIVINGCOLOR_ANALYST_MODEL == "lc-analyst-nemotron"
    assert LIVINGCOLOR_PLANNER_MODEL == "lc-planner-nemotron"
    assert LIVINGCOLOR_DEVELOPER_MODEL == "lc-developer"
    assert LIVINGCOLOR_REPORTER_PROVIDER == "openrouter"
    assert LIVINGCOLOR_REPORTER_MODEL == "openrouter/owl-alpha"
    assert LIVINGCOLOR_PUBLISHER_PROVIDER == "openrouter"
    assert LIVINGCOLOR_PUBLISHER_MODEL == "deepseek/deepseek-v4-pro"


def test_moa_tier_standard(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_MOA_TIER", "standard")
    from importlib import reload

    import lc_server.model_defaults as md

    reload(md)
    assert md.LIVINGCOLOR_ANALYST_MODEL == "lc-analyst"
    assert md.LIVINGCOLOR_PLANNER_MODEL == "lc-planner"
    assert md.LIVINGCOLOR_DEVELOPER_MODEL == "lc-developer"

    monkeypatch.delenv("LIVINGCOLOR_MOA_TIER", raising=False)
    reload(md)


def test_moa_tier_premium(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_MOA_TIER", "premium")
    from importlib import reload

    import lc_server.model_defaults as md

    reload(md)
    assert md.LIVINGCOLOR_DEVELOPER_MODEL == "lc-developer-premium"
    assert md.LIVINGCOLOR_DEVELOPER_PROVIDER == "moa"

    monkeypatch.delenv("LIVINGCOLOR_MOA_TIER", raising=False)
    reload(md)


def test_moa_tier_nemotron(monkeypatch):
    monkeypatch.setenv("LIVINGCOLOR_MOA_TIER", "nemotron")
    from importlib import reload

    import lc_server.model_defaults as md

    reload(md)
    assert md.LIVINGCOLOR_ANALYST_MODEL == "lc-analyst-nemotron"
    assert md.LIVINGCOLOR_PLANNER_MODEL == "lc-planner-nemotron"
    assert md.LIVINGCOLOR_DEVELOPER_MODEL == "lc-developer"

    monkeypatch.delenv("LIVINGCOLOR_MOA_TIER", raising=False)
    reload(md)


def test_resolve_moa_tier_model_maps_provisioned_manifests(monkeypatch):
    from lc_server.agent_bridge.inference_config import resolve_moa_tier_model

    monkeypatch.delenv("LIVINGCOLOR_MOA_TIER", raising=False)
    assert resolve_moa_tier_model("lc-analyst", role="analyst") == "lc-analyst-nemotron"
    assert resolve_moa_tier_model("lc-planner", role="planner") == "lc-planner-nemotron"
    assert resolve_moa_tier_model("lc-developer", role="developer") == "lc-developer"
    assert resolve_moa_tier_model("z-ai/glm-5.2", role="developer") == "z-ai/glm-5.2"

    monkeypatch.setenv("LIVINGCOLOR_MOA_TIER", "standard")
    assert resolve_moa_tier_model("lc-analyst", role="analyst") == "lc-analyst"


def test_developer_inference_uses_role_defaults_without_env_override(monkeypatch, tmp_path):
    from lc_server.agent_bridge.inference_config import resolve_delivery_inference

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    (tmp_path / "hermes").mkdir()
    (tmp_path / "hermes" / "config.yaml").write_text(
        "model:\n  provider: openrouter\n  default: anthropic/claude-sonnet-4.6\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_INFERENCE_MODEL", "anthropic/claude-sonnet-4.6")
    monkeypatch.setenv("HERMES_INFERENCE_PROVIDER", "openrouter")

    model, provider = resolve_delivery_inference(
        manifest=None,
        role_default_model="deepseek/deepseek-v4-pro",
        role_default_provider="openrouter",
        allow_env_override=False,
    )

    assert model == "deepseek/deepseek-v4-pro"
    assert provider == "openrouter"


def test_planner_inference_uses_owl_role_defaults(monkeypatch, tmp_path):
    from lc_server.agent_bridge.inference_config import resolve_delivery_inference
    from lc_server.model_defaults import LIVINGCOLOR_PLANNER_MODEL, LIVINGCOLOR_PLANNER_PROVIDER

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    (tmp_path / "hermes").mkdir()
    (tmp_path / "hermes" / "config.yaml").write_text(
        "model:\n  provider: openrouter\n  default: deepseek/deepseek-v4-pro\n",
        encoding="utf-8",
    )

    model, provider = resolve_delivery_inference(
        manifest=None,
        role_default_model=LIVINGCOLOR_PLANNER_MODEL,
        role_default_provider=LIVINGCOLOR_PLANNER_PROVIDER,
        allow_env_override=False,
    )

    assert model == "lc-planner-nemotron"
    assert provider == "moa"


def test_developer_inference_honors_env_override(monkeypatch, tmp_path):
    from lc_server.agent_bridge.inference_config import resolve_delivery_inference

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    (tmp_path / "hermes").mkdir()
    (tmp_path / "hermes" / "config.yaml").write_text(
        "model:\n  provider: openrouter\n  default: deepseek/deepseek-v4-pro\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_INFERENCE_MODEL", "anthropic/claude-sonnet-4.6")
    monkeypatch.setenv("HERMES_INFERENCE_PROVIDER", "openrouter")

    model, provider = resolve_delivery_inference(
        manifest=None,
        role_default_model="deepseek/deepseek-v4-pro",
        role_default_provider="openrouter",
        allow_env_override=True,
    )

    assert model == "anthropic/claude-sonnet-4.6"
    assert provider == "openrouter"


def test_developer_inference_prefers_manifest_model(monkeypatch, tmp_path):
    from delivery_runtime.agents.schema import AgentIdentity, AgentManifest, AgentMcpConfig, AgentPrompt, AgentRuntime
    from lc_server.agent_bridge.inference_config import resolve_delivery_inference

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    (tmp_path / "hermes").mkdir()
    (tmp_path / "hermes" / "config.yaml").write_text(
        "model:\n  provider: openrouter\n  default: deepseek/deepseek-v4-pro\n",
        encoding="utf-8",
    )

    manifest = AgentManifest(
        role="developer",
        template_version="1.7.0",
        template_checksum="sha256:test",
        manually_edited=False,
        runtime=AgentRuntime(
            type="hermes",
            max_iterations=60,
            toolsets=("file", "terminal", "skills"),
            model="z-ai/glm-5.2",
            provider="openrouter",
        ),
        identity=AgentIdentity(display_name="Developer Agent", platform="livingcolor-delivery"),
        prompt=AgentPrompt(system="test"),
        skills=(),
        mcp=AgentMcpConfig(inherit="project"),
        context={},
    )

    model, provider = resolve_delivery_inference(
        manifest=manifest,
        role_default_model="deepseek/deepseek-v4-pro",
        role_default_provider="openrouter",
        allow_env_override=False,
    )

    assert model == "z-ai/glm-5.2"
    assert provider == "openrouter"


def test_moa_fallback_when_preset_disabled(monkeypatch, tmp_path):
    from lc_server.agent_bridge.inference_config import resolve_moa_or_fallback

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    (tmp_path / "hermes").mkdir()
    (tmp_path / "hermes" / "config.yaml").write_text(
        "moa:\n  presets:\n    lc-analyst:\n      enabled: false\n",
        encoding="utf-8",
    )

    model, provider = resolve_moa_or_fallback(
        "lc-analyst",
        "moa",
        fallback_model="openrouter/owl-alpha",
        fallback_provider="openrouter",
    )

    assert model == "openrouter/owl-alpha"
    assert provider == "openrouter"


def test_moa_fallback_passthrough_when_not_moa():
    from lc_server.agent_bridge.inference_config import resolve_moa_or_fallback

    model, provider = resolve_moa_or_fallback(
        "deepseek/deepseek-v4-pro",
        "openrouter",
        fallback_model="openrouter/owl-alpha",
        fallback_provider="openrouter",
    )

    assert model == "deepseek/deepseek-v4-pro"
    assert provider == "openrouter"
