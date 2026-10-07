# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Utility functions for metrics evaluation."""

import json

from snowflake.snowpark import Session

from snowflake_ai_optimize.core.sql_utils import escape_sql_string, quote_identifier


def to_text(value: object) -> str:
    """Convert values (including VARIANT dict/list) to stable text."""
    if value is None:
        return ""
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def get_table_column_names(session: Session, table_name: str) -> set[str]:
    """Best-effort table column introspection for safer dynamic SQL."""
    try:
        rows = session.sql(f"DESCRIBE TABLE {table_name}").collect()
    except Exception:
        return set()

    names: set[str] = set()
    for row in rows:
        row_name = None
        if hasattr(row, "asDict"):
            row_dict = row.asDict()
            for key, value in row_dict.items():
                if str(key).upper() == "NAME":
                    row_name = value
                    break
        if row_name is None:
            try:
                row_name = row["NAME"]
            except Exception:
                try:
                    row_name = row["name"]
                except Exception:
                    row_name = None
        if row_name is not None:
            names.add(str(row_name).strip().upper())
    return names


def validate_input_columns(
    table_columns: set[str], input_columns: list[str], table_name: str
) -> None:
    """Validate that all input columns exist in the table.

    Args:
        table_columns: Set of uppercase column names from the table.
            If empty (introspection failed), validation is skipped.
        input_columns: Column names to validate.
        table_name: Table name for error messages.

    Raises:
        ValueError: If any input column is not found in the table.

    """
    if not table_columns:
        return
    missing = [
        col
        for col in input_columns
        if col.strip('"').strip("'").upper() not in table_columns
    ]
    if missing:
        raise ValueError(
            f"Input column(s) {missing} not found in table {table_name}. "
            f"Available columns: {sorted(table_columns)}."
        )


def resolve_expected_column(table_columns: set[str], expected_column: str) -> str:
    """Normalize the expected/label column name by stripping surrounding quotes.

    Callers are responsible for validating that the returned name exists in the
    target table.  No implicit fallback is performed — if the column is wrong,
    the caller should surface a clear error.

    Args:
        table_columns: Unused (kept for call-site compatibility).
        expected_column: Raw column name (may have quotes).

    Returns:
        Quote-stripped column name.

    """
    return str(expected_column).strip('"').strip("'")


def resolve_multi_output_columns(
    table_columns: set[str], expected_columns: list[str]
) -> list[tuple[str, str]]:
    """Resolve multi-output column names against table columns.

    Args:
        table_columns: Set of uppercase column names.  If empty, columns
            are returned as-is.
        expected_columns: List of output column names to resolve.

    Returns:
        List of ``(output_key, resolved_table_col)`` pairs.  Columns not
        found in the table are silently dropped.

    """
    if not table_columns:
        return [(str(c), str(c)) for c in expected_columns]
    pairs: list[tuple[str, str]] = []
    for col in expected_columns:
        upper = str(col).upper()
        if upper in table_columns:
            pairs.append((str(col), upper))
    return pairs


def build_object_construct_expr(
    resolved_pairs: list[tuple[str, str]], alias: str
) -> str:
    """Build a Snowflake ``OBJECT_CONSTRUCT(...)`` SQL expression.

    Args:
        resolved_pairs: List of ``(output_key, table_col)`` pairs.
        alias: Column alias for the expression (e.g. ``"EXPECTED"``).

    Returns:
        SQL expression like ``OBJECT_CONSTRUCT('k1', "COL1", ...) AS ALIAS``.

    """
    parts: list[str] = []
    for output_key, table_col in resolved_pairs:
        safe_key = escape_sql_string(str(output_key))
        parts.append(f"'{safe_key}'")
        parts.append(quote_identifier(table_col))
    return f"OBJECT_CONSTRUCT({', '.join(parts)}) AS {alias}"


def parse_metric_options(
    metric_options: dict | None,
) -> tuple[dict, str | None, list[str]]:
    """Parse metric options, extracting ``output_field`` and ``expected_columns``.

    Args:
        metric_options: Raw metric options dict (may be ``None``).

    Returns:
        Tuple of ``(cleaned_opts, output_field, expected_columns)`` where
        *cleaned_opts* has ``output_field`` and ``expected_columns`` removed.

    """
    if not isinstance(metric_options, dict):
        return {}, None, []
    opts = dict(metric_options)
    output_field = opts.pop("output_field", None)
    expected_columns_raw = opts.pop("expected_columns", None)
    expected_columns: list[str] = []
    if isinstance(expected_columns_raw, list | tuple):
        expected_columns = [
            str(c).strip() for c in expected_columns_raw if str(c).strip()
        ]
    return opts, output_field, expected_columns
