"""Deterministic governance kernel for intent-driven-governance.

This is intentionally small: it validates the state shape, compiles simple
column-level masking intent into intent controls, diffs intent vs observed, and
checks stale approvals before reconciliation. It is the executable counterpart to
STATE.md and the tool contracts.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

STATE_LEVELS = {"account", "database", "schema", "table", "column"}
_NODE_KEYS = {"level", "name", "observed", "intent", "intent_text"}
_CONTROL_KINDS = {"masking_policy", "tag_binding"}
_MASK_INTENT_RE = re.compile(r"\b(mask|masked|redact|redacted|protect|protected)\b", re.I)
_UNPROTECTED_INTENT_RE = re.compile(r"\b(unprotected|leave\s+.*(?:plain|exposed|unmasked)|no\s+mask)\b", re.I)
_EXCEPT_ROLE_RE = re.compile(r"except\s+(?:for\s+)?([A-Z0-9_]+)", re.I)
_ROLE_IN_SESSION_RE = re.compile(r"IS_ROLE_IN_SESSION\('([^']+)'\)", re.I)
_CURRENT_ROLE_IN_RE = re.compile(r"CURRENT_ROLE\(\)\s+IN\s*\(([^)]*)\)", re.I)
_ROLE_NAME_RE = re.compile(r"[A-Z_][A-Z0-9_]*")
_POLICY_BODY_RE = re.compile(
    r"CASE WHEN IS_ROLE_IN_SESSION\('[A-Z_][A-Z0-9_]*'\) THEN val ELSE (?:NULL|'\*\*\*') END"
)


class ValidationError(ValueError):
    """Raised when a state document violates the structural state contract."""


_SESSION_ONLY_STATE_KEYS = {
    "capabilities",
    "capability_check",
    "capability_status",
    "missing_capabilities",
    "execution_plan",
    "recommended_mode",
}


@dataclass(frozen=True)
class NodeRef:
    path: tuple[str, ...]
    node: dict[str, Any]

    @property
    def fqn(self) -> str:
        return ".".join(self.path)


def validate_state(state: dict[str, Any]) -> list[str]:
    """Validate state shape and return warnings.

    Raises ValidationError for structural issues that make deterministic actions
    unsafe. Warnings are non-fatal consistency notes.
    """

    if not isinstance(state, dict):
        raise ValidationError("state must be a mapping")

    forbidden_path = _find_session_only_state_key(state)
    if forbidden_path:
        raise ValidationError(f"session-only capability field must not be persisted in state: {forbidden_path}")

    required = {"scope", "base_version", "raw_intent", "objects", "artifacts", "intent_artifacts", "delta"}
    missing = sorted(required - set(state))
    if missing:
        raise ValidationError(f"missing top-level fields: {', '.join(missing)}")

    if not isinstance(state["scope"], str) or not state["scope"].strip():
        raise ValidationError("scope must be a non-empty string")
    if not isinstance(state["base_version"], int) or state["base_version"] < 0:
        raise ValidationError("base_version must be a non-negative integer")
    if not isinstance(state["raw_intent"], list):
        raise ValidationError("raw_intent must be a list")
    if not isinstance(state["objects"], dict):
        raise ValidationError("objects must be a mapping")
    if not isinstance(state["artifacts"], dict):
        raise ValidationError("artifacts must be a flat mapping")
    if not isinstance(state["intent_artifacts"], dict):
        raise ValidationError("intent_artifacts must be a flat mapping")
    if not isinstance(state["delta"], list):
        raise ValidationError("delta must be a list")
    if "phase_details" in state and not isinstance(state["phase_details"], dict):
        raise ValidationError("phase_details must be a mapping")

    raw_ids = _validate_raw_intent(state["raw_intent"])
    warnings: list[str] = []
    object_paths = set()
    for ref in iter_nodes(state["objects"]):
        _validate_node(ref, raw_ids)
        if ref.fqn in object_paths:
            raise ValidationError(f"duplicate object path: {ref.fqn}")
        object_paths.add(ref.fqn)
        _validate_control(ref.node.get("observed"), f"{ref.fqn}.observed")

    for artifact_field in ("artifacts", "intent_artifacts"):
        for control_name, body in state[artifact_field].items():
            if not isinstance(control_name, str) or not control_name.strip():
                raise ValidationError(f"{artifact_field} has an empty control name")
            if not isinstance(body, str):
                raise ValidationError(f"{artifact_field}.{control_name} must be a string body")

    observed_controls = set(_controls_from_nodes(state["objects"], "observed"))
    missing_observed_bodies = sorted(observed_controls - set(state["artifacts"]))
    if missing_observed_bodies:
        warnings.append("observed controls missing artifact bodies: " + ", ".join(missing_observed_bodies))

    intent_controls = set(_controls_from_nodes(state["objects"], "intent"))
    missing_intent_bodies = sorted(intent_controls - set(state["intent_artifacts"]))
    if missing_intent_bodies:
        warnings.append("intent controls missing artifact bodies: " + ", ".join(missing_intent_bodies))

    return warnings


def _find_session_only_state_key(value: Any, path: str = "state") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text in _SESSION_ONLY_STATE_KEYS:
                return child_path
            found = _find_session_only_state_key(child, child_path)
            if found:
                return found
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            found = _find_session_only_state_key(child, f"{path}[{idx}]")
            if found:
                return found
    return None


def build_column_state(
    *,
    scope: str,
    table_fqn: str,
    mask_columns: list[str],
    unprotected_columns: list[str],
    except_role: str = "ACCOUNTADMIN",
    raw_statement: str | None = None,
    who: str = "user",
    when: str = "unknown",
    context: str = "intent capture",
) -> dict[str, Any]:
    """Build a minimal valid state for one table's column masking intent."""

    except_role = _validate_role_name(except_role, "except_role")
    parts = [part.strip().strip('"').upper() for part in table_fqn.split(".") if part.strip()]
    if len(parts) != 3:
        raise ValidationError("table_fqn must be database.schema.table")
    database, schema, table = parts
    raw_statement = raw_statement or (
        f"Mask {', '.join(mask_columns)} except {except_role}; "
        f"leave {', '.join(unprotected_columns)} unprotected."
    )
    table_node: dict[str, Any] = {
        "level": "table",
        "name": table,
        "observed": None,
        "intent": None,
    }
    for column in mask_columns:
        name = column.strip().strip('"').upper()
        table_node[name] = {
            "level": "column",
            "name": name,
            "observed": None,
            "intent": {"control": f"{database}.{schema}.MASK_{name}", "kind": "masking_policy"},
        }
    for column in unprotected_columns:
        name = column.strip().strip('"').upper()
        table_node[name] = {
            "level": "column",
            "name": name,
            "observed": None,
            "intent": None,
        }
    state = {
        "scope": scope,
        "base_version": 0,
        "raw_intent": [
            {
                "id": "ri-001",
                "statement": raw_statement,
                "what": {
                    "scope": f"{database}.{schema}.{table}",
                    "objects": [column.strip().strip('"').upper() for column in [*mask_columns, *unprotected_columns]],
                },
                "how": {
                    "control": "masking_policy",
                    "protected_columns": [column.strip().strip('"').upper() for column in mask_columns],
                    "intentionally_unprotected": [column.strip().strip('"').upper() for column in unprotected_columns],
                    "exempt_roles": [except_role.upper()],
                    "protected_behavior": f"mask protected columns for everyone except {except_role.upper()}",
                },
                "who": who,
                "when": when,
                "context": context,
            }
        ],
        "objects": {
            "level": "account",
            "name": "ACCOUNT",
            "observed": None,
            "intent": None,
            database: {
                "level": "database",
                "name": database,
                "observed": None,
                "intent": None,
                schema: {
                    "level": "schema",
                    "name": schema,
                    "observed": None,
                    "intent": None,
                    table: table_node,
                },
            },
        },
        "artifacts": {},
        "intent_artifacts": {},
        "delta": [],
    }
    validate_state(state)
    return state


