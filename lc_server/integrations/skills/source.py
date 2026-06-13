"""Download source archives for pinned external skills."""

from __future__ import annotations

import urllib.request
from typing import Protocol


class SkillsArchiveSource(Protocol):
    def fetch_archive(self, *, repo: str, ref: str, resolved_commit: str) -> bytes:
        ...


class GitHubArchiveSkillsSource:
    """Fetch public GitHub repository archives without embedding credentials."""

    def fetch_archive(self, *, repo: str, ref: str, resolved_commit: str) -> bytes:
        del ref
        url = f"https://github.com/{repo}/archive/{resolved_commit}.zip"
        request = urllib.request.Request(url, headers={"User-Agent": "livingcolor-plugin"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
