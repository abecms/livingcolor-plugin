from __future__ import annotations

from lc_server.integrations.local_project_share import build_local_project_share_payload


def test_build_local_project_share_payload_exports_mapping_and_settings(tmp_path, monkeypatch):
    from delivery_runtime.automation import config as automation_config
    from delivery_runtime.persistence import paths as persistence_paths
    import lc_constants

    home = tmp_path / "livingcolor"
    monkeypatch.setattr(automation_config, "get_livingcolor_home", lambda: home)
    monkeypatch.setattr(persistence_paths, "get_livingcolor_home", lambda: home)
    monkeypatch.setattr(lc_constants, "get_livingcolor_home", lambda: home)

    config_dir = home / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "delivery.yaml").write_text(
        """
project:
  key: BN
  name: Bibliothèque Numérique
sprint:
  duration_days: 21
  capacity_days: 12.5
communication:
  language: en
""".strip(),
        encoding="utf-8",
    )
    (home / "project_mapping.yaml").write_text(
        """
BN:
  name: Bibliothèque Numérique
  default_repo: gitlab.com/client/bibnum
  repos:
    gitlab.com/client/bibnum:
      checkout_path: /tmp/bibnum
""".strip(),
        encoding="utf-8",
    )

    payload = build_local_project_share_payload("BN")
    assert payload["jiraProjectKey"] == "BN"
    assert payload["projectName"] == "Bibliothèque Numérique"
    assert payload["mapping"]["default_repo"] == "gitlab.com/client/bibnum"
    assert payload["deliverySettings"]["sprintDurationDays"] == 21
    assert payload["deliverySettings"]["communicationLanguage"] == "en"