def set_observed_masking_policy(
    state: dict[str, Any],
    table_fqn: str,
    column: str,
    *,
    except_role: str = "ACCOUNTADMIN",
) -> dict[str, Any]:
    """Return state with a live masking policy observed on one column."""

    except_role = _validate_role_name(except_role, "except_role")
    validate_state(state)
    new_state = copy.deepcopy(state)
    parts = [part.strip().strip('"').upper() for part in table_fqn.split(".")]
    if len(parts) != 3:
        raise ValidationError("table_fqn must be database.schema.table")
    database, schema, table = parts
    column_name = column.strip().strip('"').upper()
    table_node = _find_table_node(new_state["objects"], database, schema, table)
    if table_node is None or column_name not in table_node:
        raise ValidationError(f"unknown observed column: {database}.{schema}.{table}.{column_name}")
    column_node = table_node[column_name]
    control_name = f"{database}.{schema}.MASK_{column_name}"
    column_node["observed"] = _with_control(column_node.get("observed"), {"control": control_name, "kind": "masking_policy"})
    body = _masking_policy_body(f"except {except_role}", column_name)
    new_state.setdefault("artifacts", {})[control_name] = body
    new_state.pop("scoped_digest", None)
    validate_state(new_state)
    return new_state


def set_column_tag_binding(
    state: dict[str, Any],
    table_fqn: str,
    column: str,
    *,
    tag_fqn: str,
    value: str,
    field: str = "intent",
) -> dict[str, Any]:
    """Return state with a column tag binding in observed or intent state."""

    if field not in {"observed", "intent"}:
        raise ValidationError("field must be observed or intent")
    validate_state(state)
    new_state = copy.deepcopy(state)
    parts = [part.strip().strip('"').upper() for part in table_fqn.split(".")]
    if len(parts) != 3:
        raise ValidationError("table_fqn must be database.schema.table")
    database, schema, table = parts
    column_name = column.strip().strip('"').upper()
    table_node = _find_table_node(new_state["objects"], database, schema, table)
    if table_node is None or column_name not in table_node:
        raise ValidationError(f"unknown tag binding column: {database}.{schema}.{table}.{column_name}")
    tag_control = {"control": tag_fqn.strip().upper(), "kind": "tag_binding", "value": value}
    table_node[column_name][field] = _with_control(table_node[column_name].get(field), tag_control)
    new_state.pop("scoped_digest", None)
    validate_state(new_state)
    return new_state


