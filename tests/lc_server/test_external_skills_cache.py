from __future__ import annotations

import io
import urllib.request
import zipfile


class InMemoryArchiveSource:
    def __init__(self, archive: bytes) -> None:
        self.archive = archive
        self.calls: list[tuple[str, str, str]] = []

    def fetch_archive(self, *, repo: str, ref: str, resolved_commit: str) -> bytes:
        self.calls.append((repo, ref, resolved_commit))
        return self.archive


def _skills_archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        prefix = "livingcolor-skills-0123456/"
        zf.writestr(
            prefix + "registry/bundles/code-review-pipeline/bundle.yaml",
            "name: code-review-pipeline\nskills:\n  - ticket-analyst\n",
        )
        zf.writestr(
            prefix + "registry/ticket-analyst/skill.yaml",
            "name: ticket-analyst\nversion: 2.0.0\n",
        )
        zf.writestr(prefix + "registry/ticket-analyst/prompt.md", "# Ticket Analyst\n")
    return buffer.getvalue()


def _lock():
    from lc_server.integrations.skills.lock import ExternalSkillsLock

    return ExternalSkillsLock(
        repo="Tamsi/livingcolor-skills",
        ref="v0.1.0",
        resolved_commit="fdf1be62d61ef74b51d91ae81ed718350dce20d5",
        bundle="code-review-pipeline",
        skills=("ticket-analyst",),
        updated_by="livingcolor-evolution",
    )


def test_materialize_skills_archive_under_livingcolor_cache(livingcolor_home):
    from lc_server.integrations.skills.cache import materialize_external_skills

    source = InMemoryArchiveSource(_skills_archive())
    result = materialize_external_skills(_lock(), source=source)

    assert result.available is True
    assert result.registry_path == (
        livingcolor_home / "skills-cache" / "livingcolor-skills" / _lock().resolved_commit / "registry"
    )
    assert (result.registry_path / "ticket-analyst" / "prompt.md").is_file()
    assert source.calls == [("Tamsi/livingcolor-skills", "v0.1.0", _lock().resolved_commit)]


def test_materialize_reuses_existing_cache(livingcolor_home):
    from lc_server.integrations.skills.cache import materialize_external_skills

    source = InMemoryArchiveSource(_skills_archive())
    first = materialize_external_skills(_lock(), source=source)
    second = materialize_external_skills(_lock(), source=source)

    assert first.registry_path == second.registry_path
    assert len(source.calls) == 1


def test_materialize_reports_fetch_error(livingcolor_home):
    from lc_server.integrations.skills.cache import materialize_external_skills

    class BrokenSource:
        def fetch_archive(self, *, repo: str, ref: str, resolved_commit: str) -> bytes:
            raise RuntimeError("network unavailable")

    result = materialize_external_skills(_lock(), source=BrokenSource())

    assert result.available is False
    assert "network unavailable" in result.error


def test_materialize_rejects_archive_path_traversal(livingcolor_home):
    from lc_server.integrations.skills.cache import materialize_external_skills

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("livingcolor-skills-0123456/registry/ticket-analyst/prompt.md", "# Ticket Analyst\n")
        zf.writestr("../escaped.txt", "malicious")

    result = materialize_external_skills(_lock(), source=InMemoryArchiveSource(buffer.getvalue()))

    assert result.available is False
    assert "Unsafe archive member" in result.error
    assert not (livingcolor_home / "skills-cache" / "escaped.txt").exists()


def test_github_archive_source_fetches_resolved_commit(monkeypatch):
    from lc_server.integrations.skills.source import GitHubArchiveSkillsSource

    requested_urls: list[str] = []

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def read(self) -> bytes:
            return b"archive"

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> FakeResponse:
        assert timeout == 30
        requested_urls.append(request.full_url)
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    archive = GitHubArchiveSkillsSource().fetch_archive(
        repo="Tamsi/livingcolor-skills",
        ref="v0.1.0",
        resolved_commit="fdf1be62d61ef74b51d91ae81ed718350dce20d5",
    )

    assert archive == b"archive"
    assert requested_urls == [
        "https://github.com/Tamsi/livingcolor-skills/archive/fdf1be62d61ef74b51d91ae81ed718350dce20d5.zip"
    ]
    assert "v0.1.0" not in requested_urls[0]
