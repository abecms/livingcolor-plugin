from __future__ import annotations

from delivery_runtime.automation.local_projects import (
    list_local_projects,
    register_local_project,
    remove_local_project,
)


def test_remove_local_project_after_share(tmp_path, monkeypatch):
    from delivery_runtime.automation import config as automation_config
    from delivery_runtime.persistence import paths as persistence_paths
    import lc_constants

    home = tmp_path / "livingcolor"
    monkeypatch.setattr(automation_config, "get_livingcolor_home", lambda: home)
    monkeypatch.setattr(persistence_paths, "get_livingcolor_home", lambda: home)
    monkeypatch.setattr(lc_constants, "get_livingcolor_home", lambda: home)

    register_local_project("BN", "Bibliothèque Numérique")
    register_local_project("TV5", "TV5 Monde")

    remove_local_project("BN")

    keys = {row["jiraProjectKey"] for row in list_local_projects()}
    assert keys == {"TV5"}
