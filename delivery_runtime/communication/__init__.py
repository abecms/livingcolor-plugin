"""Project communication language helpers."""

from delivery_runtime.communication.language import (
    DEFAULT_COMMUNICATION_LANGUAGE,
    SUPPORTED_COMMUNICATION_LANGUAGES,
    get_clarification_comment_template,
    get_mr_labels,
    get_not_development_comment_template,
    get_stakeholder_output_instruction,
    normalize_communication_language,
)

__all__ = [
    "DEFAULT_COMMUNICATION_LANGUAGE",
    "SUPPORTED_COMMUNICATION_LANGUAGES",
    "get_clarification_comment_template",
    "get_mr_labels",
    "get_not_development_comment_template",
    "get_stakeholder_output_instruction",
    "normalize_communication_language",
]
