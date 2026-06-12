"""Detect whether a Jira ticket description is actionable for delivery."""

from __future__ import annotations

import unicodedata

from delivery_runtime.context.acceptance import extract_acceptance_criteria

ACCEPTANCE_MARKERS = (
    "acceptance criteria",
    "acceptance criterion",
    "given ",
    "when ",
    "then ",
    "- [ ]",
    "criteria:",
    "ac:",
    "definition of done",
    "dod:",
    "critères d'acceptation",
    "criteres d'acceptation",
    "critère d'acceptation",
    "criteres d acceptation",
    "résultat attendu",
    "resultat attendu",
    "résultat observé",
    "resultat observe",
    "résultat obtenu",
    "resultat obtenu",
    "comportement attendu",
    "comportement observé",
    "expected result",
    "actual result",
    "observed result",
)

REPRO_MARKERS = (
    "steps to reproduce",
    "reproduction steps",
    "repro steps",
    "how to reproduce",
    "étapes pour reproduire",
    "etapes pour reproduire",
    "étapes de reproduction",
    "etapes de reproduction",
    "comment reproduire",
    "pour reproduire",
    "étape 1",
    "etape 1",
)

URL_MARKERS = ("http://", "https://", "www.", " url:", "page:", "route:", "path:")

ACTIONABLE_CONTEXT_MARKERS = (
    "probleme",
    "problem",
    "pose un probleme",
    "impact",
    "objectif",
    "goal",
    "solution",
    "solutions",
    "comportement",
    "behaviour",
    "behavior",
    "seo",
    "rendering",
    "rendu",
    "crawl",
    "google",
    "cote client",
    "client side",
    "javascript",
    "html",
    "generee",
    "generated",
    "pas presente",
    "not present",
    "n'est pas",
    "doit",
    "should",
    "must",
    "expected",
    "observed",
    "fix",
    "corriger",
    "regler",
    "voir slides",
    "voir pj",
    "piece jointe",
    "attachment",
    "pj ",
)


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.lower().split())


def has_reproduction_steps(description: str) -> bool:
    text = _normalize_text(description)
    if not text:
        return False
    if any(marker in text for marker in REPRO_MARKERS):
        return True
    return "etape " in text and "reproduire" in text


def has_impacted_url(description: str) -> bool:
    text = _normalize_text(description)
    return any(marker in text for marker in URL_MARKERS)


def is_infrastructure_blocker(blocker: str) -> bool:
    text = _normalize_text(blocker)
    return "repository" in text and "could not be resolved" in text


def has_structured_bug_report(description: str) -> bool:
    text = _normalize_text(description)
    if not text:
        return False
    has_expected = any(
        token in text
        for token in (
            "resultat attendu",
            "expected result",
            "comportement attendu",
        )
    )
    has_observed = any(
        token in text
        for token in (
            "resultat observe",
            "resultat obtenu",
            "actual result",
            "observed result",
            "comportement observe",
        )
    )
    return has_reproduction_steps(description) and has_expected and has_observed


def _has_explicit_acceptance_markers(description: str) -> bool:
    text = (description or "").strip()
    if not text:
        return False

    normalized = _normalize_text(text)
    if any(marker in normalized for marker in ACCEPTANCE_MARKERS):
        return True

    extracted = extract_acceptance_criteria(text)
    return len(extracted) >= 2


def has_actionable_specification(
    description: str,
    *,
    issue_type: str = "",
    summary: str = "",
) -> bool:
    """Treat rich narrative specs (URL + problem/impact) as actionable for delivery."""
    text = (description or "").strip()
    if len(text) < 80:
        return False

    if _has_explicit_acceptance_markers(text):
        return True

    normalized = _normalize_text(f"{summary} {text}")
    issue = _normalize_text(issue_type)

    if issue == "bug":
        if has_structured_bug_report(text):
            return True
        if has_impacted_url(text) and has_reproduction_steps(text):
            return True

    context_hits = sum(1 for marker in ACTIONABLE_CONTEXT_MARKERS if marker in normalized)
    if has_impacted_url(text):
        if context_hits >= 2:
            return True
        if len(text) >= 200 and context_hits >= 1:
            return True

    if len(text) >= 250 and context_hits >= 3:
        return True

    return False


def has_acceptance_criteria(
    description: str,
    *,
    issue_type: str = "",
    summary: str = "",
) -> bool:
    text = (description or "").strip()
    if not text:
        return False

    if _has_explicit_acceptance_markers(text):
        return True

    issue = _normalize_text(issue_type)
    if issue == "bug" and has_structured_bug_report(text):
        return True

    return has_actionable_specification(
        text,
        issue_type=issue_type,
        summary=summary,
    )
