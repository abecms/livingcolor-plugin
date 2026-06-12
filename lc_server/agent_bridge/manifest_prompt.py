"""Manifest prompt helpers for the Hermes agent bridge."""

from __future__ import annotations

from delivery_runtime.agents.schema import AgentManifest


def render_manifest_system_prompt(manifest: AgentManifest) -> str:
    """Render the effective system prompt for a provisioned agent manifest."""
    return manifest.render_system_prompt()
