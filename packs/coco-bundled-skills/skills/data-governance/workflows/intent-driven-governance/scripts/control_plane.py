#!/usr/bin/env python3
"""CLI wrapper for the intent-driven-governance executable kernel."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - fallback for minimal environments
    yaml = None

_SKILL_DIR = Path(__file__).resolve().parents[1]
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

from kernel import (  # noqa: E402
    ValidationError,
    derive_intent,
    explain,
    reconcile_plan,
    validate_state,
)
from kernel.phases import (  # noqa: E402
    capture_intent,
    derive_specs_plan,
    execute_sql,
    generate_sql,
    observe,
)


_PHASE_VALIDATORS = {
    "1": observe,
    "observe": observe,
    "2": capture_intent,
    "capture-intent": capture_intent,
    "3": derive_specs_plan,
    "derive-specs-plan": derive_specs_plan,
    "4": generate_sql,
    "generate-sql": generate_sql,
    "5": execute_sql,
    "execute-sql": execute_sql,
}

_ARTIFACT_STAGE_RE = re.compile(r"^@GOVERNANCE_INTENT_WORKSPACE\.ARTIFACTS\.FILES/[A-Za-z0-9_./=$-]+$")
_SEMICOLON_TOKEN = "__IDG_SEMICOLON__"
_DOLLAR_DELIMITER_TOKEN = "__IDG_DOLLAR_DELIMITER__"


def _load(path: str) -> dict[str, Any]:
    text = Path(path).read_text()
    if path.endswith(".json") or yaml is None:
        return json.loads(text)
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValidationError("state file must contain a mapping")
    return data


def _dump(data: Any, output: str | None) -> None:
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if output:
        Path(output).write_text(text)
    else:
        print(text, end="")


def render_artifact_write_sql(target: str, content: str) -> str:
    if not _ARTIFACT_STAGE_RE.fullmatch(target):
        raise ValidationError("target must be under @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES")
    if _SEMICOLON_TOKEN in content or _DOLLAR_DELIMITER_TOKEN in content:
        raise ValidationError("artifact content contains reserved artifact-writer placeholder tokens")
    rows: list[str] = []
    for line_number, raw_line in enumerate(content.splitlines(), 1):
        line = raw_line.replace("$$", _DOLLAR_DELIMITER_TOKEN).replace(";", _SEMICOLON_TOKEN)
        rows.append(f"    ({line_number}, $${line}$$)")
    if not rows:
        rows.append("    (1, $$$$)")
    values = ",\n".join(rows)
    return "\n".join([
        f"COPY INTO {target}",
        "FROM (",
        "  SELECT",
        f"    REPLACE(REPLACE(line, '{_SEMICOLON_TOKEN}', CHR(59)), '{_DOLLAR_DELIMITER_TOKEN}', CHR(36) || CHR(36)) AS line",
        "  FROM (VALUES",
        values,
        "  ) AS t(line_number, line)",
        "  ORDER BY line_number",
        ")",
        "FILE_FORMAT = (",
        "  TYPE = CSV",
        "  COMPRESSION = NONE",
        "  FIELD_DELIMITER = '~!~!~'",
        "  RECORD_DELIMITER = '\\n'",
        "  FIELD_OPTIONALLY_ENCLOSED_BY = NONE",
        "  ESCAPE_UNENCLOSED_FIELD = NONE",
        "  EMPTY_FIELD_AS_NULL = FALSE",
        "  TRIM_SPACE = FALSE",
        "  NULL_IF = ()",
        ")",
        "SINGLE = TRUE",
        "OVERWRITE = TRUE;",
    ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate state structure")
    validate.add_argument("state")

    validate_phase = sub.add_parser("validate-phase", help="validate a phase artifact")
    validate_phase.add_argument("phase", choices=sorted(_PHASE_VALIDATORS))
    validate_phase.add_argument("state")

    derive = sub.add_parser("derive", help="derive intent controls and delta")
    derive.add_argument("state")
    derive.add_argument("-o", "--output")

    render = sub.add_parser("explain", help="render an English plan")
    render.add_argument("state")

    observe_summary = sub.add_parser("render-observation-summary", help="render Phase 1 Observation Summary")
    observe_summary.add_argument("state")

    intent_summary = sub.add_parser("render-intent-summary", help="render Phase 2 Consolidated Intent Summary")
    intent_summary.add_argument("state")

    governance_spec_summary = sub.add_parser("render-governance-spec", help="render Phase 3 Governance Spec")
    governance_spec_summary.add_argument("state")

    spec_plan_summary = sub.add_parser("render-spec-plan-summary", help="render Phase 3 Governance Spec (legacy alias)")
    spec_plan_summary.add_argument("state")

    governance_implementation = sub.add_parser(
        "render-governance-implementation",
        help="render Phase 4 Governance Implementation SQL",
    )
    governance_implementation.add_argument("state")

    sql_review = sub.add_parser("render-sql-review", help="render Phase 4 Governance Implementation SQL (legacy alias)")
    sql_review.add_argument("state")

    execution_summary = sub.add_parser("render-execution-summary", help="render Phase 5 Execution Summary")
    execution_summary.add_argument("state")

    write_artifact = sub.add_parser("write-artifact-sql", help="render safe COPY INTO SQL for a stage artifact")
    write_artifact.add_argument("target", help="target stage path under @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES")
    write_artifact.add_argument("content_file", help="local file containing artifact content")

    reconcile = sub.add_parser("reconcile-plan", help="verify approved delta freshness")
    reconcile.add_argument("state")
    reconcile.add_argument("approved_delta_json", help="path to a JSON file containing the approved delta list")
    reconcile.add_argument("-o", "--output")

    plan = sub.add_parser("plan-from-intent", help="build and derive a one-table masking plan")
    plan.add_argument("--scope", required=True)
    plan.add_argument("--table", required=True, help="database.schema.table")
    plan.add_argument("--mask-column", action="append", default=[])
    plan.add_argument("--unprotected-column", action="append", default=[])
    plan.add_argument(
        "--observed-policy-column",
        action="append",
        default=[],
        help="observed masked column, optionally COLUMN=EXCEPT_ROLE; repeat for brownfield setup",
    )
    plan.add_argument("--except-role", default="ACCOUNTADMIN")
    plan.add_argument("--statement")
    plan.add_argument("--who", default="user")
    plan.add_argument("--when", default="unknown")
    plan.add_argument("--context", default="intent capture")
    plan.add_argument("-o", "--output")

    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            warnings = validate_state(_load(args.state))
            _dump({"ok": True, "warnings": warnings}, None)
            return 0
        if args.command == "validate-phase":
            state = _load(args.state)
            warnings = validate_state(state)
            validator = _PHASE_VALIDATORS[args.phase]
            errors = validator.validate_artifact(state)
            _dump(
                {
                    "ok": not errors,
                    "can_exit": validator.can_exit_phase(state),
                    "errors": errors,
                    "warnings": warnings,
                },
                None,
            )
            return 0 if not errors else 2
        if args.command == "derive":
            _dump(derive_intent(_load(args.state)), args.output)
            return 0
        if args.command == "explain":
            state = derive_intent(_load(args.state))
            print(explain(state))
            return 0
        if args.command == "render-observation-summary":
            print(observe.render_observation_summary(_load(args.state)))
            return 0
        if args.command == "render-intent-summary":
            print(capture_intent.render_consolidated_intent_summary(_load(args.state)))
            return 0
        if args.command in {"render-governance-spec", "render-spec-plan-summary"}:
            print(derive_specs_plan.render_spec_plan_summary(_load(args.state)))
            return 0
        if args.command in {"render-governance-implementation", "render-sql-review"}:
            print(generate_sql.render_governance_implementation(_load(args.state)))
            return 0
        if args.command == "render-execution-summary":
            print(execute_sql.render_execution_summary(_load(args.state)))
            return 0
        if args.command == "write-artifact-sql":
            print(render_artifact_write_sql(args.target, Path(args.content_file).read_text()))
            return 0
        if args.command == "reconcile-plan":
            approved_delta = json.loads(Path(args.approved_delta_json).read_text())
            _dump(reconcile_plan(_load(args.state), approved_delta), args.output)
            return 0
        if args.command == "plan-from-intent":
            _dump(derive_specs_plan.plan_one_table_masking(
                scope=args.scope,
                table_fqn=args.table,
                mask_columns=args.mask_column,
                unprotected_columns=args.unprotected_column,
                observed_policy_columns=args.observed_policy_column,
                except_role=args.except_role,
                raw_statement=args.statement,
                who=args.who,
                when=args.when,
                context=args.context,
            ), args.output)
            return 0
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - CLI guardrail
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
