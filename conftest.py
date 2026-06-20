import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tests"))


if "hermes_cli" not in sys.modules:
    hermes_cli = ModuleType("hermes_cli")
    hermes_cli.__path__ = []  # Allow tests to register hermes_cli.* shims.
    sys.modules["hermes_cli"] = hermes_cli
else:
    hermes_cli = sys.modules["hermes_cli"]


if "hermes_cli.mcp_config" not in sys.modules:
    mcp_config = ModuleType("hermes_cli.mcp_config")
    mcp_config._get_mcp_servers = lambda: {}
    mcp_config._save_mcp_server = lambda _name, _config: True
    mcp_config._oauth_tokens_present = lambda _name: False
    mcp_config._probe_single_server = lambda _name, _config: {"status": "missing"}
    sys.modules["hermes_cli.mcp_config"] = mcp_config
    hermes_cli.mcp_config = mcp_config


if "hermes_cli.config" not in sys.modules:
    config = ModuleType("hermes_cli.config")
    config.reload_env = lambda: None
    config.load_config = lambda: {}
    sys.modules["hermes_cli.config"] = config
    hermes_cli.config = config


if "hermes_cli.mcp_runtime" not in sys.modules:
    mcp_runtime = ModuleType("hermes_cli.mcp_runtime")
    mcp_runtime.connect_mcp_server = lambda _name, _config: None
    sys.modules["hermes_cli.mcp_runtime"] = mcp_runtime
    hermes_cli.mcp_runtime = mcp_runtime


@pytest.fixture(scope="session", autouse=True)
def _global_hermes_home_guard(tmp_path_factory):
    """Hard guard: no test may ever touch the real ~/.hermes data.

    Tests that called init_db() without requesting an isolation fixture used
    to write fixture work orders into the real runtime.db. Point HERMES_HOME
    at a session temp dir for the whole run; per-test fixtures still override
    it with their own monkeypatched paths.
    """
    fake_home = tmp_path_factory.mktemp("hermes_session_home")
    previous = os.environ.get("HERMES_HOME")
    os.environ["HERMES_HOME"] = str(fake_home)
    yield fake_home
    if previous is None:
        os.environ.pop("HERMES_HOME", None)
    else:
        os.environ["HERMES_HOME"] = previous


@pytest.fixture()
def _isolate_hermes_home(tmp_path, monkeypatch):
    """Redirect HERMES_HOME so delivery_runtime tests never touch real data."""
    fake_hermes_home = tmp_path / "hermes_test"
    fake_hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(fake_hermes_home))
    monkeypatch.setenv("TZ", "UTC")
    monkeypatch.setenv("LANG", "C.UTF-8")
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    return fake_hermes_home
