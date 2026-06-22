#!/usr/bin/env python3
"""Write LivingColor cloud credentials to ~/.hermes/livingcolor/.env from stdin.

The Cloud Agent prompt may contain credential values, but Cursor does not inject
prompt text into os.environ. The agent must run this script first, then source
scripts/cloud-load-credentials.sh before cloud-bootstrap.

Input: one KEY=VALUE per line (blank lines and # comments ignored).
Never logs secret values.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ALLOWED_KEYS = frozenset(
    {
        "OPENROUTER_API_KEY",
        "JIRA_URL",
        "JIRA_USERNAME",
        "JIRA_API_TOKEN",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "STRIPE_SECRET_KEY",
        "STRIPE_TEST_CUSTOMER_ID",
        "STRIPE_DAILY_RATE_CENTS",
        "GITLAB_PERSONAL_ACCESS_TOKEN",
        "GITLAB_API_URL",
        "LIVINGCOLOR_TEST_PROJECT_KEY",
        "LIVINGCOLOR_TEST_GITHUB_REPO",
    }
)

_KEY_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


def _livingcolor_env_path() -> Path:
    return Path.home() / ".hermes" / "livingcolor" / ".env"


def parse_lines(lines: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _KEY_RE.match(line)
        if not match:
            raise ValueError(f"invalid credential line (expected KEY=VALUE): {line[:40]}")
        key, value = match.group(1), match.group(2).strip()
        if key not in ALLOWED_KEYS:
            raise ValueError(f"unsupported credential key: {key}")
        if not value:
            continue
        parsed[key] = value
    return parsed


def merge_env_file(path: Path, values: dict[str, str]) -> list[str]:
    existing: dict[str, str] = {}
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            match = _KEY_RE.match(line)
            if match:
                existing[match.group(1)] = match.group(2).strip()

    existing.update(values)
    written_keys = sorted(values.keys())
    lines = [f"{key}={existing[key]}" for key in sorted(existing)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return written_keys


def export_to_environ(values: dict[str, str]) -> None:
    for key, value in values.items():
        os.environ[key] = value
    if values.get("GH_TOKEN") and not values.get("GITHUB_TOKEN"):
        os.environ.setdefault("GITHUB_TOKEN", values["GH_TOKEN"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Write cloud credentials to Hermes livingcolor .env")
    parser.add_argument(
        "--export",
        action="store_true",
        help="Also set variables in the current process environment",
    )
    parser.add_argument(
        "--from-file",
        type=Path,
        help="Read KEY=VALUE lines from a file instead of stdin",
    )
    args = parser.parse_args()

    if args.from_file:
        lines = args.from_file.read_text(encoding="utf-8").splitlines()
    else:
        lines = sys.stdin.read().splitlines()

    try:
        values = parse_lines(lines)
    except ValueError as exc:
        print(f"[cloud-write-credentials] ERROR: {exc}", file=sys.stderr)
        return 1

    if not values:
        print("[cloud-write-credentials] ERROR: no credential lines provided", file=sys.stderr)
        return 1

    env_path = _livingcolor_env_path()
    written = merge_env_file(env_path, values)
    if args.export:
        merged = parse_lines(env_path.read_text(encoding="utf-8").splitlines())
        export_to_environ(merged)

    print(
        f"[cloud-write-credentials] wrote {len(written)} key(s) to {env_path}: "
        + ", ".join(written)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
