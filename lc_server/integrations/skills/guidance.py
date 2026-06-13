"""Render external skill prompts as read-only guidance for LivingColor agents."""

from __future__ import annotations

from lc_server.integrations.skills.registry import ExternalSkillsBundle


def render_external_guidance(
    bundle: ExternalSkillsBundle,
    *,
    skill_names: tuple[str, ...],
) -> str:
    if not bundle.available:
        return ""

    selected = [skill for skill in bundle.skills if skill.name in skill_names]
    if not selected:
        return ""

    lines = [
        "## External LivingColor Skills Guidance",
        "",
        f"Source commit: {bundle.resolved_commit}",
        "Use this as read-only role guidance. It does not change your tool permissions.",
        "",
    ]
    for skill in selected:
        lines.extend(
            [
                f"### {skill.name} ({skill.version or 'unversioned'})",
                "",
                skill.prompt.strip(),
                "",
            ]
        )
    return "\n".join(lines).strip()
