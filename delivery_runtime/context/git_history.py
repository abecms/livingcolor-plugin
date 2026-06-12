"""Relevant git history for candidate files."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def collect_git_history(
    checkout_path: str | None,
    candidate_files: list[str],
    *,
    max_entries: int = 5,
) -> list[dict[str, Any]]:
    if not checkout_path or not candidate_files:
        return []

    root = Path(checkout_path)
    git_dir = root / ".git"
    if not git_dir.exists():
        return []

    history: list[dict[str, Any]] = []
    for rel_path in candidate_files[:3]:
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "log",
                    "-n",
                    str(max_entries),
                    "--pretty=format:%h|%an|%s",
                    "--",
                    rel_path,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode != 0 or not result.stdout.strip():
            continue
        for line in result.stdout.splitlines():
            parts = line.split("|", 2)
            if len(parts) != 3:
                continue
            history.append(
                {
                    "file": rel_path,
                    "sha": parts[0],
                    "author": parts[1],
                    "subject": parts[2],
                }
            )
    return history[:max_entries]
