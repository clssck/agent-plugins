# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for deploy_ai_function_manager.py — stage name utilities.

Run:
    uv run --group test pytest tests/test_deploy_manager.py -v
"""

from __future__ import annotations

import pytest
from deploy_ai_function_manager import parse_stage_fqn, qualify_stage_name


@pytest.fixture(scope="session", autouse=True)
def cleanup_stale_test_objects():
    """Override conftest fixture -- no Snowflake connection needed for unit tests."""
    yield


class TestQualifyStageName:
    def test_bare_name_qualified(self):
        result = qualify_stage_name("MY_STAGE", "MY_DB", "MY_SCHEMA")
        assert result == "MY_DB.MY_SCHEMA.MY_STAGE"

    def test_already_qualified_passthrough(self):
        result = qualify_stage_name("DB.SCHEMA.STAGE", "OTHER_DB", "OTHER_SCHEMA")
        assert result == "DB.SCHEMA.STAGE"

    def test_partial_qualification_raises(self):
        with pytest.raises(ValueError, match=r"Stage must be NAME or DB.SCHEMA.NAME"):
            qualify_stage_name("DB.STAGE", "MY_DB", "MY_SCHEMA")

    def test_over_qualification_raises(self):
        with pytest.raises(ValueError, match=r"Stage must be NAME or DB.SCHEMA.NAME"):
            qualify_stage_name("A.B.C.D", "MY_DB", "MY_SCHEMA")


class TestParseStageFqn:
    def test_valid_three_part(self):
        db, schema, stage = parse_stage_fqn("MY_DB.MY_SCHEMA.MY_STAGE")
        assert db == "MY_DB"
        assert schema == "MY_SCHEMA"
        assert stage == "MY_STAGE"

    def test_too_few_parts_raises(self):
        with pytest.raises(ValueError, match=r"Stage must resolve to DB.SCHEMA.STAGE"):
            parse_stage_fqn("ONLY_ONE")

    def test_too_many_parts_raises(self):
        with pytest.raises(ValueError, match=r"Stage must resolve to DB.SCHEMA.STAGE"):
            parse_stage_fqn("A.B.C.D")
