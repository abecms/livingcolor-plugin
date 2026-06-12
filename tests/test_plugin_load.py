"""The plugin module must import and expose register(ctx)."""
import importlib.util
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _load_plugin_module():
    spec = importlib.util.spec_from_file_location(
        "hermes_plugins.livingcolor",
        PLUGIN_ROOT / "__init__.py",
        submodule_search_locations=[str(PLUGIN_ROOT)],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_plugins.livingcolor"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_plugin_exposes_register():
    mod = _load_plugin_module()
    assert callable(getattr(mod, "register", None))
