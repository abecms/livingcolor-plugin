"""Dedicated Hermes profile for LivingColor project dashboard chat."""

from __future__ import annotations

import logging
import shutil
import stat
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

LIVINGCOLOR_PM_PROFILE_NAME = "livingcolor-pm"
LIVINGCOLOR_PLUGIN_NAME = "livingcolor"
LIVINGCOLOR_PM_TOOLSETS = "livingcolor"
NO_BUNDLED_SKILLS_MARKER = ".no-bundled-skills"

_PROFILE_SUBDIRS = (
    "memories",
    "sessions",
    "skills",
    "skins",
    "logs",
    "plans",
    "workspace",
    "cron",
    "home",
)


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _bundled_pm_skill_dir() -> Path:
    return _plugin_root() / "skills" / "productivity" / "livingcolor-pm"


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home())
    except Exception:
        return Path.home() / ".hermes"


def _root_hermes_plugins_dir() -> Path:
    """Global plugin install dir (not profile-scoped ``HERMES_HOME``)."""
    return default_hermes_root() / "plugins"


def default_hermes_root() -> Path:
    from lc_server.integrations.mcp_config_bridge import default_hermes_root as _root

    return _root()


def _ensure_profile_plugin_link(profile_dir: Path) -> None:
    """Link the LivingColor plugin into the profile so TUI discovery finds it.

    Profile-scoped PTY children set ``HERMES_HOME`` to ``profiles/livingcolor-pm``.
    Hermes only scans ``$HERMES_HOME/plugins`` for user plugins, so without this
    symlink the ``livingcolor`` toolset registers zero tools in project chat.
    """
    source = _root_hermes_plugins_dir() / LIVINGCOLOR_PLUGIN_NAME
    if not source.is_dir():
        logger.warning("LivingColor plugin missing at %s; profile chat tools unavailable", source)
        return

    target_dir = profile_dir / "plugins"
    target_dir.mkdir(parents=True, exist_ok=True)
    link = target_dir / LIVINGCOLOR_PLUGIN_NAME

    if link.is_symlink():
        try:
            if link.resolve() == source.resolve():
                return
        except OSError:
            pass
        link.unlink()
    elif link.exists():
        return

    link.symlink_to(source, target_is_directory=True)
    logger.info("Linked LivingColor plugin into profile at %s", link)


def livingcolor_pm_profile_dir() -> Path:
    return _hermes_home() / "profiles" / LIVINGCOLOR_PM_PROFILE_NAME


def livingcolor_pm_profile_exists() -> bool:
    return livingcolor_pm_profile_dir().is_dir()


def _profile_config_template() -> dict[str, Any]:
    return {
        "display": {
            "tui_auto_resume_recent": False,
        },
        "agent": {
            "system_prompt": (
                "You are the LivingColor delivery PM assistant embedded in the project dashboard. "
                "Help with sprint planning, ticket estimation, readiness, and approvals for the active Jira project. "
                "You are not a Kanban worker and not a cron job."
            ),
        },
        "plugins": {
            "enabled": [LIVINGCOLOR_PLUGIN_NAME],
        },
        "platform_toolsets": {
            "cli": [LIVINGCOLOR_PM_TOOLSETS],
            "tui": [LIVINGCOLOR_PM_TOOLSETS],
        },
    }


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _sync_root_mcp_servers_into_profile(profile_dir: Path) -> None:
    """Copy root MCP server definitions into the PM profile config."""
    from lc_server.integrations.mcp_config_bridge import default_hermes_root

    root_mcp = _load_yaml(default_hermes_root() / "config.yaml").get("mcp_servers")
    if not isinstance(root_mcp, dict) or not root_mcp:
        return

    config_path = profile_dir / "config.yaml"
    current = _load_yaml(config_path)
    profile_mcp = current.get("mcp_servers")
    if not isinstance(profile_mcp, dict):
        profile_mcp = {}

    merged = {**root_mcp, **profile_mcp}
    if merged == current.get("mcp_servers"):
        return

    current["mcp_servers"] = merged
    config_path.write_text(yaml.safe_dump(current, sort_keys=False), encoding="utf-8")


def _ensure_profile_mcp_tokens_link(profile_dir: Path) -> None:
    """Share OAuth token files from the default Hermes home with the PM profile."""
    from lc_server.integrations.mcp_config_bridge import default_hermes_root

    root_tokens = default_hermes_root() / "mcp-tokens"
    if not root_tokens.is_dir():
        return

    link = profile_dir / "mcp-tokens"
    if link.is_symlink():
        try:
            if link.resolve() == root_tokens.resolve():
                return
        except OSError:
            pass
        link.unlink()
    elif link.exists():
        if link.is_dir() and any(link.iterdir()):
            return
        if link.is_dir():
            link.rmdir()
        else:
            link.unlink()

    link.symlink_to(root_tokens, target_is_directory=True)


