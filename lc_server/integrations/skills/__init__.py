"""External LivingColor skills integration boundary."""

from lc_server.integrations.skills.lock import ExternalSkillsLock, load_external_skills_lock

__all__ = ["ExternalSkillsLock", "load_external_skills_lock"]
