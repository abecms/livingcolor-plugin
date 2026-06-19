"""Tests for LivingColor product storage paths."""

import sqlite3
from pathlib import Path

from delivery_runtime.persistence.paths import (
    get_delivery_db_path,
    get_delivery_root,
    get_project_mapping_path,
    get_work_orders_root,
)
from lc_constants import get_livingcolor_home


def test_livingcolor_home_layout(_isolate_hermes_home, monkeypatch):
    hermes_home = _isolate_hermes_home
    livingcolor_home = hermes_home / "livingcolor"
    livingcolor_home.mkdir(parents=True)
    monkeypatch.setenv("LIVINGCOLOR_HOME", str(livingcolor_home))

    assert get_livingcolor_home() == livingcolor_home
    assert get_delivery_db_path() == livingcolor_home / "runtime.db"
    assert get_project_mapping_path() == livingcolor_home / "project_mapping.yaml"
    assert get_delivery_root() == livingcolor_home / "delivery"
    assert get_work_orders_root() == livingcolor_home / "work_orders"

    for relative in ("config", "cache", "logs", "delivery", "work_orders"):
        assert (livingcolor_home / relative).is_dir()


def test_legacy_hermes_delivery_db_is_migrated(monkeypatch, tmp_path):
    hermes_home = tmp_path / "hermes"
    livingcolor_home = hermes_home / "livingcolor"
    monkeypatch.setenv("LIVINGCOLOR_HOME", str(livingcolor_home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    legacy_db = tmp_path / ".hermes" / "delivery" / "delivery.db"
    legacy_db.parent.mkdir(parents=True)
    conn = sqlite3.connect(legacy_db)
    conn.execute("CREATE TABLE legacy_marker (id INTEGER)")
    conn.commit()
    conn.close()

    from delivery_runtime.persistence.db import init_db

    migrated = init_db()
    assert migrated == livingcolor_home / "runtime.db"
    assert migrated.exists()
    with sqlite3.connect(migrated) as migrated_conn:
        tables = {
            row[0]
            for row in migrated_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "legacy_marker" in tables
    assert "readiness_records" in tables
