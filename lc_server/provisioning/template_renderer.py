"""Render versioned agent manifest templates with variable substitution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from delivery_runtime.agents.paths import VALID_ROLES

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "agent_templates" / "v1"
_MANIFEST_PATH = _TEMPLATES_DIR / "manifest.json"
_SUBSTITUTION_VARS = frozenset({"project_key", "project_name", "language", "default_repo"})


def _load_template_manifest() -> dict[str, Any]:
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def get_template_version() -> str:
    """Return the embedded agent template bundle version."""
    template_manifest = _load_template_manifest()
    template_version = str(template_manifest.get("version") or "").strip()
    if not template_version:
        raise ValueError("Embedded template manifest is missing version")
    return template_version


def _load_role_template(role: str) -> str:
    path = _TEMPLATES_DIR / f"{role}.yaml.tmpl"
    if not path.is_file():
        raise FileNotFoundError(f"Agent template not found: {path}")
    return path.read_text(encoding="utf-8")


def _substitute(template: str, variables: dict[str, str]) -> str:
    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{{ {key} }}}}", value)
    return rendered


def _compute_checksum(rendered_without_checksum: str) -> str:
    digest = hashlib.sha256(rendered_without_checksum.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def render_role_template(role: str, variables: dict[str, str]) -> str:
    normalized_role = (role or "").strip().lower()
    if normalized_role not in VALID_ROLES:
        raise ValueError(f"Invalid agent role: {role!r}")

    missing = sorted(_SUBSTITUTION_VARS - set(variables))
    if missing:
        raise ValueError(f"Missing template variables: {', '.join(missing)}")

    template_version = get_template_version()

    template = _load_role_template(normalized_role)
    render_vars = {
        "template_version": template_version,
        "template_checksum": "",
        **{key: str(variables[key]) for key in _SUBSTITUTION_VARS},
    }
    rendered_without_checksum = _substitute(template, render_vars)
    checksum = _compute_checksum(rendered_without_checksum)
    render_vars["template_checksum"] = checksum
    return _substitute(template, render_vars)
