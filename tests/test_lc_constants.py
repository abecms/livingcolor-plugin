from pathlib import Path


def test_livingcolor_home_ignores_profile_scoped_hermes_home(monkeypatch, tmp_path):
    profile_home = tmp_path / ".hermes" / "profiles" / "livingcolor-pm"
    profile_home.mkdir(parents=True)
    root_livingcolor = tmp_path / ".hermes" / "livingcolor"
    root_livingcolor.mkdir(parents=True)

    monkeypatch.setenv("HERMES_HOME", str(profile_home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    import importlib
    import lc_constants

    importlib.reload(lc_constants)

    assert lc_constants.get_livingcolor_home() == root_livingcolor


def test_livingcolor_home_honors_explicit_override(monkeypatch, tmp_path):
    override = tmp_path / "custom-livingcolor"
    override.mkdir()
    monkeypatch.setenv("LIVINGCOLOR_HOME", str(override))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    import importlib
    import lc_constants

    importlib.reload(lc_constants)
    assert lc_constants.get_livingcolor_home() == override


def test_default_home_is_dot_hermes(monkeypatch):
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("LIVINGCOLOR_HOME", raising=False)
    import importlib
    import lc_constants

    importlib.reload(lc_constants)
    assert lc_constants.get_livingcolor_home() == Path.home() / ".hermes" / "livingcolor"


def test_ensure_layout_creates_dirs(monkeypatch, tmp_path):
    livingcolor_home = tmp_path / ".hermes" / "livingcolor"
    monkeypatch.setenv("LIVINGCOLOR_HOME", str(livingcolor_home))
    import importlib
    import lc_constants

    importlib.reload(lc_constants)
    home = lc_constants.ensure_livingcolor_home_layout()
    for sub in ("config", "cache", "logs", "delivery", "work_orders"):
        assert (home / sub).is_dir()
