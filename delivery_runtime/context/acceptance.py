"""Acceptance criteria extraction from Jira ticket text."""

from __future__ import annotations

import re


def extract_acceptance_criteria(description: str, *, summary: str = "") -> list[str]:
    text = (description or "").strip()
    if not text and summary:
        return [summary.strip()] if summary.strip() else []

    criteria: list[str] = []

    ac_block = re.search(
        r"(?is)(acceptance criteria|crit[eè]res d['']acceptation)\s*:?\s*(.+?)(?:\n\s*\n|\Z)",
        text,
    )
    if ac_block:
        block = ac_block.group(2).strip()
        for line in block.splitlines():
            cleaned = re.sub(r"^[\-*\d.]+\s*", "", line.strip())
            if cleaned:
                criteria.append(cleaned)

    for match in re.finditer(r"(?im)^\s*(?:given|when|then)\s+.+$", text):
        criteria.append(match.group(0).strip())

    if not criteria:
        sentences = [part.strip() for part in re.split(r"[.\n]", text) if len(part.strip()) >= 20]
        criteria.extend(sentences[:3])

    if not criteria and summary.strip():
        criteria.append(summary.strip())

    seen: set[str] = set()
    unique: list[str] = []
    for item in criteria:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[:8]
