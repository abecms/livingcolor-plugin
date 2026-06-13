"""Build a Context Pack from orchestration context."""

from __future__ import annotations

from typing import Any

from delivery_runtime.context.acceptance import extract_acceptance_criteria
from delivery_runtime.context.git_history import collect_git_history
from delivery_runtime.context.models import ContextPack
from delivery_runtime.context.repo_architecture import architecture_profile_is_current
from delivery_runtime.context.repo_resolver import resolve_repository
from delivery_runtime.context.repo_scanner import scan_repository
from delivery_runtime.context.skills_context import render_skills_context_markdown
from delivery_runtime.pm_inbox.project_memory import load_existing_memory
from delivery_runtime.readiness.project_settings import load_project_vcs_provider


class ContextPackBuilder:
    """Assemble repo-aware planning context before Gate 1."""

    def build(self, context: dict[str, Any]) -> ContextPack:
        work_order = context.get("workOrder") or {}
        snapshot = context.get("jiraSnapshot") or {}
        recommended = [str(item) for item in (context.get("recommendedRepos") or []) if item]
        feedback = str(context.get("rejectionFeedback") or "").strip()
        node_payload = context.get("nodePayload") or {}
        override_repo = str(node_payload.get("resolvedRepo") or "").strip() or None

        jira_key = str(work_order.get("jiraKey") or snapshot.get("key") or "")
        project_key = str(snapshot.get("projectKey") or jira_key.split("-")[0])
        summary = str(work_order.get("title") or snapshot.get("summary") or jira_key)
        description = str(work_order.get("description") or snapshot.get("description") or "")
        vcs_provider = load_project_vcs_provider(project_key)

        if description == "Ready for Phase 2.5 validation":
            description = str(snapshot.get("description") or "")

        acceptance = extract_acceptance_criteria(description, summary=summary)
        comments = _normalize_comments(snapshot.get("comments"))
        attachment_extracts = _normalize_attachment_extracts(snapshot.get("attachmentExtracts"))
        linked = _normalize_linked(snapshot.get("linkedIssues") or snapshot.get("linkedTickets"))
        epic = snapshot.get("epic") if isinstance(snapshot.get("epic"), dict) else None

        resolved = resolve_repository(
            project_key=project_key,
            snapshot=snapshot,
            recommended_repos=recommended,
            override_repo=override_repo,
        )

        search_terms = [summary, description, feedback, jira_key]
        search_terms.extend(acceptance)
        if epic:
            search_terms.append(str(epic.get("summary") or ""))

        repo_structure: list[str] = []
        candidate_files: list[str] = []
        conventions: list[str] = []
        git_history: list[dict[str, Any]] = []
        build_notes: list[str] = []
        repo_architecture: dict[str, Any] = {}

        existing_memory = load_existing_memory(project_key=project_key)
        stored_architecture = existing_memory.get("repositoryArchitecture")
        if isinstance(stored_architecture, dict):
            repo_architecture = stored_architecture

        checkout_path = resolved.checkout_path if resolved else None
        if resolved and checkout_path:
            if architecture_profile_is_current(
                repo_architecture,
                repo_id=resolved.repo_id,
                checkout_path=checkout_path,
            ):
                preview = repo_architecture.get("structurePreview") or []
                if isinstance(preview, list):
                    repo_structure = [str(item) for item in preview[:120]]
                stored_conventions = repo_architecture.get("conventions") or []
                if isinstance(stored_conventions, list):
                    conventions = list(dict.fromkeys([*resolved.conventions, *[str(item) for item in stored_conventions]]))
                else:
                    conventions = list(resolved.conventions)
            else:
                repo_structure, candidate_files, scanned_conventions = scan_repository(
                    checkout_path,
                    search_terms=search_terms,
                )
                conventions = list(dict.fromkeys(resolved.conventions + scanned_conventions))
            if not candidate_files:
                candidate_files = _architecture_candidate_files(repo_architecture, search_terms)
            git_history = collect_git_history(checkout_path, candidate_files)
            if not candidate_files:
                build_notes.append("Repository checkout scanned but no candidate files matched ticket terms.")
        elif resolved:
            build_notes.append(f"Repository {resolved.repo_id} mapped without local checkout_path.")

        pack = ContextPack(
            jira_key=jira_key,
            jira_ticket={
                "key": jira_key,
                "summary": summary,
                "description": description,
                "status": snapshot.get("status"),
                "issueType": snapshot.get("issueType"),
                "priority": snapshot.get("priority") or work_order.get("priority"),
                "projectKey": project_key,
                "attachments": snapshot.get("attachments") if isinstance(snapshot.get("attachments"), list) else [],
            },
            jira_comments=comments,
            jira_attachment_extracts=attachment_extracts,
            acceptance_criteria=acceptance,
            epic=epic,
            linked_tickets=linked,
            identified_repo=resolved.repo_id if resolved else None,
            repo_checkout_path=checkout_path,
            repo_structure=repo_structure,
            candidate_files=candidate_files,
            project_conventions=conventions,
            git_history=git_history,
            repo_architecture=repo_architecture,
            vcs_provider=vcs_provider,
            rejection_feedback=feedback,
            resolved_repo_override=override_repo,
            build_notes=build_notes,
        )
        pack.skills_context_markdown = render_skills_context_markdown(pack)
        return pack


def _normalize_attachment_extracts(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    extracts: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        extracts.append(
            {
                "name": str(item.get("name") or "attachment"),
                "mimeType": str(item.get("mimeType") or ""),
                "extractKind": str(item.get("extractKind") or ""),
                "content": content,
                "error": str(item.get("error") or "").strip() or None,
            }
        )
    return extracts[:8]


def _normalize_comments(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    comments: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            body = str(item.get("body") or item.get("text") or "").strip()
            if body:
                comments.append(
                    {
                        "author": item.get("author"),
                        "body": body,
                    }
                )
        elif isinstance(item, str) and item.strip():
            comments.append({"author": None, "body": item.strip()})
    return comments[:10]


def _normalize_linked(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    linked: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            key = str(item.get("key") or item.get("jiraKey") or "").strip()
            if key:
                linked.append(
                    {
                        "key": key,
                        "summary": item.get("summary"),
                        "relationship": item.get("relationship") or item.get("linkType"),
                    }
                )
        elif isinstance(item, str) and item.strip():
            linked.append({"key": item.strip(), "summary": None, "relationship": None})
    return linked[:10]


def _architecture_candidate_files(profile: dict[str, Any], search_terms: list[str]) -> list[str]:
    preview = profile.get("structurePreview") or []
    if not isinstance(preview, list):
        return []
    tokens = {token.lower() for token in " ".join(search_terms).split() if len(token) >= 4}
    if not tokens:
        return [str(path) for path in preview if str(path).endswith((".py", ".ts", ".tsx", ".js", ".go", ".sql"))][:5]

    scored: list[tuple[int, str]] = []
    for raw in preview:
        path = str(raw)
        if path.endswith("/"):
            continue
        haystack = path.lower()
        score = sum(1 for token in tokens if token in haystack)
        if score:
            scored.append((score, path))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [path for _, path in scored[:5]]
