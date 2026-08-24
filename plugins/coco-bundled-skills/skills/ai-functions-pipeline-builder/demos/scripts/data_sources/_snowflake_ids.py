# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Validate Snowflake identifiers before interpolating into SQL."""

from __future__ import annotations

import re
import sys

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


def check_snowflake_ident(name: str, label: str) -> str:
    if not _IDENT.match(name):
        raise SystemExit(f"invalid {label}: {name!r}")
    return name


def check_db_schema(database: str, schema: str) -> tuple[str, str]:
    return (
        check_snowflake_ident(database, "database"),
        check_snowflake_ident(schema, "schema"),
    )
