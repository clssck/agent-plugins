"""`pack.aliases` accepts both legacy short keys and NiFi
parameter names verbatim. The orchestrator translates aliases to NiFi names
before upserting; the validator looks up by either form.
"""
from __future__ import annotations

import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent.parent
if str(ASSETS) not in sys.path:
    sys.path.insert(0, str(ASSETS))

from pack.aliases import canonicalize, get_with_aliases


def test_canonicalize_legacy_short_keys_to_nifi_names():
    assert canonicalize("postgresql", "ingestion", "slot") == "Replication Slot Name"
    assert canonicalize("postgresql", "ingestion", "jdbc_url") == "PostgreSQL Connection URL"
    assert canonicalize("postgresql", "ingestion", "destination_database") == "Destination Database"
    assert canonicalize("postgresql", "source", "user") == "PostgreSQL Username"
    assert canonicalize("postgresql", "source", "password") == "PostgreSQL Password"
    assert canonicalize("postgresql", "source", "publication") == "Publication Name"


def test_canonicalize_nifi_names_pass_through():
    """A YAML written in the NiFi-name form should produce the same NiFi name."""
    assert canonicalize("postgresql", "ingestion", "Replication Slot Name") == "Replication Slot Name"
    assert canonicalize("postgresql", "source", "PostgreSQL Username") == "PostgreSQL Username"


def test_canonicalize_unknown_keys_pass_through():
    """If a flow upgrade adds a new parameter, the user can write the new
    name directly — the skill passes it through verbatim."""
    assert canonicalize("postgresql", "ingestion", "Brand New Parameter") == "Brand New Parameter"
    assert canonicalize("postgresql", "source", "future_field") == "future_field"


def test_canonicalize_destination_aliases_are_connector_type_agnostic():
    """Snowflake destination params are the same across all connector types,
    so the alias map uses '*' as the connector_type wildcard."""
    for ct in ("postgresql", "mysql", "sqlserver-multidatabase", "oracle-embedded"):
        assert canonicalize(ct, "destination", "account") == "Snowflake Account Identifier"
        assert canonicalize(ct, "destination", "auth") == "Snowflake Authentication Strategy"
        assert canonicalize(ct, "destination", "role") == "Snowflake Role"
        assert canonicalize(ct, "destination", "warehouse") == "Snowflake Warehouse"


def test_get_with_aliases_finds_via_legacy_key():
    """Validator's lookup should succeed when YAML uses the legacy alias."""
    overrides = {"slot": "pg_cdc_tb", "jdbc_url": "jdbc:postgresql://h/db"}
    assert get_with_aliases(overrides, "postgresql", "ingestion", "slot") == "pg_cdc_tb"


def test_get_with_aliases_finds_via_nifi_name():
    """And also when YAML uses the NiFi name directly."""
    overrides = {"Replication Slot Name": "pg_cdc_tb"}
    assert get_with_aliases(overrides, "postgresql", "ingestion", "slot") == "pg_cdc_tb"


def test_get_with_aliases_returns_none_when_neither_present():
    overrides = {"some_other_key": "x"}
    assert get_with_aliases(overrides, "postgresql", "ingestion", "slot") is None


def test_get_with_aliases_supports_multiple_aliases():
    """Some lookups need to try several aliases (e.g. databases / Databases)."""
    overrides = {"Databases": ["db1", "db2"]}
    result = get_with_aliases(overrides, "sqlserver-multidatabase", "ingestion",
                              "databases", "Databases")
    assert result == ["db1", "db2"]


def test_replication_slot_and_legacy_slot_canonicalize_the_same():
    """Both `replication_slot` (preferred) and the legacy `slot` map to the
    NiFi parameter name."""
    assert canonicalize("postgresql", "ingestion", "replication_slot") == "Replication Slot Name"
    assert canonicalize("postgresql", "ingestion", "slot") == "Replication Slot Name"


def test_tables_regex_canonicalizes_per_type():
    """tables_regex maps to the connector's include-pattern parameter."""
    for ct in ("postgresql", "mysql", "sqlserver-multidatabase",
               "oracle-embedded", "oracle-independent"):
        assert canonicalize(ct, "ingestion", "tables_regex") == "Included Table Regex"


def test_single_db_sqlserver_is_not_mapped():
    """Single-DB sqlserver is unsupported; its ingestion aliases are not in the
    map, so they pass through unchanged (validation rejects the type upstream)."""
    assert canonicalize("sqlserver", "ingestion", "schema_pattern") == "schema_pattern"

