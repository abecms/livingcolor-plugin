"""Tests for delivery agent inference resolution."""

from __future__ import annotations

import pytest


def test_developer_default_model_is_deepseek():
    from lc_server.model_defaults import LIVINGCOLOR_DEVELOPER_MODEL

    assert LIVINGCOLOR_DEVELOPER_MODEL == "deepseek/deepseek-v4-pro"


def test_developer_inference_uses_role_defaults_without_env_override(monkeypatch, tmp_path):
    from lc_server.agent_bridge.inference_config import resolve_delivery_inference
    from lc_server.model_defaults import (
        LIVINGCOLOR_DEVELOPER_MODEL,
        LIVINGCOLOR_DEVELOPER_PROVIDER,
    )

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    (tmp_path / "hermes").mkdir()
    (tmp_path / "hermes" / "config.yaml").write_text(
        "model:\n  provider: openrouter\n  default: deepseek/deepseek-v4-pro\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_INFERENCE_MODEL", "deepseek/deepseek-v4-pro")
    monkeypatch.setenv("HERMES_INFERENCE_PROVIDER", "openrouter")

    model, provider = resolve_delivery_inference(
        manifest=None,
        role_default_model=LIVINGCOLOR_DEVELOPER_MODEL,
        role_default_provider=LIVINGCOLOR_DEVELOPER_PROVIDER,
        allow_env_override=False,
    )

    assert model == LIVINGCOLOR_DEVELOPER_MODEL
    assert model == "deepseek/deepseek-v4-pro"
    assert provider == "openrouter"


def test_developer_inference_honors_env_override(monkeypatch, tmp_path):
    from lc_server.agent_bridge.inference_config import resolve_delivery_inference
    from lc_server.model_defaults import (
        LIVINGCOLOR_DEVELOPER_MODEL,
        LIVINGCOLOR_DEVELOPER_PROVIDER,
    )

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
        role_default_model=LIVINGCOLOR_DEVELOPER_MODEL,
        role_default_provider=LIVINGCOLOR_DEVELOPER_PROVIDER,
        allow_env_override=True,
    )

    assert model == "anthropic/claude-sonnet-4.6"
    assert provider == "openrouter"


def test_developer_inference_prefers_manifest_model(monkeypatch, tmp_path):
    from delivery_runtime.agents.schema import AgentIdentity, AgentManifest, AgentMcpConfig, AgentPrompt, AgentRuntime
    from lc_server.agent_bridge.inference_config import resolve_delivery_inference
    from lc_server.model_defaults import (
        LIVINGCOLOR_DEVELOPER_MODEL,
        LIVINGCOLOR_DEVELOPER_PROVIDER,
    )

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    (tmp_path / "hermes").mkdir()
    (tmp_path / "hermes" / "config.yaml").write_text(
        "model:\n  provider: openrouter\n  default: deepseek/deepseek-v4-pro\n",
        encoding="utf-8",
    )

    manifest = AgentManifest(
        role="developer",
        template_version="1.1.0",
        template_checksum="sha256:test",
        manually_edited=False,
        runtime=AgentRuntime(
            type="hermes",
            max_iterations=60,
            toolsets=("file", "terminal", "skills"),
            model="anthropic/claude-sonnet-4.6",
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
        role_default_model=LIVINGCOLOR_DEVELOPER_MODEL,
        role_default_provider=LIVINGCOLOR_DEVELOPER_PROVIDER,
        allow_env_override=False,
    )

    assert model == "anthropic/claude-sonnet-4.6"
    assert provider == "openrouter"
