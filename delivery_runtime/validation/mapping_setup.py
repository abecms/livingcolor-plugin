"""Install Phase 2.5 project mapping fixtures for delivery runtime tests."""

from __future__ import annotations

import shutil
from pathlib import Path

from delivery_runtime.persistence.paths import get_project_mapping_path

_FIXTURE_MAPPING = (
    Path(__file__).resolve().parents[2] / "tests" / "delivery_runtime" / "fixtures" / "project_mapping_phase25.yaml"
)
_FIXTURES_ROOT = _FIXTURE_MAPPING.parent


def install_phase25_project_mapping() -> Path:
    """Copy the Phase 2.5 fixture mapping into LivingColor home."""
    target = get_project_mapping_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = _FIXTURE_MAPPING.read_text(encoding="utf-8")
    rendered = raw.replace("{fixtures_root}", str(_FIXTURES_ROOT.resolve()))
    target.write_text(rendered, encoding="utf-8")
    return target
