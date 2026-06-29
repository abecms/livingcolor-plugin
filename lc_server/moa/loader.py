from functools import lru_cache
from importlib.resources import files
from typing import Any
import yaml

_BUNDLE_VERSION = "1.1.0"


@lru_cache(maxsize=1)
def load_bundled_presets() -> dict[str, dict[str, Any]]:
    raw = files("lc_server.moa").joinpath("presets.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    presets = data.get("presets") or {}
    if not isinstance(presets, dict):
        raise ValueError("Invalid moa presets bundle")
    return presets


def bundled_preset_version() -> str:
    return _BUNDLE_VERSION
