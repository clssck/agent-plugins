# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Stage and file operation utilities for multimodal AI functions."""

import json
import re
from typing import Any

from snowflake.snowpark import Session

from snowflake_ai_optimize.core.constants import (
    AI_COMPLETE_FILE_PROMPT_PREFIX,
    STAGE_KEY_PREFIX,
)
from snowflake_ai_optimize.core.sql_utils import FunctionArg

_ALREADY_FILE_PREFIXED_PROMPT_RE = re.compile(r"file:\s*\{0\}", re.IGNORECASE)
_TO_FILE_RE = re.compile(
    r"TO_FILE\(\s*'((?:(?:'')|[^'])+)'\s*,\s*(\w+)\s*\)", re.IGNORECASE
)


def stage_key(col_name: str) -> str:
    """Return the inputs-dict key that holds the per-row stage for *col_name*."""
    return f"{STAGE_KEY_PREFIX}{col_name}"


def parse_file_value(val: object) -> tuple[str, str] | None:
    """Parse a Snowflake FILE variant collected into Python.

    When a FILE-typed column is collected via Snowpark, the value arrives as
    a Python ``dict`` (interactive sessions) **or** a JSON string (inside
    stored procedures)::

        {"STAGE": "@DB.SCHEMA.STAGE", "RELATIVE_PATH": "images/cat.jpg", ...}

    Returns ``(stage_name, relative_path)`` if *val* is a FILE variant,
    or ``None`` otherwise.
    """
    parsed = val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(parsed, dict) and "RELATIVE_PATH" in parsed and "STAGE" in parsed:
        return (str(parsed["STAGE"]), str(parsed["RELATIVE_PATH"]))
    return None


def apply_file_prompt_prefix_workaround(
    prompt_template: str,
    *,
    first_prompt_arg_is_file: bool,
) -> str:
    """Temporarily prefix file-first PROMPT templates for AI_COMPLETE.

    Once AI_COMPLETE handles file-first multimodal prompts correctly without
    this hint, revert the workaround here and keep callers unchanged.
    """
    if not first_prompt_arg_is_file:
        return prompt_template

    stripped_template = prompt_template.lstrip()
    if _ALREADY_FILE_PREFIXED_PROMPT_RE.match(stripped_template):
        return prompt_template
    if not stripped_template.startswith("{0}"):
        return prompt_template

    leading_ws = prompt_template[: len(prompt_template) - len(stripped_template)]
    return f"{leading_ws}{AI_COMPLETE_FILE_PROMPT_PREFIX}{stripped_template}"


def extract_to_file_refs(body: str) -> tuple[str, list[str]] | None:
    """Extract stage name and file-path columns from ``TO_FILE()`` in a body.

    *body* is the raw function body (``FunctionDefinition.body`` from
    ``describe_function``) — ``TO_FILE(...)`` calls live in the body, not in
    the CREATE header.  Returns ``(stage_name, [column_names])`` or ``None``
    if no ``TO_FILE()`` calls are found.  Used to auto-detect multimodal
    functions so the LLM judge can receive images.
    """
    matches = _TO_FILE_RE.findall(body)
    if not matches:
        return None
    stage = matches[0][0].replace("''", "'")
    columns = list(dict.fromkeys(m[1] for m in matches))
    return stage, columns


def file_type_param_names(args: "list[FunctionArg]") -> list[str] | None:
    """Return parameter names declared with the ``FILE`` data type.

    Reads structured ``FunctionDefinition.args`` (from ``describe_function``)
    instead of regex-parsing a DDL signature.  Returns ``None`` when no FILE
    parameters exist so callers can distinguish "no file params" from an
    empty list.

    This complements :func:`extract_to_file_refs` which detects VARCHAR-path
    functions with ``TO_FILE()`` in the body.  Together they cover both
    multimodal patterns.
    """
    names = [a.name for a in args if a.type.upper() == "FILE"]
    if not names:
        return None
    return list(dict.fromkeys(names))


def validate_stage_file_access(
    session: Session,
    stage_name: str | None,
    file_columns: list[str] | None = None,
    *,
    sample_file_paths: list[str] | None = None,
    table_name: str | None = None,
    dataset: list[dict[Any, Any]] | None = None,
) -> None:
    """Validate stage accessibility and file availability for multimodal functions.

    Call before evaluate/optimize to catch configuration issues early.

    Supply file samples via exactly one of:
        - ``sample_file_paths``: pre-extracted list of paths
        - ``table_name``: queries up to 3 sample paths from the table
        - ``dataset``: extracts paths from loaded data dicts
        (all optional — if none given, only stage accessibility is checked)

    Raises:
        ValueError: With an actionable message if any check fails.

    """
    if not file_columns:
        return

    if not stage_name:
        raise ValueError(
            "stage_name is required when the function uses file inputs "
            f"(detected file columns: {file_columns}). "
            "Provide stage_name in metric_options, e.g. "
            "metric_options={'stage_name': '@DB.SCHEMA.AI_FUNCTIONS', ...}"
        )

    try:
        session.sql(f"SELECT 1 FROM DIRECTORY({stage_name}) LIMIT 1").collect()
    except Exception as e:
        raise ValueError(
            f"Cannot access stage {stage_name}. "
            "Verify the stage exists and your role has USAGE privilege. "
            f"Error: {e}"
        ) from e

    paths = _resolve_sample_paths(
        session, file_columns[0], sample_file_paths, table_name, dataset
    )
    if not paths:
        return

    paths_to_check = paths[:3]
    conditions = " OR ".join(f"RELATIVE_PATH = '{p}'" for p in paths_to_check)
    try:
        rows = session.sql(
            f"SELECT RELATIVE_PATH FROM DIRECTORY({stage_name}) "
            f"WHERE {conditions} LIMIT 1"
        ).collect()
    except Exception as e:
        raise ValueError(f"Cannot query files in stage {stage_name}. Error: {e}") from e

    if not rows:
        sample_display = ", ".join(f"'{p}'" for p in paths_to_check)
        raise ValueError(
            f"No matching files found in stage {stage_name}. "
            f"Checked paths: {sample_display}. "
            "Verify that stage_name points to the correct stage "
            "and that the file paths in your data are stage-relative paths."
        )


def _resolve_sample_paths(
    session: Session,
    file_column: str,
    sample_file_paths: list[str] | None,
    table_name: str | None,
    dataset: list[dict] | None,
) -> list[str]:
    """Extract sample file paths from whichever source is provided."""
    if sample_file_paths:
        return [p for p in sample_file_paths if p]

    if table_name:
        quoted = f'"{file_column}"' if not file_column.startswith('"') else file_column
        rows = session.sql(
            f"SELECT {quoted} AS FP FROM {table_name} "
            f"WHERE {quoted} IS NOT NULL LIMIT 3"
        ).collect()
        return [str(r["FP"]) for r in rows]

    if dataset:
        return [
            str(item["inputs"][file_column])
            for item in dataset[:3]
            if item.get("inputs", {}).get(file_column)
        ]

    return []
