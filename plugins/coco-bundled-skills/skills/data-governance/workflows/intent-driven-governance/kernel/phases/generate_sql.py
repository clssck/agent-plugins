"""Validation for Phase 4: Generate Governance Implementation SQL."""

from __future__ import annotations

from typing import Any

from .common import artifact_state_path, has_delta, phase_artifact, validate_artifact_location, validate_phase_log_entry
from ..operations import operation_inventory, render_operations, rollback_notes, validate_operation

_ALLOWED_NON_SEMANTIC_CHANGE_CLASSES = {"non_semantic_sql_change", "equivalent_regeneration", "syntax_only"}
_UPSTREAM_CHANGE_CLASSES = {"spec_change", "intent_change"}
_REQUIRED_HEADER_MARKERS = (
    "Governance Implementation SQL",
    "Purpose:",
    "Source Artifacts:",
    "Implementation Boundary:",
    "Statement Inventory:",
    "Precheck / Dry Run Evidence:",
    "Approval Boundary:",
)
_MONITOR_OPERATION_KINDS = {
    "create_monitoring_schema",
    "create_drift_runs_table",
    "create_drift_findings_table",
    "create_drift_check_procedure",
    "create_drift_monitor_task",
    "resume_drift_monitor_task",
    "reference_notification_integration",
}


def validate_artifact(state: dict[str, Any]) -> list[str]:
    errors = validate_phase_log_entry(state, 4, "generate_sql")
    artifact = phase_artifact(state, "generate_sql")
    if artifact is None:
        errors.append("missing phase_details.generate_sql")
    else:
        errors.extend(validate_artifact_location(artifact, "generate_sql", 4))
        errors.extend(_validate_generate_sql_artifact(artifact, state))
    if not has_delta(state):
        errors.append("delta must be present")
    entry = _phase_entry(state)
    if entry and entry.get("user_agreed") is not True:
        errors.append("phase 4 requires explicit user approval of exact governance implementation SQL")
    return errors


def can_exit_phase(state: dict[str, Any]) -> bool:
    return not validate_artifact(state)


