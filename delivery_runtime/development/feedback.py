"""Structured reviewer feedback parsing for development rework."""

from __future__ import annotations

import json
import re
from typing import Any


def parse_reviewer_feedback(raw: str | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [_normalize_item(item) for item in raw if _normalize_item(item)]

    text = raw.strip()
    if not text:
        return []

    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [item for item in (_normalize_item(entry) for entry in parsed) if item]
        except json.JSONDecodeError:
            pass

    items: list[dict[str, Any]] = []
    for line in text.splitlines():
        cleaned = line.strip(" -•\t")
        if not cleaned:
            continue
        typed = re.match(r"^(?P<type>[a-z_]+)\s*:\s*(?P<message>.+)$", cleaned, flags=re.IGNORECASE)
        if typed:
            items.append(
                {
                    "type": typed.group("type").lower(),
                    "message": typed.group("message").strip(),
                }
            )
            continue
        items.append({"type": "general", "message": cleaned})

    if not items:
        items.append({"type": "general", "message": text})
    return items


def _normalize_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    message = str(item.get("message") or "").strip()
    if not message:
        return {}
    return {
        "type": str(item.get("type") or "general").strip().lower(),
        "message": message,
    }
