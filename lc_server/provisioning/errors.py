"""Provisioning errors for project automation setup."""

from __future__ import annotations


class ProvisionError(Exception):
    """Raised when project automation provisioning prerequisites are not met."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = list(missing)
        codes = ", ".join(self.missing) if self.missing else "none"
        super().__init__(f"Missing provisioning prerequisites: {codes}")
