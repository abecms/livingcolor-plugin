"""Resolve repository hints from human clarification feedback."""

from __future__ import annotations

import re


def parse_resolved_repo_from_feedback(feedback: str) -> str | None:
    text = feedback.strip()
    if not text:
        return None

    explicit = re.search(
        r"(?i)(?:repo|repository)\s*[:=]\s*([^\s,;]+)",
        text,
    )
    if explicit:
        return explicit.group(1).strip()

    if re.match(r"^[\w.-]+/[\w.-]+/[\w.-]+$", text):
        return text

    return None
