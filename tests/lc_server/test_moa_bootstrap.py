import yaml

from lc_server.integrations.moa_bootstrap import ensure_moa_presets_from_bundle, _parse_version
from lc_server.moa.loader import load_bundled_presets


def test_parse_version():
    assert _parse_version("1.0.0") == (1, 0, 0)
    assert _parse_version("9.0.0") == (9, 0, 0)
    assert _parse_version("") == (0, 0, 0)


def test_bootstrap_creates_presets(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("model:\n  provider: openrouter\n", encoding="utf-8")
    monkeypatch.setattr(
        "lc_server.integrations.moa_bootstrap.default_hermes_root",
        lambda: tmp_path,
    )
    changed = ensure_moa_presets_from_bundle()
    bundled = load_bundled_presets()
    assert set(changed) == set(bundled)
    saved = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert saved["moa"]["presets"]["lc-analyst"]["livingcolor"]["managed"] is True
    assert saved["model"]["provider"] == "openrouter"


def test_bootstrap_skips_newer_local(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump({
            "moa": {
                "presets": {
                    "lc-analyst": {
                        "enabled": True,
                        "aggregator": {"provider": "openrouter", "model": "custom/model"},
                        "livingcolor": {"presetVersion": "9.0.0", "managed": True},
                    }
                }
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "lc_server.integrations.moa_bootstrap.default_hermes_root",
        lambda: tmp_path,
    )
    changed = ensure_moa_presets_from_bundle()
    assert "lc-analyst" not in changed
    saved = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert saved["moa"]["presets"]["lc-analyst"]["aggregator"]["model"] == "custom/model"


def test_bootstrap_upgrades_older(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump({
            "moa": {
                "presets": {
                    "lc-analyst": {
                        "enabled": True,
                        "aggregator": {"provider": "openrouter", "model": "custom/model"},
                        "livingcolor": {"presetVersion": "1.0.0", "managed": True},
                    }
                }
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "lc_server.integrations.moa_bootstrap.default_hermes_root",
        lambda: tmp_path,
    )
    changed = ensure_moa_presets_from_bundle()
    assert "lc-analyst" not in changed
    bundled = load_bundled_presets()
    missing = set(bundled) - {"lc-analyst"}
    assert missing.issubset(set(changed))
    saved = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert saved["moa"]["presets"]["lc-analyst"]["aggregator"]["model"] == "custom/model"
    for name in missing:
        assert name in saved["moa"]["presets"]


def test_bootstrap_never_touches_custom(tmp_path, monkeypatch):
    custom_preset = {
        "enabled": True,
        "aggregator": {"provider": "openrouter", "model": "user/custom-model"},
        "livingcolor": {"managed": False},
    }
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump({
            "moa": {
                "presets": {
                    "my-custom-preset": custom_preset,
                }
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "lc_server.integrations.moa_bootstrap.default_hermes_root",
        lambda: tmp_path,
    )
    ensure_moa_presets_from_bundle()
    saved = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert saved["moa"]["presets"]["my-custom-preset"] == custom_preset
