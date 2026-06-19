"""LivingColor project context for embedded Hermes dashboard chat (PTY + TUI gateway).

The LivingColor plugin chat panel opens a PTY to ``hermes --tui``. Unlike the
agent-lc desktop app (which calls ``session.create`` with ``livingcolor_project_key``),
the stock Hermes stack has no project scope. These hooks:

1. Forward ``livingcolor_project_key`` from ``/api/pty`` into the child env.
2. Teach ``tui_gateway`` to read that env (or RPC param) when building sessions.
3. Inject a project-scoped system prompt and enable the ``livingcolor`` toolset.
"""

from __future__ import annotations

import contextvars
import logging
import os
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlparse

from lc_server.integrations.livingcolor_pm_profile import (
    LIVINGCOLOR_PM_PROFILE_NAME,
    LIVINGCOLOR_PM_TOOLSETS,
    ensure_livingcolor_pm_profile,
    livingcolor_pm_state_db_path,
)

logger = logging.getLogger(__name__)

_LC_HOOKS_INSTALLED = False
_LC_PTY_PROJECT_KEY: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "lc_pty_project_key",
    default=None,
)
_LC_CHANNEL_PROJECT_RE = re.compile(r"^lc-([A-Z][A-Z0-9]*)-", re.IGNORECASE)


def _project_key_from_channel(channel: str | None) -> str | None:
    if not channel:
        return None
    match = _LC_CHANNEL_PROJECT_RE.match(channel.strip())
    if not match:
        return None
    return normalize_livingcolor_project_key(match.group(1))


def _project_key_from_sidecar_url(sidecar_url: str | None) -> str | None:
    if not sidecar_url:
        return None
    try:
        query = parse_qs(urlparse(sidecar_url).query)
        channel = (query.get("channel") or [""])[0]
        return _project_key_from_channel(channel)
    except Exception:
        logger.debug("Could not parse LivingColor project key from sidecar URL", exc_info=True)
        return None


def _resolve_pty_project_key(*, sidecar_url: str | None = None) -> str | None:
    for candidate in (
        _LC_PTY_PROJECT_KEY.get(),
        _project_key_from_sidecar_url(sidecar_url),
    ):
        key = normalize_livingcolor_project_key(candidate)
        if key:
            return key
    return None


def _rebind_dashboard_pty_endpoint(handler) -> bool:
    """FastAPI binds the original ``pty_ws`` at import time — replace that route."""
    try:
        from starlette.routing import WebSocketRoute

        import hermes_cli.web_server as ws
    except ImportError:
        return False

    rebound = False
    for route in ws.app.routes:
        if isinstance(route, WebSocketRoute) and route.path == "/api/pty":
            route.endpoint = handler
            rebound = True
    return rebound


def normalize_livingcolor_project_key(value: str | None) -> str | None:
    key = str(value or "").strip().upper()
    return key or None


def resolve_livingcolor_project_cwd(project_key: str) -> str | None:
    """Return the mapped local repo for a Jira project, when configured."""
    key = normalize_livingcolor_project_key(project_key)
    if not key:
        return None
    try:
        from delivery_runtime.readiness.project_mapping import load_project_mapping

        mapping = load_project_mapping()
        project_cfg = mapping.get(key) or {}
        if not isinstance(project_cfg, dict):
            return None
        default_repo = str(project_cfg.get("default_repo") or "").strip()
        if not default_repo:
            return None
        resolved = os.path.abspath(os.path.expanduser(default_repo))
        if os.path.isdir(resolved):
            return resolved
    except Exception:
        logger.debug("Could not resolve LivingColor project cwd for %s", key, exc_info=True)
    return None


def livingcolor_project_chat_session_title(project_key: str) -> str:
    key = normalize_livingcolor_project_key(project_key) or ""
    return f"LivingColor {key}" if key else "LivingColor"


def livingcolor_project_system_prompt(project_key: str) -> str:
    key = normalize_livingcolor_project_key(project_key) or ""
    parts = [
        "[LIVINGCOLOR PROJECT CHAT]",
        f"You are the LivingColor PM assistant for Jira project {key}.",
        f"The ONLY active Jira project for this chat is {key}. Ignore BN or any other project mentioned in older messages unless the user explicitly switches project.",
        "You are NOT a Kanban worker, NOT a cron job, and NOT the TV5 Bibnum ticket resolver.",
        "Ignore kanban-worker, tv5monde-bibnum-tickets-resolver, and any prior cron instructions in history.",
        "Use the livingcolor tools for sprint, estimation, analysis, and approval actions.",
        "Do NOT call raw jira_* MCP tools for sprint or ticket lists — use livingcolor_get_delivery_context first.",
        "Primary tools: livingcolor_get_delivery_context, livingcolor_run_daily_analysis, "
        "livingcolor_update_sprint_selection, livingcolor_update_ticket_estimation, livingcolor_promote_ticket.",
        "Always scope actions to this project key unless the user explicitly names another project.",
        "This session is scoped to that delivery project — not the Hermes Agent source checkout.",
        "When the user asks which project they are on, answer with this Jira project key.",
        "Do not assume files from the Hermes or LivingColor plugin checkout are the user's product unless they attach them.",
    ]
    mapped = resolve_livingcolor_project_cwd(key)
    if mapped:
        parts.append(f"Mapped product repository for {key}: {mapped}.")
    return "\n".join(parts)


