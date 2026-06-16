"""Post messages through Hermes configured messaging platforms (Slack, etc.)."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_MESSAGING_PLATFORM_PRIORITY = ("slack", "discord", "telegram", "mattermost", "matrix")


def resolve_messaging_target() -> str | None:
    """Return a send_message target for the first enabled platform with a home channel."""
    try:
        from gateway.config import Platform, load_gateway_config

        config = load_gateway_config()
    except Exception as exc:
        logger.warning("Could not load Hermes gateway config for messaging: %s", exc)
        return None

    for name in _MESSAGING_PLATFORM_PRIORITY:
        try:
            platform = Platform(name)
        except (ValueError, KeyError):
            continue
        pconfig = config.platforms.get(platform)
        if not pconfig or not pconfig.enabled:
            continue
        if config.get_home_channel(platform):
            return name
    return None


def send_to_home_channel(*, message: str, platform: str | None = None) -> dict[str, Any]:
    """Deliver ``message`` to the Hermes home channel for ``platform`` (or auto-detected)."""
    from lc_server.env_loader import prepare_delivery_agent_environment

    prepare_delivery_agent_environment()

    target = (platform or resolve_messaging_target() or "").strip().lower()
    if not target:
        return {
            "success": False,
            "error": "No enabled messaging platform with a home channel found in Hermes.",
        }

    body = (message or "").strip()
    if not body:
        return {"success": False, "error": "Message body is empty."}

    try:
        from tools.send_message_tool import send_message_tool
    except ImportError as exc:
        return {
            "success": False,
            "error": f"Hermes send_message tool is unavailable: {exc}",
        }

    raw = send_message_tool({"action": "send", "target": target, "message": body})
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        payload = {"error": str(raw)}

    if isinstance(payload, dict) and payload.get("error"):
        return {"success": False, "error": str(payload["error"]), "platform": target}

    success = bool((payload or {}).get("success", True)) if isinstance(payload, dict) else True
    return {"success": success, "platform": target, "result": payload}
