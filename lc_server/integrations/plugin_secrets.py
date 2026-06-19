"""LivingColor plugin-level secrets persisted under ~/.hermes/livingcolor/.env."""

from __future__ import annotations

import os
import re
from pathlib import Path

_STRIPE_ENV_KEYS = ("STRIPE_SECRET_KEY", "STRIPE_API_KEY")
_ENV_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def _livingcolor_env_path() -> Path:
    from lc_constants import ensure_livingcolor_home_layout

    return ensure_livingcolor_home_layout() / ".env"


def _parse_env_lines(text: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ENV_LINE_RE.match(stripped)
        if not match:
            continue
        entries.append((match.group(1), match.group(2)))
    return entries


def _format_env_value(value: str) -> str:
    if not value:
        return '""'
    if any(char.isspace() for char in value) or any(char in value for char in '#"\\\''):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _render_env_lines(entries: list[tuple[str, str]], *, comments: list[str] | None = None) -> str:
    lines: list[str] = []
    if comments:
        lines.extend(comments)
        if comments and not comments[-1].endswith("\n"):
            lines.append("")
    for key, value in entries:
        lines.append(f"{key}={_format_env_value(value)}")
    return "\n".join(lines).rstrip() + "\n"


def _read_env_entries(path: Path) -> list[tuple[str, str]]:
    if not path.is_file():
        return []
    return _parse_env_lines(path.read_text(encoding="utf-8"))


def _upsert_env_entry(entries: list[tuple[str, str]], key: str, value: str | None) -> list[tuple[str, str]]:
    filtered = [(existing_key, existing_value) for existing_key, existing_value in entries if existing_key != key]
    if value:
        filtered.append((key, value))
    return filtered


def redact_secret(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "***"
    return f"{text[:7]}...{text[-4:]}"


def load_stripe_secret_key() -> str:
    for name in _STRIPE_ENV_KEYS:
        value = os.getenv(name, "").strip()
        if value:
            return value

    path = _livingcolor_env_path()
    for key, raw_value in _read_env_entries(path):
        if key not in _STRIPE_ENV_KEYS:
            continue
        value = raw_value.strip().strip('"').strip("'")
        if value:
            return value
    return ""


def stripe_secret_key_configured() -> bool:
    return bool(load_stripe_secret_key())


def persist_stripe_secret_key(value: str | None) -> None:
    """Write or clear STRIPE_SECRET_KEY in the LivingColor plugin .env file."""
    path = _livingcolor_env_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    entries = _read_env_entries(path)
    normalized = (value or "").strip() or None
    entries = _upsert_env_entry(entries, "STRIPE_SECRET_KEY", normalized)
    for legacy_key in _STRIPE_ENV_KEYS:
        if legacy_key != "STRIPE_SECRET_KEY":
            entries = _upsert_env_entry(entries, legacy_key, None)

    comments = [
        "# LivingColor plugin secrets",
        "# STRIPE_SECRET_KEY is used for sprint invoice creation.",
    ]
    if not path.exists() and not entries:
        path.write_text("\n".join(comments) + "\n", encoding="utf-8")
        return

    path.write_text(_render_env_lines(entries, comments=comments), encoding="utf-8")

    if normalized:
        os.environ["STRIPE_SECRET_KEY"] = normalized
    else:
        os.environ.pop("STRIPE_SECRET_KEY", None)
        os.environ.pop("STRIPE_API_KEY", None)
