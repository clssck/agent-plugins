# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Domain types for custom AI function UDF specifications.

Defines the pure value objects that describe a UDF's shape: its inputs,
outputs, and overall specification.  These types carry no IO or session
dependencies and are safe to import anywhere in the dependency graph.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InputParam:
    """Represents a function input parameter."""

    name: str
    sql_type: str
    is_file_path: bool = False


@dataclass
class OutputField:
    """Represents an output field in the JSON schema."""

    name: str
    json_type: str
    description: str


@dataclass
class UDFSpec:
    """Complete specification for a UDF."""

    database: str
    schema: str
    function_name: str
    model: str
    inputs: list[InputParam]
    outputs: list[OutputField]
    system_prompt: str
    user_prompt_template: str
    function_intention: str = ""
    stage_name: str | None = None

    @property
    def is_multimodal(self) -> bool:
        return any(inp.is_file_path for inp in self.inputs)


JSON_TO_SQL_TYPE = {
    "string": "VARCHAR",
    "number": "FLOAT",
    "integer": "NUMBER",
    "boolean": "BOOLEAN",
    "array": "VARIANT",
    "object": "VARIANT",
}
