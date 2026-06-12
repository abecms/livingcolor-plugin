"""Build a durable repository architecture profile for agent context."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from delivery_runtime.context.repo_scanner import IGNORED_DIRS, SOURCE_EXTENSIONS, _load_conventions
from delivery_runtime.persistence.db import utc_now_iso

ARCHITECTURE_CONFIG_FILES = (
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "Makefile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "tsconfig.json",
    "vite.config.ts",
    "vitest.config.ts",
    "jest.config.js",
    "next.config.js",
    "next.config.mjs",
    "encore.app",
)

DIRECTORY_ROLE_HINTS: dict[str, str] = {
    "src": "Application source code",
    "app": "Application routes or modules",
    "apps": "Multi-app workspace",
    "packages": "Shared packages or libraries",
    "lib": "Shared libraries and helpers",
    "services": "Backend services",
    "api": "HTTP or RPC API layer",
    "components": "UI components",
    "pages": "UI pages or routes",
    "tests": "Automated tests",
    "test": "Automated tests",
    "__tests__": "Automated tests",
    "docs": "Documentation",
    "scripts": "Automation scripts",
    "tools": "Tooling and utilities",
    "migrations": "Database or schema migrations",
    "models": "Domain or data models",
    "handlers": "Request or event handlers",
    "plugins": "Plugin modules",
    "gateway": "Gateway or adapter layer",
    "agent": "Agent runtime",
    "delivery_runtime": "Delivery orchestration runtime",
}


def analyze_repository_architecture(
    checkout_path: str,
    *,
    repo_id: str,
    max_structure_entries: int = 120,
) -> dict[str, Any]:
    """Scan a local checkout and return a durable architecture profile."""
    root = Path(checkout_path)
    if not root.is_dir():
        raise ValueError(f"Repository checkout does not exist: {checkout_path}")

    config_files = _discover_config_files(root)
    stack = _detect_stack(root, config_files)
    top_level_directories = _describe_top_level_directories(root)
    entry_points = _detect_entry_points(root, stack)
    test_directories = _detect_test_directories(root)
    structure_preview = _list_structure_preview(root, max_entries=max_structure_entries)
    architecture_notes = _extract_architecture_notes(root)
    conventions = _load_conventions(root)

    return {
        "repoId": repo_id,
        "checkoutPath": str(root),
        "analyzedAt": utc_now_iso(),
        "stack": stack,
        "summary": _build_summary(
            repo_id=repo_id,
            stack=stack,
            top_level_directories=top_level_directories,
            entry_points=entry_points,
            test_directories=test_directories,
            config_files=config_files,
        ),
        "topLevelDirectories": top_level_directories,
        "entryPoints": entry_points,
        "configFiles": config_files,
        "conventions": conventions,
        "testDirectories": test_directories,
        "architectureNotes": architecture_notes,
        "structurePreview": structure_preview,
    }


def architecture_profile_is_current(existing: dict[str, Any] | None, *, repo_id: str, checkout_path: str) -> bool:
    if not existing or not isinstance(existing, dict):
        return False
    if str(existing.get("repoId") or "") != repo_id:
        return False
    if str(existing.get("checkoutPath") or "") != str(Path(checkout_path)):
        return False
    return bool(existing.get("analyzedAt"))


def format_architecture_for_prompt(profile: dict[str, Any]) -> str:
    """Render a compact architecture brief for agent prompts."""
    if not profile:
        return ""

    lines = [
        f"Repository: {profile.get('repoId') or 'unknown'}",
        f"Summary: {profile.get('summary') or 'No architecture summary available.'}",
    ]

    stack = profile.get("stack") or []
    if stack:
        lines.append(f"Stack: {', '.join(str(item) for item in stack)}")

    directories = profile.get("topLevelDirectories") or []
    if directories:
        lines.append("Top-level layout:")
        for item in directories[:8]:
            if isinstance(item, dict):
                lines.append(f"- `{item.get('path')}` — {item.get('role')}")

    entry_points = profile.get("entryPoints") or []
    if entry_points:
        lines.append("Entry points:")
        lines.extend(f"- `{path}`" for path in entry_points[:6])

    test_directories = profile.get("testDirectories") or []
    if test_directories:
        lines.append(f"Tests: {', '.join(str(item) for item in test_directories[:6])}")

    notes = profile.get("architectureNotes") or []
    if notes:
        lines.append("Architecture notes:")
        lines.extend(f"- {note}" for note in notes[:8])

    return "\n".join(lines)


def _discover_config_files(root: Path) -> list[str]:
    found: list[str] = []
    for name in ARCHITECTURE_CONFIG_FILES:
        if (root / name).is_file():
            found.append(name)
    return found


def _detect_stack(root: Path, config_files: list[str]) -> list[str]:
    stack: list[str] = []

    if "package.json" in config_files:
        stack.append("Node.js")
        package_json = root / "package.json"
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        deps = {
            **(payload.get("dependencies") or {}),
            **(payload.get("devDependencies") or {}),
        }
        if "react" in deps or "react-dom" in deps:
            stack.append("React")
        if "next" in deps:
            stack.append("Next.js")
        if "typescript" in deps or (root / "tsconfig.json").is_file():
            stack.append("TypeScript")
        if "vitest" in deps:
            stack.append("Vitest")
        if "jest" in deps:
            stack.append("Jest")
        if "electron" in deps:
            stack.append("Electron")

    if "pyproject.toml" in config_files or "requirements.txt" in config_files:
        stack.append("Python")
        pyproject = root / "pyproject.toml"
        if pyproject.is_file():
            text = pyproject.read_text(encoding="utf-8", errors="ignore").lower()
            if "fastapi" in text:
                stack.append("FastAPI")
            if "pytest" in text:
                stack.append("pytest")

    if "go.mod" in config_files:
        stack.append("Go")
    if "Cargo.toml" in config_files:
        stack.append("Rust")
    if "encore.app" in config_files:
        stack.append("Encore")

    if not stack and any(path.suffix.lower() in {".ts", ".tsx"} for path in root.rglob("*") if path.is_file()):
        stack.append("TypeScript")

    if (root / "docker-compose.yml").is_file() or (root / "docker-compose.yaml").is_file():
        stack.append("Docker Compose")

    return _dedupe(stack)


def _describe_top_level_directories(root: Path) -> list[dict[str, str]]:
    directories: list[dict[str, str]] = []
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        if path.name in IGNORED_DIRS or path.name.startswith("."):
            continue
        role = DIRECTORY_ROLE_HINTS.get(path.name.lower(), "Project module")
        directories.append({"path": f"{path.name}/", "role": role})
    return directories


def _detect_entry_points(root: Path, stack: list[str]) -> list[str]:
    candidates = [
        "src/main.ts",
        "src/main.tsx",
        "src/index.ts",
        "src/index.tsx",
        "src/app/main.ts",
        "src/app/main.tsx",
        "main.py",
        "app/main.py",
        "server.py",
        "cmd/main.go",
        "src/main.go",
    ]
    if "Next.js" in stack:
        candidates.extend(["app/page.tsx", "pages/index.tsx"])
    if "Electron" in stack:
        candidates.extend(["electron/main.ts", "electron/main.js", "src/main/electron.ts"])

    found = [candidate for candidate in candidates if (root / candidate).is_file()]
    if found:
        return found[:8]

    fallback: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        if rel.count("/") > 2:
            continue
        if path.name in {"main.py", "main.ts", "main.tsx", "index.ts", "index.tsx", "server.py"}:
            fallback.append(rel)
        if len(fallback) >= 5:
            break
    return fallback


def _detect_test_directories(root: Path) -> list[str]:
    directories: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_dir():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        name = path.name.lower()
        if name in {"tests", "test", "__tests__"} or rel.endswith("/tests"):
            directories.append(f"{rel}/")
        if len(directories) >= 8:
            break
    return _dedupe(directories)


def _list_structure_preview(root: Path, *, max_entries: int) -> list[str]:
    entries: list[str] = []
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            if rel and rel.count("/") <= 3:
                entries.append(f"{rel}/")
        elif path.suffix.lower() in SOURCE_EXTENSIONS or path.name in {"AGENTS.md", "README.md"}:
            if rel.count("/") <= 5:
                entries.append(rel)
        if len(entries) >= max_entries:
            break
    return entries


def _extract_architecture_notes(root: Path) -> list[str]:
    notes: list[str] = []
    for filename in ("AGENTS.md", "README.md"):
        path = root / filename
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            cleaned = line.strip()
            if not cleaned or cleaned.startswith("#"):
                continue
            if cleaned.startswith(("-", "*", ">")):
                cleaned = cleaned.lstrip("-*> ").strip()
            if len(cleaned) < 12:
                continue
            if any(token in cleaned.lower() for token in ("architecture", "module", "service", "layer", "runtime", "gateway")):
                notes.append(cleaned[:240])
            if len(notes) >= 8:
                break
        if notes:
            break
    return notes


def _build_summary(
    *,
    repo_id: str,
    stack: list[str],
    top_level_directories: list[dict[str, str]],
    entry_points: list[str],
    test_directories: list[str],
    config_files: list[str],
) -> str:
    stack_text = ", ".join(stack) if stack else "unknown stack"
    layout = ", ".join(item["path"] for item in top_level_directories[:6]) or "flat layout"
    tests = ", ".join(test_directories[:3]) if test_directories else "no dedicated test directory detected"
    entry = entry_points[0] if entry_points else "entry point not detected"
    config = ", ".join(config_files[:4]) if config_files else "minimal config"
    return (
        f"{repo_id} uses {stack_text}. Top-level layout: {layout}. "
        f"Primary entry: {entry}. Tests: {tests}. Config: {config}."
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
