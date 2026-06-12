"""Repository resolver tests."""

from __future__ import annotations

from unittest.mock import patch

from delivery_runtime.context.repo_resolver import resolve_repository


def test_resolve_repository_uses_managed_checkout_when_mapping_has_list_repos(_isolate_hermes_home):
    mapping = {
        "TVP": {
            "default_repo": "tv5monde/tv5mondeplus-front",
            "repos": [
                {"path": "tv5monde/tv5mondeplus-front", "gitlabId": 20},
            ],
            "integrations": {
                "mcp_servers": {
                    "gitlab": {
                        "env": {
                            "GITLAB_API_URL": "https://gitlab.example.com/api/v4",
                            "GITLAB_PERSONAL_ACCESS_TOKEN": "token",
                        }
                    }
                }
            },
        }
    }
    managed_path = "/Users/me/.livingcolor/TVP/tv5monde/tv5mondeplus-front"

    with patch("delivery_runtime.context.repo_resolver.load_project_mapping", return_value=mapping), patch(
        "delivery_runtime.context.repo_resolver.ensure_managed_checkout",
        return_value=managed_path,
    ) as ensure_mock:
        resolved = resolve_repository(
            project_key="TVP",
            snapshot={"projectKey": "TVP", "labels": []},
            recommended_repos=["tv5monde/tv5mondeplus-front"],
        )

    assert resolved is not None
    assert resolved.checkout_path == managed_path
    ensure_mock.assert_called_once()
