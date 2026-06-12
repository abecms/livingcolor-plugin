from pathlib import Path


def test_home_is_under_hermes_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    import importlib
    import lc_constants
    importlib.reload(lc_constants)
    assert lc_constants.get_livingcolor_home() == tmp_path / "livingcolor"


def test_default_home_is_dot_hermes(monkeypatch):
    monkeypatch.delenv("HERMES_HOME", raising=False)
    import importlib
    import lc_constants
    importlib.reload(lc_constants)
    assert lc_constants.get_livingcolor_home() == Path.home() / ".hermes" / "livingcolor"


def test_ensure_layout_creates_dirs(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    import importlib
    import lc_constants
    importlib.reload(lc_constants)
    home = lc_constants.ensure_livingcolor_home_layout()
    for sub in ("config", "cache", "logs", "delivery", "work_orders"):
        assert (home / sub).is_dir()
