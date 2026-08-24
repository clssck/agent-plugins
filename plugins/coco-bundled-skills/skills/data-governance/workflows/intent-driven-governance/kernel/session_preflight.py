"""Session-only capability routing for intent-driven-governance.

This module intentionally does not read or write durable workflow state. It
converts current-session capability probe results into statement routing for the
active turn only.
"""

from __future__ import annotations

from typing import Any

from .core import ValidationError
from .operations import required_capabilities, route_operations

_CAPABILITY_STATUSES = {"confirmed", "probable", "unknown", "handoff_required", "unsafe_until_visible"}
_EXECUTABLE_STATUSES = {"confirmed", "probable"}


def statement_capability_statuses(
    operations: list[dict[str, Any]],
    capability_status_by_requirement: dict[str, str],
) -> dict[int, str]:
    """Return ephemeral statement statuses from current-session capability probes."""

    if not isinstance(capability_status_by_requirement, dict):
        raise ValidationError("capability_status_by_requirement must be a mapping")
    statuses: dict[int, str] = {}
    for index, operation in enumerate(operations, 1):
        requirement_statuses = [
            _capability_status(capability_status_by_requirement.get(requirement, "unknown"))
            for requirement in required_capabilities(operation)
        ]
        statuses[index] = _combine_requirement_statuses(requirement_statuses)
    return statuses


def route_operations_for_session(
    operations: list[dict[str, Any]],
    capability_status_by_requirement: dict[str, str],
) -> dict[str, list[int]]:
    """Route durable operations using only current-session capability results."""

    statuses = statement_capability_statuses(operations, capability_status_by_requirement)
    return route_operations(operations, statuses)


def _capability_status(value: Any) -> str:
    if value not in _CAPABILITY_STATUSES:
        raise ValidationError(f"capability status must be one of {sorted(_CAPABILITY_STATUSES)}")
    return str(value)


def _combine_requirement_statuses(statuses: list[str]) -> str:
    if not statuses:
        return "unknown"
    if any(status == "unsafe_until_visible" for status in statuses):
        return "unsafe_until_visible"
    if any(status in {"handoff_required", "unknown"} for status in statuses):
        return "handoff_required"
    if any(status == "probable" for status in statuses):
        return "probable"
    if all(status in _EXECUTABLE_STATUSES for status in statuses):
        return "confirmed"
    return "unknown"
