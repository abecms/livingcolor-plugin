"""Bundled inference credentials for downloadable LivingColor builds."""

from __future__ import annotations

import os
from pathlib import Path


def _upsert_env_value(env_path: Path, key: str, value: str) -> None:
    lines: list[str] = []
    replaced = False
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        current_key, _, _ = stripped.partition("=")
        if current_key.strip() == key:
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)

    if not replaced:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={value}")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    try:
        env_path.chmod(0o600)
    except OSError:
        pass


def ensure_bundled_openrouter_credentials() -> bool:
    """Persist OPENROUTER_API_KEY from the process environment into ~/.livingcolor/.env."""
    from lc_server.env_loader import get_livingcolor_env_path, load_livingcolor_dotenv

    load_livingcolor_dotenv(override=True)
    api_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        return False

    env_path = get_livingcolor_env_path()
    existing = ""
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                continue
            current_key, _, current_val = stripped.partition("=")
            if current_key.strip() == "OPENROUTER_API_KEY":
                existing = current_val.strip().strip("'\"")
                break

    if existing == api_key:
        return True

    _upsert_env_value(env_path, "OPENROUTER_API_KEY", api_key)
    os.environ["OPENROUTER_API_KEY"] = api_key
    return True
