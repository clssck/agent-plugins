"""Typed governance operation rendering for intent-driven-governance."""

from __future__ import annotations

import re
from typing import Any

from .core import ValidationError

_SUPPORTED_OPS = {
    "create_tag",
    "create_masking_policy",
    "set_masking_policy",
    "set_tag",
    "create_classification_profile",
    "set_classification_profile",
    "create_monitoring_schema",
    "create_drift_runs_table",
    "create_drift_findings_table",
    "create_drift_check_procedure",
    "create_drift_monitor_task",
    "resume_drift_monitor_task",
    "reference_notification_integration",
}
_CAPABILITY_STATUSES = {"confirmed", "probable", "unknown", "handoff_required", "unsafe_until_visible"}
_IDENTIFIER_RE = re.compile(r"^[A-Z_][A-Z0-9_$]*$")
_TYPE_RE = re.compile(r"^[A-Z][A-Z0-9_]*(?:\([0-9]+(?:\s*,\s*[0-9]+)?\))?$", re.I)
_SAFE_LITERAL_RE = re.compile(r"^(NULL|TRUE|FALSE|[-]?[0-9]+(?:\.[0-9]+)?|'(?:''|[^'])*')$", re.I)


def validate_operation(operation: dict[str, Any]) -> list[str]:
    """Return validation errors for one typed operation."""

    try:
        _render_operation(operation)
        _validate_capability_metadata(operation)
    except ValidationError as exc:
        return [str(exc)]
    return []


def render_operation_sql(operation: dict[str, Any]) -> str:
    """Render one validated typed operation to deterministic Snowflake SQL."""

    return _render_operation(operation)


def render_operations(operations: list[dict[str, Any]]) -> list[str]:
    """Render typed operations to exact SQL statements."""

    if not isinstance(operations, list) or not operations:
        raise ValidationError("operations must be a non-empty list")
    statements: list[str] = []
    for idx, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise ValidationError(f"operations[{idx}] must be a mapping")
        statements.append(render_operation_sql(operation))
    return statements


def statement_purpose(operation: dict[str, Any], index: int) -> dict[str, Any]:
    """Build a statement inventory entry for a typed operation."""

    op = _operation_kind(operation)
    target = (
        operation.get("target_fqn")
        or operation.get("tag_fqn")
        or operation.get("policy_fqn")
        or operation.get("table_fqn")
        or operation.get("procedure_fqn")
        or operation.get("task_fqn")
        or operation.get("integration_name")
        or operation.get("schema_fqn")
    )
    return {
        "statement_index": index,
        "purpose": _purpose_text(op, str(target)),
        "spec_item": _non_empty_text(operation.get("source_spec_item"), "typed_operation"),
        "destructive_change": "yes" if operation.get("destructive_change") is True else "no",
        "required_capabilities": required_capabilities(operation),
    }


def required_capabilities(operation: dict[str, Any]) -> list[str]:
    """Return coarse capability families required to execute one operation.

    These are intentionally capability labels rather than exact GRANT SQL. The
    skill converts them into scoped customer guidance after target scope and
    current-role probes are known.
    """

    op = _operation_kind(operation)
    if op == "create_tag":
        return ["usage_on_tag_database", "usage_on_tag_schema", "create_tag"]
    if op == "create_masking_policy":
        return ["usage_on_policy_database", "usage_on_policy_schema", "create_masking_policy"]
    if op == "set_masking_policy":
        return ["ownership_or_alter_on_target_table", "apply_masking_policy"]
    if op == "set_tag":
        return ["ownership_or_alter_on_target_table", "apply_tag"]
    if op == "create_classification_profile":
        return ["snowflake_classification_admin", "create_classification_profile"]
    if op == "set_classification_profile":
        return ["alter_target_database_or_schema", "execute_auto_classification"]
    if op == "create_monitoring_schema":
        return ["usage_on_workspace_database", "create_schema"]
    if op in {"create_drift_runs_table", "create_drift_findings_table"}:
        return ["usage_on_monitoring_schema", "create_table"]
    if op == "create_drift_check_procedure":
        return ["usage_on_monitoring_schema", "create_procedure", "monitor_execution_role_visibility"]
    if op == "create_drift_monitor_task":
        return ["usage_on_monitoring_schema", "create_task", "execute_task", "monitor_execution_role_visibility"]
    if op == "resume_drift_monitor_task":
        return ["operate_on_task", "monitor_execution_role_visibility"]
    if op == "reference_notification_integration":
        return ["usage_on_notification_integration"]
    raise ValidationError(f"unsupported operation: {op}")


