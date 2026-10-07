# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Regression test for the inline-eval input schema.

Guards against the Snowpark 1.52.0 ``create_dataframe`` inference bug where a
schema-less call typed text columns as ``StringType(1)`` (VARCHAR(1)), causing
the inline-eval temp table to truncate every multi-character input and silently
zero out all metric calls.
"""

from __future__ import annotations

from snowflake.snowpark.types import LongType, StringType

from snowflake_ai_optimize.core.temp_ai_function import (
    _inline_input_schema as _core_schema,
)
from snowflake_ai_optimize.gepa.optimize_body import (
    _inline_input_schema as _gepa_schema,
)


def _assert_unbounded_text_schema(builder):
    rows = [
        {"__ROW_ID": 0, "TEXT": "a string much longer than one character"},
        {"__ROW_ID": 1, "TEXT": "x"},
    ]
    schema = builder(rows, ["__ROW_ID", "TEXT"])
    by_name = {f.name.strip('"'): f.datatype for f in schema.fields}

    assert isinstance(by_name["__ROW_ID"], LongType)
    text_type = by_name["TEXT"]
    assert isinstance(text_type, StringType)
    # The bug produced StringType(1); the fix must leave the length unbounded.
    assert text_type.length is None, f"expected unbounded VARCHAR, got {text_type!r}"


def test_gepa_inline_input_schema_is_unbounded_varchar():
    _assert_unbounded_text_schema(_gepa_schema)


def test_core_inline_input_schema_is_unbounded_varchar():
    _assert_unbounded_text_schema(_core_schema)
