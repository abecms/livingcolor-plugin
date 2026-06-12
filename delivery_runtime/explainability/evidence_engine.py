"""Evidence extraction for explainable delivery (Phase 4B)."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from delivery_runtime.explainability.models import EvidenceItem

TEST_MARKERS = ("/tests/", "/test/", ".test.", ".spec.", "_test.", "/__tests__/")
UI_MARKERS = ("/components/", "/pages/", "/views/", "/ui/", ".tsx", ".jsx", ".css", ".scss")
API_MARKERS = ("/api/", "/routes/", "/controllers/", "/handlers/", "/services/", "service.", "controller.")
DB_MARKERS = ("/migrations/", "/models/", ".sql", "/schema/", "/db/")


def collect_ticket_text(jira_snapshot: dict[str, Any], approved_plan: dict[str, Any]) -> str:
    parts = [
        str(jira_snapshot.get("summary") or ""),
        str(jira_snapshot.get("description") or ""),
        str(approved_plan.get("ticketUnderstanding") or ""),
    ]
    jira_context = approved_plan.get("jiraContextUsed") or {}
    acceptance = jira_context.get("acceptanceCriteria")
    if isinstance(acceptance, list):
        parts.extend(str(item) for item in acceptance)
    elif acceptance:
        parts.append(str(acceptance))
    return " ".join(part for part in parts if part).strip()


def count_ticket_references(path: str, ticket_text: str) -> int:
    if not ticket_text:
        return 0
    stem_tokens = _path_tokens(path)
    ticket_tokens = set(re.findall(r"[a-zA-ZÀ-ÿ0-9]{3,}", ticket_text.lower()))
    matches = 0
    for token in stem_tokens:
        if token in ticket_tokens:
            matches += 1
        if any(token in other or other in token for other in ticket_tokens if len(other) >= 4):
            matches += 1
    return matches


def build_file_evidence(
    *,
    path: str,
    ticket_text: str,
    approved_plan: dict[str, Any],
    context_pack: dict[str, Any],
    code_review_payload: dict[str, Any],
    scope_contract: dict[str, Any] | None = None,
) -> tuple[list[str], list[EvidenceItem]]:
    """Return human bullets and structured evidence for one touched file."""
    why: list[str] = []
    evidence: list[EvidenceItem] = []

    reference_count = count_ticket_references(path, ticket_text)
    if reference_count:
        why.append(f"{reference_count} ticket reference{'s' if reference_count != 1 else ''} matched this path")
        evidence.append(
            EvidenceItem(
                source="jira",
                summary=f"{reference_count} ticket references matched",
                detail=_matching_ticket_phrase(path, ticket_text),
            )
        )

    ticket_phrase = _describe_ticket_link(path, ticket_text)
    if ticket_phrase:
        why.append(ticket_phrase)
        evidence.append(EvidenceItem(source="jira", summary=ticket_phrase))

    likely_impacted = [str(item) for item in approved_plan.get("likelyImpactedFiles") or []]
    if path in likely_impacted:
        why.append("Implementation planner selected this file for the approved plan")
        evidence.append(EvidenceItem(source="planner", summary="Selected in Gate 1 likelyImpactedFiles"))

    candidate_files = [str(item) for item in context_pack.get("candidate_files") or []]
    if path in candidate_files:
        rank = candidate_files.index(path) + 1
        why.append(f"Context Pack ranked this file #{rank} among repository candidates")
        evidence.append(
            EvidenceItem(
                source="context_pack",
                summary=f"Ranked #{rank} in candidate_files",
            )
        )

    scope_contract = scope_contract or {}
    allowed_files = [str(item) for item in scope_contract.get("allowedFiles") or []]
    if allowed_files and path in allowed_files:
        evidence.append(EvidenceItem(source="scope_contract", summary="Within approved scope contract"))

    touched = _touched_paths(code_review_payload)
    if path in touched:
        why.append("Patch evidence confirms this file was modified or created")
        evidence.append(EvidenceItem(source="patch", summary="Present in developer patch output"))

    role = infer_file_role(path)
    if role:
        why.append(role)
        evidence.append(EvidenceItem(source="repo_structure", summary=role))

    test_run = code_review_payload.get("testRun") or {}
    if _looks_like_test_path(path) and test_run.get("passed"):
        why.append("Associated tests ran successfully")
        evidence.append(EvidenceItem(source="tests", summary="Test run passed for this change set"))

    if not why:
        why.append("File appears in the delivery patch without stronger upstream signals")
        evidence.append(EvidenceItem(source="patch", summary="Only patch output linked this file"))

    return _dedupe_preserve(why), evidence


def infer_file_role(path: str) -> str:
    lowered = path.lower()
    name = PurePosixPath(path).name
    if _looks_like_test_path(path):
        return "This file adds or updates automated test coverage"
    if any(marker in lowered for marker in UI_MARKERS) or name.endswith((".tsx", ".jsx")):
        return "This component or view is responsible for the UI rendering path"
    if any(marker in lowered for marker in API_MARKERS):
        return "This module participates in API or service-layer behavior"
    if any(marker in lowered for marker in DB_MARKERS):
        return "This file may affect persistence or schema behavior"
    return ""


def rejected_alternatives_for_file(
    *,
    selected_path: str,
    files_modified: list[str],
    approved_plan: dict[str, Any],
    context_pack: dict[str, Any],
) -> list[str]:
    candidates = _unique_paths(
        list(context_pack.get("candidate_files") or [])
        + list(approved_plan.get("likelyImpactedFiles") or [])
    )
    selected = set(files_modified)
    rejected = [path for path in candidates if path not in selected and path != selected_path]
    return rejected[:5]


def _describe_ticket_link(path: str, ticket_text: str) -> str:
    if not ticket_text:
        return ""
    lowered_ticket = ticket_text.lower()
    stem = PurePosixPath(path).stem.lower().replace("_", " ").replace("-", " ")
    for phrase in (
        "thumbnail",
        "vignette",
        "author",
        "auteur",
        "criteria",
        "critere",
        "oauth",
        "render",
        "component",
    ):
        if phrase in lowered_ticket and phrase.replace(" ", "") in stem.replace(" ", ""):
            return f"Ticket mentions {phrase}-related behavior aligned with this module"
    return ""


def _matching_ticket_phrase(path: str, ticket_text: str) -> str:
    stem_tokens = _path_tokens(path)
    ticket_tokens = set(re.findall(r"[a-zA-ZÀ-ÿ0-9]{3,}", ticket_text.lower()))
    overlap = sorted(token for token in stem_tokens if token in ticket_tokens)
    if overlap:
        return ", ".join(overlap[:4])
    return ""


def _path_tokens(path: str) -> list[str]:
    stem = PurePosixPath(path).stem.lower()
    parts = re.split(r"[_\-. /]+", stem)
    return [part for part in parts if len(part) >= 3]


def _looks_like_test_path(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in TEST_MARKERS)


def _touched_paths(code_review_payload: dict[str, Any]) -> list[str]:
    return _unique_paths(
        list(code_review_payload.get("filesModified") or [])
        + list(code_review_payload.get("filesCreated") or [])
    )


def _unique_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in paths:
        path = str(item).strip().replace("\\", "/")
        if not path or path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return ordered


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered
