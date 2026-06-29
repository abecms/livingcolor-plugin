from lc_server.moa.loader import load_bundled_presets, bundled_preset_version


def test_load_bundled_presets_contains_standard_and_premium():
    presets = load_bundled_presets()
    assert "lc-analyst" in presets
    assert "lc-developer-premium" in presets
    assert presets["lc-developer"]["aggregator"]["model"] == "anthropic/claude-opus-4.8"
    assert presets["lc-developer-premium"]["aggregator"]["model"] == "anthropic/claude-opus-4.8"
    assert bundled_preset_version() == "1.1.0"


def test_load_bundled_presets_contains_nemotron_tier():
    presets = load_bundled_presets()
    assert "lc-analyst-nemotron" in presets
    assert "lc-planner-nemotron" in presets
    assert "lc-developer-nemotron" not in presets
    assert presets["lc-planner-nemotron"]["aggregator"]["provider"] == "nvidia"
    assert presets["lc-planner-nemotron"]["aggregator"]["model"] == "nvidia/nemotron-3-ultra-550b-a55b"