def derive_intent(state: dict[str, Any]) -> dict[str, Any]:
    """Return a new state with intent artifacts and delta.

    The minimal kernel treats object-level `intent` as the executable target: a
    control binding, `null` for intentionally unprotected, or `unspecified`. It
    materializes policy bodies and diffs that intent against observed state.
    """

    validate_state(state)
    new_state = copy.deepcopy(state)
    digest = scoped_digest(new_state)
    if new_state.get("scoped_digest") == digest and new_state.get("intent_artifacts") is not None:
        return new_state

    new_state["intent_artifacts"] = {}
    for ref in iter_nodes(new_state["objects"]):
        node = ref.node
        if node.get("level") != "column":
            continue
        target = effective_intent_target(new_state["objects"], ref.path)
        node["intent"] = copy.deepcopy(target)
        for control in _controls(target):
            if control.get("kind") != "masking_policy":
                continue
            control_name = control["control"]
            intent_statement = _intent_statement_for(node, new_state.get("raw_intent", []))
            new_state["intent_artifacts"][control_name] = _masking_policy_body(intent_statement, ref.path[-1])

    new_state["delta"] = diff_state(new_state)
    new_state["scoped_digest"] = digest
    return new_state


def diff_state(state: dict[str, Any]) -> list[str]:
    """Build SQL delta for intent-vs-observed masking controls."""

    delta: list[str] = []
    intent_artifacts = state.get("intent_artifacts", {})
    artifacts = state.get("artifacts", {})
    for ref in iter_nodes(state["objects"]):
        if ref.node.get("level") != "column":
            continue
        target = ref.node.get("intent")
        observed = ref.node.get("observed")
        if target is None:
            if _masking_controls(observed):
                delta.append(f"ALTER TABLE {_table_fqn(ref.path)} MODIFY COLUMN {_quote_ident(ref.path[-1])} UNSET MASKING POLICY;")
            continue
        if target == "unspecified" or isinstance(target, str):
            continue
        observed_controls = _controls(observed)
        observed_mask = _first_control(observed_controls, "masking_policy")
        for intent in _controls(target):
            intent_kind = intent.get("kind")
            intent_control = intent["control"]
            if intent_kind == "masking_policy":
                observed_control = observed_mask.get("control") if observed_mask else None
                intent_body = intent_artifacts.get(intent_control, "")
                observed_body = artifacts.get(observed_control, "") if observed_control else ""
                if not observed_control or observed_control != intent_control or not semantic_match(intent_body, observed_body):
                    if observed_control:
                        delta.append(
                            f"ALTER TABLE {_table_fqn(ref.path)} MODIFY COLUMN {_quote_ident(ref.path[-1])} "
                            "UNSET MASKING POLICY;"
                        )
                    delta.append(_create_policy_sql(intent_control, intent_body, _policy_value_type(ref.node)))
                    delta.append(
                        f"ALTER TABLE {_table_fqn(ref.path)} MODIFY COLUMN {_quote_ident(ref.path[-1])} "
                        f"SET MASKING POLICY {_quote_fqn(intent_control)};"
                    )
            elif intent_kind == "tag_binding" and not _has_matching_tag_binding(observed_controls, intent):
                delta.append(
                    f"ALTER TABLE {_table_fqn(ref.path)} MODIFY COLUMN {_quote_ident(ref.path[-1])} "
                    f"SET TAG {_quote_fqn(intent_control)} = {_quote_literal(str(intent.get('value', '')))};"
                )
    return delta


