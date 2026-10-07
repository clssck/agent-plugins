# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Session management, AI_COMPLETE invocation, and query tagging utilities."""

import json
import logging
import re
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from snowflake.snowpark import Session
from snowflake.snowpark.functions import (
    array_construct,
    call_function,
    col,
    lit,
    object_construct,
    parse_json,
)

from snowflake_ai_optimize.core.constants import CUSTOM_AI_FUNCTION_TAG_PREFIX
from snowflake_ai_optimize.core.stage import apply_file_prompt_prefix_workaround

logger = logging.getLogger(__name__)


def create_session_from_connection(connection: str) -> Session:
    """Create a Snowpark session from a named connection.

    Args:
        connection: Snowflake connection name from ~/.snowflake/connections.toml.

    Returns:
        An active Snowpark Session.

    """
    session: Session = Session.builder.config("connection_name", connection).create()
    return session


@contextmanager
def custom_ai_query_tag_logging(
    session: Session,
    tag_suffix: str,
    *,
    tag_prefix: str = CUSTOM_AI_FUNCTION_TAG_PREFIX,
) -> Generator[Session, None, None]:
    """Context manager that appends a key to the session QUERY_TAG.

    Composes the tag into the existing QUERY_TAG (JSON dict, JSON list, or
    plain string) and restores the original tag on exit.

    Args:
        session: Active Snowpark session.
        tag_suffix: Value to associate with the tag key.
        tag_prefix: Tag key prefix.

    Yields:
        The session (for convenience in ``with`` blocks).

    """
    original_tag = session.query_tag

    def _compose_next_tag() -> str:
        if not original_tag:
            return json.dumps({tag_prefix: tag_suffix}, separators=(",", ":"))

        string_tag = f"{original_tag}|{tag_prefix}{tag_suffix}"

        try:
            parsed = json.loads(original_tag)

            if isinstance(parsed, dict):
                parsed[tag_prefix] = tag_suffix
            elif isinstance(parsed, list):
                parsed.append(string_tag)
            else:
                logger.warning(
                    "QUERY_TAG is valid JSON but not a dict or list "
                    "(type=%s); falling back to pipe-delimited format.",
                    type(parsed).__name__,
                )
                return string_tag

            return json.dumps(parsed, separators=(",", ":"))
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(
                "Could not parse existing QUERY_TAG as JSON; "
                "falling back to pipe-delimited format. Error: %s",
                e,
            )
            return string_tag

    try:
        session.query_tag = _compose_next_tag()
        yield session
    finally:
        session.query_tag = original_tag  # type: ignore[assignment]


