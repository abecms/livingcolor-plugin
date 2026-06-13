"""Materialize pinned external skills under LivingColor-managed cache paths."""

from __future__ import annotations

import io
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from lc_constants import ensure_livingcolor_home_layout, get_livingcolor_home
from lc_server.integrations.skills.lock import ExternalSkillsLock
from lc_server.integrations.skills.source import GitHubArchiveSkillsSource, SkillsArchiveSource


@dataclass(frozen=True)
class ExternalSkillsCacheResult:
    available: bool
    registry_path: Path
    cache_path: Path
    source_ref: str
    resolved_commit: str
    error: str = ""


def external_skills_cache_root() -> Path:
    ensure_livingcolor_home_layout()
    root = get_livingcolor_home() / "skills-cache" / "livingcolor-skills"
    root.mkdir(parents=True, exist_ok=True)
    return root


def materialize_external_skills(
    lock: ExternalSkillsLock,
    *,
    source: SkillsArchiveSource | None = None,
) -> ExternalSkillsCacheResult:
    cache_path = external_skills_cache_root() / lock.resolved_commit
    registry_path = cache_path / "registry"
    if registry_path.is_dir():
        return ExternalSkillsCacheResult(
            available=True,
            registry_path=registry_path,
            cache_path=cache_path,
            source_ref=lock.ref,
            resolved_commit=lock.resolved_commit,
        )

    try:
        archive_source = source or GitHubArchiveSkillsSource()
        archive = archive_source.fetch_archive(
            repo=lock.repo,
            ref=lock.ref,
            resolved_commit=lock.resolved_commit,
        )
        _extract_archive(archive, cache_path)
    except Exception as exc:
        return ExternalSkillsCacheResult(
            available=False,
            registry_path=registry_path,
            cache_path=cache_path,
            source_ref=lock.ref,
            resolved_commit=lock.resolved_commit,
            error=str(exc),
        )

    return ExternalSkillsCacheResult(
        available=registry_path.is_dir(),
        registry_path=registry_path,
        cache_path=cache_path,
        source_ref=lock.ref,
        resolved_commit=lock.resolved_commit,
        error="" if registry_path.is_dir() else "archive did not contain registry/",
    )


def _extract_archive(archive: bytes, destination: Path) -> None:
    temp_path = destination.with_suffix(".tmp")
    if temp_path.exists():
        shutil.rmtree(temp_path)
    temp_path.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            _extract_zip_safely(zf, temp_path)

        roots = [path for path in temp_path.iterdir() if path.is_dir()]
        source_root = roots[0] if len(roots) == 1 else temp_path
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(source_root), destination)
    except Exception:
        if temp_path.exists():
            shutil.rmtree(temp_path)
        raise
    finally:
        if temp_path.exists():
            shutil.rmtree(temp_path)


def _extract_zip_safely(zf: zipfile.ZipFile, destination: Path) -> None:
    for member in zf.infolist():
        member_path = _safe_archive_member_path(member.filename)
        target_path = destination / member_path

        if member.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as source, target_path.open("wb") as target:
            shutil.copyfileobj(source, target)


def _safe_archive_member_path(filename: str) -> Path:
    path = PurePosixPath(filename)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe archive member: {filename}")
    return Path(path)
