"""Request/response models for the LivingColor cloud API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class UserPreferencesUpdate(BaseModel):
    selectedJiraProjectKey: str | None = None


class ProjectConfigUpdate(BaseModel):
    projectName: str | None = None
    mapping: dict[str, Any] | None = None
    deliverySettings: dict[str, Any] | None = None


class CreateTeamOrgBody(BaseModel):
    name: str


class ActiveOrgUpdate(BaseModel):
    orgId: str


class InviteMemberBody(BaseModel):
    email: str
    role: str = "member"


class CreateOrgProjectBody(BaseModel):
    jiraProjectKey: str
    projectName: str


class ShareLocalProjectBody(BaseModel):
    jiraProjectKey: str
    projectName: str | None = None
    mapping: dict[str, Any] | None = None
    deliverySettings: dict[str, Any] | None = None
