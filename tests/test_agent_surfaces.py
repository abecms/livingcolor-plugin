"""Agent surfaces: /delivery slash command and livingcolor model tools."""
import json


class FakeCtx:
    def __init__(self):
        self.commands = {}
        self.tools = {}

    def register_command(self, name, handler, description="", args_hint=""):
        self.commands[name] = handler

    def register_tool(self, name, toolset, schema, handler, **kwargs):
        self.tools[name] = handler


def _registered(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from test_plugin_load import _load_plugin_module

    mod = _load_plugin_module()
    ctx = FakeCtx()
    mod.register(ctx)
    return ctx


def test_registers_delivery_command_and_tools(monkeypatch, tmp_path):
    ctx = _registered(monkeypatch, tmp_path)
    assert "delivery" in ctx.commands
    for tool in (
        "delivery_overview",
        "delivery_scan_readiness",
        "delivery_promote",
        "delivery_gate_decision",
        "delivery_work_order_status",
    ):
        assert tool in ctx.tools


def test_delivery_status_returns_text(monkeypatch, tmp_path):
    ctx = _registered(monkeypatch, tmp_path)
    out = ctx.commands["delivery"]("status")
    assert isinstance(out, str) and out


def test_overview_tool_returns_json(monkeypatch, tmp_path):
    ctx = _registered(monkeypatch, tmp_path)
    payload = json.loads(ctx.tools["delivery_overview"]({}))
    assert "workOrders" in payload or "readiness" in payload or payload
