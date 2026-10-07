"""Validation for Phase 5: Execute SQL."""

from __future__ import annotations

import re
from typing import Any

from .common import artifact_state_path, has_observed_state, phase_artifact, validate_artifact_location, validate_phase_log_entry

_REQUIRED_EXECUTION_HEADINGS = (
    "Purpose",
    "Source Artifacts",
    "Execution Boundary",
    "Statement Execution Inventory",
    "Post-Execution Verification",
    "Preservation Checks",
    "Destructive Change Result",
    "Committed Version",
    "Remaining Gaps",
    "Closing Status",
)
_REQUIRED_COMMITTED_ARTIFACTS = (
    "state",
    "observation_summary",
    "consolidated_intent_summary",
    "governance_spec",
    "governance_implementation",
    "execution_summary",
)
_REQUIRED_MONITORING_ARTIFACTS = ("drift_contract", "drift_monitor_summary")
_REQUIRED_LATEST_MONITORING_ARTIFACTS = ("latest_drift_contract",)


def validate_artifact(state: dict[str, Any]) -> list[str]:
    errors = validate_phase_log_entry(state, 5, "execute_sql")
    artifact = phase_artifact(state, "execute_sql")
    if artifact is None:
        errors.append("missing phase_details.execute_sql")
    else:
        errors.extend(validate_artifact_location(artifact, "execute_sql", 5))
        errors.extend(_validate_execute_sql_artifact(artifact, state))
    if not has_observed_state(state):
        errors.append("post-execution observed_fetched_at is required")
    if state.get("delta") not in ([], None):
        errors.append("delta should be empty after verified execution")
    if not isinstance(state.get("base_version"), int) or state.get("base_version", -1) < 1:
        errors.append("base_version must be bumped after execution")
    return errors


def can_exit_phase(state: dict[str, Any]) -> bool:
    return not validate_artifact(state)


def render_execution_summary(state: dict[str, Any]) -> str:
    artifact = phase_artifact(state, "execute_sql") or {}
    source_paths = artifact.get("source_artifacts", {}) if isinstance(artifact.get("source_artifacts"), dict) else {}
    remaining_gaps = artifact.get("remaining_gaps", [])
    lines = [
        "# Execution Summary — Governance Implementation Result",
        "",
        "## Purpose",
        "This artifact records execution and verification of the approved Governance Implementation SQL.",
        "",
        "## Source Artifacts",
        f"- Governance Spec: {_text(source_paths.get('governance_spec'), '@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/governance_spec.md')}",
        f"- Governance Implementation SQL: {_text(source_paths.get('governance_implementation'), '@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/governance_implementation.sql')}",
        f"- State: {_text(source_paths.get('state'), artifact_state_path(artifact.get('artifact_location', {})))}",
        f"- Source Governance Spec digest: {_text(artifact.get('source_governance_spec_digest'), 'unknown')}",
        f"- Source Governance Implementation SQL digest: {_text(artifact.get('source_governance_implementation_digest'), 'unknown')}",
        "",
        "## Execution Boundary",
    ]
    sql_approval = artifact.get("implementation_sql_approval", {}) if isinstance(artifact.get("implementation_sql_approval"), dict) else {}
    approval = artifact.get("execution_approval", {}) if isinstance(artifact.get("execution_approval"), dict) else {}
    lines.extend([
        f"- SQL readiness approved by: {_text(sql_approval.get('approved_by'), 'unknown')}",
        f"- Execution approved by: {_text(approval.get('approved_by'), 'unknown')}",
        f"- Execution approver persona: {_text(approval.get('approver_persona'), 'unknown')}",
        f"- Approved SQL digest: {_text(approval.get('approved_sql_digest'), 'unknown')}",
        f"- Approval scope: {_text(approval.get('approval_scope'), 'unknown')}",
    ])

    lines.extend(["", "## Statement Execution Inventory"])
    lines.extend(_inventory_lines(artifact.get("statement_execution_inventory")))

    lines.extend(["", "## Post-Execution Verification"])
    lines.extend(_verification_lines(artifact.get("post_execution_verification")))

    lines.extend(["", "## Preservation Checks"])
    lines.extend(_list_lines(artifact.get("preservation_checks")))

    lines.extend(["", "## Destructive Change Result"])
    destructive_results = artifact.get("destructive_change_results", [])
    if isinstance(destructive_results, list) and destructive_results:
        lines.extend(_list_lines(destructive_results))
    else:
        lines.extend([
            "- Destructive changes executed: no",
            "- Replacements: none",
            "- Removals: none",
            "- Weakening changes: none",
            "- Broad-impact changes: none",
        ])

    lines.extend(["", "## Committed Version"])
    lines.extend([
        f"- Version: v{artifact.get('committed_version', 'unknown')}",
        f"- Committed state: {_text(artifact.get('committed_state_path'), 'unknown')}",
        f"- Deployed baseline: {_text(artifact.get('committed_state_path'), 'unknown')}",
        "- Working draft retained files: "
        + _retained_working_files_text(artifact.get("working_retained")),
    ])
    committed_paths = artifact.get("committed_artifact_paths", {})
    if isinstance(committed_paths, dict) and committed_paths:
        lines.append("- Committed artifacts:")
        for name in _REQUIRED_COMMITTED_ARTIFACTS:
            lines.append(f"  - {name}: {_text(committed_paths.get(name), 'missing')}")

    lines.extend(["", "## Remaining Gaps"])
    lines.extend(_list_lines(remaining_gaps))

    anomalies = artifact.get("execution_anomalies", [])
    if isinstance(anomalies, list) and anomalies:
        lines.extend(["", "## Execution Anomalies"])
        lines.extend(_list_lines(anomalies))

    lines.extend(["", "## Closing Status"])
    if artifact.get("observed_matches_intent") is True and artifact.get("post_execution_verification"):
        lines.append("- Complete: approved SQL executed, target governance status verified, and committed version persisted.")
    else:
        lines.append("- Incomplete: verification did not reconcile to target governance status.")
    return "\n".join(lines)


