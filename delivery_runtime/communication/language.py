"""Localized templates for Jira comments, MR drafts, and stakeholder communications."""

from __future__ import annotations

from typing import Any

SUPPORTED_COMMUNICATION_LANGUAGES = ("en", "fr")
DEFAULT_COMMUNICATION_LANGUAGE = "fr"

_CLARIFICATION_TEMPLATES = {
    "en": """I do not currently have enough information to work on this ticket.

Please provide:
- reproduction steps
- impacted URL
- expected behaviour
- observed behaviour
- screenshots if available""",
    "fr": """Je n'ai pas actuellement assez d'informations pour travailler sur ce ticket.

Merci de préciser :
- les étapes de reproduction
- l'URL impactée
- le comportement attendu
- le comportement observé
- des captures d'écran si disponibles""",
}

_NOT_DEVELOPMENT_TEMPLATES = {
    "en": """This ticket does not appear to be a development delivery item.

LivingColor has classified it as a non-development request (for example content, editorial, support, or business questions). Please confirm whether engineering work is required or route it to the appropriate team.""",
    "fr": """Ce ticket ne semble pas être un item de livraison développement.

LivingColor l'a classé comme une demande non-développement (par exemple contenu, éditorial, support ou question métier). Merci de confirmer si un travail d'ingénierie est requis ou de l'orienter vers l'équipe appropriée.""",
}

_MR_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "acceptanceCriteria": "Acceptance criteria",
        "build": "Build",
        "changes": "Changes",
        "confidence": "Confidence",
        "context": "Context",
        "filesImpacted": "Files Impacted",
        "noFilesRecorded": "No files recorded in the patch.",
        "noImplementationSummary": "No implementation summary captured.",
        "noReasoningCaptured": "No reasoning captured.",
        "noReviewersConfigured": "No reviewers configured.",
        "noRisksRecorded": "No risks recorded.",
        "noTicketContext": "No ticket context captured.",
        "overallConfidence": "Overall confidence",
        "reasoningSummary": "Reasoning Summary",
        "recommendedReviewers": "Recommended Reviewers",
        "rejectedAlternatives": "Rejected alternatives",
        "repositoryOwnerFor": "Repository owner for {repo_id}",
        "riskAssessment": "Risk Assessment",
        "risks": "Risks",
        "scopeValidation": "Scope validation",
        "tests": "Tests",
        "validation": "Validation",
        "whyFile": "Why `{path}`?",
    },
    "fr": {
        "acceptanceCriteria": "Critères d'acceptation",
        "build": "Build",
        "changes": "Modifications",
        "confidence": "Confiance",
        "context": "Contexte",
        "filesImpacted": "Fichiers impactés",
        "noFilesRecorded": "Aucun fichier enregistré dans le patch.",
        "noImplementationSummary": "Aucun résumé d'implémentation enregistré.",
        "noReasoningCaptured": "Aucun raisonnement enregistré.",
        "noReviewersConfigured": "Aucun reviewer configuré.",
        "noRisksRecorded": "Aucun risque enregistré.",
        "noTicketContext": "Aucun contexte ticket enregistré.",
        "overallConfidence": "Confiance globale",
        "reasoningSummary": "Synthèse du raisonnement",
        "recommendedReviewers": "Reviewers recommandés",
        "rejectedAlternatives": "Alternatives rejetées",
        "repositoryOwnerFor": "Owner du dépôt pour {repo_id}",
        "riskAssessment": "Évaluation des risques",
        "risks": "Risques",
        "scopeValidation": "Validation du périmètre",
        "tests": "Tests",
        "validation": "Validation",
        "whyFile": "Pourquoi `{path}` ?",
    },
}

_STAKEHOLDER_OUTPUT_INSTRUCTIONS = {
    "en": "Write all generated text in English.",
    "fr": "Rédige tout le texte généré en français.",
}


def normalize_communication_language(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in SUPPORTED_COMMUNICATION_LANGUAGES:
        return text
    if text.startswith("fr"):
        return "fr"
    if text.startswith("en"):
        return "en"
    return DEFAULT_COMMUNICATION_LANGUAGE


def get_clarification_comment_template(language: str | None = None) -> str:
    lang = normalize_communication_language(language)
    return _CLARIFICATION_TEMPLATES[lang]


def get_not_development_comment_template(language: str | None = None) -> str:
    lang = normalize_communication_language(language)
    return _NOT_DEVELOPMENT_TEMPLATES[lang]


def get_mr_labels(language: str | None = None) -> dict[str, str]:
    lang = normalize_communication_language(language)
    return dict(_MR_LABELS[lang])


def get_stakeholder_output_instruction(language: str | None = None) -> str:
    lang = normalize_communication_language(language)
    return _STAKEHOLDER_OUTPUT_INSTRUCTIONS[lang]
