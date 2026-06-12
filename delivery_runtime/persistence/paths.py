"""Filesystem paths for Delivery Runtime persistence."""

from __future__ import annotations

from pathlib import Path

from lc_constants import ensure_livingcolor_home_layout, get_livingcolor_home


def get_delivery_root() -> Path:
    """Return the delivery runtime data directory under LivingColor home."""
    ensure_livingcolor_home_layout()
    return get_livingcolor_home() / "delivery"


def get_delivery_db_path() -> Path:
    """Return the SQLite database path for delivery state."""
    ensure_livingcolor_home_layout()
    return get_livingcolor_home() / "runtime.db"


def get_project_mapping_path() -> Path:
    """Return the Jira project → repository mapping file path."""
    ensure_livingcolor_home_layout()
    return get_livingcolor_home() / "project_mapping.yaml"


def get_work_orders_root() -> Path:
    """Return the work-order artifacts directory under LivingColor home."""
    ensure_livingcolor_home_layout()
    return get_livingcolor_home() / "work_orders"