def explain(state: dict[str, Any]) -> str:
    """Render observed/intent/delta in plain English."""

    validate_state(state)
    lines = ["Governance plan:"]
    delta = state.get("delta", [])
    for ref in iter_nodes(state["objects"]):
        if ref.node.get("level") != "column":
            continue
        target = ref.node.get("intent")
        intent_statement = _intent_statement_for(ref.node, state.get("raw_intent", []))
        observed = ref.node.get("observed")
        if _masking_controls(target) and _masking_controls(observed) and _masking_controls(target)[0].get("control") == _masking_controls(observed)[0].get("control"):
            status = "already satisfies intent"
        elif _controls(target):
            kinds = sorted({str(control.get("kind")) for control in _controls(target)})
            status = "planned " + ", ".join(kinds) + " change"
        elif observed:
            status = "planned unprotect change"
        elif target == "unspecified":
            status = "unspecified; ask/propose before reconcile"
        else:
            status = "intentionally unprotected"
        lines.append(f"- {ref.fqn}: {status}. Intent: {intent_statement}.")
    if delta:
        lines.append("Delta SQL:")
        lines.extend(f"- {statement}" for statement in delta)
    else:
        lines.append("Delta SQL: none; observed already matches intent.")
    return "\n".join(lines)


def reconcile_plan(state: dict[str, Any], approved_delta: list[str]) -> dict[str, Any]:
    """Verify approval freshness and return the immutable snapshot candidate.

    This intentionally does not execute SQL. The caller/tool owns execution after
    this stale-plan check passes.
    """

    derived = derive_intent(state)
    current_delta = derived.get("delta", [])
    if current_delta != approved_delta:
        raise ValidationError("approved delta is stale; rerun explain and request approval again")
    if _has_unspecified(derived["objects"]):
        raise ValidationError("cannot reconcile while in-scope objects remain unspecified")
    snapshot = copy.deepcopy(derived)
    snapshot["base_version"] = int(snapshot["base_version"]) + 1
    _mark_observed_reconciled(snapshot)
    snapshot["delta"] = []
    snapshot["scoped_digest"] = scoped_digest(snapshot)
    return snapshot


