"""Direct GitHub publication for cloud/heuristic delivery runs."""

from __future__ import annotations

import json
import logging
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from delivery_runtime.shadow.context import allow_internal_git
from lc_server.agent_bridge.hermes_publisher import PublisherCompletionError

logger = logging.getLogger(__name__)

_GITHUB_API_URL = "https://api.github.com"


def find_existing_github_pull_request(
    *,
    token: str,
    repo_path: str,
    head_branch: str,
    base_branch: str | None = None,
) -> dict[str, Any] | None:
    """Return an open pull request for ``head_branch`` when one already exists."""
    repo = repo_path.strip().removeprefix("github.com/").strip("/")
    owner, _, name = repo.partition("/")
    if not owner or not name:
        return None
    query = urllib.parse.urlencode(
        {
            "head": f"{owner}:{head_branch}",
            "state": "open",
            **({"base": base_branch} if base_branch else {}),
        }
    )
    request = urllib.request.Request(
        f"{_GITHUB_API_URL}/repos/{repo}/pulls?{query}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            items = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError):
        return None
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    return first if isinstance(first, dict) else None


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
        if exc.code == 422:
            existing = find_existing_github_pull_request(
                token=token,
                repo_path=repo_path,
                head_branch=head_branch,
                base_branch=base_branch,
            )
            if existing:
                logger.info(
                    "Reusing existing GitHub PR #%s for %s",
                    existing.get("number"),
                    head_branch,
                )
                return existing
        raise PublisherCompletionError(f"GitHub PR creation failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise PublisherCompletionError(f"GitHub PR creation failed: {exc.reason}") from exc

    if not isinstance(result, dict):
        raise PublisherCompletionError("GitHub API returned an unexpected pull request payload")
    return result


def push_delivery_branch(workspace: Path, *, delivery_branch: str) -> None:
    """Push the delivery branch to origin, reconciling with an existing remote branch."""
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

        fetch = subprocess.run(
            ["git", "fetch", "origin", delivery_branch],
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
        )
        if fetch.returncode == 0:
            remote_ref = f"origin/{delivery_branch}"
            has_remote = subprocess.run(
                ["git", "rev-parse", "--verify", remote_ref],
                cwd=workspace,
                check=False,
                capture_output=True,
                text=True,
            ).returncode == 0
            if has_remote:
                pull = subprocess.run(
                    ["git", "pull", "--rebase", "origin", delivery_branch],
                    cwd=workspace,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if pull.returncode != 0:
                    detail = (pull.stderr or pull.stdout or "").strip()
                    raise PublisherCompletionError(
                        f"Could not reconcile local {delivery_branch} with origin: {detail}"
                    )

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