def route_operations(
    operations: list[dict[str, Any]],
    capability_status_by_statement: dict[int, str] | None = None,
) -> dict[str, list[int]]:
    """Group operations by ephemeral current-session capability status.

    Statement indexes are 1-based and match render_operations/order. Dependency
    promotion is conservative: if an operation depends on any handoff-required
    or unsafe operation, the dependent operation is also blocked for this
    iteration. Capability statuses are intentionally supplied outside the typed
    operations because the operations are durable workflow state while current
    role capabilities are session-only facts.
    """

    render_operations(operations)
    operation_count = len(operations)
    statuses = _capability_statuses(capability_status_by_statement, operation_count)
    dependencies_by_index = {
        index: _validated_dependency_indexes(operation, index, operation_count)
        for index, operation in enumerate(operations, 1)
    }
    handoff_blocked_indexes = {index for index, status in statuses.items() if status in {"handoff_required", "unknown"}}
    unsafe_blocked_indexes = {index for index, status in statuses.items() if status == "unsafe_until_visible"}

    changed = True
    while changed:
        changed = False
        for index, dependencies in dependencies_by_index.items():
            if index in handoff_blocked_indexes or index in unsafe_blocked_indexes:
                continue
            if handoff_blocked_indexes.intersection(dependencies):
                handoff_blocked_indexes.add(index)
                changed = True
            elif unsafe_blocked_indexes.intersection(dependencies):
                unsafe_blocked_indexes.add(index)
                changed = True

    executable: list[int] = []
    handoff: list[int] = []
    unsafe: list[int] = []

    for index in range(1, operation_count + 1):
        status = statuses[index]
        if index in unsafe_blocked_indexes:
            unsafe.append(index)
        elif index in handoff_blocked_indexes:
            handoff.append(index)
        else:
            executable.append(index)

    return {
        "executable_with_current_role": executable,
        "handoff_required": handoff,
        "unsafe_until_visibility_improves": unsafe,
    }


def rollback_note(operation: dict[str, Any]) -> str:
    """Build a concise rollback note for a typed operation."""

    op = _operation_kind(operation)
    if op == "create_tag":
        return f"Drop tag {_required_fqn(operation, 'tag_fqn', 3)} only after all dependent tag bindings are unset or migrated."
    if op == "create_masking_policy":
        return f"Drop masking policy {_required_fqn(operation, 'policy_fqn', 3)} if no bindings depend on it."
    if op == "set_masking_policy":
        table_fqn, column_name = _split_column_fqn(operation.get("target_fqn"), "target_fqn")
        return f"Unset masking policy from {table_fqn}.{column_name} or restore the previously recorded binding."
    if op == "set_tag":
        table_fqn, column_name = _split_column_fqn(operation.get("target_fqn"), "target_fqn")
        tag_fqn = _required_fqn(operation, "tag_fqn", 3)
        return f"Unset tag {tag_fqn} from {table_fqn}.{column_name} or restore the previous tag value."
    if op == "create_classification_profile":
        return f"Drop classification profile {_required_fqn(operation, 'profile_fqn', 3)} if no targets depend on it."
    if op == "create_monitoring_schema":
        return f"Keep monitoring schema {_required_fqn(operation, 'schema_fqn', 2)} for audit history; disable tasks before any removal."
    if op in {"create_drift_runs_table", "create_drift_findings_table"}:
        return f"Keep monitoring table {_required_fqn(operation, 'table_fqn', 3)} for drift audit history; archive before any removal."
    if op == "create_drift_check_procedure":
        return f"Replace or drop drift check procedure {_required_fqn(operation, 'procedure_fqn', 3)} only after dependent tasks are suspended."
    if op == "create_drift_monitor_task":
        return f"Suspend drift monitor task {_required_fqn(operation, 'task_fqn', 3)} before changing schedule or procedure bindings."
    if op == "resume_drift_monitor_task":
        return f"Suspend drift monitor task {_required_fqn(operation, 'task_fqn', 3)} if scheduled monitoring must be paused."
    if op == "reference_notification_integration":
        return f"Update notification integration {_identifier(operation.get('integration_name'), 'reference_notification_integration.integration_name')} or recipients through approved monitor configuration SQL."
    target_type = _target_type(operation, {"database", "schema"})
    target_fqn = _target_fqn(operation, target_type)
    return f"Unset CLASSIFICATION_PROFILE from {target_type} {target_fqn} or restore the previously recorded profile."


