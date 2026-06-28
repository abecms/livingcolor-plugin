"""Provision LivingColor MoA presets from the bundled preset definitions.

Idempotent merge into ``~/.hermes/config.yaml``: creates missing managed presets,
upgrades when the bundled ``livingcolor.presetVersion`` is newer, and never
downgrades or modifies user/custom presets.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from lc_server.integrations.mcp_config_bridge import default_hermes_root

logger = logging.getLogger(__name__)


def _parse_version(s: str) -> tuple[int, ...]:
    parts = (s or "0.0.0").strip().split(".")
    return tuple(int(part) for part in parts)


def _preset_version_tuple(preset: dict[str, Any]) -> tuple[int, ...]:
    lc = preset.get("livingcolor")
    if isinstance(lc, dict):
        version = lc.get("presetVersion")
        if version:
            return _parse_version(str(version))
    return _parse_version("0.0.0")


def _should_upgrade(existing: dict[str, Any], bundled: dict[str, Any]) -> bool:
    local = _preset_version_tuple(existing)
    bundled_ver = _preset_version_tuple(bundled)
    return bundled_ver > local


def _merge_presets_into_config(data: dict[str, Any], bundled: dict[str, dict[str, Any]]) -> list[str]:
    moa = data.get("moa")
    if not isinstance(moa, dict):
        moa = {}
        data["moa"] = moa

    presets = moa.get("presets")
    if not isinstance(presets, dict):
        presets = {}
        moa["presets"] = presets

    changed: list[str] = []

    for name, bundled_preset in bundled.items():
        if not isinstance(bundled_preset, dict):
            continue
        lc = bundled_preset.get("livingcolor")
        if not isinstance(lc, dict) or not lc.get("managed"):
            continue

        existing = presets.get(name)
        if existing is None:
            presets[name] = copy.deepcopy(bundled_preset)
            changed.append(name)
            logger.info("Created MoA preset %s from bundle", name)
        elif isinstance(existing, dict) and _should_upgrade(existing, bundled_preset):
            presets[name] = copy.deepcopy(bundled_preset)
            changed.append(name)
            logger.info("Upgraded MoA preset %s from bundle", name)
        else:
            logger.debug("Skipped MoA preset %s (local version current)", name)

    return changed


def ensure_moa_presets_from_bundle() -> list[str]:
    """Merge bundled LivingColor MoA presets into the Hermes root config.

    Returns preset names that were created or upgraded.
    """
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML unavailable; cannot bootstrap MoA presets from bundle")
        return []

    from lc_server.moa.loader import load_bundled_presets

    bundled = load_bundled_presets()
    cfg_path = default_hermes_root() / "config.yaml"

    data: dict[str, Any] = {}
    if cfg_path.is_file():
        loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded

    changed = _merge_presets_into_config(data, bundled)
    if changed:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    return changed
