import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tests"))


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
