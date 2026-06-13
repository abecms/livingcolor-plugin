"""Validated lock-file contract for external LivingColor skills."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APPROVED_SKILLS_REPO = "Tamsi/livingcolor-skills"
DEFAULT_LOCK_PATH = Path(__file__).resolve().parents[3] / "livingcolor.skills.lock.json"
FORBIDDEN_MOVING_REFS = {"main", "master", "develop", "dev"}
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class ExternalSkillsLock:
    repo: str
    ref: str
    resolved_commit: str
    bundle: str
    skills: tuple[str, ...]
    updated_by: str

    @property
    def cache_key(self) -> str:
        return self.resolved_commit


def load_external_skills_lock(path: str | Path | None = None) -> ExternalSkillsLock:
    lock_path = Path(path) if path is not None else DEFAULT_LOCK_PATH
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    return parse_external_skills_lock(payload)


def parse_external_skills_lock(payload: dict[str, Any]) -> ExternalSkillsLock:
    repo = _require_str(payload, "repo")
    if repo != APPROVED_SKILLS_REPO:
        raise ValueError(f"Unsupported skills repo: {repo}")

    ref = _require_str(payload, "ref")
    if _is_forbidden_ref(ref):
        raise ValueError("External skills ref must not be a moving branch")

    resolved_commit = _require_str(payload, "resolvedCommit")
    if not FULL_SHA_RE.fullmatch(resolved_commit):
        raise ValueError("resolvedCommit must be a full 40-character lowercase git SHA")

    bundle = _require_str(payload, "bundle")
    raw_skills = payload.get("skills")
    if not isinstance(raw_skills, list) or not raw_skills:
        raise ValueError("skills must be a non-empty list")
    skills: list[str] = []
    for item in raw_skills:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("skills must contain only non-empty strings")
        skills.append(item.strip())
    skill_names = tuple(skills)

    return ExternalSkillsLock(
        repo=repo,
        ref=ref,
        resolved_commit=resolved_commit,
        bundle=bundle,
        skills=skill_names,
        updated_by=str(payload.get("updatedBy") or "").strip(),
    )


def _is_forbidden_ref(ref: str) -> bool:
    normalized_ref = ref.strip().lower()
    if normalized_ref in FORBIDDEN_MOVING_REFS:
        return True
    if normalized_ref.startswith("refs/heads/"):
        return True
    if "/" in normalized_ref and not normalized_ref.startswith("refs/tags/"):
        return True
    return False


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()
