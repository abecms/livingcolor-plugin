"""Validate extracted LivingColor skills registries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ExternalSkill:
    name: str
    version: str
    root_path: Path
    prompt: str


@dataclass(frozen=True)
class ExternalSkillsBundle:
    available: bool
    bundle_name: str
    resolved_commit: str
    skills: tuple[ExternalSkill, ...] = ()
    error: str = ""


def resolve_external_bundle(
    *,
    registry_path: Path,
    bundle_name: str,
    required_skills: tuple[str, ...],
    resolved_commit: str,
) -> ExternalSkillsBundle:
    bundle_path = registry_path / "bundles" / bundle_name / "bundle.yaml"
    if not bundle_path.is_file():
        return _unavailable(bundle_name, resolved_commit, f"bundle not found: {bundle_name}")

    try:
        bundle_payload = yaml.safe_load(bundle_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return _unavailable(bundle_name, resolved_commit, f"invalid bundle yaml: {exc}")

    raw_skills = bundle_payload.get("skills") if isinstance(bundle_payload, dict) else None
    if not isinstance(raw_skills, list):
        return _unavailable(bundle_name, resolved_commit, "bundle skills must be a list")
    if any(not isinstance(item, str) or not item.strip() for item in raw_skills):
        return _unavailable(bundle_name, resolved_commit, "bundle skills must contain only non-empty strings")

    listed_skills = tuple(item.strip() for item in raw_skills)
    missing_from_bundle = [skill for skill in required_skills if skill not in listed_skills]
    if missing_from_bundle:
        return _unavailable(
            bundle_name,
            resolved_commit,
            f"bundle missing required skills: {', '.join(missing_from_bundle)}",
        )

    skills: list[ExternalSkill] = []
    for skill_name in required_skills:
        loaded = _load_skill(registry_path, skill_name)
        if isinstance(loaded, str):
            return _unavailable(bundle_name, resolved_commit, loaded)
        skills.append(loaded)

    return ExternalSkillsBundle(
        available=True,
        bundle_name=bundle_name,
        resolved_commit=resolved_commit,
        skills=tuple(skills),
    )


def _load_skill(registry_path: Path, skill_name: str) -> ExternalSkill | str:
    root = registry_path / skill_name
    manifest_path = root / "skill.yaml"
    prompt_path = root / "prompt.md"
    if not manifest_path.is_file():
        return f"skill manifest not found: {skill_name}"
    if not prompt_path.is_file():
        return f"skill prompt not found: {skill_name}"
    try:
        manifest: dict[str, Any] = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return f"invalid skill yaml for {skill_name}: {exc}"
    if not isinstance(manifest, dict):
        return f"invalid skill yaml for {skill_name}: manifest must be a mapping"

    name = str(manifest.get("name") or "").strip()
    if name != skill_name:
        return f"skill name mismatch: expected {skill_name}, got {name or '(missing)'}"
    version = str(manifest.get("version") or "").strip()
    try:
        prompt = prompt_path.read_text(encoding="utf-8")
    except Exception as exc:
        return f"invalid skill prompt for {skill_name}: {exc}"
    return ExternalSkill(
        name=skill_name,
        version=version,
        root_path=root,
        prompt=prompt,
    )


def _unavailable(bundle_name: str, resolved_commit: str, error: str) -> ExternalSkillsBundle:
    return ExternalSkillsBundle(
        available=False,
        bundle_name=bundle_name,
        resolved_commit=resolved_commit,
        error=error,
    )
