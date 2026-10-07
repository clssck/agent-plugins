# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

r"""Create custom AI functions in Snowflake.

Supports two modes:

1. **Flagged mode** (--database, --schema, etc.): Generates a standard AI_COMPLETE
   UDF from individual CLI flags specifying system prompt, user prompt template,
   inputs and outputs. Supports both text-only and multimodal (image/document)
   inputs. Uses response_format for structured JSON output when outputs are
   specified.

2. **Raw SQL mode** (--sql-body): Executes an agent-authored CREATE FUNCTION DDL
   directly. Supports arbitrary SQL UDF bodies (not limited to a single AI_COMPLETE
   call). The script handles execution, object tagging, and query tag logging.

Example usage:
    # Flagged mode
    python create_udf.py \
        --connection my_conn --database MY_DB --schema MY_SCHEMA \
        --function-name MY_FUNC --model claude-sonnet-4-5 \
        --system-prompt 'Classify sentiment' \
        --user-prompt-template '{TEXT}' \
        --inputs '[{"name":"TEXT","sql_type":"VARCHAR"}]' \
        --outputs '[{"name":"label","json_type":"string","description":"sentiment"}]'

    # Raw SQL mode
    python create_udf.py \
        --connection my_conn \
        --sql-body 'CREATE FUNCTION ...'
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
from textwrap import dedent
from typing import Any

from snowflake.snowpark import Session

from snowflake_ai_optimize.core.constants import COCO_SESSION_TAG_PREFIX
from snowflake_ai_optimize.core.session import (
    create_session_from_connection,
    custom_ai_query_tag_logging,
)
from snowflake_ai_optimize.core.sproc_decorators import surface_sproc_error
from snowflake_ai_optimize.core.udf_ddl import (
    CUSTOM_AI_FUNCTION_OBJECT_TAG,
    generate_sql,
    parse_config,
)

# Regex components for parsing CREATE FUNCTION DDL signatures.
_QUOTED_IDENTIFIER_RE = r'"(?:[^"]|"")+"'
_UNQUOTED_IDENTIFIER_RE = r"\w+"
_IDENTIFIER_RE = rf"(?:{_QUOTED_IDENTIFIER_RE}|{_UNQUOTED_IDENTIFIER_RE})"
_FQN_RE = rf"{_IDENTIFIER_RE}(?:\.{_IDENTIFIER_RE}){{0,2}}"
_CREATE_FUNCTION_RE = re.compile(
    rf"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+({_FQN_RE})\s*\(", re.IGNORECASE
)
_PARAM_DECL_RE = re.compile(rf"\s*{_IDENTIFIER_RE}\s+(.+?)\s*$", re.DOTALL)


@surface_sproc_error()
def create_handler(
    session: Session,
    function_name: str,
    model: str,
    system_prompt: str,
    user_prompt_template: str,
    inputs: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    function_intention: str | None = None,
    sql_body: str | None = None,
    stage_name: str | None = None,
) -> str:
    """SPROC entry point for CREATE_AI_FUNCTION stored procedure.

    Called by the Snowflake runtime with a live session. Supports two modes:
    - Flagged mode (sql_body is None): builds DDL from params via parse_config
    - Raw SQL mode (sql_body provided): executes the DDL directly

    Returns:
        The fully qualified name of the created function.

    """
    if not sql_body:
        parts = function_name.rsplit(".", 2)
        if len(parts) < 3:
            raise ValueError(
                f"Function name '{function_name}' must be fully qualified (DB.SCHEMA.FUNC)."
            )
        database, schema, func_name = parts[0], parts[1], parts[2]

        # Convert VARIANT inputs/outputs to Python lists if needed.
        # Snowflake may pass VARIANT as a JSON string in some contexts.
        if isinstance(inputs, str):
            input_list = json.loads(inputs) if inputs else []
        else:
            input_list = list(inputs) if inputs else []
        if isinstance(outputs, str):
            output_list = json.loads(outputs) if outputs else []
        else:
            output_list = list(outputs) if outputs else []

        config = {
            "database": database,
            "schema": schema,
            "function_name": func_name,
            "function_intention": function_intention or "",
            "model": model,
            "system_prompt": system_prompt,
            "user_prompt_template": user_prompt_template,
            "inputs": input_list,
            "outputs": output_list,
            "stage_name": stage_name,
        }

        sql_body = generate_sql(parse_config(config))

    return _execute_ddl(session, sql_body, tag_value="SPROC")


def main(
    connection: str,
    sql_body: str | None = None,
    config: dict[str, Any] | None = None,
    warehouse: str | None = None,
) -> None:
    """Create a custom AI function.

    Args:
        connection: Snowflake connection name.
        sql_body: Raw CREATE FUNCTION DDL (mutually exclusive with config).
        config: Dict config for flagged mode (passed to parse_config).
        warehouse: Optional warehouse override.

    Raises:
        ValueError: On invalid inputs or missing required fields.

    """
    if not sql_body and not config:
        raise ValueError("Either sql_body or config must be provided")

    with create_session_from_connection(connection) as session:
        if not warehouse:
            warehouse = _resolve_warehouse(session)
        session.use_warehouse(warehouse)

        if not sql_body:
            assert config is not None
            sql_body = generate_sql(parse_config(config))

        _execute_ddl(session, sql_body)


def _execute_ddl(session: Session, ddl: str, *, tag_value: str | None = None) -> str:
    """Execute a CREATE FUNCTION DDL with tagging and query tag logging.

    Sets the session database/schema from the fully-qualified function name
    in the DDL before execution.

    Args:
        session: Active Snowpark session.
        ddl: Complete CREATE FUNCTION DDL.
        tag_value: Value for the object tag. Defaults to CORTEX_SESSION_ID
            or "NO_ID" if not provided.

    Returns:
        The fully-qualified function name parsed from the DDL.

    """
    fqn, param_types = _parse_fqn_from_ddl(ddl)

    parts = fqn.rsplit(".", 2)
    if len(parts) < 3:
        raise ValueError(
            f"Function name '{fqn}' must be fully qualified (DB.SCHEMA.FUNC)."
        )
    session.use_database(parts[0])
    session.use_schema(parts[1])

    coco_session_id = os.environ.get("CORTEX_SESSION_ID")
    resolved_tag = tag_value or coco_session_id or "NO_ID"

    session.sql(f"CREATE TAG IF NOT EXISTS {CUSTOM_AI_FUNCTION_OBJECT_TAG}").collect()

    tag_sql = (
        f"ALTER FUNCTION {fqn}({param_types}) "
        f"SET TAG {CUSTOM_AI_FUNCTION_OBJECT_TAG}='{resolved_tag}'"
    )

    ctx: contextlib.AbstractContextManager
    if coco_session_id and tag_value is None:
        ctx = custom_ai_query_tag_logging(
            session, coco_session_id, tag_prefix=COCO_SESSION_TAG_PREFIX
        )
    else:
        ctx = contextlib.nullcontext()

    with ctx:
        session.sql(ddl).collect()
        _set_object_tag_with_retry(session, tag_sql)

    return fqn


def _set_object_tag_with_retry(session: Session, tag_alter_sql: str) -> None:
    """Run ALTER ... SET TAG defensively with one retry on missing tag.

    Handles the race where a concurrent session drops the tag between
    CREATE TAG IF NOT EXISTS and ALTER ... SET TAG. On a "tag does not
    exist" failure, re-creates the tag and retries once.
    """
    try:
        session.sql(tag_alter_sql).collect()
        return
    except Exception as exc:
        msg = str(exc).lower()
        is_tag_missing = CUSTOM_AI_FUNCTION_OBJECT_TAG.lower() in msg and (
            "does not exist" in msg or "not authorized" in msg
        )
        if not is_tag_missing:
            raise
    session.sql(f"CREATE TAG IF NOT EXISTS {CUSTOM_AI_FUNCTION_OBJECT_TAG}").collect()
    session.sql(tag_alter_sql).collect()


def _resolve_warehouse(session: Session) -> str:
    """Return the explicit warehouse or fall back to the session's current warehouse."""
    rows = session.sql("SELECT CURRENT_WAREHOUSE()").collect()
    wh = rows[0][0] if rows and rows[0] else None
    if not wh:
        raise ValueError(
            "No active warehouse (pass --warehouse or set one in your connection config)"
        )
    return str(wh)