def _validate_execute_sql_artifact(artifact: dict[str, Any], state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(artifact.get("source_governance_spec_digest"), str) or not artifact.get("source_governance_spec_digest", "").strip():
        errors.append("phase_details.execute_sql.source_governance_spec_digest must be a non-empty string")
    if not isinstance(artifact.get("source_governance_implementation_digest"), str) or not artifact.get("source_governance_implementation_digest", "").strip():
        errors.append("phase_details.execute_sql.source_governance_implementation_digest must be a non-empty string")
    errors.extend(_validate_digest_matches_phase4(artifact, state))
    errors.extend(_validate_phase4_executable(state))

    if not isinstance(artifact.get("executed_statements"), list):
        errors.append("phase_details.execute_sql.executed_statements must be a list")
    if artifact.get("executed_statements") != _approved_statements(state):
        errors.append("phase_details.execute_sql.executed_statements must exactly match approved Governance Implementation SQL statements")
    if not isinstance(artifact.get("statement_execution_inventory"), list) or not artifact.get("statement_execution_inventory"):
        errors.append("phase_details.execute_sql.statement_execution_inventory must be a non-empty list")
    else:
        errors.extend(_validate_statement_execution_inventory(artifact))
    errors.extend(_validate_execution_approval(artifact.get("execution_approval")))
    if "implementation_sql_approval" in artifact:
        errors.extend(_validate_execution_approval(artifact.get("implementation_sql_approval"), prefix="implementation_sql_approval"))
    else:
        errors.append("phase_details.execute_sql.implementation_sql_approval must record Phase 4 SQL approval")

    for list_field in ("execution_anomalies", "post_execution_verification", "preservation_checks", "destructive_change_results", "remaining_gaps"):
        if list_field in artifact and not isinstance(artifact[list_field], list):
            errors.append(f"phase_details.execute_sql.{list_field} must be a list")
    if not artifact.get("post_execution_verification"):
        errors.append("phase_details.execute_sql.post_execution_verification must be non-empty")
    if artifact.get("execution_anomalies") and not artifact.get("post_anomaly_reobservation"):
        errors.append("phase_details.execute_sql.post_anomaly_reobservation is required when execution_anomalies are recorded")
    if _has_privilege_execution_anomaly(artifact.get("execution_anomalies")):
        errors.append("phase_details.execute_sql privilege execution anomaly must return to Generate SQL handoff before commit")

    committed_version = artifact.get("committed_version")
    if not isinstance(committed_version, int) or committed_version < 1:
        errors.append("phase_details.execute_sql.committed_version must be a positive integer")
    elif isinstance(state.get("base_version"), int) and committed_version != state.get("base_version"):
        errors.append("phase_details.execute_sql.committed_version must match base_version")
    for field in ("committed_state_path", "execution_summary"):
        if not isinstance(artifact.get(field), str) or not artifact.get(field, "").strip():
            errors.append(f"phase_details.execute_sql.{field} must be a non-empty string")
    expected_retained = {
        "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/governance_spec.md",
        "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/state.yaml",
    }
    working_retained = artifact.get("working_retained")
    if set(working_retained or []) != expected_retained:
        errors.append("phase_details.execute_sql.working_retained must contain only working/governance_spec.md and working/state.yaml")
    errors.extend(_validate_committed_paths(artifact.get("committed_artifact_paths")))
    errors.extend(_validate_monitoring_execution(artifact, state))
    if artifact.get("observed_matches_intent") is not True:
        errors.append("phase_details.execute_sql.observed_matches_intent must be true")

    summary = artifact.get("execution_summary")
    if isinstance(summary, str) and summary.strip():
        for heading in _REQUIRED_EXECUTION_HEADINGS:
            if heading not in summary:
                errors.append(f"phase_details.execute_sql.execution_summary missing required section: {heading}")
    return errors


def _validate_monitoring_execution(artifact: dict[str, Any], state: dict[str, Any]) -> list[str]:
    phase4 = phase_artifact(state, "generate_sql") or {}
    monitoring = phase4.get("monitoring_implementation") if isinstance(phase4.get("monitoring_implementation"), dict) else {}
    if monitoring.get("enabled") is not True:
        return []
    errors: list[str] = []
    committed_paths = artifact.get("committed_artifact_paths")
    if not isinstance(committed_paths, dict):
        return ["phase_details.execute_sql.committed_artifact_paths must include scheduled drift monitoring artifacts"]
    for field in _REQUIRED_MONITORING_ARTIFACTS:
        if not isinstance(committed_paths.get(field), str) or not committed_paths.get(field, "").strip():
            errors.append(f"phase_details.execute_sql.committed_artifact_paths.{field} must be a non-empty string when scheduled drift monitoring is enabled")
    if monitoring.get("baseline_tracking") == "latest_committed":
        for field in _REQUIRED_LATEST_MONITORING_ARTIFACTS:
            if not isinstance(committed_paths.get(field), str) or not committed_paths.get(field, "").strip():
                errors.append(f"phase_details.execute_sql.committed_artifact_paths.{field} must point to the latest committed drift contract when baseline_tracking is latest_committed")
    verification = artifact.get("monitoring_verification")
    if not isinstance(verification, dict):
        errors.append("phase_details.execute_sql.monitoring_verification must be recorded when scheduled drift monitoring is enabled")
        return errors
    for field in ("procedure_verified", "runs_table_verified", "findings_table_verified", "task_verified", "notification_reference_verified", "no_auto_remediation_verified"):
        if verification.get(field) is not True:
            errors.append(f"phase_details.execute_sql.monitoring_verification.{field} must be true")
    if not isinstance(verification.get("monitor_execution_role"), str) or not verification.get("monitor_execution_role", "").strip():
        errors.append("phase_details.execute_sql.monitoring_verification.monitor_execution_role must be recorded")
    return errors


def _retained_working_files_text(value: Any) -> str:
    if isinstance(value, list) and value:
        return ", ".join(str(item) for item in value)
    return "missing"


def _validate_digest_matches_phase4(artifact: dict[str, Any], state: dict[str, Any]) -> list[str]:
    phase4 = phase_artifact(state, "generate_sql") or {}
    errors: list[str] = []
    spec_digest = phase4.get("source_governance_spec_digest")
    sql_digest = phase4.get("governance_implementation_digest")
    if isinstance(spec_digest, str) and artifact.get("source_governance_spec_digest") != spec_digest:
        errors.append("phase_details.execute_sql.source_governance_spec_digest must match Phase 4 source_governance_spec_digest")
    if isinstance(sql_digest, str) and artifact.get("source_governance_implementation_digest") != sql_digest:
        errors.append("phase_details.execute_sql.source_governance_implementation_digest must match Phase 4 governance_implementation_digest")
    return errors


def _approved_statements(state: dict[str, Any]) -> list[Any] | None:
    phase4 = phase_artifact(state, "generate_sql") or {}
    statements = phase4.get("statements")
    return statements if isinstance(statements, list) else None


def _validate_phase4_executable(state: dict[str, Any]) -> list[str]:
    phase4 = phase_artifact(state, "generate_sql") or {}
    errors: list[str] = []
    if phase4.get("implementation_status") == "handoff_required":
        errors.append("phase_details.execute_sql cannot execute a handoff_required Governance Implementation SQL package")
    if phase4.get("ready_for_execution") is not True:
        errors.append("phase_details.execute_sql requires Phase 4 ready_for_execution to be true")
    return errors


_NON_EXECUTED_RESULTS = {
    "blocked",
    "handoff",
    "handoff_required",
    "not_executed",
    "plan_only",
    "planned",
    "skipped",
    "unsafe",
    "unsafe_until_visible",
}


def _validate_statement_execution_inventory(artifact: dict[str, Any]) -> list[str]:
    inventory = artifact.get("statement_execution_inventory", [])
    executed = artifact.get("executed_statements", [])
    errors: list[str] = []
    if isinstance(inventory, list) and isinstance(executed, list) and len(inventory) != len(executed):
        errors.append("phase_details.execute_sql.statement_execution_inventory must map every executed statement")
    for idx, item in enumerate(inventory if isinstance(inventory, list) else []):
        if not isinstance(item, dict):
            errors.append(f"phase_details.execute_sql.statement_execution_inventory[{idx}] must be a mapping")
            continue
        for field in ("statement_index", "spec_item", "query_id", "result"):
            if field not in item:
                errors.append(f"phase_details.execute_sql.statement_execution_inventory[{idx}].{field} is required")
        result = item.get("result")
        if isinstance(result, str) and result.strip().lower() in _NON_EXECUTED_RESULTS:
            errors.append(f"phase_details.execute_sql.statement_execution_inventory[{idx}].result must record executed SQL, not handoff/unsafe status")
        if item.get("destructive_change") in ("yes", True) and not item.get("destructive_change_id"):
            errors.append(f"phase_details.execute_sql.statement_execution_inventory[{idx}].destructive_change_id is required")
    return errors


_PRIVILEGE_ANOMALY_KINDS = {
    "access_control_error",
    "authorization_error",
    "insufficient_privilege",
    "permission_denied",
    "privilege_error",
}
_PRIVILEGE_ANOMALY_CODES = {
    "002003",  # Snowflake SQL access-control error.
    "42501",  # SQLSTATE insufficient privilege.
}
_RUNTIME_ANOMALY_KINDS = {
    "database_error",
    "execution_error",
    "runtime_error",
    "snowflake_error",
    "sql_error",
    "statement_error",
}
_PRIVILEGE_MESSAGE_PATTERNS = (
    re.compile(r"\bsql access control error\b"),
    re.compile(r"\binsufficient privileges\b"),
    re.compile(r"\bnot authorized to (?:operate|perform)\b"),
    re.compile(r"\bpermission denied\b"),
)
_ANOMALY_TEXT_FIELDS = ("message", "summary", "result", "error", "error_message", "detail")


def _has_privilege_execution_anomaly(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if isinstance(item, dict):
            kind = _normalized_anomaly_kind(item)
            if kind in _PRIVILEGE_ANOMALY_KINDS or _has_privilege_anomaly_code(item):
                return True
            if kind and kind not in _RUNTIME_ANOMALY_KINDS:
                continue
            text = _anomaly_text(item)
        else:
            kind = ""
            text = str(item)
        lowered = text.lower()
        if any(pattern.search(lowered) for pattern in _PRIVILEGE_MESSAGE_PATTERNS):
            return True
    return False


def _normalized_anomaly_kind(item: dict[str, Any]) -> str:
    for field in ("kind", "type", "category", "error_type", "exception_type"):
        value = _normalized_anomaly_field(item, field)
        if value:
            return value
    return ""


def _normalized_anomaly_field(item: dict[str, Any], field: str) -> str:
    value = item.get(field)
    if not isinstance(value, str):
        return ""
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _has_privilege_anomaly_code(value: Any) -> bool:
    for code in _iter_anomaly_codes(value):
        if code in _PRIVILEGE_ANOMALY_CODES:
            return True
        if code.isdigit() and code.zfill(6) in _PRIVILEGE_ANOMALY_CODES:
            return True
    return False


def _iter_anomaly_codes(value: Any) -> list[str]:
    codes: list[str] = []
    if not isinstance(value, dict):
        return codes
    for field in ("sqlstate", "sql_state", "code", "error_code", "errno", "sqlcode"):
        item = value.get(field)
        if item is None:
            continue
        text = str(item).strip().upper()
        if text:
            codes.append(text)
    for nested_field in ("exception", "cause", "details"):
        nested = value.get(nested_field)
        if isinstance(nested, dict):
            codes.extend(_iter_anomaly_codes(nested))
    return codes


def _anomaly_text(item: dict[str, Any]) -> str:
    parts = [str(item.get(field, "")) for field in _ANOMALY_TEXT_FIELDS]
    for nested_field in ("exception", "cause"):
        nested = item.get(nested_field)
        if isinstance(nested, dict):
            parts.append(_anomaly_text(nested))
    return " ".join(part for part in parts if part)


def _validate_execution_approval(value: Any, prefix: str = "execution_approval") -> list[str]:
    if not isinstance(value, dict):
        return [f"phase_details.execute_sql.{prefix} must be a mapping"]
    errors: list[str] = []
    for field in ("approved_by", "approver_persona", "approved_at", "approved_sql_digest", "approval_scope"):
        if not isinstance(value.get(field), str) or not value.get(field, "").strip():
            errors.append(f"phase_details.execute_sql.{prefix}.{field} must be a non-empty string")
    return errors


def _validate_committed_paths(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["phase_details.execute_sql.committed_artifact_paths must be a mapping"]
    errors: list[str] = []
    for field in _REQUIRED_COMMITTED_ARTIFACTS:
        if not isinstance(value.get(field), str) or not value.get(field, "").strip():
            errors.append(f"phase_details.execute_sql.committed_artifact_paths.{field} must be a non-empty string")
    return errors


def _inventory_lines(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["- None recorded"]
    lines = []
    for item in value:
        if not isinstance(item, dict):
            lines.append(f"- {item}")
            continue
        lines.append(
            f"- Statement {item.get('statement_index', '?')}: spec item `{_text(item.get('spec_item'), 'unmapped')}`, "
            f"query `{_text(item.get('query_id'), 'unknown')}`, result `{_text(item.get('result'), 'unknown')}`, "
            f"destructive item `{_text(item.get('destructive_change_id'), 'none')}`"
        )
    return lines


def _verification_lines(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["- None recorded"]
    lines = []
    for item in value:
        if isinstance(item, dict):
            lines.append(
                f"- {_text(item.get('scope_path'), _text(item.get('object'), 'unknown'))}: "
                f"target `{_text(item.get('target'), 'unknown')}`, observed `{_text(item.get('observed'), 'unknown')}`, "
                f"match `{item.get('match') is True}`"
            )
        else:
            lines.append(f"- {item}")
    return lines


def _list_lines(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["- None"]
    lines = []
    for item in value:
        if isinstance(item, dict):
            label = item.get("description") or item.get("object") or item.get("id") or item
            lines.append(f"- {label}")
        else:
            lines.append(f"- {item}")
    return lines


def _text(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) and value.strip() else fallback