def _livingcolor_pm_inline_prompt() -> str | None:
    """Load livingcolor-pm instructions when the skill is installed."""
    try:
        from pathlib import Path

        from hermes_constants import get_bundled_skills_dir, get_hermes_home

        candidates = [
            get_bundled_skills_dir(Path(__file__).resolve().parents[2] / "skills")
            / "productivity"
            / "livingcolor-pm"
            / "SKILL.md",
            get_hermes_home() / "skills" / "productivity" / "livingcolor-pm" / "SKILL.md",
        ]
        for skill_md in candidates:
            if not skill_md.is_file():
                continue
            content = skill_md.read_text(encoding="utf-8")
            if content.startswith("---"):
                end = content.find("---", 3)
                if end != -1:
                    content = content[end + 3 :].lstrip("\n")
            stripped = content.strip()
            if stripped:
                return stripped
    except Exception:
        logger.debug("livingcolor-pm skill not available for project chat", exc_info=True)
    return None


def _compose_livingcolor_system_prompt(project_key: str) -> str:
    inline_pm = _livingcolor_pm_inline_prompt()
    parts = [livingcolor_project_system_prompt(project_key)]
    if inline_pm:
        parts.append(
            "[IMPORTANT: The user is in the LivingColor project dashboard chat. "
            "Treat the following PM assistant instructions as active guidance.]\n\n"
            f"{inline_pm}"
        )
    return "\n\n".join(parts).strip()


def _resolve_project_key(params: dict[str, Any] | None = None) -> str | None:
    params = params or {}
    return normalize_livingcolor_project_key(
        params.get("livingcolor_project_key") or os.environ.get("HERMES_TUI_LIVINGCOLOR_PROJECT_KEY")
    )


def _resolve_livingcolor_chat_project_key(
    *,
    explicit: str | None = None,
    session: dict[str, Any] | None = None,
) -> str | None:
    """Resolve the active dashboard project for PM chat.

    The PTY env reflects the project currently open in the browser and must
    win over any stale ``livingcolor_project_key`` cached on a resumed session.
    """
    for candidate in (
        explicit,
        os.environ.get("HERMES_TUI_LIVINGCOLOR_PROJECT_KEY"),
        (session or {}).get("livingcolor_project_key"),
    ):
        key = normalize_livingcolor_project_key(candidate)
        if key:
            return key
    return None


def _sync_livingcolor_chat_project_scope(
    gw: Any,
    sid: str,
    *,
    explicit: str | None = None,
    session: dict[str, Any] | None = None,
) -> str | None:
    lc_key = _resolve_livingcolor_chat_project_key(explicit=explicit, session=session)
    if not lc_key:
        return None

    os.environ["HERMES_TUI_LIVINGCOLOR_PROJECT_KEY"] = lc_key
    if session is not None:
        session["livingcolor_project_key"] = lc_key
        return lc_key

    with gw._sessions_lock:
        live = gw._sessions.get(sid)
        if live is not None:
            live["livingcolor_project_key"] = lc_key
    return lc_key


def _livingcolor_resume_allowed(resume_id: str, project_key: str) -> bool:
    sid = str(resume_id or "").strip()
    key = normalize_livingcolor_project_key(project_key)
    if not sid or not key:
        return False

    db_path = livingcolor_pm_state_db_path()
    if not db_path.is_file():
        return False

    expected = livingcolor_project_chat_session_title(key)
    try:
        from hermes_state import SessionDB

        db = SessionDB(db_path)
        session = db.get_session(sid)
        if not session:
            return False
        title = str(db.get_session_title(sid) or "").strip()
        return title == expected
    except Exception:
        logger.debug("Could not validate LivingColor resume session %s", sid, exc_info=True)
        return False


def _session_title_matches_livingcolor_project(session_id: str, project_key: str) -> bool:
    return _livingcolor_resume_allowed(session_id, project_key)


