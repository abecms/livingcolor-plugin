"""Direct GitHub publication for cloud/heuristic delivery runs."""

from __future__ import annotations

import json
import logging
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from delivery_runtime.shadow.context import allow_internal_git
from lc_server.agent_bridge.hermes_publisher import PublisherCompletionError

logger = logging.getLogger(__name__)

_GITHUB_API_URL = "https://api.github.com"


def create_github_pull_request(
    *,
    token: str,
    repo_path: str,
    title: str,
    body: str,
    head_branch: str,
    base_branch: str,
) -> dict[str, Any]:
    """Create a GitHub pull request via REST API."""
    repo = repo_path.strip().removeprefix("github.com/").strip("/")
    payload = json.dumps(
        {
            "title": title,
            "body": body,
            "head": head_branch,
            "base": base_branch,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{_GITHUB_API_URL}/repos/{repo}/pulls",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise PublisherCompletionError(f"GitHub PR creation failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise PublisherCompletionError(f"GitHub PR creation failed: {exc.reason}") from exc

    if not isinstance(result, dict):
        raise PublisherCompletionError("GitHub API returned an unexpected pull request payload")
    return result


def push_delivery_branch(workspace: Path, *, delivery_branch: str) -> None:
    """Push the delivery branch to origin."""
    with allow_internal_git():
        checkout = subprocess.run(
            ["git", "checkout", delivery_branch],
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
        )
        if checkout.returncode != 0:
            detail = (checkout.stderr or checkout.stdout or "").strip()
            raise PublisherCompletionError(f"Could not checkout {delivery_branch}: {detail}")

        push = subprocess.run(
            ["git", "push", "-u", "origin", delivery_branch],
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
        )
        if push.returncode != 0:
            detail = (push.stderr or push.stdout or "").strip()
            raise PublisherCompletionError(f"git push failed for {delivery_branch}: {detail}")