def semantic_match(intent_body: str, observed_body: str) -> bool:
    """Small semantic matcher for equivalent role-based masking bodies."""

    return _normalize_sql(intent_body) == _normalize_sql(observed_body)


def scoped_digest(state: dict[str, Any]) -> str:
    relevant = {
        "scope": state.get("scope"),
        "raw_intent": state.get("raw_intent", []),
        "observed": [
            {"path": ref.path, "observed": ref.node.get("observed"), "intent": ref.node.get("intent")}
            for ref in iter_nodes(state.get("objects", {}))
        ],
        "artifacts": state.get("artifacts", {}),
    }
    payload = json.dumps(relevant, sort_keys=True, separators=(",", ":"), default=list)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def iter_nodes(root: dict[str, Any]) -> Iterable[NodeRef]:
    if not isinstance(root, dict):
        return
    root_name = root.get("name")
    if not isinstance(root_name, str) or not root_name:
        root_name = "ACCOUNT"
    yield from _iter_nodes(root, (root_name,))


def _iter_nodes(node: dict[str, Any], path: tuple[str, ...]) -> Iterable[NodeRef]:
    yield NodeRef(path, node)
    for key, value in node.items():
        if key in _NODE_KEYS or not isinstance(value, dict) or "level" not in value:
            continue
        child_name = value.get("name") if isinstance(value.get("name"), str) else key
        yield from _iter_nodes(value, path + (child_name,))