def _merge_profile_config(profile_dir: Path) -> None:
    config_path = profile_dir / "config.yaml"
    current = _load_yaml(config_path)
    template = _profile_config_template()

    display = dict(current.get("display") or {})
    display["tui_auto_resume_recent"] = False
    current["display"] = display

    agent = dict(current.get("agent") or {})
    if not str(agent.get("system_prompt") or "").strip():
        agent["system_prompt"] = template["agent"]["system_prompt"]
    current["agent"] = agent

    plugins = dict(current.get("plugins") or {})
    enabled = list(plugins.get("enabled") or [])
    if LIVINGCOLOR_PLUGIN_NAME not in enabled:
        enabled.append(LIVINGCOLOR_PLUGIN_NAME)
    plugins["enabled"] = enabled
    current["plugins"] = plugins

    platform_toolsets = dict(current.get("platform_toolsets") or {})
    for platform in ("cli", "tui"):
        existing = list(platform_toolsets.get(platform) or [])
        if LIVINGCOLOR_PM_TOOLSETS not in existing:
            existing.append(LIVINGCOLOR_PM_TOOLSETS)
        platform_toolsets[platform] = existing
    current["platform_toolsets"] = platform_toolsets

    model = current.get("model")
    if not isinstance(model, dict) or not str(model.get("default") or "").strip():
        default_config = _load_yaml(_hermes_home() / "config.yaml").get("model")
        if isinstance(default_config, dict) and str(default_config.get("default") or "").strip():
            current["model"] = dict(default_config)

    config_path.write_text(yaml.safe_dump(current, sort_keys=False), encoding="utf-8")


def _seed_pm_skill(profile_dir: Path) -> None:
    source = _bundled_pm_skill_dir()
    if not source.is_dir():
        logger.warning("livingcolor-pm skill bundle missing at %s", source)
        return
    target = profile_dir / "skills" / "productivity" / "livingcolor-pm"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def _seed_default_credentials(profile_dir: Path) -> None:
    """Copy default profile credentials once so chat works out of the box."""
    target_env = profile_dir / ".env"
    if target_env.exists():
        return

    source_env = _hermes_home() / ".env"
    if not source_env.is_file():
        return

    shutil.copy2(source_env, target_env)
    try:
        target_env.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _ensure_profile_env_defaults(profile_dir: Path) -> None:
    """Persist PM chat defaults in the profile .env for the TUI gateway child."""
    env_path = profile_dir / ".env"
    lines: list[str] = []
    if env_path.is_file():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    desired = {
        "HERMES_TUI_TOOLSETS": LIVINGCOLOR_PM_TOOLSETS,
        "HERMES_IGNORE_RULES": "1",
    }
    present = {line.split("=", 1)[0].strip() for line in lines if "=" in line}
    changed = False
    for key, value in desired.items():
        if key not in present:
            lines.append(f"{key}={value}")
            changed = True

    if changed:
        env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        try:
            env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


def _bootstrap_profile_tree(profile_dir: Path) -> bool:
    created = not profile_dir.is_dir()
    profile_dir.mkdir(parents=True, exist_ok=True)
    for subdir in _PROFILE_SUBDIRS:
        (profile_dir / subdir).mkdir(parents=True, exist_ok=True)
    (profile_dir / NO_BUNDLED_SKILLS_MARKER).touch(exist_ok=True)
    return created


def ensure_livingcolor_pm_profile() -> Path:
    """Create or repair the isolated Hermes profile used by project dashboard chat."""
    profile_dir = livingcolor_pm_profile_dir()
    created = _bootstrap_profile_tree(profile_dir)
    _seed_default_credentials(profile_dir)
    _ensure_profile_env_defaults(profile_dir)
    _ensure_profile_plugin_link(profile_dir)
    _merge_profile_config(profile_dir)
    _sync_root_mcp_servers_into_profile(profile_dir)
    _ensure_profile_mcp_tokens_link(profile_dir)
    _seed_pm_skill(profile_dir)

    if created:
        logger.info("Bootstrapped Hermes profile %s at %s", LIVINGCOLOR_PM_PROFILE_NAME, profile_dir)
    return profile_dir


def livingcolor_pm_state_db_path() -> Path:
    return livingcolor_pm_profile_dir() / "state.db"
