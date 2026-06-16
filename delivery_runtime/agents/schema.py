from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

API_VERSION = "livingcolor.dev/v1"
KIND = "AgentManifest"
VALID_ROLES = frozenset({"orchestrator", "analyst", "planner", "developer", "publisher", "reporter"})
VALID_RUNTIME_TYPES = frozenset({"hermes", "none"})


class AgentManifestError(ValueError):
    pass


@dataclass(frozen=True)
class PromptRule:
    id: str
    content: str


@dataclass(frozen=True)
class AgentPrompt:
    system: str
    rules: tuple[PromptRule, ...] = ()


@dataclass(frozen=True)
class AgentRuntime:
    type: str
    max_iterations: int = 60
    toolsets: tuple[str, ...] = ()
    model: str | None = None
    provider: str | None = None


@dataclass(frozen=True)
class AgentIdentity:
    display_name: str
    platform: str


@dataclass(frozen=True)
class AgentSkillRef:
    path: str


@dataclass(frozen=True)
class AgentMcpConfig:
    inherit: str
    additional: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentManifest:
    role: str
    template_version: str
    template_checksum: str
    manually_edited: bool
    runtime: AgentRuntime
    identity: AgentIdentity
    prompt: AgentPrompt
    skills: tuple[AgentSkillRef, ...]
    mcp: AgentMcpConfig
    context: dict[str, Any]

    def render_system_prompt(self) -> str:
        parts = [self.prompt.system.rstrip()]
        for rule in self.prompt.rules:
            parts.append(f"## Rule: {rule.id}\n{rule.content.rstrip()}")
        return "\n\n".join(parts) + "\n"

    @property
    def skill_paths(self) -> list[str]:
        return [item.path for item in self.skills]


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentManifestError(f"{key} must be a non-empty string")
    return value.strip()


def parse_agent_manifest(raw_yaml: str) -> AgentManifest:
    loaded = yaml.safe_load(raw_yaml)
    if not isinstance(loaded, dict):
        raise AgentManifestError("manifest must be a mapping")

    if _require_str(loaded, "apiVersion") != API_VERSION:
        raise AgentManifestError(f"unsupported apiVersion (expected {API_VERSION})")
    if _require_str(loaded, "kind") != KIND:
        raise AgentManifestError(f"unsupported kind (expected {KIND})")

    role = _require_str(loaded, "role").lower()
    if role not in VALID_ROLES:
        raise AgentManifestError(f"invalid role: {role!r}")

    runtime_raw = loaded.get("runtime")
    if not isinstance(runtime_raw, dict):
        raise AgentManifestError("runtime must be a mapping")
    runtime_type = _require_str(runtime_raw, "type").lower()
    if runtime_type not in VALID_RUNTIME_TYPES:
        raise AgentManifestError(f"invalid runtime.type: {runtime_type!r}")

    max_iterations = int(runtime_raw.get("maxIterations") or 60)
    toolsets_raw = runtime_raw.get("toolsets") or []
    if not isinstance(toolsets_raw, list):
        raise AgentManifestError("runtime.toolsets must be a list")
    toolsets = tuple(str(item).strip() for item in toolsets_raw if str(item).strip())

    runtime_model = runtime_raw.get("model")
    runtime_provider = runtime_raw.get("provider")
    model = str(runtime_model).strip() if isinstance(runtime_model, str) and runtime_model.strip() else None
    provider = (
        str(runtime_provider).strip()
        if isinstance(runtime_provider, str) and runtime_provider.strip()
        else None
    )

    identity_raw = loaded.get("identity")
    if not isinstance(identity_raw, dict):
        raise AgentManifestError("identity must be a mapping")

    prompt_raw = loaded.get("prompt")
    if not isinstance(prompt_raw, dict):
        raise AgentManifestError("prompt must be a mapping")
    system = _require_str(prompt_raw, "system")
    rules_raw = prompt_raw.get("rules") or []
    if not isinstance(rules_raw, list):
        raise AgentManifestError("prompt.rules must be a list")
    rules: list[PromptRule] = []
    for item in rules_raw:
        if not isinstance(item, dict):
            continue
        rules.append(PromptRule(id=_require_str(item, "id"), content=_require_str(item, "content")))

    skills_raw = loaded.get("skills") or []
    if not isinstance(skills_raw, list):
        raise AgentManifestError("skills must be a list")
    skills = tuple(AgentSkillRef(path=_require_str(item, "path")) for item in skills_raw if isinstance(item, dict))

    mcp_raw = loaded.get("mcp")
    if not isinstance(mcp_raw, dict):
        raise AgentManifestError("mcp must be a mapping")
    additional_raw = mcp_raw.get("additional") or []
    additional = tuple(str(item).strip() for item in additional_raw if str(item).strip()) if isinstance(additional_raw, list) else ()

    context_raw = loaded.get("context") or {}
    context = dict(context_raw) if isinstance(context_raw, dict) else {}

    return AgentManifest(
        role=role,
        template_version=_require_str(loaded, "templateVersion"),
        template_checksum=_require_str(loaded, "templateChecksum"),
        manually_edited=bool(loaded.get("manuallyEdited")),
        runtime=AgentRuntime(
            type=runtime_type,
            max_iterations=max_iterations,
            toolsets=toolsets,
            model=model,
            provider=provider,
        ),
        identity=AgentIdentity(
            display_name=_require_str(identity_raw, "displayName"),
            platform=_require_str(identity_raw, "platform"),
        ),
        prompt=AgentPrompt(system=system, rules=tuple(rules)),
        skills=skills,
        mcp=AgentMcpConfig(inherit=_require_str(mcp_raw, "inherit"), additional=additional),
        context=context,
    )