def operation_inventory(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build statement inventory entries for typed operations."""

    return [statement_purpose(operation, idx) for idx, operation in enumerate(operations, 1)]


def rollback_notes(operations: list[dict[str, Any]]) -> list[str]:
    """Build rollback notes for typed operations."""

    return [rollback_note(operation) for operation in operations]


def _render_operation(operation: dict[str, Any]) -> str:
    if not isinstance(operation, dict):
        raise ValidationError("operation must be a mapping")
    op = _operation_kind(operation)
    if operation.get("destructive_change") is True and not _non_empty_text(operation.get("destructive_change_id"), ""):
        raise ValidationError(f"{op}.destructive_change_id is required for destructive changes")
    if op == "create_tag":
        return _render_create_tag(operation)
    if op == "create_masking_policy":
        return _render_create_masking_policy(operation)
    if op == "set_masking_policy":
        return _render_set_masking_policy(operation)
    if op == "set_tag":
        return _render_set_tag(operation)
    if op == "create_classification_profile":
        return _render_create_classification_profile(operation)
    if op == "set_classification_profile":
        return _render_set_classification_profile(operation)
    if op == "create_monitoring_schema":
        return _render_create_monitoring_schema(operation)
    if op == "create_drift_runs_table":
        return _render_create_drift_runs_table(operation)
    if op == "create_drift_findings_table":
        return _render_create_drift_findings_table(operation)
    if op == "create_drift_check_procedure":
        return _render_create_drift_check_procedure(operation)
    if op == "create_drift_monitor_task":
        return _render_create_drift_monitor_task(operation)
    if op == "resume_drift_monitor_task":
        return _render_resume_drift_monitor_task(operation)
    if op == "reference_notification_integration":
        return _render_reference_notification_integration(operation)
    raise ValidationError(f"unsupported operation: {op}")


def _render_create_tag(operation: dict[str, Any]) -> str:
    tag_fqn = _required_fqn(operation, "tag_fqn", 3)
    allowed_values = operation.get("allowed_values", [])
    if not isinstance(allowed_values, list) or not allowed_values:
        raise ValidationError("create_tag.allowed_values must be a non-empty list")
    value_literals = []
    for value in allowed_values:
        value_literals.append(_string_literal(value, "create_tag.allowed_values"))
    return f"CREATE TAG IF NOT EXISTS {tag_fqn}\n  ALLOWED_VALUES {', '.join(value_literals)};"


def _render_create_masking_policy(operation: dict[str, Any]) -> str:
    policy_fqn = _required_fqn(operation, "policy_fqn", 3)
    argument = operation.get("argument")
    if not isinstance(argument, dict):
        raise ValidationError("create_masking_policy.argument must be a mapping")
    arg_name = _identifier(argument.get("name"), "create_masking_policy.argument.name")
    arg_type = _type_name(argument.get("type"), "create_masking_policy.argument.type")
    returns = _type_name(operation.get("returns"), "create_masking_policy.returns")
    body = operation.get("body")
    if not isinstance(body, dict):
        raise ValidationError("create_masking_policy.body must be a mapping")
    if body.get("kind") != "role_allowlist":
        raise ValidationError("create_masking_policy.body.kind must be role_allowlist")
    roles = body.get("clear_roles")
    if not isinstance(roles, list) or not roles:
        raise ValidationError("create_masking_policy.body.clear_roles must be a non-empty list")
    role_checks = [f"IS_ROLE_IN_SESSION('{_identifier(role, 'create_masking_policy.body.clear_roles')}')" for role in roles]
    masked_expression = _safe_masked_expression(body.get("masked_expression"))
    if operation.get("replace") is True or operation.get("or_replace") is True:
        raise ValidationError("create_masking_policy does not support CREATE OR REPLACE")
    conditions = "\n          OR ".join(role_checks)
    return "\n".join([
        f"CREATE MASKING POLICY {policy_fqn}",
        f"  AS ({arg_name} {arg_type})",
        f"  RETURNS {returns}",
        "  -> CASE",
        f"      WHEN {conditions}",
        f"      THEN {arg_name}",
        f"      ELSE {masked_expression}",
        "    END;",
    ])


def _render_set_masking_policy(operation: dict[str, Any]) -> str:
    target_type = _target_type(operation, {"column"})
    table_fqn, column_name = _split_column_fqn(operation.get("target_fqn"), "target_fqn")
    policy_fqn = _required_fqn(operation, "policy_fqn", 3)
    return "\n".join([
        f"ALTER TABLE {table_fqn}",
        f"  MODIFY COLUMN {column_name} SET MASKING POLICY {policy_fqn};",
    ])


def _render_set_tag(operation: dict[str, Any]) -> str:
    target_type = _target_type(operation, {"column"})
    table_fqn, column_name = _split_column_fqn(operation.get("target_fqn"), "target_fqn")
    tag_fqn = _required_fqn(operation, "tag_fqn", 3)
    tag_value = _string_literal(operation.get("tag_value"), "tag_value")
    return "\n".join([
        f"ALTER TABLE {table_fqn}",
        f"  MODIFY COLUMN {column_name} SET TAG {tag_fqn} = {tag_value};",
    ])


def _render_create_classification_profile(operation: dict[str, Any]) -> str:
    profile_fqn = _required_fqn(operation, "profile_fqn", 3)
    config = operation.get("config")
    if not isinstance(config, dict):
        raise ValidationError("create_classification_profile.config must be a mapping")
    minimum_age = _non_negative_int(
        config.get("minimum_object_age_for_classification_days", 0),
        "create_classification_profile.config.minimum_object_age_for_classification_days",
    )
    maximum_validity = _positive_int(
        config.get("maximum_classification_validity_days", 30),
        "create_classification_profile.config.maximum_classification_validity_days",
    )
    auto_tag = _bool(config.get("auto_tag", False), "create_classification_profile.config.auto_tag")
    classify_views = _bool(config.get("classify_views", False), "create_classification_profile.config.classify_views")
    tag_mappings = config.get("tag_mappings")
    mapping_lines: list[str] = []
    tag_map_lines: list[str] = []
    if auto_tag:
        if not isinstance(tag_mappings, list) or not tag_mappings:
            raise ValidationError("create_classification_profile.config.tag_mappings must be a non-empty list when auto_tag is true")
        for idx, mapping in enumerate(tag_mappings):
            if not isinstance(mapping, dict):
                raise ValidationError(f"create_classification_profile.config.tag_mappings[{idx}] must be a mapping")
            tag_name = _required_fqn(mapping, "tag_name", 3)
            tag_value = _string_literal(mapping.get("tag_value"), "tag_value")
            categories = mapping.get("semantic_categories")
            if not isinstance(categories, list) or not categories:
                raise ValidationError(
                    f"create_classification_profile.config.tag_mappings[{idx}].semantic_categories must be a non-empty list"
                )
            category_values = ", ".join(_string_literal(category, "semantic_categories") for category in categories)
            mapping_lines.extend([
                "        {",
                f"          'tag_name': '{tag_name}',",
                f"          'tag_value': {tag_value},",
                f"          'semantic_categories': [{category_values}]",
                "        }",
            ])
            if idx != len(tag_mappings) - 1:
                mapping_lines[-1] += ","
        tag_map_lines = [
            "    'tag_map': {",
            "      'column_tag_map': [",
            *mapping_lines,
            "      ]",
            "    }",
        ]
    config_lines = [
        "  {",
        f"    'minimum_object_age_for_classification_days': {minimum_age},",
        f"    'maximum_classification_validity_days': {maximum_validity},",
        f"    'auto_tag': {_json_bool(auto_tag)},",
        f"    'classify_views': {_json_bool(classify_views)}" + ("," if tag_map_lines else ""),
        *tag_map_lines,
        "  }",
    ]
    return "\n".join([
        f"CREATE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE {profile_fqn}(",
        *config_lines,
        ");",
    ])


def _render_set_classification_profile(operation: dict[str, Any]) -> str:
    target_type = _target_type(operation, {"database", "schema"})
    target_fqn = _target_fqn(operation, target_type)
    profile_fqn = _required_fqn(operation, "profile_fqn", 3)
    return "\n".join([
        f"ALTER {target_type.upper()} {target_fqn}",
        f"  SET CLASSIFICATION_PROFILE = '{profile_fqn}';",
    ])


def _render_create_monitoring_schema(operation: dict[str, Any]) -> str:
    schema_fqn = _required_fqn(operation, "schema_fqn", 2)
    return f"CREATE SCHEMA IF NOT EXISTS {schema_fqn};"


def _render_create_drift_runs_table(operation: dict[str, Any]) -> str:
    table_fqn = _required_fqn(operation, "table_fqn", 3)
    return "\n".join([
        f"CREATE TABLE IF NOT EXISTS {table_fqn} (",
        "  RUN_ID STRING NOT NULL,",
        "  MONITOR_NAME STRING NOT NULL,",
        "  BASELINE_VERSION STRING NOT NULL,",
        "  STARTED_AT TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),",
        "  COMPLETED_AT TIMESTAMP_NTZ,",
        "  STATUS STRING NOT NULL,",
        "  FINDING_COUNT NUMBER NOT NULL DEFAULT 0,",
        "  HIGHEST_SEVERITY STRING,",
        "  SUMMARY_STAGE_PATH STRING,",
        "  DETAILS VARIANT",
        ");",
    ])


def _render_create_drift_findings_table(operation: dict[str, Any]) -> str:
    table_fqn = _required_fqn(operation, "table_fqn", 3)
    return "\n".join([
        f"CREATE TABLE IF NOT EXISTS {table_fqn} (",
        "  RUN_ID STRING NOT NULL,",
        "  FINDING_ID STRING NOT NULL,",
        "  ASSERTION_ID STRING,",
        "  FINDING_TYPE STRING NOT NULL,",
        "  SEVERITY STRING NOT NULL,",
        "  OBJECT_FQN STRING,",
        "  EXPECTED VARIANT,",
        "  OBSERVED VARIANT,",
        "  MESSAGE STRING NOT NULL,",
        "  CREATED_AT TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()",
        ");",
    ])


def _render_create_drift_check_procedure(operation: dict[str, Any]) -> str:
    procedure_fqn = _required_fqn(operation, "procedure_fqn", 3)
    runs_table = _required_fqn(operation, "runs_table_fqn", 3)
    findings_table = _required_fqn(operation, "findings_table_fqn", 3)
    if operation.get("auto_remediate") is True:
        raise ValidationError("create_drift_check_procedure.auto_remediate must not be true")
    finding_inserts = _drift_finding_insert_statements(operation.get("drift_contract"), findings_table)
    notification_lines = _drift_notification_lines(operation, runs_table, findings_table)
    return "\n".join([
        f"CREATE PROCEDURE IF NOT EXISTS {procedure_fqn}(",
        "  MONITOR_NAME STRING,",
        "  BASELINE_VERSION STRING,",
        "  DRIFT_CONTRACT VARIANT",
        ")",
        "RETURNS VARIANT",
        "LANGUAGE SQL",
        "AS",
        "$$",
        "DECLARE",
        "  RUN_ID STRING DEFAULT TO_VARCHAR(CURRENT_TIMESTAMP(), 'YYYYMMDDHH24MISSFF3');",
        "BEGIN",
        f"  INSERT INTO {runs_table} (RUN_ID, MONITOR_NAME, BASELINE_VERSION, STATUS, DETAILS)",
        "    SELECT :RUN_ID, :MONITOR_NAME, :BASELINE_VERSION, 'RECORDED', OBJECT_CONSTRUCT('contract_assertions', ARRAY_SIZE(:DRIFT_CONTRACT:assertions));",
        *finding_inserts,
        f"  UPDATE {runs_table}",
        "    SET COMPLETED_AT = CURRENT_TIMESTAMP(),",
        "        FINDING_COUNT = (SELECT COUNT(*) FROM " + findings_table + " WHERE RUN_ID = :RUN_ID),",
        "        STATUS = IFF((SELECT COUNT(*) FROM " + findings_table + " WHERE RUN_ID = :RUN_ID) = 0, 'NO_DRIFT', 'DRIFT_DETECTED')",
        "    WHERE RUN_ID = :RUN_ID;",
        *notification_lines,
        f"  RETURN OBJECT_CONSTRUCT('run_id', :RUN_ID, 'status', 'RECORDED', 'findings_table', '{findings_table}', 'auto_remediation', FALSE);",
        "END;",
        "$$;",
    ])


def _drift_finding_insert_statements(value: Any, findings_table: str) -> list[str]:
    if not isinstance(value, dict):
        return [
            "  -- No inline drift_contract was supplied to the typed operation; generated monitor records runs and expects the uploaded drift_contract.json to be evaluated by the shared drift engine before notification.",
        ]
    assertions = value.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        raise ValidationError("create_drift_check_procedure.drift_contract.assertions must be a non-empty list when supplied")
    statements: list[str] = []
    for idx, assertion in enumerate(assertions, 1):
        if not isinstance(assertion, dict):
            raise ValidationError(f"create_drift_check_procedure.drift_contract.assertions[{idx - 1}] must be a mapping")
        statements.extend(_drift_assertion_insert(assertion, idx, findings_table))
    return statements


def _drift_assertion_insert(assertion: dict[str, Any], index: int, findings_table: str) -> list[str]:
    assertion_id = _string_literal(assertion.get("id", f"assertion_{index}"), "drift_contract.assertion.id")
    assertion_type = _non_empty_text(assertion.get("type"), "")
    object_fqn = _string_literal(assertion.get("object"), "drift_contract.assertion.object")
    severity = _string_literal(assertion.get("severity", "medium"), "drift_contract.assertion.severity")
    message = _string_literal(f"Scheduled drift assertion {assertion.get('id', index)} did not match approved baseline.", "drift_contract.assertion.message")
    predicate = _drift_assertion_missing_predicate(assertion, assertion_type)
    return [
        f"  INSERT INTO {findings_table} (RUN_ID, FINDING_ID, ASSERTION_ID, FINDING_TYPE, SEVERITY, OBJECT_FQN, EXPECTED, OBSERVED, MESSAGE)",
        f"    SELECT :RUN_ID, :RUN_ID || '-{index:03d}', {assertion_id}, 'DRIFT', {severity}, {object_fqn}, PARSE_JSON({ _string_literal(_drift_expected_json(assertion), 'drift_contract.expected') }), NULL, {message}",
        f"    WHERE {predicate};",
    ]


def _drift_assertion_missing_predicate(assertion: dict[str, Any], assertion_type: str) -> str:
    object_value = assertion.get("object")
    object_parts = _fqn(str(object_value), "drift_contract.assertion.object", len(str(object_value).split("."))).split(".") if isinstance(object_value, str) else []
    if assertion_type == "object_exists" and len(object_parts) == 3:
        db, schema, name = object_parts
        return (
            "NOT EXISTS (SELECT 1 FROM "
            f"{db}.INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = '{schema}' AND TABLE_NAME = '{name}')"
        )
    if assertion_type == "column_exists" and len(object_parts) == 4:
        db, schema, table, column = object_parts
        return (
            "NOT EXISTS (SELECT 1 FROM "
            f"{db}.INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = '{schema}' AND TABLE_NAME = '{table}' AND COLUMN_NAME = '{column}')"
        )
    if assertion_type == "tag_binding" and len(object_parts) == 4:
        db, schema, table, column = object_parts
        tag_parts = _fqn(assertion.get("tag"), "drift_contract.assertion.tag", 3).split(".")
        tag_value = _string_literal(assertion.get("expected_value"), "drift_contract.assertion.expected_value")
        return (
            "NOT EXISTS (SELECT 1 FROM TABLE("
            f"{db}.INFORMATION_SCHEMA.TAG_REFERENCES_ALL_COLUMNS('{db}.{schema}.{table}', 'TABLE')) "
            f"WHERE COLUMN_NAME = '{column}' AND TAG_DATABASE = '{tag_parts[0]}' AND TAG_SCHEMA = '{tag_parts[1]}' "
            f"AND TAG_NAME = '{tag_parts[2]}' AND TAG_VALUE = {tag_value})"
        )
    if assertion_type in {"masking_policy_binding", "row_access_policy_binding"} and len(object_parts) in {3, 4}:
        db, schema, table = object_parts[:3]
        column_predicate = f" AND REF_COLUMN_NAME = '{object_parts[3]}'" if len(object_parts) == 4 else ""
        policy_fqn = _fqn(assertion.get("expected_policy"), "drift_contract.assertion.expected_policy", 3).split(".")
        policy_kind = "MASKING_POLICY" if assertion_type == "masking_policy_binding" else "ROW_ACCESS_POLICY"
        return (
            "NOT EXISTS (SELECT 1 FROM TABLE("
            f"{db}.INFORMATION_SCHEMA.POLICY_REFERENCES(REF_ENTITY_NAME => '{db}.{schema}.{table}', REF_ENTITY_DOMAIN => 'TABLE')) "
            f"WHERE REF_DATABASE_NAME = '{db}' AND REF_SCHEMA_NAME = '{schema}' AND REF_ENTITY_NAME = '{table}'{column_predicate} "
            f"AND POLICY_DB = '{policy_fqn[0]}' AND POLICY_SCHEMA = '{policy_fqn[1]}' AND POLICY_NAME = '{policy_fqn[2]}' "
            f"AND POLICY_KIND = '{policy_kind}')"
        )
    if assertion_type == "classification_profile_attachment" and len(object_parts) in {1, 2}:
        object_type = "DATABASE" if len(object_parts) == 1 else "SCHEMA"
        profile = _string_literal(assertion.get("expected_profile"), "drift_contract.assertion.expected_profile")
        object_literal = _string_literal(".".join(object_parts), "drift_contract.assertion.object")
        return f"GET_DDL('{object_type}', {object_literal}) NOT ILIKE '%' || {profile} || '%'"
    if assertion_type == "policy_digest":
        expected_digest = _string_literal(assertion.get("expected_digest"), "drift_contract.assertion.expected_digest")
        return f"SHA2_HEX(GET_DDL('MASKING POLICY', { _string_literal(assertion.get('object'), 'drift_contract.assertion.object') })) <> {expected_digest}"
    raise ValidationError(f"create_drift_check_procedure cannot render scheduled predicate for assertion type {assertion_type!r}")


def _drift_notification_lines(operation: dict[str, Any], runs_table: str, findings_table: str) -> list[str]:
    integration = operation.get("notification_integration")
    recipients = operation.get("notification_recipients")
    if integration in (None, "") and recipients in (None, []):
        return ["  -- No notification integration was supplied; findings are recorded for CoCo review without sending email."]
    integration_name = _identifier(integration, "create_drift_check_procedure.notification_integration")
    if not isinstance(recipients, list) or not recipients:
        raise ValidationError("create_drift_check_procedure.notification_recipients must be a non-empty list when notification_integration is set")
    recipient_literal = _string_literal(",".join(str(recipient) for recipient in recipients), "create_drift_check_procedure.notification_recipients")
    return [
        f"  IF ((SELECT FINDING_COUNT FROM {runs_table} WHERE RUN_ID = :RUN_ID) > 0) THEN",
        "    CALL SYSTEM$SEND_EMAIL(",
        f"      '{integration_name}',",
        f"      {recipient_literal},",
        "      'Governance Drift Detected: ' || :MONITOR_NAME,",
        "      'Governance Drift Detected: ' || :MONITOR_NAME || CHR(10) || CHR(10) ||",
        "      'Intent-driven Governance has detected potential drift in approved governance controls.' || CHR(10) || CHR(10) ||",
        "      'Summary' || CHR(10) || CHR(10) ||",
        "      'Monitor: ' || :MONITOR_NAME || CHR(10) ||",
        "      'Run ID: ' || :RUN_ID || CHR(10) ||",
        "      'Baseline: ' || :BASELINE_VERSION || CHR(10) ||",
        "      'Severity: Review Required' || CHR(10) ||",
        f"      'Findings: ' || (SELECT FINDING_COUNT FROM {runs_table} WHERE RUN_ID = :RUN_ID) || ' potential difference(s) were detected relative to the approved baseline.' || CHR(10) ||",
        "      'Remediation Status: No changes were applied automatically.' || CHR(10) || CHR(10) ||",
        "      'Recommended Next Step' || CHR(10) || CHR(10) ||",
        "      'Open a CoCo conversation with the Intent-driven Governance skill and ask:' || CHR(10) || CHR(10) ||",
        "      '\"Review the latest scheduled drift run, explain the findings, and prepare a fix-forward remediation plan for approval.\"' || CHR(10) || CHR(10) ||",
        "      'Artifacts' || CHR(10) || CHR(10) ||",
        f"      'Drift Findings Table: {findings_table}' || CHR(10) ||",
        "      'Baseline Contract: ' || COALESCE(:DRIFT_CONTRACT:drift_contract_stage_path::STRING, '@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/latest/drift_contract.json')",
        "    );",
        "  END IF;",
    ]


def _drift_expected_json(assertion: dict[str, Any]) -> str:
    parts = []
    for key in ("type", "object", "tag", "expected_value", "expected_policy", "expected_profile", "expected_digest"):
        if key in assertion:
            text = str(assertion[key]).replace('"', '\\"')
            parts.append(f'"{key}": "{text}"')
    return "{" + ", ".join(parts) + "}"


def _render_create_drift_monitor_task(operation: dict[str, Any]) -> str:
    task_fqn = _required_fqn(operation, "task_fqn", 3)
    warehouse = _identifier(operation.get("warehouse"), "create_drift_monitor_task.warehouse")
    schedule = _string_literal(operation.get("schedule"), "create_drift_monitor_task.schedule")
    procedure_fqn = _required_fqn(operation, "procedure_fqn", 3)
    monitor_name = _string_literal(operation.get("monitor_name"), "create_drift_monitor_task.monitor_name")
    baseline_version = _string_literal(operation.get("baseline_version", "latest_committed"), "create_drift_monitor_task.baseline_version")
    contract_stage_path = _string_literal(operation.get("drift_contract_stage_path"), "create_drift_monitor_task.drift_contract_stage_path")
    return "\n".join([
        f"CREATE TASK IF NOT EXISTS {task_fqn}",
        f"  WAREHOUSE = {warehouse}",
        f"  SCHEDULE = {schedule}",
        "AS",
        f"  CALL {procedure_fqn}({monitor_name}, {baseline_version}, OBJECT_CONSTRUCT('drift_contract_stage_path', {contract_stage_path}));",
    ])


def _render_resume_drift_monitor_task(operation: dict[str, Any]) -> str:
    task_fqn = _required_fqn(operation, "task_fqn", 3)
    return f"ALTER TASK {task_fqn} RESUME;"


def _render_reference_notification_integration(operation: dict[str, Any]) -> str:
    integration = _identifier(operation.get("integration_name"), "reference_notification_integration.integration_name")
    recipients = operation.get("recipients")
    if not isinstance(recipients, list) or not recipients:
        raise ValidationError("reference_notification_integration.recipients must be a non-empty list")
    _string_literal(",".join(str(recipient) for recipient in recipients), "reference_notification_integration.recipients")
    return "\n".join([
        f"SHOW NOTIFICATION INTEGRATIONS LIKE '{integration}';",
        "-- Notification recipients are stored in the approved monitor configuration; no install-time email is sent.",
    ])


def _operation_kind(operation: dict[str, Any]) -> str:
    op = operation.get("op")
    if not isinstance(op, str) or not op.strip():
        raise ValidationError("operation.op must be a non-empty string")
    op = op.strip().lower()
    if op not in _SUPPORTED_OPS:
        raise ValidationError(f"unsupported operation: {op}")
    return op


def _validate_capability_metadata(operation: dict[str, Any]) -> None:
    if "capability_status" in operation:
        raise ValidationError("operation.capability_status is session-only and must not be persisted in typed operations")
    if "missing_capabilities" in operation:
        raise ValidationError("operation.missing_capabilities is session-only; persist required_privileges on the handoff package")
    _dependency_indexes(operation)


def _capability_statuses(value: dict[int, str] | None, operation_count: int) -> dict[int, str]:
    if value is None:
        return {index: "unknown" for index in range(1, operation_count + 1)}
    if not isinstance(value, dict):
        raise ValidationError("capability_status_by_statement must be a mapping of statement index to status")
    statuses: dict[int, str] = {}
    for index in range(1, operation_count + 1):
        status = value.get(index, "unknown")
        if status not in _CAPABILITY_STATUSES:
            raise ValidationError(f"capability status must be one of {sorted(_CAPABILITY_STATUSES)}")
        statuses[index] = status
    out_of_range = sorted(index for index in value if not isinstance(index, int) or index < 1 or index > operation_count)
    if out_of_range:
        raise ValidationError(f"capability_status_by_statement indexes out of range: {out_of_range}")
    return statuses


def _dependency_indexes(operation: dict[str, Any]) -> set[int]:
    raw = operation.get("depends_on_statement_indexes", [])
    if raw in (None, ""):
        return set()
    if not isinstance(raw, list):
        raise ValidationError("operation.depends_on_statement_indexes must be a list of positive integers")
    indexes: set[int] = set()
    for value in raw:
        if not isinstance(value, int) or value < 1:
            raise ValidationError("operation.depends_on_statement_indexes must be a list of positive integers")
        indexes.add(value)
    return indexes


def _validated_dependency_indexes(operation: dict[str, Any], index: int, operation_count: int) -> set[int]:
    indexes = _dependency_indexes(operation)
    if index in indexes:
        raise ValidationError("operation.depends_on_statement_indexes cannot include the operation's own statement index")
    out_of_range = sorted(value for value in indexes if value > operation_count)
    if out_of_range:
        raise ValidationError(
            "operation.depends_on_statement_indexes must reference existing statement indexes; "
            f"out of range: {out_of_range}"
        )
    forward = sorted(value for value in indexes if value > index)
    if forward:
        raise ValidationError(
            "operation.depends_on_statement_indexes must reference earlier statement indexes only; "
            f"forward references: {forward}"
        )
    return indexes


def _purpose_text(op: str, target: str) -> str:
    return {
        "create_tag": f"Create tag {target}",
        "create_masking_policy": f"Create masking policy {target}",
        "set_masking_policy": f"Bind masking policy to {target}",
        "set_tag": f"Set tag on {target}",
        "create_classification_profile": f"Create classification profile {target}",
        "set_classification_profile": f"Attach classification profile to {target}",
        "create_monitoring_schema": f"Create monitoring schema {target}",
        "create_drift_runs_table": f"Create drift runs table {target}",
        "create_drift_findings_table": f"Create drift findings table {target}",
        "create_drift_check_procedure": f"Create scheduled drift check procedure {target}",
        "create_drift_monitor_task": f"Create scheduled drift monitor task {target}",
        "resume_drift_monitor_task": f"Resume scheduled drift monitor task {target}",
        "reference_notification_integration": f"Reference drift notification integration {target}",
    }[op]


def _target_type(operation: dict[str, Any], allowed: set[str]) -> str:
    target_type = operation.get("target_type")
    if not isinstance(target_type, str):
        raise ValidationError("target_type must be a string")
    target_type = target_type.strip().lower()
    if target_type not in allowed:
        raise ValidationError(f"target_type must be one of: {', '.join(sorted(allowed))}")
    return target_type


def _target_fqn(operation: dict[str, Any], target_type: str) -> str:
    return _required_fqn(operation, "target_fqn", 1 if target_type == "database" else 2)


def _split_column_fqn(value: Any, field: str) -> tuple[str, str]:
    fqn = _fqn(value, field, 4)
    parts = fqn.split(".")
    return ".".join(parts[:3]), parts[3]


def _required_fqn(operation: dict[str, Any], field: str, parts: int) -> str:
    return _fqn(operation.get(field), field, parts)


def _fqn(value: Any, field: str, parts: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be a non-empty string")
    normalized = ".".join(_identifier(part, field) for part in value.strip().split("."))
    if len(normalized.split(".")) != parts:
        raise ValidationError(f"{field} must have {parts} identifier part(s)")
    return normalized


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be a non-empty identifier")
    identifier = value.strip().strip('"').upper()
    if not _IDENTIFIER_RE.fullmatch(identifier):
        raise ValidationError(f"{field} must be an unquoted Snowflake identifier")
    return identifier


def _type_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be a non-empty type")
    type_name = value.strip().upper()
    if not _TYPE_RE.fullmatch(type_name):
        raise ValidationError(f"{field} must be a simple Snowflake type")
    return type_name


def _safe_masked_expression(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("create_masking_policy.body.masked_expression must be a safe literal or NULL")
    expression = value.strip()
    if not _SAFE_LITERAL_RE.fullmatch(expression):
        raise ValidationError("create_masking_policy.body.masked_expression must be a safe literal or NULL")
    return expression.upper() if expression.upper() == "NULL" else expression


def _string_literal(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be a non-empty string")
    return "'" + value.replace("'", "''") + "'"


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"{field} must be a boolean")
    return value


def _non_negative_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValidationError(f"{field} must be a non-negative integer")
    return value


def _positive_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValidationError(f"{field} must be a positive integer")
    return value


def _json_bool(value: bool) -> str:
    return "true" if value else "false"


def _non_empty_text(value: Any, fallback: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback
