# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for JSON schema patching utilities."""

from __future__ import annotations

import pytest

from snowflake_ai_optimize.core.session import (
    patch_response_format_additional_properties,
)


def test_returns_non_dict_unmodified():
    assert patch_response_format_additional_properties("x") == "x"
    assert patch_response_format_additional_properties(123) == 123
    assert patch_response_format_additional_properties(None) is None


def test_sets_additional_properties_on_root_object_type():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    patched = patch_response_format_additional_properties(schema)
    assert patched["additionalProperties"] is False


def test_sets_additional_properties_on_object_with_properties_even_without_type():
    schema = {"properties": {"a": {"type": "string"}}}
    patched = patch_response_format_additional_properties(schema)
    assert patched["additionalProperties"] is False


def test_sets_additional_properties_on_object_type_in_union():
    schema = {"type": ["object", "null"], "properties": {"a": {"type": "string"}}}
    patched = patch_response_format_additional_properties(schema)
    assert patched["additionalProperties"] is False


def test_overrides_existing_additional_properties_true():
    schema = {
        "type": "object",
        "additionalProperties": True,
        "properties": {"a": {"type": "string"}},
    }
    patched = patch_response_format_additional_properties(schema)
    assert patched["additionalProperties"] is False


def test_recurses_into_nested_properties_objects():
    schema = {
        "type": "object",
        "properties": {
            "outer": {
                "type": "object",
                "properties": {
                    "inner": {"type": "object", "properties": {"x": {"type": "string"}}}
                },
            }
        },
    }
    patched = patch_response_format_additional_properties(schema)

    assert patched["additionalProperties"] is False
    assert patched["properties"]["outer"]["additionalProperties"] is False
    assert (
        patched["properties"]["outer"]["properties"]["inner"]["additionalProperties"]
        is False
    )


def test_recurses_through_arrays_items():
    schema = {
        "type": "object",
        "properties": {
            "arr": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"a": {"type": "string"}},
                },
            }
        },
    }
    patched = patch_response_format_additional_properties(schema)
    assert patched["properties"]["arr"]["items"]["additionalProperties"] is False


def test_recurses_through_anyof_oneof_allof():
    schema = {
        "type": "object",
        "properties": {
            "x": {
                "anyOf": [
                    {"type": "object", "properties": {"a": {"type": "string"}}},
                    {"type": "string"},
                ]
            },
            "y": {
                "oneOf": [{"type": "object", "properties": {"b": {"type": "string"}}}]
            },
            "z": {
                "allOf": [{"type": "object", "properties": {"c": {"type": "string"}}}]
            },
        },
    }
    patched = patch_response_format_additional_properties(schema)
    assert patched["properties"]["x"]["anyOf"][0]["additionalProperties"] is False
    assert patched["properties"]["y"]["oneOf"][0]["additionalProperties"] is False
    assert patched["properties"]["z"]["allOf"][0]["additionalProperties"] is False


def test_handles_pattern_properties_as_object_schema_signal():
    schema = {
        "type": "object",
        "properties": {
            "m": {
                "patternProperties": {
                    "^k_": {"type": "object", "properties": {"a": {"type": "string"}}}
                }
            }
        },
    }
    patched = patch_response_format_additional_properties(schema)
    assert patched["properties"]["m"]["additionalProperties"] is False
    # patternProperties entry is itself an object schema
    only_entry = next(iter(patched["properties"]["m"]["patternProperties"].values()))
    assert only_entry["additionalProperties"] is False


def test_does_not_mutate_input():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    original = {"type": "object", "properties": {"a": {"type": "string"}}}
    _ = patch_response_format_additional_properties(schema)
    assert schema == original


def test_list_root_is_patched_recursively():
    schema = [
        {"type": "object", "properties": {"a": {"type": "string"}}},
        {"type": "string"},
    ]
    patched = patch_response_format_additional_properties(schema)
    assert patched[0]["additionalProperties"] is False


@pytest.mark.parametrize(
    "node_type,expected",
    [
        ("object", True),
        (["object"], True),
        ("string", False),
        (["string", "null"], False),
        (None, False),
    ],
)
def test_is_object_type_gate(node_type, expected):
    schema = {"type": node_type}
    patched = patch_response_format_additional_properties(schema)

    if expected:
        assert patched.get("additionalProperties") is False
    else:
        assert "additionalProperties" not in patched
