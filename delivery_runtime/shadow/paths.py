"""Shadow evaluation workspace paths."""

from __future__ import annotations

from pathlib import Path

from delivery_runtime.persistence.paths import get_work_orders_root
from delivery_runtime.shadow.mode import is_shadow_mode
from lc_constants import ensure_livingcolor_home_layout, get_livingcolor_home


def get_evaluation_root() -> Path:
    ensure_livingcolor_home_layout()
    root = get_livingcolor_home() / "evaluation"
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_work_order_artifact_root(work_order_id: str) -> Path:
    if is_shadow_mode():
        return get_evaluation_root() / work_order_id
    return get_work_orders_root() / work_order_id
