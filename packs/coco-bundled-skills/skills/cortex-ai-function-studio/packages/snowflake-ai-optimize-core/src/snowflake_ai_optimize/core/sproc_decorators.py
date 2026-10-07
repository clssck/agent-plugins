# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""SPROC lifecycle decorators.

Includes error surfacing, session parameter management, and query tagging.
"""

import traceback
from collections.abc import Callable, Generator
from contextlib import contextmanager
from functools import wraps
from typing import ParamSpec, TypeVar, cast

from snowflake.snowpark import Session

from snowflake_ai_optimize.core.errors import classify, incident_signature
from snowflake_ai_optimize.core.session import custom_ai_query_tag_logging

P = ParamSpec("P")
R = TypeVar("R")


def _get_ai_sql_error_handling_value(session: Session) -> str | None:
    rows = session.sql(
        "SHOW PARAMETERS LIKE 'AI_SQL_ERROR_HANDLING_USE_FAIL_ON_ERROR' IN SESSION"
    ).collect()

    row_dict = rows[0].asDict()
    val = row_dict.get("value")
    return str(val) if val is not None else None


@contextmanager
def ai_sql_error_handling_use_fail_on_error_disabled_for_sproc(
    session: Session,
) -> Generator[Session, None, None]:
    """Set AI_SQL_ERROR_HANDLING_USE_FAIL_ON_ERROR=FALSE for a SPROC handler."""
    orig = _get_ai_sql_error_handling_value(session)

    session.sql(
        "ALTER SESSION SET AI_SQL_ERROR_HANDLING_USE_FAIL_ON_ERROR = FALSE"
    ).collect()

    try:
        yield session
    finally:
        # unset if none
        if orig is None or str(orig).strip() == "":
            session.sql(
                "ALTER SESSION UNSET AI_SQL_ERROR_HANDLING_USE_FAIL_ON_ERROR"
            ).collect()
        else:
            session.sql(
                f"ALTER SESSION SET AI_SQL_ERROR_HANDLING_USE_FAIL_ON_ERROR = {str(orig).strip().upper()}"
            ).collect()


def surface_sproc_error() -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Surface an unhandled SPROC-handler exception via the ``_snowflake`` types.

    Translates by taxonomy (see ``core.errors.classify``):

    * A **user** error (``UserError`` or a builtin ``ValueError``) →
      ``_snowflake.SnowflakeUserException(str(e))`` — the message is shown to the
      caller so they can fix it.
    * An **internal** error (``InternalError`` or any unexpected exception) →
      ``_snowflake._SystemDefinedFunctionInternalError(<signature>, <traceback>)``
      — the caller sees only a generic system error while the detail routes to a
      Snowflake incident keyed by a stable signature.

    Already-``_snowflake`` exceptions (raised deeper, already classified) pass
    through unchanged so they are never downgraded. Outside the Snowflake runtime
    (``import _snowflake`` fails, e.g. local tests) the original exception is
    re-raised unchanged.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                try:
                    import _snowflake
                except ImportError:
                    raise e from e  # not in the Snowflake runtime (e.g. tests)

                # _SystemDefinedFunctionInternalError is a private _snowflake API;
                # guard it (unlike the public SnowflakeUserException) in case a
                # runtime lacks it, falling back to surfacing the message.
                incident_exc = getattr(
                    _snowflake, "_SystemDefinedFunctionInternalError", None
                )
                user_exc = _snowflake.SnowflakeUserException

                # Already-surfaced _snowflake exceptions pass through unchanged —
                # never downgrade an internal error to a user exception.
                surfaced = (user_exc,) + ((incident_exc,) if incident_exc else ())
                if isinstance(e, surfaced):
                    raise

                if classify(e) == "user" or incident_exc is None:
                    raise user_exc(str(e)) from e
                raise incident_exc(
                    incident_signature(func.__name__), traceback.format_exc()
                ) from e

        return cast(Callable[P, R], wrapper)

    return decorator


def with_ai_sql_error_handling_use_fail_on_error_disabled_for_sproc() -> Callable[
    [Callable[P, R]], Callable[P, R]
]:
    """Wrap a Snowpark-SPROC handler in the session param context.

    With this, temporary functions will return {value: T, error: string} (when used with
    TempAIFunction class). With permanent functions, this will make failures return null
    instead of failing entire query it is to note that with BCR, this will soon become
    default behaviour and decorator will soon be not needed
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(session: Session, *args: P.args, **kwargs: P.kwargs) -> R:
            with ai_sql_error_handling_use_fail_on_error_disabled_for_sproc(session):
                return func(session, *args, **kwargs)  # type: ignore[arg-type]

        return cast(Callable[P, R], wrapper)

    return decorator


def with_custom_ai_function_query_tag(
    tag_suffix: str,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(session: Session, *args: P.args, **kwargs: P.kwargs) -> R:
            with custom_ai_query_tag_logging(session, tag_suffix):
                return func(session, *args, **kwargs)  # type: ignore[arg-type]

        return wrapper  # type: ignore[return-value]

    return decorator
