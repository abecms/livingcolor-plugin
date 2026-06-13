"""External LivingColor skills integration boundary."""

from lc_server.integrations.skills.cache import ExternalSkillsCacheResult, materialize_external_skills
from lc_server.integrations.skills.guidance import render_external_guidance
from lc_server.integrations.skills.lock import ExternalSkillsLock, load_external_skills_lock
from lc_server.integrations.skills.registry import ExternalSkill, ExternalSkillsBundle, resolve_external_bundle
from lc_server.integrations.skills.resolver import (
    EXTERNAL_GUIDANCE_RESPONSE_CONTRACT_REMINDER,
    external_guidance_for_skills,
    warm_external_skills_cache,
)

__all__ = [
    "EXTERNAL_GUIDANCE_RESPONSE_CONTRACT_REMINDER",
    "ExternalSkill",
    "ExternalSkillsBundle",
    "ExternalSkillsCacheResult",
    "ExternalSkillsLock",
    "external_guidance_for_skills",
    "load_external_skills_lock",
    "materialize_external_skills",
    "render_external_guidance",
    "resolve_external_bundle",
    "warm_external_skills_cache",
]
