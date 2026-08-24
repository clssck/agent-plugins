"""YAML key → NiFi parameter name aliases.

The skill accepts BOTH forms in user YAML:
  - NiFi parameter names verbatim (e.g. "PostgreSQL Username", "Replication Slot Name") —
    matches what the NiFi UI shows. Recommended for new configs.
  - Legacy short aliases (e.g. "user", "slot", "jdbc_url") — back-compat and
    shorter to type.

`canonicalize(connector_type, scope, key)` translates a known short alias to its
NiFi name; unknown keys pass through verbatim. The orchestrator + worker call
this before every parameter upsert, so the parameter context always ends up
populated under the NiFi name regardless of which form the user wrote.

Adding a new alias is a 1-line change in `_ALIAS_MAP`. If a flow upgrade
introduces a new NiFi parameter, the user can write the new name directly and
the skill will pass it through (no map update required).

Scope is one of:
  - "source"       — shared.source / Source parameter context
  - "destination"  — shared.snowflake / Destination parameter context
  - "ingestion"    — shared.ingestion + connector overrides / Ingestion ctx
"""
from __future__ import annotations

# Per-(connector_type, scope, alias) → NiFi name. `*` connector_type means
# applies to all connector types (used for Snowflake destination params).
_ALIAS_MAP: dict[tuple[str, str, str], str] = {
    # Snowflake destination — same for every connector type.
    ("*", "destination", "account"):    "Snowflake Account Identifier",
    ("*", "destination", "auth"):       "Snowflake Authentication Strategy",
    ("*", "destination", "role"):       "Snowflake Role",
    ("*", "destination", "warehouse"):  "Snowflake Warehouse",
    ("*", "destination", "user"):       "Snowflake Username",
    ("*", "destination", "private_key"): "Snowflake Private Key",

    # PostgreSQL.
    ("postgresql", "source", "user"):                       "PostgreSQL Username",
    ("postgresql", "source", "password"):                   "PostgreSQL Password",
    ("postgresql", "source", "publication"):                "Publication Name",
    ("postgresql", "ingestion", "jdbc_url"):                "PostgreSQL Connection URL",
    ("postgresql", "ingestion", "replication_slot"):        "Replication Slot Name",
    ("postgresql", "ingestion", "slot"):                    "Replication Slot Name",  # legacy alias for replication_slot
    ("postgresql", "ingestion", "tables_regex"):            "Included Table Regex",
    ("postgresql", "ingestion", "destination_database"):    "Destination Database",
    ("postgresql", "ingestion", "object_identifier_resolution"): "Object Identifier Resolution",
    ("postgresql", "ingestion", "ingestion_type"):          "Ingestion Type",
    ("postgresql", "ingestion", "concurrent_snapshot_queries"): "Concurrent Snapshot Queries",
    ("postgresql", "ingestion", "merge_task_schedule"):     "Merge Task Schedule",

    # MySQL.
    ("mysql", "source", "user"):                            "MySQL Username",
    ("mysql", "source", "password"):                        "MySQL Password",
    ("mysql", "ingestion", "jdbc_url"):                     "MySQL Connection URL",
    ("mysql", "ingestion", "server_id"):                    "Server ID",
    ("mysql", "ingestion", "tables_regex"):                 "Included Table Regex",
    ("mysql", "ingestion", "destination_database"):         "Destination Database",

    # SQL Server (multidatabase only — single-DB `sqlserver` is not offered).
    ("sqlserver-multidatabase", "source", "user"):          "SQL Server Username",
    ("sqlserver-multidatabase", "source", "password"):      "SQL Server Password",
    ("sqlserver-multidatabase", "ingestion", "jdbc_url"):   "SQL Server Connection URL",
    ("sqlserver-multidatabase", "ingestion", "databases"):  "Databases",
    ("sqlserver-multidatabase", "ingestion", "destination_database"): "Destination Database",
    ("sqlserver-multidatabase", "ingestion", "schema_pattern"): "Schema Pattern",
    ("sqlserver-multidatabase", "ingestion", "tables_regex"): "Included Table Regex",

    # Oracle.
    ("oracle-embedded", "source", "user"):                  "Oracle Username",
    ("oracle-embedded", "source", "password"):              "Oracle Password",
    ("oracle-embedded", "ingestion", "jdbc_url"):           "Oracle Connection URL",
    ("oracle-embedded", "ingestion", "xstream_outbound_server"): "XStream Outbound Server",
    ("oracle-embedded", "ingestion", "destination_database"): "Destination Database",
    ("oracle-embedded", "ingestion", "tables_regex"):       "Included Table Regex",

    ("oracle-independent", "source", "user"):               "Oracle Username",
    ("oracle-independent", "source", "password"):           "Oracle Password",
    ("oracle-independent", "ingestion", "jdbc_url"):        "Oracle Connection URL",
    ("oracle-independent", "ingestion", "xstream_outbound_server"): "XStream Outbound Server",
    ("oracle-independent", "ingestion", "destination_database"): "Destination Database",
    ("oracle-independent", "ingestion", "tables_regex"):    "Included Table Regex",
}


def canonicalize(connector_type: str, scope: str, key: str) -> str:
    """Return the NiFi parameter name for a legacy short alias, or the key
    verbatim if it's already a NiFi name (or an unknown extension parameter
    we should pass through to NiFi as-is)."""
    return (
        _ALIAS_MAP.get((connector_type, scope, key))
        or _ALIAS_MAP.get(("*", scope, key))
        or key
    )


def get_with_aliases(d: dict, connector_type: str, scope: str, *aliases: str):
    """Look up a value in `d` trying each alias AND its canonical NiFi name.

    Supports both YAML forms (short alias or verbatim NiFi name) so a check
    written against one name still matches a config that used the other.

    Returns the first non-None hit, or None.
    """
    for alias in aliases:
        if alias in d and d[alias] is not None:
            return d[alias]
        nifi_name = canonicalize(connector_type, scope, alias)
        if nifi_name in d and d[nifi_name] is not None:
            return d[nifi_name]
    return None
