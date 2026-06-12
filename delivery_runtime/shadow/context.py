"""Delivery-runtime execution context (internal git allowance, agent role)."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Iterator

_internal_git_allowed: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "livingcolor_internal_git_allowed",
    default=False,
)


def internal_git_allowed() -> bool:
    return _internal_git_allowed.get()


@contextmanager
def allow_internal_git() -> Iterator[None]:
    token = _internal_git_allowed.set(True)
    try:
        yield
    finally:
        _internal_git_allowed.reset(token)


_delivery_agent_role: contextvars.ContextVar[str] = contextvars.ContextVar(
    "delivery_agent_role",
    default="",
)


def current_delivery_agent_role() -> str:
    return _delivery_agent_role.get()


@contextmanager
def delivery_agent_role(role: str) -> Iterator[None]:
    token = _delivery_agent_role.set(role)
    try:
        yield
    finally:
        _delivery_agent_role.reset(token)
