"""Scan a local repository checkout for structure and candidate files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


IGNORED_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".next",
    "coverage",
}

SOURCE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".sql",
    ".yaml",
    ".yml",
    ".md",
}


def scan_repository(
    checkout_path: str | None,
    *,
    search_terms: list[str],
    max_structure_entries: int = 40,
    max_candidates: int = 6,
) -> tuple[list[str], list[str], list[str]]:
    """Return repo_structure, candidate_files, conventions."""
    if not checkout_path:
        return [], [], []

    root = Path(checkout_path)
    if not root.is_dir():
        return [], [], []

    structure = _list_structure(root, max_entries=max_structure_entries)
    candidates = _rank_candidate_files(root, search_terms, max_candidates=max_candidates)
    conventions = _load_conventions(root)
    return structure, candidates, conventions


def _list_structure(root: Path, *, max_entries: int) -> list[str]:
    entries: list[str] = []
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.is_dir():
            rel = path.relative_to(root).as_posix()
            if rel and rel.count("/") <= 2:
                entries.append(f"{rel}/")
        elif path.suffix.lower() in SOURCE_EXTENSIONS:
            rel = path.relative_to(root).as_posix()
            if rel.count("/") <= 4:
                entries.append(rel)
        if len(entries) >= max_entries:
            break
    return entries


def _rank_candidate_files(root: Path, search_terms: list[str], *, max_candidates: int) -> list[str]:
    tokens = _tokenize(" ".join(search_terms))
    if not tokens:
        return []

    scored: list[tuple[int, str]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in SOURCE_EXTENSIONS and path.name not in {"AGENTS.md", "README.md"}:
            continue
        rel = path.relative_to(root).as_posix()
        score = _score_path(rel, tokens)
        if score > 0:
            scored.append((score, rel))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [path for _, path in scored[:max_candidates]]


def _score_path(path: str, tokens: set[str]) -> int:
    haystack = path.lower().replace("_", " ").replace("-", " ")
    score = 0
    for token in tokens:
        if len(token) < 3:
            continue
        if token in haystack:
            score += 3
        if token in Path(path).stem.lower():
            score += 2
    if "/tests/" in f"/{haystack}/" or haystack.endswith(".test.ts"):
        score += 1
    return score


def _tokenize(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-zA-ZÀ-ÿ0-9]{3,}", text.lower()))
    extras = {
        "ame": {"render", "media", "offline", "encoder"},
        "partial": {"checkin", "audio", "sound"},
        "flex": {"workflow", "variable", "metadata"},
        "localstorage": {"storage", "cache", "panel", "lenteur", "lent"},
        "dbt": {"gold", "snowflake", "ingestion", "cra", "sard"},
        "notebook": {"scheduler", "workspace", "execution"},
        "search": {"far", "migrate", "query"},
        "targetfield": {"news", "field", "query"},
        "oauth": {"token", "callback", "auth"},
        "health": {"probe", "endpoint", "deployment"},
    }
    expanded = set(tokens)
    for token in list(tokens):
        expanded.update(extras.get(token, set()))
    return expanded


def _load_conventions(root: Path) -> list[str]:
    conventions: list[str] = []
    agents_md = root / "AGENTS.md"
    if agents_md.is_file():
        for line in agents_md.read_text(encoding="utf-8", errors="ignore").splitlines()[:12]:
            cleaned = line.strip(" #-")
            if cleaned:
                conventions.append(cleaned)
    return conventions[:8]
