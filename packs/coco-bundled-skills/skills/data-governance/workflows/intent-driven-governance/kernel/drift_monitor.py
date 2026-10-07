"""Deterministic drift monitor contract evaluation.

The scheduled monitor and one-off Drift Review use the same contract shape:
``drift_contract["assertions"]`` describes expected governance state and an
observed snapshot supplies current metadata. Unknown visibility is a finding,
not a pass, so limited roles cannot silently under-report drift.
"""

from __future__ import annotations

from typing import Any

_SUPPORTED_ASSERTIONS = {
    "object_exists",
    "column_exists",
    "tag_binding",
    "masking_policy_binding",
    "row_access_policy_binding",
    "classification_profile_attachment",
    "policy_digest",
    "grant_present",
    "monitor_task_health",
    "manual_control",
}
_SEVERITIES = {"info", "low", "medium", "high", "critical"}


def evaluate_drift_contract(drift_contract: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a normalized drift contract against observed metadata."""

    assertions = drift_contract.get("assertions") if isinstance(drift_contract, dict) else None
    if not isinstance(assertions, list):
        return {"passed": False, "findings": [_finding("contract_invalid", "contract", "critical", "missing_assertions", "drift_contract.assertions must be a list")]}
    findings: list[dict[str, Any]] = []
    for idx, assertion in enumerate(assertions, 1):
        if not isinstance(assertion, dict):
            findings.append(_finding(f"assertion_{idx}", "contract", "critical", "assertion_invalid", "assertion must be a mapping"))
            continue
        findings.extend(_evaluate_assertion(assertion, observed, idx))
    return {
        "passed": not findings,
        "finding_count": len(findings),
        "highest_severity": _highest_severity(findings),
        "findings": findings,
    }


def validate_drift_contract(drift_contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    assertions = drift_contract.get("assertions") if isinstance(drift_contract, dict) else None
    if not isinstance(assertions, list) or not assertions:
        return ["drift_contract.assertions must be a non-empty list"]
    for idx, assertion in enumerate(assertions):
        if not isinstance(assertion, dict):
            errors.append(f"drift_contract.assertions[{idx}] must be a mapping")
            continue
        assertion_type = assertion.get("type")
        if assertion_type not in _SUPPORTED_ASSERTIONS:
            errors.append(f"drift_contract.assertions[{idx}].type is unsupported")
        if not _text(assertion.get("id")):
            errors.append(f"drift_contract.assertions[{idx}].id must be a non-empty string")
        severity = assertion.get("severity", "medium")
        if severity not in _SEVERITIES:
            errors.append(f"drift_contract.assertions[{idx}].severity is invalid")
        if assertion_type != "manual_control" and not _text(assertion.get("object")):
            errors.append(f"drift_contract.assertions[{idx}].object must be a non-empty string")
    return errors


def _evaluate_assertion(assertion: dict[str, Any], observed: dict[str, Any], index: int) -> list[dict[str, Any]]:
    assertion_id = _text(assertion.get("id")) or f"assertion_{index}"
    assertion_type = assertion.get("type")
    severity = assertion.get("severity") if assertion.get("severity") in _SEVERITIES else "medium"
    if assertion_type not in _SUPPORTED_ASSERTIONS:
        return [_finding(assertion_id, _text(assertion.get("object")), "critical", "unsupported_assertion", f"Unsupported assertion type: {assertion_type}")]
    if assertion_type == "manual_control":
        return [_finding(assertion_id, _text(assertion.get("object"), "manual_control"), "info", "manual_review_required", _text(assertion.get("reason"), "Manual governance control requires review."))]
    object_fqn = _text(assertion.get("object"))
    if _visibility_unknown(observed, assertion):
        return [_finding(assertion_id, object_fqn, severity, "unknown_visibility", f"Visibility is unknown for {object_fqn}; drift cannot be safely cleared.")]
    actual = _observed_value(observed, assertion_type, object_fqn)
    expected = _expected_value(assertion_type, assertion)
    if assertion_type == "monitor_task_health":
        return [] if _task_healthy(actual, assertion) else [_finding(assertion_id, object_fqn, severity, "monitor_health_drift", "Scheduled drift monitor task is missing, suspended, stale, or failed.", expected, actual)]
    if actual == expected or (assertion_type in {"object_exists", "column_exists"} and actual is True):
        return []
    finding_type = "missing_expected_control" if actual in (None, False) else "unexpected_control_state"
    return [_finding(assertion_id, object_fqn, severity, finding_type, f"Observed state for {object_fqn} does not match the approved drift contract.", expected, actual)]


def _observed_value(observed: dict[str, Any], assertion_type: str, object_fqn: str) -> Any:
    bucket_by_type = {
        "object_exists": "objects",
        "column_exists": "columns",
        "tag_binding": "tag_bindings",
        "masking_policy_binding": "masking_policy_bindings",
        "row_access_policy_binding": "row_access_policy_bindings",
        "classification_profile_attachment": "classification_profile_attachments",
        "policy_digest": "policy_digests",
        "grant_present": "grants",
        "monitor_task_health": "monitor_tasks",
    }
    bucket = observed.get(bucket_by_type[assertion_type], {}) if isinstance(observed, dict) else {}
    if isinstance(bucket, dict):
        return bucket.get(object_fqn)
    return None


def _expected_value(assertion_type: str, assertion: dict[str, Any]) -> Any:
    if assertion_type in {"object_exists", "column_exists", "grant_present"}:
        return True
    if assertion_type == "tag_binding":
        return {"tag": assertion.get("tag"), "value": assertion.get("expected_value")}
    if assertion_type in {"masking_policy_binding", "row_access_policy_binding"}:
        return assertion.get("expected_policy")
    if assertion_type == "classification_profile_attachment":
        return assertion.get("expected_profile")
    if assertion_type == "policy_digest":
        return assertion.get("expected_digest")
    return assertion.get("expected")


def _task_healthy(actual: Any, assertion: dict[str, Any]) -> bool:
    if not isinstance(actual, dict):
        return False
    if actual.get("state") != "started":
        return False
    if actual.get("last_run_status") not in {"succeeded", "success", "skipped_no_drift", None}:
        return False
    max_age = assertion.get("max_last_run_age_minutes")
    age = actual.get("last_run_age_minutes")
    if isinstance(max_age, int) and isinstance(age, int) and age > max_age:
        return False
    return True


def _visibility_unknown(observed: dict[str, Any], assertion: dict[str, Any]) -> bool:
    unknown = observed.get("unknown_visibility") if isinstance(observed, dict) else None
    object_fqn = _text(assertion.get("object"))
    if unknown is True:
        return True
    if isinstance(unknown, list) and object_fqn in unknown:
        return True
    return False


def _finding(assertion_id: str, object_fqn: str, severity: str, finding_type: str, message: str, expected: Any = None, observed: Any = None) -> dict[str, Any]:
    return {
        "assertion_id": assertion_id,
        "object_fqn": object_fqn,
        "severity": severity,
        "finding_type": finding_type,
        "message": message,
        "expected": expected,
        "observed": observed,
    }


def _highest_severity(findings: list[dict[str, Any]]) -> str | None:
    if not findings:
        return None
    order = {name: idx for idx, name in enumerate(["info", "low", "medium", "high", "critical"])}
    return max((finding.get("severity", "medium") for finding in findings), key=lambda item: order.get(str(item), 2))


def _text(value: Any, fallback: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback
