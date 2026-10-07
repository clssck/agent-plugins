# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Minimal unit tests for the UserError/InternalError taxonomy (§3.2).

Covers only the new, non-trivial logic: classify()'s mapping, surface_sproc_error's
internal->incident path plus the pass-through that must not downgrade an internal
error, and that error_type reaches the recorded run. The user->SnowflakeUserException
and no-_snowflake-module branches are already covered in test_unit.py.

Run:
    uv run --group test pytest tests/test_error_taxonomy.py -q
"""

from __future__ import annotations

import sys
import types

import pytest

from snowflake_ai_optimize.core.errors import InternalError, UserError, classify
from snowflake_ai_optimize.core.sproc_decorators import surface_sproc_error


@pytest.mark.parametrize(
    "exc, expected",
    [
        (UserError("x"), "user"),
        (InternalError("x"), "internal"),
        (ValueError("x"), "user"),
        (RuntimeError("x"), "internal"),  # any non-ValueError -> internal
    ],
)
def test_classify(exc, expected):
    assert classify(exc) == expected


def test_surface_routes_internal_to_incident_without_downgrading(monkeypatch):
    """Internal -> incident, and an already-internal exception is not downgraded."""
    module = types.ModuleType("_snowflake")

    class SnowflakeUserException(Exception):
        pass

    class _SystemDefinedFunctionInternalError(Exception):
        def __init__(self, tag, msg):
            self.tag = tag
            super().__init__("system error")

    module.SnowflakeUserException = SnowflakeUserException
    module._SystemDefinedFunctionInternalError = _SystemDefinedFunctionInternalError
    monkeypatch.setitem(sys.modules, "_snowflake", module)

    @surface_sproc_error()
    def internal():
        raise RuntimeError("bug")

    @surface_sproc_error()
    def already_internal():
        raise _SystemDefinedFunctionInternalError("SIG", "detail")

    # internal -> incident, signed with the handler name
    with pytest.raises(_SystemDefinedFunctionInternalError) as info:
        internal()
    assert info.value.tag == "CAIFS_INCIDENT_INTERNAL"

    # already-internal is re-raised unchanged, not re-wrapped/re-signed
    with pytest.raises(_SystemDefinedFunctionInternalError) as info:
        already_internal()
    assert info.value.tag == "SIG"


def test_fail_run_threads_error_type(monkeypatch):
    from snowflake_ai_optimize.core import experiment as exp

    captured = {}
    monkeypatch.setattr(
        exp,
        "add_experiment_run",
        lambda *a, params=None, **k: captured.update(p=params),
    )
    monkeypatch.setattr(exp, "commit_experiment_run", lambda *a, **k: None)

    exp.fail_run(object(), "EXP", "SEED", error_message="boom", error_type="internal")
    assert captured["p"].error_type == "internal"