def effective_intent_target(root: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: dict[str, Any] | None = root
    nearest: Any = "unspecified"
    for idx, part in enumerate(path):
        if idx == 0:
            current = root
        elif current is not None:
            current = _find_child(current, part)
        if not current:
            break
        if "intent" in current and current["intent"] != "inherit":
            nearest = current["intent"]
    return nearest


def _find_child(node: dict[str, Any], name: str) -> dict[str, Any] | None:
    for key, value in node.items():
        if key in _NODE_KEYS or not isinstance(value, dict):
            continue
        if key == name or value.get("name") == name:
            return value
    return None


def _find_table_node(root: dict[str, Any], database: str, schema: str, table: str) -> dict[str, Any] | None:
    database_node = _find_child(root, database)
    schema_node = _find_child(database_node, schema) if database_node else None
    return _find_child(schema_node, table) if schema_node else None


def _validate_raw_intent(raw_intent: list[Any]) -> set[str]:
    raw_ids: set[str] = set()
    for idx, entry in enumerate(raw_intent):
        if not isinstance(entry, dict):
            raise ValidationError(f"raw_intent[{idx}] must be a mapping")
        for field in ("id", "statement", "who", "when", "context"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValidationError(f"raw_intent[{idx}].{field} must be a non-empty string")
        _validate_structured_intent(entry, idx)
        if entry["id"] in raw_ids:
            raise ValidationError(f"duplicate raw_intent id: {entry['id']}")
        raw_ids.add(entry["id"])
    return raw_ids


def _validate_structured_intent(entry: dict[str, Any], idx: int) -> None:
    what = entry.get("what")
    if not isinstance(what, dict):
        raise ValidationError(f"raw_intent[{idx}].what must be a mapping")
    if not isinstance(what.get("scope"), str) or not what["scope"].strip():
        raise ValidationError(f"raw_intent[{idx}].what.scope must be a non-empty string")
    objects = what.get("objects", [])
    if objects is not None and not isinstance(objects, list):
        raise ValidationError(f"raw_intent[{idx}].what.objects must be a list")

    how = entry.get("how")
    if not isinstance(how, dict):
        raise ValidationError(f"raw_intent[{idx}].how must be a mapping")
    if not isinstance(how.get("control"), str) or not how["control"].strip():
        raise ValidationError(f"raw_intent[{idx}].how.control must be a non-empty string")
    if "why" in entry and entry["why"] is not None and not isinstance(entry["why"], str):
        raise ValidationError(f"raw_intent[{idx}].why must be a string when present")


def _validate_node(ref: NodeRef, raw_ids: set[str]) -> None:
    node = ref.node
    for field in ("level", "name", "observed", "intent"):
        if field not in node:
            raise ValidationError(f"{ref.fqn} missing {field}")
    if node["level"] not in STATE_LEVELS:
        raise ValidationError(f"{ref.fqn}.level is invalid: {node['level']}")
    if not isinstance(node["name"], str) or not node["name"]:
        raise ValidationError(f"{ref.fqn}.name must be a non-empty string")
    target = node.get("intent")
    _validate_intent_target(target, f"{ref.fqn}.intent")
    intent_from = node.get("intent_from", [])
    if not isinstance(intent_from, list):
        raise ValidationError(f"{ref.fqn}.intent_from must be a list")
    for raw_id in intent_from:
        if raw_id not in raw_ids:
            raise ValidationError(f"{ref.fqn}.intent_from references unknown raw_intent id: {raw_id}")


def _mark_observed_reconciled(state: dict[str, Any]) -> None:
    intent_artifacts = state.get("intent_artifacts", {})
    artifacts = state.setdefault("artifacts", {})
    for ref in iter_nodes(state["objects"]):
        if ref.node.get("level") != "column":
            continue
        target = ref.node.get("intent")
        if _controls(target):
            ref.node["observed"] = copy.deepcopy(target)
            for control in _controls(target):
                control_name = control["control"]
                if control_name in intent_artifacts:
                    artifacts[control_name] = intent_artifacts[control_name]
        elif target is None:
            ref.node["observed"] = None


def _validate_control(control: Any, field_name: str) -> None:
    if control is None:
        return
    if isinstance(control, list):
        if not control:
            raise ValidationError(f"{field_name} control list must not be empty")
        for idx, item in enumerate(control):
            _validate_control(item, f"{field_name}[{idx}]")
        return
    if not isinstance(control, dict):
        raise ValidationError(f"{field_name} must be null or a mapping")
    if not isinstance(control.get("control"), str) or not control["control"].strip():
        raise ValidationError(f"{field_name}.control must be a non-empty string")
    if control.get("kind") not in _CONTROL_KINDS:
        raise ValidationError(f"{field_name}.kind must be one of {sorted(_CONTROL_KINDS)}")
    if control.get("kind") == "tag_binding" and (
        not isinstance(control.get("value"), str) or not control.get("value", "").strip()
    ):
        raise ValidationError(f"{field_name}.value must be a non-empty string for tag_binding")


def _validate_intent_target(target: Any, field_name: str) -> None:
    if target in (None, "inherit", "unspecified"):
        return
    _validate_control(target, field_name)


def _controls_from_nodes(root: dict[str, Any], field: str) -> Iterable[str]:
    for ref in iter_nodes(root):
        value = ref.node.get(field)
        for control in _controls(value):
            if control.get("kind") == "masking_policy" and control.get("control"):
                yield control["control"]


def _controls(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict) and isinstance(value.get("control"), str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict) and isinstance(item.get("control"), str)]
    return []


def _masking_controls(value: Any) -> list[dict[str, Any]]:
    return [control for control in _controls(value) if control.get("kind") == "masking_policy"]


def _first_control(controls: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    for control in controls:
        if control.get("kind") == kind:
            return control
    return None


def _has_matching_tag_binding(observed_controls: list[dict[str, Any]], intent: dict[str, Any]) -> bool:
    return any(
        control.get("kind") == "tag_binding"
        and control.get("control") == intent.get("control")
        and str(control.get("value", "")) == str(intent.get("value", ""))
        for control in observed_controls
    )


def _with_control(value: Any, new_control: dict[str, Any]) -> Any:
    controls = _controls(value)
    filtered = [
        control
        for control in controls
        if not (
            control.get("kind") == new_control.get("kind")
            and control.get("control") == new_control.get("control")
        )
    ]
    filtered.append(new_control)
    return filtered[0] if len(filtered) == 1 else filtered


def _has_unspecified(root: dict[str, Any]) -> bool:
    return any(ref.node.get("intent") == "unspecified" for ref in iter_nodes(root))


def _intent_statement_for(node: dict[str, Any], raw_intent: list[dict[str, Any]]) -> str:
    statements = [entry.get("statement", "") for entry in raw_intent]
    return " ".join(statement for statement in statements if statement) or "intent target"

def _is_masking_intent(intent: str) -> bool:
    return bool(_MASK_INTENT_RE.search(intent))


def _is_unprotected_intent(intent: str) -> bool:
    return bool(_UNPROTECTED_INTENT_RE.search(intent))


def _allowed_role(intent: str) -> str:
    match = _EXCEPT_ROLE_RE.search(intent)
    role = match.group(1).upper() if match else "ACCOUNTADMIN"
    return _validate_role_name(role, "masking policy role")


def _validate_role_name(role: str, field: str) -> str:
    normalized = str(role).strip().strip('"').upper()
    if not _ROLE_NAME_RE.fullmatch(normalized):
        raise ValidationError(f"{field} must be an unquoted Snowflake role identifier")
    return normalized


def _intent_control_name(path: tuple[str, ...]) -> str:
    database = path[1] if len(path) > 1 else path[0]
    schema = path[2] if len(path) > 2 else "GOVERNANCE_INTENT_WORKSPACE"
    column = re.sub(r"[^A-Z0-9_]", "_", path[-1].upper())
    return f"{database}.{schema}.MASK_{column}"


def _masking_policy_body(intent: str, column_name: str) -> str:
    role = _allowed_role(intent)
    if "date" in column_name.lower() or "dob" in column_name.lower():
        return f"CASE WHEN IS_ROLE_IN_SESSION('{role}') THEN val ELSE NULL END"
    return f"CASE WHEN IS_ROLE_IN_SESSION('{role}') THEN val ELSE '***' END"


def _create_policy_sql(control_name: str, body: str, value_type: str) -> str:
    if not _POLICY_BODY_RE.fullmatch(body):
        raise ValidationError("masking policy body must match a supported kernel template")
    return (
        f"CREATE OR REPLACE MASKING POLICY {_quote_fqn(control_name)} "
        f"AS (val {value_type}) RETURNS {value_type} -> {body};"
    )


def _policy_value_type(node: dict[str, Any]) -> str:
    data_type = str(node.get("data_type") or "").upper()
    if data_type in {"DATE", "TIMESTAMP", "TIMESTAMP_NTZ", "TIMESTAMP_LTZ", "TIMESTAMP_TZ"}:
        return data_type
    name = str(node.get("name") or "").lower()
    if "date" in name or name == "dob" or name.endswith("_dob"):
        return "DATE"
    return "VARCHAR"


def _table_fqn(path: tuple[str, ...]) -> str:
    if len(path) < 4:
        raise ValidationError(f"column path must include database.schema.table.column: {'.'.join(path)}")
    return ".".join(_quote_ident(part) for part in path[1:-1])


def _quote_fqn(name: str) -> str:
    return ".".join(_quote_ident(part) for part in name.split("."))


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _quote_ident(name: str) -> str:
    if re.fullmatch(r"[A-Z_][A-Z0-9_]*", name):
        return name
    return '"' + name.replace('"', '""') + '"'


def _normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().rstrip(";")).upper()


def _roles_from_policy(sql: str) -> set[str]:
    roles = {role.upper() for role in _ROLE_IN_SESSION_RE.findall(sql)}
    match = _CURRENT_ROLE_IN_RE.search(sql)
    if match:
        roles.update(part.strip().strip("'").upper() for part in match.group(1).split(",") if part.strip())
    return roles
