"""Tests for Hermes messaging helpers."""

from __future__ import annotations

import json
import sys
from types import ModuleType
from unittest.mock import patch

from lc_server.integrations import hermes_messaging


def test_send_to_home_channel_uses_send_message_tool():
    captured: dict[str, str] = {}

    def fake_send_message_tool(args, **kwargs):
        captured.update(args)
        return json.dumps({"success": True})

    tool_module = ModuleType("tools.send_message_tool")
    tool_module.send_message_tool = fake_send_message_tool
    tools_module = ModuleType("tools")
    tools_module.send_message_tool = tool_module

    with patch.dict(sys.modules, {"tools": tools_module, "tools.send_message_tool": tool_module}):
        with patch("lc_server.env_loader.prepare_delivery_agent_environment", lambda: None):
            result = hermes_messaging.send_to_home_channel(
                message="Hello sprint team",
                platform="slack",
            )

    assert result["success"] is True
    assert captured["action"] == "send"
    assert captured["target"] == "slack"
    assert captured["message"] == "Hello sprint team"
