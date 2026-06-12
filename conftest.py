import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tests"))


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
