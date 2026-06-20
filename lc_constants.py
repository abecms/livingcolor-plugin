"""LivingColor plugin paths and constants.

Import-safe module with no Hermes dependencies. Single source of truth for
the plugin's data home: ``~/.hermes/livingcolor/`` (follows ``HERMES_HOME``).

Function names intentionally mirror agent-lc's ``livingcolor_constants`` so
ported modules only need their import rewritten.
"""
from __future__ import annotations

import os
from pathlib import Path


def _hermes_home() -> Path:
    override = os.environ.get("HERMES_HOME", "").strip()
    return Path(override) if override else Path.home() / ".hermes"


def _default_hermes_root() -> Path:
    try:
        from hermes_constants import get_default_hermes_root

        return Path(get_default_hermes_root())
    except ImportError:
        return Path.home() / ".hermes"


def get_livingcolor_home() -> Path:
    """Return the plugin data home (default: ~/.hermes/livingcolor).

    Delivery state is shared across Hermes profiles. Project dashboard chat runs
    under an isolated profile (``profiles/livingcolor-pm``) but must read the
    same ``project_mapping.yaml``, SQLite DB, and config as the gateway.
    """
    override = os.environ.get("LIVINGCOLOR_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    return _default_hermes_root() / "livingcolor"


def ensure_livingcolor_home_layout() -> Path:
    """Create the standard data home layout if missing."""
    home = get_livingcolor_home()
    for relative in ("config", "cache", "logs", "delivery", "work_orders"):
        (home / relative).mkdir(parents=True, exist_ok=True)
    return home


def display_livingcolor_home() -> str:
    """User-facing path string for logs and UI copy."""
    home = get_livingcolor_home()
    try:
        return "~/" + str(home.relative_to(Path.home()))
    except ValueError:
        return str(home)


def readonly_skill_roots() -> list[Path]:
    """Roots where Hermes/LivingColor skill files may be loaded read-only."""
    hermes_home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser().resolve()
    roots = [hermes_home / "skills", get_livingcolor_home().resolve() / "skills"]
    bundled: Path | None = None
    try:
        from hermes_constants import get_bundled_delivery_skills_dir

        bundled = Path(get_bundled_delivery_skills_dir())
    except (ImportError, AttributeError, TypeError, ValueError, OSError):
        try:
            from hermes_constants import get_bundled_skills_dir

            bundled = Path(get_bundled_skills_dir())
        except (ImportError, AttributeError, TypeError, ValueError, OSError):
            bundled = None
    if bundled is not None and bundled.is_dir():
        roots.append(bundled.resolve())
    return roots
