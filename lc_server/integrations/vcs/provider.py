"""Shared VCS provider types and resolution helpers."""

from __future__ import annotations

from typing import Literal

VcsProviderName = Literal["gitlab", "github"]
DEFAULT_VCS_PROVIDER: VcsProviderName = "gitlab"
SUPPORTED_VCS_PROVIDERS: tuple[VcsProviderName, ...] = ("gitlab", "github")


def normalize_vcs_provider(value: object) -> VcsProviderName:
    raw = str(value or "").strip().lower()
    if not raw:
        return DEFAULT_VCS_PROVIDER
    if raw in SUPPORTED_VCS_PROVIDERS:
        return raw  # type: ignore[return-value]
    raise ValueError(f"Unsupported VCS provider: {raw}")