def _apply_livingcolor_pty_env(env: dict[str, str], project_key: str, resume: str | None = None) -> None:
    key = normalize_livingcolor_project_key(project_key)
    if not key:
        return

    ensure_livingcolor_pm_profile()
    env["HERMES_TUI_LIVINGCOLOR_PROJECT_KEY"] = key
    env["LIVINGCOLOR_PROJECT_KEY"] = key
    env["HERMES_IGNORE_RULES"] = "1"
    env["HERMES_TUI_SKILLS"] = "livingcolor-pm"
    env["HERMES_TUI_TOOLSETS"] = LIVINGCOLOR_PM_TOOLSETS

    mapped = resolve_livingcolor_project_cwd(key)
    if mapped:
        env["TERMINAL_CWD"] = mapped

    resume_id = str(resume or env.get("HERMES_TUI_RESUME") or "").strip()
    env.pop("HERMES_TUI_RESUME", None)
    if resume_id and _livingcolor_resume_allowed(resume_id, key):
        env["HERMES_TUI_RESUME"] = resume_id
    elif resume_id:
        logger.info(
            "Dropped invalid LivingColor resume session %s for project %s",
            resume_id,
            key,
        )


def _patch_tui_gateway_make_agent(gw: Any) -> None:
    if getattr(gw, "_LC_ORIG_MAKE_AGENT", None) is not None:
        return

    gw._LC_ORIG_MAKE_AGENT = gw._make_agent

    def _make_agent(
        sid: str,
        key: str,
        session_id: str | None = None,
        session_db=None,
        *,
        livingcolor_project_key: str | None = None,
        **kwargs: Any,
    ):
        with gw._sessions_lock:
            session = gw._sessions.get(sid) or {}
        lc_key = _sync_livingcolor_chat_project_scope(
            gw,
            sid,
            explicit=livingcolor_project_key,
            session=session,
        )

        if not lc_key:
            return gw._LC_ORIG_MAKE_AGENT(
                sid,
                key,
                session_id=session_id,
                session_db=session_db,
                **kwargs,
            )

        injected_prompt = _compose_livingcolor_system_prompt(lc_key)
        orig_load_cfg = gw._load_cfg
        orig_load_toolsets = gw._load_enabled_toolsets

        def patched_load_cfg():
            cfg = orig_load_cfg()
            agent_cfg = dict(cfg.get("agent") or {})
            agent_cfg["system_prompt"] = injected_prompt
            cfg = dict(cfg)
            cfg["agent"] = agent_cfg
            return cfg

        orig_parse_skills = None
        try:
            import tui_gateway.server as gw_module

            orig_parse_skills = gw_module._parse_tui_skills_env

            def patched_parse_skills():
                raw = os.environ.get("HERMES_TUI_SKILLS", "")
                skills = [part.strip() for part in raw.split(",") if part.strip()]
                return skills

            gw_module._parse_tui_skills_env = patched_parse_skills
        except Exception:
            gw_module = None

        def patched_load_toolsets():
            enabled = list(orig_load_toolsets() or [])
            if "livingcolor" not in enabled:
                enabled.append("livingcolor")
            return enabled or None

        gw._load_cfg = patched_load_cfg
        gw._load_enabled_toolsets = patched_load_toolsets
        try:
            return gw._LC_ORIG_MAKE_AGENT(
                sid,
                key,
                session_id=session_id,
                session_db=session_db,
                **kwargs,
            )
        finally:
            gw._load_cfg = orig_load_cfg
            gw._load_enabled_toolsets = orig_load_toolsets
            if orig_parse_skills is not None and gw_module is not None:
                gw_module._parse_tui_skills_env = orig_parse_skills

    gw._make_agent = _make_agent


def _wrap_session_rpc(gw: Any, method_name: str, mutator: Callable[[dict[str, Any]], None]) -> None:
    original = gw._methods.get(method_name)
    if original is None or getattr(original, "_lc_wrapped", False):
        return

    def wrapped(rid, params: dict | None = None):
        params = dict(params or {})
        mutator(params)
        response = original(rid, params)
        lc_key = normalize_livingcolor_project_key(params.get("livingcolor_project_key"))
        if not lc_key or not isinstance(response, dict):
            return response
        result = response.get("result")
        if not isinstance(result, dict):
            return response
        sid = result.get("session_id")
        if not sid:
            return response
        with gw._sessions_lock:
            session = gw._sessions.get(sid)
            if session is not None:
                session["livingcolor_project_key"] = lc_key
        return response

    wrapped._lc_wrapped = True  # type: ignore[attr-defined]
    gw._methods[method_name] = wrapped