def _split_top_level_csv(text: str) -> list[str]:
    """Split by commas, ignoring commas inside parens or quoted identifiers."""
    parts: list[str] = []
    start = 0
    depth = 0
    in_quotes = False

    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"':
            if in_quotes and i + 1 < len(text) and text[i + 1] == '"':
                i += 1
            else:
                in_quotes = not in_quotes
        elif not in_quotes:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif ch == "," and depth == 0:
                parts.append(text[start:i].strip())
                start = i + 1
        i += 1

    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_fqn_from_ddl(ddl: str) -> tuple[str, str]:
    """Extract the fully-qualified function name and param type signature from DDL.

    Returns:
        (fqn, param_types) where param_types is e.g. "VARCHAR, NUMBER".

    """
    m = _CREATE_FUNCTION_RE.search(ddl)
    if not m:
        raise ValueError(
            "Could not parse function name from DDL. "
            "Expected 'CREATE [OR REPLACE] FUNCTION <name>(...)'."
        )
    fqn = m.group(1)
    params_start = m.end() - 1  # points to opening "("
    depth = 0
    in_quotes = False
    params_end = -1

    i = params_start
    while i < len(ddl):
        ch = ddl[i]
        if ch == '"':
            if in_quotes and i + 1 < len(ddl) and ddl[i + 1] == '"':
                i += 1
            else:
                in_quotes = not in_quotes
        elif not in_quotes:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    params_end = i
                    break
        i += 1

    if params_end == -1:
        raise ValueError(
            "Could not parse function signature from DDL. "
            "Expected balanced parentheses in CREATE FUNCTION parameters."
        )

    raw_params = ddl[params_start + 1 : params_end].strip()
    if not raw_params:
        return fqn, ""

    param_types = []
    for decl in _split_top_level_csv(raw_params):
        type_match = _PARAM_DECL_RE.match(decl)
        if type_match:
            param_types.append(type_match.group(1).strip())
        else:
            param_types.append(decl.strip())

    param_types_str = ", ".join(param_types)
    return fqn, param_types_str


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create custom AI functions in Snowflake.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=dedent(
            """\
            Examples:
                # Flagged mode — generate and execute
                PYTHONPATH=<SKILL_DIR>/src uv run python create_udf.py \\
                    --database DB --schema SCH --function-name MY_FUNC \\
                    --system-prompt 'Classify sentiment' --user-prompt-template '{TEXT}' \\
                    --inputs '[{"name":"TEXT","sql_type":"VARCHAR"}]' \\
                    --outputs '[{"name":"label","json_type":"string","description":"sentiment"}]' \\
                    --execute --connection my_conn

                # Raw SQL — execute agent-authored DDL directly
                PYTHONPATH=<SKILL_DIR>/src uv run python create_udf.py \\
                    --sql-body 'CREATE FUNCTION ...' --execute --connection my_conn
            """
        ),
    )
    parser.add_argument(
        "--sql-body",
        type=str,
        dest="sql_body",
        help="Complete CREATE FUNCTION DDL to execute directly (requires --execute)",
    )
    parser.add_argument(
        "--connection",
        required=True,
        help="Snowflake connection name",
    )
    parser.add_argument(
        "--warehouse",
        help="Warehouse for session context (defaults to connection's current warehouse)",
    )

    # --- Flagged arguments ---
    flag_group = parser.add_argument_group(
        "flagged config",
        "Individual arguments for specifying UDF configuration. "
        "Provide --database to activate this mode.",
    )
    flag_group.add_argument("--database", type=str, help="Target Snowflake database")
    flag_group.add_argument("--schema", type=str, help="Target Snowflake schema")
    flag_group.add_argument(
        "--function-name", type=str, dest="function_name", help="Name for the UDF"
    )
    flag_group.add_argument(
        "--function-intention",
        type=str,
        dest="function_intention",
        help="One-line description of the function's purpose",
    )
    flag_group.add_argument(
        "--model",
        type=str,
        dest="flag_model",
        help="Cortex model name (default: claude-sonnet-4-5)",
    )
    flag_group.add_argument(
        "--system-prompt", type=str, dest="system_prompt", help="System prompt text"
    )
    flag_group.add_argument(
        "--user-prompt-template",
        type=str,
        dest="user_prompt_template",
        help="User prompt template with {PLACEHOLDER} syntax",
    )
    flag_group.add_argument(
        "--inputs",
        type=json.loads,
        dest="inputs",
        default=[],
        help='JSON array of input specs, e.g. \'[{"name":"TEXT","sql_type":"VARCHAR"}]\'',
    )
    flag_group.add_argument(
        "--outputs",
        type=json.loads,
        dest="outputs",
        default=[],
        help='JSON array of output specs, e.g. \'[{"name":"label","json_type":"string","description":"..."}]\'',
    )
    flag_group.add_argument(
        "--stage-name",
        type=str,
        dest="stage_name",
        help="Snowflake stage name (required for multimodal/file inputs)",
    )

    args = parser.parse_args()

    if args.sql_body:
        main(
            sql_body=args.sql_body,
            connection=args.connection,
            warehouse=args.warehouse,
        )
    else:
        config = {
            "database": args.database,
            "schema": args.schema,
            "function_name": args.function_name,
            "function_intention": args.function_intention,
            "model": args.flag_model,
            "system_prompt": args.system_prompt,
            "user_prompt_template": args.user_prompt_template,
            "inputs": args.inputs,
            "outputs": args.outputs,
            "stage_name": args.stage_name,
        }
        main(
            config=config,
            connection=args.connection,
            warehouse=args.warehouse,
        )