def render_governance_implementation(state: dict[str, Any]) -> str:
    artifact = phase_artifact(state, "generate_sql") or {}
    sql_file = artifact.get("sql_file", {}) if isinstance(artifact.get("sql_file"), dict) else {}
    dry_run = artifact.get("dry_run_result", {}) if isinstance(artifact.get("dry_run_result"), dict) else {}
    lines = [
        "-- Governance Implementation SQL",
        "--",
        "-- Purpose:",
        "--   Exact SQL that implements the approved Governance Spec.",
        "--",
        "-- Source Artifacts:",
        f"--   Governance Spec: {_text(artifact.get('source_governance_spec_path'), '@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/governance_spec.md')}",
        f"--   Consolidated Intent Summary: {_text(artifact.get('source_intent_path'), '@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/consolidated_intent_summary.md')}",
        f"--   Observation Summary: {_text(artifact.get('source_observation_path'), '@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/observation_summary.md')}",
        f"--   State: {_text(artifact_state_path(artifact.get('artifact_location', {})), '@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/state.yaml')}",
        "--",
        "-- Implementation Boundary:",
        "--   This file implements only the approved Governance Spec. Semantic changes must return to the Governance Spec or Intent phase before SQL regeneration.",
        "--",
        "-- Digest:",
        f"--   Source Governance Spec digest: {_text(artifact.get('source_governance_spec_digest'), 'unknown')}",
        f"--   Governance Implementation SQL digest: {_text(artifact.get('governance_implementation_digest'), 'unknown')}",
        "--",
        "-- Statement Inventory:",
    ]
    purposes = artifact.get("statement_purposes", [])
    if isinstance(purposes, list) and purposes:
        for item in purposes:
            if isinstance(item, dict):
                lines.extend([
                    f"--   {item.get('statement_index', '?')}. {_text(item.get('purpose'), 'no purpose')}",
                    f"--      Spec item: {_text(item.get('spec_item'), 'unmapped')}",
                    f"--      Destructive change: {_text(item.get('destructive_change'), 'no')}",
                    f"--      Required capabilities: {_join(item.get('required_capabilities'))}",
                ])
    else:
        statements = artifact.get("statements", [])
        if isinstance(statements, list) and statements:
            for idx, _ in enumerate(statements, 1):
                lines.append(f"--   {idx}. Statement {idx}")
        else:
            lines.append("--   None recorded")

    lines.extend([
        "--",
        "-- Precheck / Dry Run Evidence:",
        f"--   Status: {_text(dry_run.get('status'), 'not recorded')}",
    ])
    evidence = artifact.get("precheck_evidence", [])
    if isinstance(evidence, list) and evidence:
        for item in evidence:
            lines.append(f"--   - {item}")
    limitations = dry_run.get("limitations", [])
    if isinstance(limitations, list) and limitations:
        for item in limitations:
            lines.append(f"--   Limitation: {item}")

    lines.extend([
        "--",
        "-- Safety Checks:",
    ])
    safety_checks = artifact.get("safety_checks", [])
    if isinstance(safety_checks, list) and safety_checks:
        for item in safety_checks:
            lines.append(f"--   - {item}")
    else:
        lines.append("--   - None recorded")

    monitoring = artifact.get("monitoring_implementation")
    if isinstance(monitoring, dict) and monitoring.get("enabled") is True:
        lines.extend([
            "--",
            "-- Scheduled Drift Monitoring:",
            f"--   Monitor name: {_text(monitoring.get('monitor_name'), 'not recorded')}",
            f"--   Schedule: {_text(monitoring.get('schedule'), 'not recorded')}",
            f"--   Baseline tracking: {_text(monitoring.get('baseline_tracking'), 'not recorded')}",
            f"--   Drift contract: {_text(monitoring.get('drift_contract_path'), 'not recorded')}",
            "--   Automatic remediation: disabled; scheduled jobs may notify only.",
        ])

    lines.extend([
        "--",
        "-- Rollback Notes:",
    ])
    rollback_notes = artifact.get("rollback_notes", [])
    if isinstance(rollback_notes, list) and rollback_notes:
        for item in rollback_notes:
            lines.append(f"--   - {item}")
    else:
        lines.append("--   - None recorded")

    lines.extend([
        "--",
        "-- Approval Boundary:",
        "--   Approval means execution of exactly the statements below and no others.",
        "",
        _text(sql_file.get("content"), "-- SQL file content missing"),
    ])
    return "\n".join(lines)


# Legacy command compatibility.
def render_sql_review(state: dict[str, Any]) -> str:
    return render_governance_implementation(state)


def _phase_entry(state: dict[str, Any]) -> dict[str, Any] | None:
    entries = state.get("phase_log", [])
    if not isinstance(entries, list):
        return None
    matches = [entry for entry in entries if isinstance(entry, dict) and entry.get("phase") == 4]
    return matches[-1] if matches else None