def patch_response_format_additional_properties(
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Recursively ensures ``additionalProperties: false`` on all object schemas.

    Required by Snowflake's strict JSON mode which rejects responses with
    extra fields unless the schema explicitly disallows them.

    Args:
        schema: JSON Schema object (root-level dict).

    Returns:
        A copy of the schema with ``additionalProperties: false`` injected
        into every object-typed node.

    """

    def _patch(node: Any) -> Any:
        if isinstance(node, list):
            return [_patch(v) for v in node]
        if not isinstance(node, dict):
            return node

        patched: dict[str, Any] = {k: _patch(v) for k, v in node.items()}

        node_type = patched.get("type")
        is_object_type = node_type == "object" or (
            isinstance(node_type, list) and "object" in node_type
        )
        looks_like_object_schema = any(
            k in patched for k in ("properties", "patternProperties", "required")
        )

        if is_object_type or looks_like_object_schema:
            patched["additionalProperties"] = False

        return patched

    result: dict[str, Any] = _patch(schema)
    return result


class RobustAIComplete:
    """Utilities for parsing and recovering JSON-like model outputs."""

    _error_mode_init_attempted = False
    _can_use_error_details_mode = False

    JSON_CODE_BLOCK_RE = re.compile(
        r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE
    )
    JSON_MODE_ERROR_MARKERS = (
        "json mode output validation error",
        "unmarshalling the model output",
        "invalid json",
        "unexpected end of json input",
        # Common parser failures surfaced by vLLM/OpenAI-compatible servers.
        "eof while parsing",
        "while parsing a string",
        "unterminated string",
        "expecting value",
        "expecting ',' delimiter",
    )
    RETURN_DETAILS_BLOCK_MARKERS = (
        "return details is not allowed",
        "ai_sql_error_handling_use_fail_on_error",
    )

    @classmethod
    def _initialize_error_mode_once(cls, session: Session) -> None:
        """Try once to enable return_error_details compatibility in the session."""
        if cls._error_mode_init_attempted:
            return
        # Cache the capability check once per process to avoid repeated ALTER SESSION
        # calls.
        cls._error_mode_init_attempted = True
        try:
            session.sql(
                "ALTER SESSION SET AI_SQL_ERROR_HANDLING_USE_FAIL_ON_ERROR = FALSE"
            ).collect()
            cls._can_use_error_details_mode = True
        except Exception:
            cls._can_use_error_details_mode = False

    @staticmethod
    def _extract_balanced_substring(
        text: str, open_ch: str, close_ch: str
    ) -> str | None:
        start: int | None = None
        depth = 0
        # Track string/escape state so braces/brackets inside quoted text are ignored.
        in_string = False
        escape = False
        for idx, ch in enumerate(text):
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue
            if ch == open_ch:
                if depth == 0:
                    start = idx
                depth += 1
            elif ch == close_ch and depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    return text[start : idx + 1]
        return None

    @classmethod
    def _parse_json(cls, value: object) -> object | None:
        """Parse JSON from a string value."""
        if not isinstance(value, str):
            return value

        text = value.strip()
        if not text:
            return None

        result: object = json.loads(text)
        return result

    @classmethod
    def parse_ai_complete_payload(cls, raw_response: object) -> object | None:
        """Parse AI_COMPLETE response payload into JSON-like Python objects."""
        parsed = cls._parse_json(raw_response)
        if parsed is None:
            return None

        # Detail-enabled calls can wrap payload in {'value', 'error'}.
        if isinstance(parsed, dict) and ("value" in parsed or "error" in parsed):
            error_text = parsed.get("error")
            if error_text is not None and str(error_text).strip():
                raise RuntimeError(str(error_text))
            parsed = parsed.get("value")

        return cls._parse_json(parsed)

    @classmethod
    def is_json_mode_validation_error(cls, message: str) -> bool:
        """Return True when error text indicates a JSON schema validation failure."""
        lowered = message.lower()
        return any(marker in lowered for marker in cls.JSON_MODE_ERROR_MARKERS)

    @classmethod
    def _is_return_details_not_allowed_error(cls, exc: Exception) -> bool:
        lowered = str(exc).lower()
        return all(marker in lowered for marker in cls.RETURN_DETAILS_BLOCK_MARKERS)

    @staticmethod
    def _normalize_user_prompts(user_prompts: list[str] | str) -> list[str]:
        """Normalize user prompts to a list for downstream batching logic."""
        return [user_prompts] if isinstance(user_prompts, str) else user_prompts

    @staticmethod
    def _validate_multimodal_inputs(
        user_prompts: list[str],
        file_paths: list[str] | None,
        stage_name: str | list[str] | None,
    ) -> tuple[bool, bool]:
        """Validate multimodal batching inputs.

        Returns ``(multimodal, per_row_stages)`` where:
        - ``multimodal`` means file paths and stages were provided together
        - ``per_row_stages`` means stage_name is a list aligned with prompts
        """
        has_file_paths = file_paths is not None
        has_stage_name = stage_name is not None
        if has_file_paths != has_stage_name:
            raise ValueError("file_paths and stage_name must be provided together")

        per_row_stages = isinstance(stage_name, list)
        multimodal = has_file_paths and has_stage_name
        if not multimodal:
            return False, per_row_stages

        assert file_paths is not None
        assert stage_name is not None
        if len(file_paths) != len(user_prompts):
            raise ValueError(
                f"file_paths length ({len(file_paths)}) must match "
                f"user_prompts length ({len(user_prompts)})"
            )
        if per_row_stages:
            assert isinstance(stage_name, list)
            if len(stage_name) != len(user_prompts):
                raise ValueError(
                    f"stage_name length ({len(stage_name)}) must match "
                    f"user_prompts length ({len(user_prompts)})"
                )
        return True, per_row_stages

    @staticmethod
    def _build_ai_complete_content_expr(
        *,
        multimodal: bool,
        per_row_stages: bool,
        stage_name: str | list[str] | None,
    ) -> Any:
        """Build the user-message content expression passed into AI_COMPLETE."""
        if not multimodal:
            return col("PROMPT_EXPR_COL")

        stage_expr = col("STAGE_COL") if per_row_stages else lit(stage_name)
        return call_function(
            "PROMPT",
            lit(
                apply_file_prompt_prefix_workaround(
                    "{0} {1}",
                    first_prompt_arg_is_file=True,
                )
            ),
            call_function("TO_FILE", stage_expr, col("FILE_PATH_COL")),
            col("PROMPT_EXPR_COL"),
        )

    @staticmethod
    def _build_prompt_dataframe_inputs(
        user_prompts: list[str],
        *,
        multimodal: bool,
        per_row_stages: bool,
        file_paths: list[str] | None,
        stage_name: str | list[str] | None,
    ) -> tuple[list[list[object]], list[str]]:
        """Build rows/schema for the intermediate Snowpark DataFrame."""
        if not multimodal:
            return [[i, p] for i, p in enumerate(user_prompts)], [
                "IDX",
                "PROMPT_EXPR_COL",
            ]

        if per_row_stages:
            assert file_paths is not None
            assert isinstance(stage_name, list)
            return [
                [i, prompt, file_path, row_stage]
                for i, (prompt, file_path, row_stage) in enumerate(
                    zip(user_prompts, file_paths, stage_name, strict=True)
                )
            ], ["IDX", "PROMPT_EXPR_COL", "FILE_PATH_COL", "STAGE_COL"]

        assert file_paths is not None
        return [
            [i, prompt, file_path]
            for i, (prompt, file_path) in enumerate(
                zip(user_prompts, file_paths, strict=True)
            )
        ], ["IDX", "PROMPT_EXPR_COL", "FILE_PATH_COL"]

    @classmethod
    def _execute_ai_complete(
        cls,
        session: Session,
        model: str,
        user_prompts: list[str] | str,
        temperature: float,
        max_tokens: int,
        response_schema: dict[str, Any] | None,
        include_error_details: bool,
        system_prompt: str | None = None,
        file_paths: list[str] | None = None,
        stage_name: str | list[str] | None = None,
    ) -> list[object]:
        """Execute Snowflake AI_COMPLETE() and return the raw payload.

        AI_COMPLETE v9 signature:
            AI_COMPLETE(
              model string,
              messages array,
              model_parameters object default {},
              response_format variant default null,
              show_details boolean default false,
              provisioned_throughput_id string default null,
              return_error_details boolean default false
            )

        When ``file_paths`` and ``stage_name`` are provided, each prompt
        is wrapped with the temporary file-prefix workaround via
        ``PROMPT('file: {0} {1}', TO_FILE(stage, path), text)``. Pass a
        ``str`` for a single stage or ``list[str]`` for per-row stages.
        """
        if response_schema is not None:
            response_schema = patch_response_format_additional_properties(
                response_schema
            )

        user_prompts = cls._normalize_user_prompts(user_prompts)
        multimodal, per_row_stages = cls._validate_multimodal_inputs(
            user_prompts,
            file_paths,
            stage_name,
        )
        content_expr = cls._build_ai_complete_content_expr(
            multimodal=multimodal,
            per_row_stages=per_row_stages,
            stage_name=stage_name,
        )

        message_exprs = []
        if system_prompt is not None and system_prompt.strip():
            system_msg = object_construct(
                lit("role"), lit("system"), lit("content"), lit(system_prompt)
            )
            message_exprs.append(system_msg)
        message_exprs.append(
            object_construct(lit("role"), lit("user"), lit("content"), content_expr)
        )
        messages = array_construct(*message_exprs)

        model_parameters = object_construct(
            lit("temperature"),
            lit(temperature),
            lit("max_tokens"),
            lit(max_tokens),
        )

        response_format = (
            object_construct(
                lit("type"),
                lit("json"),
                lit("schema"),
                parse_json(lit(json.dumps(response_schema))),
            )
            if response_schema is not None
            else lit(None)
        )

        arguments = [
            lit(model),
            messages,
            model_parameters,
            response_format,
            lit(False),  # show_details
            lit(""),  # provisioned_throughput_id
            lit(include_error_details),  # return_error_details
        ]

        prompts_for_df, schema = cls._build_prompt_dataframe_inputs(
            user_prompts,
            multimodal=multimodal,
            per_row_stages=per_row_stages,
            file_paths=file_paths,
            stage_name=stage_name,
        )

        df = session.create_dataframe(prompts_for_df, schema=schema)

        df_result = df.select(
            col("IDX"),
            col("PROMPT_EXPR_COL"),
            call_function("AI_COMPLETE", *arguments).alias("RESPONSE"),
        ).order_by(col("IDX"))
        rows = df_result.collect()
        return [row["RESPONSE"] for row in rows]

    @classmethod
    def call_ai_complete(
        cls,
        session: Session,
        model: str,
        user_prompts: list[str],
        temperature: float,
        max_tokens: int,
        response_schema: dict[str, Any] | None,
        system_prompt: str | None = None,
        file_paths: list[str] | None = None,
        stage_name: str | list[str] | None = None,
    ) -> list[object] | None:
        cls._initialize_error_mode_once(session)

        def dispatch(include_error_details: bool) -> list[object]:
            raw_variant = cls._execute_ai_complete(
                session,
                model=model,
                user_prompts=user_prompts,
                temperature=temperature,
                max_tokens=max_tokens,
                response_schema=response_schema,
                include_error_details=include_error_details,
                system_prompt=system_prompt,
                file_paths=file_paths,
                stage_name=stage_name,
            )
            return [
                json.loads(row) if isinstance(row, str | bytes | bytearray) else row
                for row in raw_variant
            ]

        # Use cached session capability to decide whether return_error_details is safe.
        if cls._can_use_error_details_mode:
            try:
                raw_responses: list[Any] = dispatch(True)
                raw_responses = [resp["value"] for resp in raw_responses]
            except Exception as exc:
                if not cls._is_return_details_not_allowed_error(exc):
                    raise
                cls._can_use_error_details_mode = False
                raw_responses = dispatch(False)
        else:
            raw_responses = dispatch(False)

        return raw_responses if raw_responses else None

    @classmethod
    def run_ai_complete_with_json_fallback(
        cls,
        session: Session,
        model: str,
        primary_prompt: str,
        fallback_prompt: str,
        response_schema: dict[str, Any],
        temperature: float,
        max_tokens: int,
    ) -> object:
        """Run AI_COMPLETE with strict schema first, then prompt-only fallback."""
        strict_result: list[Any] | None = None
        try:
            strict_result = cls.call_ai_complete(
                session,
                model=model,
                user_prompts=[primary_prompt],
                temperature=temperature,
                max_tokens=max_tokens,
                response_schema=response_schema,
            )
        except Exception as exc:
            if not (
                isinstance(exc, json.JSONDecodeError)
                or cls.is_json_mode_validation_error(str(exc))
            ):
                raise

        # A strict call can return null/empty payloads in some backends.
        # Treat that as non-success and attempt prompt-only fallback.
        if strict_result is not None:
            return strict_result[0]

        fallback_result = cls.call_ai_complete(
            session,
            model=model,
            user_prompts=[fallback_prompt],
            temperature=temperature,
            max_tokens=max_tokens,
            response_schema=None,
        )
        return cls._parse_json(fallback_result[0]) if fallback_result else None