def _patch_tui_gateway_session_methods(gw: Any) -> None:
    def _mutate_create_params(params: dict[str, Any]) -> None:
        lc_key = _resolve_project_key(params)
        if not lc_key:
            return
        params["livingcolor_project_key"] = lc_key
        if not str(params.get("title") or "").strip():
            params["title"] = livingcolor_project_chat_session_title(lc_key)
        raw_cwd = str(params.get("cwd") or "").strip()
        if raw_cwd:
            return
        mapped = resolve_livingcolor_project_cwd(lc_key)
        if mapped:
            params["cwd"] = mapped

    def _mutate_resume_params(params: dict[str, Any]) -> None:
        lc_key = _resolve_project_key(params)
        if not lc_key:
            return
        params["livingcolor_project_key"] = lc_key
        if not str(params.get("title") or "").strip():
            params["title"] = livingcolor_project_chat_session_title(lc_key)

    _wrap_session_rpc(gw, "session.create", _mutate_create_params)
    _wrap_session_rpc(gw, "session.resume", _mutate_resume_params)


def _patch_tui_gateway_start_agent_build(gw: Any) -> None:
    if getattr(gw, "_LC_ORIG_START_AGENT_BUILD", None) is not None:
        return

    gw._LC_ORIG_START_AGENT_BUILD = gw._start_agent_build

    def _start_agent_build(sid: str, session: dict) -> None:
        _sync_livingcolor_chat_project_scope(gw, sid, session=session)
        return gw._LC_ORIG_START_AGENT_BUILD(sid, session)

    gw._start_agent_build = _start_agent_build


def install_tui_gateway_project_chat_hooks() -> None:
    try:
        import tui_gateway.server as gw
    except ImportError:
        logger.debug("tui_gateway not importable; skipping project chat hooks")
        return

    if getattr(gw, "_LC_PROJECT_CHAT_HOOKS", False):
        return

    gw._LC_PROJECT_CHAT_HOOKS = True
    _patch_tui_gateway_make_agent(gw)
    _patch_tui_gateway_session_methods(gw)
    _patch_tui_gateway_start_agent_build(gw)
    _preload_livingcolor_plugin_for_tui()
    logger.info("LivingColor project chat hooks installed on tui_gateway")


def _preload_livingcolor_plugin_for_tui() -> None:
    """Ensure LivingColor tools register before the first TUI agent snapshot."""
    if not _resolve_project_key():
        return
    try:
        from hermes_cli.plugins import discover_plugins

        discover_plugins()
    except Exception:
        logger.debug("LivingColor plugin preload for TUI failed", exc_info=True)


def install_pty_project_chat_hooks() -> None:
    try:
        import hermes_cli.web_server as ws
    except ImportError:
        logger.debug("hermes_cli.web_server not importable; skipping PTY project chat hooks")
        return

    if getattr(ws, "_LC_PTY_PROJECT_CHAT_HOOKS", False):
        return

    ws._LC_PTY_PROJECT_CHAT_HOOKS = True
    original_resolve = ws._resolve_chat_argv
    original_resolve_profile_dir = ws._resolve_profile_dir
    original_pty_ws = ws.pty_ws

    def _resolve_profile_dir(name: str):
        if str(name or "").strip().lower() == LIVINGCOLOR_PM_PROFILE_NAME:
            ensure_livingcolor_pm_profile()
        return original_resolve_profile_dir(name)

    def _resolve_chat_argv(resume=None, sidecar_url=None, profile=None):
        lc_key = _resolve_pty_project_key(sidecar_url=sidecar_url)
        if lc_key:
            ensure_livingcolor_pm_profile()
            profile = LIVINGCOLOR_PM_PROFILE_NAME
            if resume and not _livingcolor_resume_allowed(resume, lc_key):
                resume = None
        argv, cwd, env = original_resolve(resume=resume, sidecar_url=sidecar_url, profile=profile)
        if lc_key:
            _apply_livingcolor_pty_env(env, lc_key, resume=resume)
        return argv, cwd, env

    async def pty_ws(ws_conn):
        lc_key = normalize_livingcolor_project_key(ws_conn.query_params.get("livingcolor_project_key"))
        if not lc_key:
            lc_key = _project_key_from_channel(ws_conn.query_params.get("channel"))
        token = _LC_PTY_PROJECT_KEY.set(lc_key)
        try:
            await original_pty_ws(ws_conn)
        finally:
            _LC_PTY_PROJECT_KEY.reset(token)

    ws._resolve_chat_argv = _resolve_chat_argv
    ws._resolve_profile_dir = _resolve_profile_dir
    ws.pty_ws = pty_ws
    if _rebind_dashboard_pty_endpoint(pty_ws):
        logger.info("LivingColor project chat hooks rebound /api/pty websocket")
    else:
        logger.warning("LivingColor /api/pty websocket was not rebound; using sidecar channel fallback")
    logger.info("LivingColor project chat hooks installed on /api/pty")


def install_project_chat_context_hooks() -> None:
    global _LC_HOOKS_INSTALLED
    if _LC_HOOKS_INSTALLED:
        return
    _LC_HOOKS_INSTALLED = True
    install_tui_gateway_project_chat_hooks()
    install_pty_project_chat_hooks()
