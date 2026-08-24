"""Shared helpers for phase detail validation."""

from __future__ import annotations

from typing import Any


def phase_entries(state: dict[str, Any], phase_number: int) -> list[dict[str, Any]]:
    entries = state.get("phase_log", [])
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict) and entry.get("phase") == phase_number]


def latest_phase_entry(state: dict[str, Any], phase_number: int) -> dict[str, Any] | None:
    entries = phase_entries(state, phase_number)
    return entries[-1] if entries else None


def has_user_agreement(state: dict[str, Any], phase_number: int) -> bool:
    entry = latest_phase_entry(state, phase_number)
    return bool(entry and entry.get("user_agreed") is True)


def validate_phase_log_entry(state: dict[str, Any], phase_number: int, name: str) -> list[str]:
    errors: list[str] = []
    entry = latest_phase_entry(state, phase_number)
    if entry is None:
        return [f"missing phase_log entry for phase {phase_number}"]
    if entry.get("name") != name:
        errors.append(f"phase {phase_number} phase_log.name must be {name!r}")
    if not isinstance(entry.get("summary"), str) or not entry.get("summary", "").strip():
        errors.append(f"phase {phase_number} phase_log.summary must be non-empty")
    if not isinstance(entry.get("when"), str) or not entry.get("when", "").strip():
        errors.append(f"phase {phase_number} phase_log.when must be non-empty")
    return errors


def has_observed_state(state: dict[str, Any]) -> bool:
    return bool(state.get("observed_fetched_at"))


def has_delta(state: dict[str, Any]) -> bool:
    return isinstance(state.get("delta"), list)


def phase_artifact(state: dict[str, Any], name: str) -> dict[str, Any] | None:
    details = state.get("phase_details", {})
    if not isinstance(details, dict):
        return None
    artifact = details.get(name)
    return artifact if isinstance(artifact, dict) else None


def require_phase_artifact(state: dict[str, Any], name: str) -> list[str]:
    return [] if phase_artifact(state, name) is not None else [f"missing phase_details.{name}"]


def validate_artifact_location(artifact: dict[str, Any], phase_name: str, phase_number: int) -> list[str]:
    errors: list[str] = []
    location = artifact.get("artifact_location")
    if not isinstance(location, dict):
        errors.append(f"phase_details.{phase_name}.artifact_location must be a mapping")
    else:
        state_path = location.get("working_state_path") or location.get("state_path")
        if not isinstance(state_path, str) or not state_path.strip():
            errors.append(
                f"phase_details.{phase_name}.artifact_location.working_state_path must be a non-empty string"
            )
        if not isinstance(location.get("customer_artifact_path"), str) or not location.get("customer_artifact_path", "").strip():
            errors.append(f"phase_details.{phase_name}.artifact_location.customer_artifact_path must be a non-empty string")

    progress = artifact.get("progress")
    if not isinstance(progress, dict):
        errors.append(f"phase_details.{phase_name}.progress must be a mapping")
    else:
        if progress.get("current_phase") != phase_number:
            errors.append(f"phase_details.{phase_name}.progress.current_phase must be {phase_number}")
        if progress.get("current_phase_name") != phase_name:
            errors.append(f"phase_details.{phase_name}.progress.current_phase_name must be {phase_name!r}")
        completed_phases = progress.get("completed_phases")
        if not isinstance(completed_phases, list):
            errors.append(f"phase_details.{phase_name}.progress.completed_phases must be a list")
        elif completed_phases != list(range(phase_number + 1)):
            errors.append(
                f"phase_details.{phase_name}.progress.completed_phases must exactly equal every phase from 0 through {phase_number} in order"
            )
        if not isinstance(progress.get("status"), str) or not progress.get("status", "").strip():
            errors.append(f"phase_details.{phase_name}.progress.status must be a non-empty string")
        if "working_status" in progress and progress.get("working_status") not in {"dirty", "awaiting_customer_approval", "clean"}:
            errors.append(
                f"phase_details.{phase_name}.progress.working_status must be dirty, awaiting_customer_approval, or clean"
            )

    if not isinstance(artifact.get("customer_message"), str) or not artifact.get("customer_message", "").strip():
        errors.append(f"phase_details.{phase_name}.customer_message must be a non-empty string")
    return errors


def artifact_state_path(location: dict[str, Any]) -> str | None:
    value = location.get("working_state_path") or location.get("state_path")
    return value if isinstance(value, str) and value.strip() else None