def _validate_generate_sql_artifact(artifact: dict[str, Any], state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if artifact.get("implementation_status") == "superseded":
        errors.append("phase_details.generate_sql.implementation_status is superseded; regenerate from approved Governance Spec")
    if not isinstance(artifact.get("source_governance_spec_digest"), str) or not artifact.get("source_governance_spec_digest", "").strip():
        errors.append("phase_details.generate_sql.source_governance_spec_digest must be a non-empty string")
    current_spec_digest = _current_governance_spec_digest(state)
    if current_spec_digest and artifact.get("source_governance_spec_digest") != current_spec_digest:
        errors.append("phase_details.generate_sql.source_governance_spec_digest does not match current approved Governance Spec digest")
    if not isinstance(artifact.get("governance_implementation_digest"), str) or not artifact.get("governance_implementation_digest", "").strip():
        errors.append("phase_details.generate_sql.governance_implementation_digest must be a non-empty string")

    errors.extend(_validate_sql_file(artifact.get("sql_file")))

    statements = artifact.get("statements")
    if not isinstance(statements, list) or not statements:
        errors.append("phase_details.generate_sql.statements must be a non-empty list")
    elif statements != state.get("delta"):
        errors.append("phase_details.generate_sql.statements must exactly match delta")

    for list_field in ("statement_purposes", "safety_checks", "precheck_evidence", "change_requests", "rollback_notes"):
        if list_field in artifact and not isinstance(artifact[list_field], list):
            errors.append(f"phase_details.generate_sql.{list_field} must be a list")

    errors.extend(_validate_statement_purposes(artifact))
    errors.extend(_validate_typed_operations(artifact))
    errors.extend(_validate_classification_profile_prechecks(artifact))
    errors.extend(_validate_monitoring_sql_contract(artifact, state))
    errors.extend(_validate_change_requests(artifact.get("change_requests", [])))
    errors.extend(_validate_create_or_replace_safety(artifact))

    dry_run = artifact.get("dry_run_result")
    if not isinstance(dry_run, dict):
        errors.append("phase_details.generate_sql.dry_run_result must be a mapping")
    elif not isinstance(dry_run.get("status"), str) or not dry_run.get("status", "").strip():
        errors.append("phase_details.generate_sql.dry_run_result.status must be a non-empty string")

    if "implementation_sql_approval" in artifact:
        errors.extend(_validate_approval(artifact["implementation_sql_approval"], "phase_details.generate_sql.implementation_sql_approval"))
    handoff_required = artifact.get("implementation_status") == "handoff_required"
    if handoff_required:
        if artifact.get("ready_for_execution") is not False:
            errors.append("phase_details.generate_sql.ready_for_execution must be false when implementation_status is handoff_required")
        if not isinstance(artifact.get("required_privileges"), list) or not artifact.get("required_privileges"):
            errors.append("phase_details.generate_sql.required_privileges must be non-empty for handoff_required SQL")
    else:
        if artifact.get("ready_for_execution") is not True:
            errors.append("phase_details.generate_sql.ready_for_execution must be true after exact SQL approval")
        elif "implementation_sql_approval" not in artifact:
            errors.append("phase_details.generate_sql.implementation_sql_approval is required before execution")
        else:
            approval = artifact["implementation_sql_approval"]
            if isinstance(approval, dict) and approval.get("approved_sql_digest") != artifact.get("governance_implementation_digest"):
                errors.append("phase_details.generate_sql.implementation_sql_approval.approved_sql_digest must match governance_implementation_digest")

    content = artifact.get("sql_file", {}).get("content", "") if isinstance(artifact.get("sql_file"), dict) else ""
    errors.extend(_validate_governance_implementation_contains_exact_sql(artifact))
    for marker in _REQUIRED_HEADER_MARKERS:
        if marker not in content:
            errors.append(f"phase_details.generate_sql.sql_file.content missing header marker: {marker}")
    return errors


def _validate_monitoring_sql_contract(artifact: dict[str, Any], state: dict[str, Any]) -> list[str]:
    spec = phase_artifact(state, "derive_specs_plan") or {}
    monitoring_intent = spec.get("monitoring_intent") if isinstance(spec.get("monitoring_intent"), dict) else {}
    if monitoring_intent.get("enabled") is not True:
        return []
    errors: list[str] = []
    implementation = artifact.get("monitoring_implementation")
    if not isinstance(implementation, dict) or implementation.get("enabled") is not True:
        errors.append("phase_details.generate_sql.monitoring_implementation.enabled must be true when Governance Spec includes monitoring intent")
    else:
        for field in ("monitor_name", "schedule", "baseline_tracking", "drift_contract_path", "monitor_execution_role", "no_auto_remediation"):
            if field not in implementation:
                errors.append(f"phase_details.generate_sql.monitoring_implementation.{field} is required")
        if implementation.get("no_auto_remediation") is not True:
            errors.append("phase_details.generate_sql.monitoring_implementation.no_auto_remediation must be true")
    operations = artifact.get("operations")
    op_kinds = {str(operation.get("op", "")).strip().lower() for operation in operations if isinstance(operation, dict)} if isinstance(operations, list) else set()
    missing = sorted(_MONITOR_OPERATION_KINDS - op_kinds)
    if missing:
        errors.append("phase_details.generate_sql.operations missing scheduled drift monitoring operations: " + ", ".join(missing))
    content = artifact.get("sql_file", {}).get("content", "") if isinstance(artifact.get("sql_file"), dict) else ""
    markers = ["Scheduled Drift Monitoring", "RUN_GOVERNANCE_DRIFT_CHECK"]
    if isinstance(implementation, dict) and implementation.get("notification_integration"):
        markers.append("SYSTEM$SEND_EMAIL")
    for marker in markers:
        if marker not in content:
            errors.append(f"phase_details.generate_sql.sql_file.content missing monitoring marker: {marker}")
    lowered = content.lower()
    if "auto_remediate" in lowered or "automatic remediation: enabled" in lowered:
        errors.append("phase_details.generate_sql.sql_file.content must not enable scheduled auto-remediation")
    return errors


def _current_governance_spec_digest(state: dict[str, Any]) -> str | None:
    artifact = phase_artifact(state, "derive_specs_plan") or {}
    digest = artifact.get("governance_spec_digest") or artifact.get("scoped_digest") or state.get("scoped_digest")
    return digest if isinstance(digest, str) and digest.strip() else None


def _validate_approval(value: Any, prefix: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{prefix} must be a mapping"]
    errors: list[str] = []
    for field in ("approved_by", "approver_persona", "approved_at", "approved_sql_digest", "approval_scope"):
        if not isinstance(value.get(field), str) or not value.get(field, "").strip():
            errors.append(f"{prefix}.{field} must be a non-empty string")
    return errors


def _validate_sql_file(sql_file: Any) -> list[str]:
    if not isinstance(sql_file, dict):
        return ["phase_details.generate_sql.sql_file must be a mapping"]
    errors: list[str] = []
    path = sql_file.get("path")
    if not isinstance(path, str) or not path.strip():
        errors.append("phase_details.generate_sql.sql_file.path must be a non-empty string")
    elif not path.endswith("/governance_implementation.sql") and not path.endswith("governance_implementation.sql"):
        errors.append("phase_details.generate_sql.sql_file.path must be the working governance_implementation.sql path")
    if not isinstance(sql_file.get("content"), str) or not sql_file.get("content", "").strip():
        errors.append("phase_details.generate_sql.sql_file.content must be a non-empty string")
    return errors


def _validate_statement_purposes(artifact: dict[str, Any]) -> list[str]:
    purposes = artifact.get("statement_purposes")
    statements = artifact.get("statements")
    if not isinstance(purposes, list) or not isinstance(statements, list):
        return []
    errors: list[str] = []
    if len(purposes) != len(statements):
        errors.append("phase_details.generate_sql.statement_purposes must map every statement")
    for idx, item in enumerate(purposes):
        if not isinstance(item, dict):
            errors.append(f"phase_details.generate_sql.statement_purposes[{idx}] must be a mapping")
            continue
        for field in ("statement_index", "purpose", "spec_item", "destructive_change"):
            if field not in item:
                errors.append(f"phase_details.generate_sql.statement_purposes[{idx}].{field} is required")
        destructive = item.get("destructive_change")
        if destructive not in ("no", "yes") and not isinstance(destructive, bool):
            errors.append(f"phase_details.generate_sql.statement_purposes[{idx}].destructive_change must be yes/no")
        if destructive in ("yes", True) and not item.get("destructive_change_id"):
            errors.append(f"phase_details.generate_sql.statement_purposes[{idx}].destructive_change_id is required for destructive statements")
    return errors


def _validate_typed_operations(artifact: dict[str, Any]) -> list[str]:
    if "operations" not in artifact:
        return []
    operations = artifact.get("operations")
    if not isinstance(operations, list) or not operations:
        return ["phase_details.generate_sql.operations must be a non-empty list when present"]
    try:
        for idx, operation in enumerate(operations):
            operation_errors = validate_operation(operation)
            if operation_errors:
                return [
                    f"phase_details.generate_sql.operations[{idx}] invalid: {error}"
                    for error in operation_errors
                ]
        rendered_statements = render_operations(operations)
        rendered_purposes = operation_inventory(operations)
        rendered_rollback_notes = rollback_notes(operations)
    except Exception as exc:
        return [f"phase_details.generate_sql.operations invalid: {exc}"]

    errors: list[str] = []
    if artifact.get("statements") != rendered_statements:
        errors.append("phase_details.generate_sql.statements must match rendered typed operations")
    purposes = artifact.get("statement_purposes")
    if isinstance(purposes, list) and len(purposes) == len(rendered_purposes):
        for idx, expected in enumerate(rendered_purposes):
            actual = purposes[idx]
            if not isinstance(actual, dict):
                continue
            for field in ("statement_index", "spec_item"):
                if actual.get(field) != expected[field]:
                    errors.append(f"phase_details.generate_sql.statement_purposes[{idx}].{field} must match typed operation")
            if _destructive_text(actual.get("destructive_change")) != expected["destructive_change"]:
                errors.append(f"phase_details.generate_sql.statement_purposes[{idx}].destructive_change must match typed operation")
    rollback = artifact.get("rollback_notes")
    if isinstance(rollback, list) and rollback and rollback != rendered_rollback_notes:
        errors.append("phase_details.generate_sql.rollback_notes must match rendered typed operations when supplied")
    return errors


def _validate_classification_profile_prechecks(artifact: dict[str, Any]) -> list[str]:
    operations = artifact.get("operations")
    if not isinstance(operations, list) or not any(
        isinstance(operation, dict) and operation.get("op") == "create_classification_profile"
        for operation in operations
    ):
        return []

    if artifact.get("implementation_status") == "handoff_required" and artifact.get("ready_for_execution") is False:
        return []

    evidence_items = artifact.get("precheck_evidence", [])
    if not isinstance(evidence_items, list):
        evidence_items = []
    evidence_text = "\n".join(str(item).lower() for item in evidence_items)
    has_profile_precheck = (
        "show instances of class snowflake.data_privacy.classification_profile in account" in evidence_text
        or "show snowflake.data_privacy.classification_profile in schema" in evidence_text
    )
    proves_absence = any(
        phrase in evidence_text
        for phrase in (
            "target profile absent",
            "profile absent",
            "object absence confirmed",
            "does not exist",
            "no matching profile found",
            "0 rows returned",
            "zero rows returned",
        )
    )
    if has_profile_precheck and proves_absence:
        return []

    return [
        "phase_details.generate_sql.precheck_evidence must include classification profile object-absence evidence before create_classification_profile can be execution-ready"
    ]


def _validate_change_requests(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    errors: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"phase_details.generate_sql.change_requests[{idx}] must be a mapping")
            continue
        classification = item.get("classification")
        if classification in _UPSTREAM_CHANGE_CLASSES:
            errors.append(f"phase_details.generate_sql.change_requests[{idx}] requires routing to upstream phase before exit")
        elif classification not in _ALLOWED_NON_SEMANTIC_CHANGE_CLASSES:
            errors.append(f"phase_details.generate_sql.change_requests[{idx}].classification is invalid or missing")
    return errors


def _destructive_text(value: Any) -> str:
    return "yes" if value in ("yes", True) else "no"


def _validate_create_or_replace_safety(artifact: dict[str, Any]) -> list[str]:
    statements = artifact.get("statements")
    if not isinstance(statements, list):
        return []
    joined = "\n".join(str(statement).upper() for statement in statements)
    if "CREATE OR REPLACE" not in joined:
        return []
    safety_checks = artifact.get("safety_checks", [])
    purposes = artifact.get("statement_purposes", [])
    has_absence_precheck = any("does not exist" in str(check).lower() or "object absence" in str(check).lower() for check in safety_checks if isinstance(safety_checks, list))
    has_destructive_mapping = any(
        isinstance(item, dict) and item.get("destructive_change") in ("yes", True) and item.get("destructive_change_id")
        for item in purposes if isinstance(purposes, list)
    )
    if not (has_absence_precheck or has_destructive_mapping):
        return ["CREATE OR REPLACE requires object-absence precheck or approved destructive replacement mapping"]
    return []


def _validate_governance_implementation_contains_exact_sql(artifact: dict[str, Any]) -> list[str]:
    statements = artifact.get("statements", [])
    sql_file = artifact.get("sql_file", {})
    content = sql_file.get("content", "") if isinstance(sql_file, dict) else ""
    errors: list[str] = []
    for idx, statement in enumerate(statements if isinstance(statements, list) else []):
        if isinstance(statement, str) and statement.strip() and statement.strip() not in content:
            errors.append(f"phase_details.generate_sql.sql_file.content missing exact statement {idx + 1}")
    return errors


def _text(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) and value.strip() else fallback


def _join(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "none recorded"
    return ", ".join(str(item) for item in value)
