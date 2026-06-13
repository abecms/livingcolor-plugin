from __future__ import annotations

import pytest


def test_normalize_vcs_provider_defaults_to_gitlab():
    from lc_server.integrations.vcs.provider import normalize_vcs_provider

    assert normalize_vcs_provider(None) == "gitlab"
    assert normalize_vcs_provider("") == "gitlab"


def test_normalize_vcs_provider_accepts_github():
    from lc_server.integrations.vcs.provider import normalize_vcs_provider

    assert normalize_vcs_provider(" github ") == "github"


def test_normalize_vcs_provider_rejects_unknown():
    from lc_server.integrations.vcs.provider import normalize_vcs_provider

    with pytest.raises(ValueError, match="Unsupported VCS provider"):
        normalize_vcs_provider("bitbucket")
