# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""DDL generation and config parsing for custom AI function UDFs.

Stateless module that transforms a ``UDFSpec`` into executable SQL DDL.
Handles both text-only and multimodal (PROMPT + TO_FILE) paths.  Also
provides ``parse_config`` for converting raw dict configs into typed
``UDFSpec`` instances.

This module has no IO or session dependencies — it produces SQL strings
that callers execute against Snowflake.
"""

from __future__ import annotations

import json
import re
from textwrap import dedent
from typing import Any

from snowflake_ai_optimize.core.sql_utils import escape_sql_string
from snowflake_ai_optimize.core.stage import apply_file_prompt_prefix_workaround
from snowflake_ai_optimize.core.udf_types import (
    JSON_TO_SQL_TYPE,
    InputParam,
    OutputField,
    UDFSpec,
)

# ``escape_sql_string`` now lives in ``core.sql_utils`` (the single source of
# truth for SQL-literal escaping); re-exported here for existing callers.
__all__ = ["escape_sql_string"]

CUSTOM_AI_FUNCTION_OBJECT_TAG = "CUSTOM_AI_FUNCTION_UDF_TAG"
COMMENT_PREFIX = "[CORTEX AI FUNC STUDIO] "


def build_user_prompt_sql(template: str, inputs: list[InputParam]) -> str:
    """Build the SQL expression for the user prompt with input concatenation.

    Args:
        template: The user prompt template with {PLACEHOLDER} syntax.
        inputs: List of input parameters.

    Returns:
        SQL expression that concatenates the prompt parts with inputs.

    """
    input_types = {inp.name.upper(): inp.sql_type for inp in inputs}

    placeholders = re.findall(r"\{(\w+)\}", template)
    placeholders = [p.upper() for p in placeholders if p.upper() in input_types]

    if not placeholders:
        return f"'{escape_sql_string(template)}'"

    parts = []
    remaining = template

    for placeholder in placeholders:
        pattern = f"{{{placeholder}}}"
        if pattern in remaining:
            before, remaining = remaining.split(pattern, 1)
            if before:
                parts.append(f"'{escape_sql_string(before)}'")
            param_name = placeholder.upper()
            sql_type = input_types.get(param_name, "VARCHAR")
            parts.append(_sql_to_varchar(param_name, sql_type))

    if remaining:
        parts.append(f"'{escape_sql_string(remaining)}'")

    return " || ".join(parts)


def build_json_schema(outputs: list[OutputField]) -> dict[str, Any]:
    """Build the JSON schema for structured output.

    Args:
        outputs: List of output fields.

    Returns:
        JSON schema dictionary.

    """
    properties = {}
    required = []

    for out in outputs:
        prop: dict[str, Any] = {
            "type": out.json_type,
            "description": out.description,
        }
        if out.json_type == "array":
            prop["items"] = {"type": "string"}
        properties[out.name] = prop
        required.append(out.name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def generate_sql(spec: UDFSpec) -> str:
    """Generate the complete CREATE FUNCTION SQL DDL.

    Routes to multimodal (PROMPT + TO_FILE) when file inputs are present,
    otherwise uses text-only (messages array).
    """
    if spec.is_multimodal:
        return _generate_multimodal_sql(spec)
    else:
        return _generate_text_sql(spec)


def generate_object_tag_alter(spec: UDFSpec, tag_value: str) -> str:
    """Generate ALTER FUNCTION SET TAG DDL for object tagging."""
    fqn = f"{spec.database}.{spec.schema}.{spec.function_name}"
    input_params = ", ".join(inp.sql_type for inp in spec.inputs)

    sql = dedent(f"""
        ALTER FUNCTION {fqn}({input_params}) set TAG {CUSTOM_AI_FUNCTION_OBJECT_TAG}='{tag_value}'
    """)

    return sql


def parse_config(config: dict[str, Any]) -> UDFSpec:
    """Parse JSON configuration into a UDFSpec.

    Args:
        config: Dictionary with UDF configuration.

    Returns:
        UDFSpec object.

    Raises:
        ValueError: If required fields are missing or invalid.

    """
    required = [
        "database",
        "schema",
        "function_name",
        "model",
        "inputs",
        "outputs",
        "system_prompt",
        "user_prompt_template",
    ]
    missing = [f for f in required if f not in config or config[f] is None]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    inputs = []
    for inp in config["inputs"]:
        if "name" not in inp:
            raise ValueError("Each input must have a 'name' field")
        if "sql_type" not in inp:
            raise ValueError(f"Input '{inp['name']}' must have a 'sql_type' field")
        raw_sql_type = inp["sql_type"].upper()
        # Accept sql_type "STAGE_FILE_PATH" as the canonical way to declare
        # a file-path input.  Normalise to VARCHAR (the actual SQL param type)
        # and set is_file_path automatically.  The legacy is_file_path boolean
        # is still honoured for backward compatibility.
        is_file_path = raw_sql_type == "STAGE_FILE_PATH" or inp.get(
            "is_file_path", False
        )
        sql_type = "VARCHAR" if raw_sql_type == "STAGE_FILE_PATH" else raw_sql_type
        inputs.append(
            InputParam(
                name=inp["name"].upper(),
                sql_type=sql_type,
                is_file_path=is_file_path,
            )
        )

    if not inputs:
        raise ValueError("At least one input parameter is required")

    has_file_inputs = any(inp.is_file_path for inp in inputs)
    stage_name = config.get("stage_name")
    if has_file_inputs and not stage_name:
        raise ValueError(
            "stage_name is required when any input has "
            "sql_type: STAGE_FILE_PATH (or is_file_path: true)"
        )

    outputs = []
    for out in config["outputs"]:
        if "name" not in out:
            raise ValueError("Each output must have a 'name' field")
        if "json_type" not in out:
            raise ValueError(f"Output '{out['name']}' must have a 'json_type' field")
        outputs.append(
            OutputField(
                name=out["name"],
                json_type=out["json_type"].lower(),
                description=out.get("description", ""),
            )
        )

    if not outputs:
        raise ValueError("At least one output field is required")

    function_intention = config.get("function_intention") or ""

    return UDFSpec(
        database=config["database"].upper(),
        schema=config["schema"].upper(),
        function_name=config["function_name"].upper(),
        model=config["model"],
        inputs=inputs,
        outputs=outputs,
        system_prompt=config["system_prompt"],
        user_prompt_template=config["user_prompt_template"],
        function_intention=function_intention,
        stage_name=stage_name,
    )


def _sql_to_varchar(param_name: str, sql_type: str) -> str:
    """Convert a SQL parameter to VARCHAR for string concatenation.

    Args:
        param_name: The parameter name (column name).
        sql_type: The SQL type of the parameter.

    Returns:
        SQL expression that yields a VARCHAR.

    """
    sql_type_upper = sql_type.upper()
    if sql_type_upper in ("VARCHAR", "STRING", "TEXT", "CHAR"):
        return param_name
    if sql_type_upper == "ARRAY" or sql_type_upper.startswith("ARRAY"):
        return f"ARRAY_TO_STRING({param_name}, ', ')"
    return f"TO_VARCHAR({param_name})"


def _normalize_comment(text: str, *, max_len: int = 1000) -> str:
    cleaned = " ".join(str(text).split())
    if not cleaned:
        return ""
    prefix_len = len(COMMENT_PREFIX)
    effective_max = max_len - prefix_len
    if len(cleaned) > effective_max:
        cleaned = cleaned[: effective_max - 3].rstrip() + "..."
    return cleaned


def _build_multimodal_prompt_args(
    template: str,
    inputs: list[InputParam],
    stage_name: str,
) -> tuple[str, list[str]]:
    """Build the PROMPT() template string and argument list for multimodal calls.

    Translates {COLUMN_NAME} placeholders in the user template to {0}, {1}, ...
    positional placeholders expected by Snowflake's PROMPT() function, and builds
    the corresponding argument expressions (TO_FILE for file inputs, column name
    for text inputs).

    Returns:
        (prompt_template, prompt_args) where prompt_template has {0}/{1}/... and
        prompt_args are SQL expressions for each positional slot.

    """
    input_lookup = {inp.name.upper(): inp for inp in inputs}
    placeholders = re.findall(r"\{(\w+)\}", template)

    seen: dict[str, int] = {}
    prompt_args: list[str] = []
    translated_template = template

    for placeholder in placeholders:
        upper = placeholder.upper()
        if upper in seen:
            continue
        idx = len(prompt_args)
        seen[upper] = idx

        inp = input_lookup.get(upper)
        if inp and inp.is_file_path:
            prompt_args.append(
                f"TO_FILE('{escape_sql_string(stage_name)}', {inp.name})"
            )
        elif inp:
            prompt_args.append(_sql_to_varchar(inp.name, inp.sql_type))
        else:
            prompt_args.append(placeholder.upper())

    for placeholder in re.findall(r"\{(\w+)\}", template):
        upper = placeholder.upper()
        idx = seen[upper]
        translated_template = translated_template.replace(
            f"{{{placeholder}}}", f"{{{idx}}}", 1
        )

    return translated_template, prompt_args


def _resolve_output_schema(
    outputs: list[OutputField],
) -> tuple[str, str, str | None]:
    """Compute return type, result suffix, and response_format expression.

    Returns:
        (return_type, result_suffix, response_format_expr)
        - result_suffix is appended to AI_COMPLETE() to extract/cast the result

    """
    if not outputs:
        return "VARCHAR", "::VARCHAR", None

    json_schema = build_json_schema(outputs)
    response_format_json = json.dumps({"type": "json", "schema": json_schema}, indent=4)
    response_format_expr = f"PARSE_JSON('{escape_sql_string(response_format_json)}')"

    if len(outputs) == 1:
        return_type = JSON_TO_SQL_TYPE.get(outputs[0].json_type, "VARCHAR")
        result_suffix = f":{outputs[0].name}::{return_type}"
    else:
        return_type = "VARIANT"
        result_suffix = ""

    return return_type, result_suffix, response_format_expr


def _resolve_multimodal_prompt_template_and_args(
    spec: UDFSpec,
) -> tuple[str, list[str]]:
    """Resolve the PROMPT template and argument list for multimodal UDFs."""
    has_template_placeholders = bool(
        re.findall(r"\{(\w+)\}", spec.user_prompt_template)
    )
    assert spec.stage_name is not None
    if has_template_placeholders:
        return _build_multimodal_prompt_args(
            spec.user_prompt_template,
            spec.inputs,
            spec.stage_name,
        )

    prompt_args = []
    for inp in spec.inputs:
        if inp.is_file_path:
            prompt_args.append(
                f"TO_FILE('{escape_sql_string(spec.stage_name)}', {inp.name})"
            )
        else:
            prompt_args.append(_sql_to_varchar(inp.name, inp.sql_type))

    input_refs = " ".join(f"{{{i}}}" for i in range(len(prompt_args)))
    return f"{input_refs} {spec.user_prompt_template}", prompt_args


def _prompt_arg_is_to_file_expression(prompt_arg: str | None) -> bool:
    """Return True when the SQL expression passed to PROMPT() starts with TO_FILE."""
    return bool(prompt_arg and prompt_arg.lstrip().upper().startswith("TO_FILE("))


def _build_create_function_ddl(
    fqn: str,
    input_params: str,
    return_type: str,
    escaped_comment: str,
    body_expr: str,
) -> str:
    """Build the CREATE FUNCTION DDL wrapper."""
    return dedent(f"""\
        CREATE FUNCTION {fqn}({input_params})
        RETURNS {return_type}
        LANGUAGE SQL
        COMMENT = '{COMMENT_PREFIX}{escaped_comment}'
        AS
        $$
            {body_expr}
        $$;""")


def _generate_text_sql(spec: UDFSpec) -> str:
    """Generate CREATE FUNCTION DDL for a text-only AI_COMPLETE UDF."""
    fqn = f"{spec.database}.{spec.schema}.{spec.function_name}"
    input_params = ", ".join(f"{inp.name} {inp.sql_type}" for inp in spec.inputs)
    comment = _normalize_comment(spec.function_intention)
    escaped_comment = escape_sql_string(comment)
    return_type, result_suffix, response_format_expr = _resolve_output_schema(
        spec.outputs
    )

    user_prompt_sql = build_user_prompt_sql(spec.user_prompt_template, spec.inputs)

    response_format_line = (
        f",\n            response_format=>{response_format_expr}"
        if response_format_expr
        else ""
    )

    ai_complete_call = dedent(f"""\
        AI_COMPLETE(
            model=>'{escape_sql_string(spec.model)}',
            messages=>ARRAY_CONSTRUCT(
                OBJECT_CONSTRUCT(
                    'role', 'system',
                    'content', '{escape_sql_string(spec.system_prompt)}'
                ),
                OBJECT_CONSTRUCT(
                    'role', 'user',
                    'content', {user_prompt_sql}
                )
            ){response_format_line}
        )""").strip()

    body_expr = f"{ai_complete_call}{result_suffix}"
    return _build_create_function_ddl(
        fqn, input_params, return_type, escaped_comment, body_expr
    )


def _generate_multimodal_sql(spec: UDFSpec) -> str:
    """Generate CREATE FUNCTION DDL for a multimodal AI_COMPLETE UDF.

    Uses messages array with PROMPT() + TO_FILE() for file inputs loaded from
    a Snowflake stage. System and user prompts are separated into distinct
    messages, matching the text-only path structure.

    Important: Snowflake's PROMPT() interprets every {…} in the template string
    as a positional placeholder. Text containing literal braces must be passed
    as a PROMPT argument value, NOT embedded in the template.
    """
    assert spec.stage_name, "stage_name is required for multimodal UDFs"

    fqn = f"{spec.database}.{spec.schema}.{spec.function_name}"
    input_params = ", ".join(f"{inp.name} {inp.sql_type}" for inp in spec.inputs)
    comment = _normalize_comment(spec.function_intention)
    escaped_comment = escape_sql_string(comment)
    return_type, result_suffix, response_format_expr = _resolve_output_schema(
        spec.outputs
    )
    translated_template, prompt_args = _resolve_multimodal_prompt_template_and_args(
        spec
    )

    args_str = ",\n                        ".join(prompt_args)
    response_format_line = (
        f",\n            response_format=>{response_format_expr}"
        if response_format_expr
        else ""
    )

    prompt_template = apply_file_prompt_prefix_workaround(
        translated_template,
        first_prompt_arg_is_file=_prompt_arg_is_to_file_expression(
            prompt_args[0] if prompt_args else None
        ),
    )
    ai_complete_call = dedent(f"""\
        AI_COMPLETE(
            model=>'{escape_sql_string(spec.model)}',
            messages=>ARRAY_CONSTRUCT(
                OBJECT_CONSTRUCT(
                    'role', 'system',
                    'content', '{escape_sql_string(spec.system_prompt)}'
                ),
                OBJECT_CONSTRUCT(
                    'role', 'user',
                    'content', PROMPT(
                        '{escape_sql_string(prompt_template)}',
                        {args_str}
                    )
                )
            ){response_format_line}
        )""").strip()

    body_expr = f"{ai_complete_call}{result_suffix}"
    return _build_create_function_ddl(
        fqn, input_params, return_type, escaped_comment, body_expr
    )
