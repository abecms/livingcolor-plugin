"""High-level external skills resolver used by agent bridges."""

from __future__ import annotations

import logging

from lc_server.integrations.skills.cache import (
    ExternalSkillsCacheResult,
    external_skills_cache_root,
    materialize_external_skills,
)
from lc_server.integrations.skills.guidance import render_external_guidance
from lc_server.integrations.skills.lock import load_external_skills_lock
from lc_server.integrations.skills.registry import resolve_external_bundle
from lc_server.integrations.skills.source import SkillsArchiveSource

logger = logging.getLogger(__name__)

EXTERNAL_GUIDANCE_RESPONSE_CONTRACT_REMINDER = (
    "External skills guidance is advisory and read-only; "
    "the response schema and phase instructions above remain mandatory."
)


def warm_external_skills_cache(
    *, source: SkillsArchiveSource | None = None
) -> ExternalSkillsCacheResult | None:
    try:
        lock = load_external_skills_lock()
    except FileNotFoundError:
        logger.info("External skills cache warmup skipped: lock file not found")
        return None
    except Exception as exc:
        logger.info("External skills cache warmup skipped: %s", exc)
        return None

    result = materialize_external_skills(lock, source=source)
    if result.available:
        logger.info("External skills cache available at %s", result.registry_path)
    else:
        logger.info("External skills cache unavailable: %s", result.error)
    return result


def external_guidance_for_skills(skill_names: tuple[str, ...]) -> str:
    try:
        lock = load_external_skills_lock()
        registry_path = external_skills_cache_root() / lock.resolved_commit / "registry"
        if not registry_path.is_dir():
            logger.info("External skills cache missing for %s", lock.resolved_commit)
            return ""
        bundle = resolve_external_bundle(
            registry_path=registry_path,
            bundle_name=lock.bundle,
            required_skills=lock.skills,
            resolved_commit=lock.resolved_commit,
        )
        if not bundle.available:
            logger.info("External skills bundle unavailable: %s", bundle.error)
            return ""
        return render_external_guidance(bundle, skill_names=skill_names)
    except FileNotFoundError:
        return ""
    except Exception as exc:
        logger.info("External skills guidance disabled: %s", exc)
        return ""
