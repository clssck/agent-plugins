#!/usr/bin/env python3
"""
pg_lake catalog integration management for the SNOWFLAKE_POSTGRES path.

Drives CREATE CATALOG INTEGRATION + CREATE ICEBERG TABLE + Catalog-Linked
Database workflows against a Snowflake account paired with a pg_lake-enabled
Postgres instance. This is the managed-storage + VENDED_CREDENTIALS path;
customer-S3 + external-stage flows remain the domain of pg_lake_storage.py.

Connection: Uses ~/.snowflake/connections.toml or ~/.snowflake/config.toml,
same as pg_lake_storage.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import urllib.parse

try:
    import snowflake.connector
except ImportError:
    snowflake = None

# Make ./shared/ importable when this script is run directly (pytest already
# injects it via pythonpath). Mirrors the bootstrap in pg_connect.py.
_SHARED_DIR = Path(__file__).resolve().parent / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

import pg_common  # noqa: E402


# Portable Snowflake-query exception tuple. Lets call sites catch DDL
# rejections ("already exists", "does not exist", privilege errors) without
# branching on which backend (connector vs `snow` CLI) ran the query.
def _snowflake_query_errors() -> tuple:
    from sf_session import SnowflakeError
    if snowflake is not None:
        return (snowflake.connector.errors.ProgrammingError, SnowflakeError)
    return (SnowflakeError,)


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

# Unquoted Snowflake identifier: starts with letter/underscore, ASCII only.
# Also matches valid Postgres unquoted identifiers.
_UNQUOTED_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
_MAX_IDENTIFIER_LEN = 255

# Canonical account params for CATALOG_SOURCE = SNOWFLAKE_POSTGRES.
# ENABLE_SNOWFLAKE_POSTGRES gates the catalog source itself. The managed-volume
# flag has been published under two names — _HIDDEN_EXTERNAL_VOLUME and
# _EXTERNAL_VOLUME — across versions; check-account-params looks up both and
# treats either being TRUE as satisfying the requirement, so the script keeps
# working through any rename without prose updates.
REQUIRED_ACCOUNT_PARAMS = ("ENABLE_SNOWFLAKE_POSTGRES",)
PREFERRED_ACCOUNT_PARAMS = (
    "ENABLE_POSTGRES_HIDDEN_EXTERNAL_VOLUME",
    "ENABLE_POSTGRES_EXTERNAL_VOLUME",
)

# Valid bounds for REFRESH_INTERVAL_SECONDS. 30s is the minimum Snowflake
# accepts; 86400s (24h) is the maximum. Validated client-side so users never
# round-trip a known-bad value; if Snowflake widens or narrows the range,
# the server returns 001008 (22023) and the refresh_interval_out_of_range
# translator surfaces the current bounds.
REFRESH_INTERVAL_MIN = 30
REFRESH_INTERVAL_MAX = 86400

# Cost-warning threshold for the READ-FROM-SNOWFLAKE workflow. When the user
# is about to enable AUTO_REFRESH = TRUE on ≥ this many tables at the default
# 30s interval, the workflow surfaces a Snowpipe billing note + suggests a
# longer interval. Tunable via these constants rather than hardcoded in prose.
AUTO_REFRESH_COST_WARNING_THRESHOLD = 10
AUTO_REFRESH_COST_SUGGESTED_INTERVAL = 300

# Error patterns matching known Snowflake error shapes for the
# CATALOG_SOURCE = SNOWFLAKE_POSTGRES path. Each pattern is a compiled regex
# so the invalid_table match can cope with Snowflake's literal-{1}/{2}
# template-formatting in the error string.
#
# BRITTLENESS NOTE: every regex here was extracted from a SINGLE live error
# sample. Unit tests pin against the captured sample, so they keep passing
# even when Snowflake changes the real-world wording in a later release.
# When that happens, translate_error() returns None and the caller sees the
# raw error — a safe fallback, not a crash. Most fragile patterns to watch:
#   - wrong_catalog_name: pinned to the internal Java class name embedded in
#     the INTERNAL_ERROR message; may rename across releases.
#   - object_not_found: case-exact match on `Integration|Iceberg table|
#     Database`; Snowflake has shifted keyword casing across releases before.
# When wording drifts, capture a fresh error sample from a live round-trip
# and update the corresponding regex + its mocked test sample.
ERROR_PATTERNS: dict[str, tuple[re.Pattern[str], str]] = {
    "invalid_instance": (
        re.compile(
            r"002001\s*\(02000\):\s*SQL compilation error:\s*"
            r"Object '(?P<name>[^']+)' does not exist or not authorized\.",
            re.IGNORECASE | re.DOTALL,
        ),
        # The raw error is deliberately ambiguous (security-by-obscurity): the
        # instance may not exist, OR the current role may lack USAGE on it.
        # SHOW POSTGRES INSTANCES silently filters rows by role USAGE grants
        # — so a role with no visibility sees 0 rows, identical to "no
        # instances exist". Causes are ordered by likelihood (most common
        # first) so the agent investigates the right thing first.
        "POSTGRES_INSTANCE='{name}' is not visible to your current role. "
        "Most likely causes, in order: (1) your role lacks USAGE on the "
        "instance (SHOW POSTGRES INSTANCES filters silently by role — "
        "this is the most common cause), (2) the instance does not exist "
        "on this Snowflake account, (3) the instance was created on a "
        "different SF account. Verify: run `check-account-params` to see "
        "the instances visible to your role, or retry with "
        "--use-role ACCOUNTADMIN to check without role filtering.",
    ),
    "invalid_table": (
        re.compile(
            r"093740\s*\(22023\):\s*Could not find Iceberg table "
            r"'Table '(?P<table>[^']+)' not found in namespace '(?P<ns>[^']+)''",
            re.IGNORECASE | re.DOTALL,
        ),
        "The Postgres iceberg table '{table}' does not exist in namespace "
        "'{ns}'. Run `list-pg-iceberg` to see valid "
        "(catalog_name, namespace, table_name) triples.",
    ),
    "wrong_catalog_name": (
        re.compile(
            r"CrunchyCatalogSnapshotReader.*?"
            r"databaseName\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
            re.IGNORECASE | re.DOTALL,
        ),
        "CATALOG_NAME='{name}' does not resolve on the Postgres instance. "
        "The catalog integration was created, but no iceberg table can be "
        "resolved through it. CATALOG_NAME is the **Postgres database name** "
        "(the database where pg_lake lives), not the Snowflake database "
        "name — these are commonly confused. First verify: run "
        "`list-pg-iceberg --connection-name <PG_CONNECTION>` to see the "
        "valid catalog_name values for this PG instance and confirm "
        "whether '{name}' is a typo or the wrong database. Only if the "
        "name is genuinely wrong, drop and recreate the integration with "
        "the correct `--database` value (drop is destructive — confirm "
        "first).",
    ),
    "insufficient_privileges_account": (
        re.compile(
            r"003001\s*\(42501\):\s*SQL access control error:\s*"
            r"Insufficient privileges to operate on account '(?P<account>[^']+)'\.\s*"
            r"Your primary role (?P<role>\w+) must have "
            r"(?P<privilege>[A-Z][A-Z ]*?) granted on ACCOUNT",
            re.IGNORECASE | re.DOTALL,
        ),
        "Role '{role}' lacks the {privilege} privilege on account '{account}'. "
        "Retry with --use-role ACCOUNTADMIN (or another role that has this "
        "privilege), or ask an account admin to run: "
        "GRANT {privilege} ON ACCOUNT TO ROLE {role};",
    ),
    "feature_not_enabled": (
        re.compile(
            r"004101\s*\(42601\):\s*Invalid option CATALOG_SOURCE on catalog integration\.",
            re.IGNORECASE,
        ),
        "This Snowflake account does not have CATALOG_SOURCE = SNOWFLAKE_POSTGRES "
        "enabled. The account params ENABLE_SNOWFLAKE_POSTGRES and "
        "ENABLE_POSTGRES_HIDDEN_EXTERNAL_VOLUME (or ENABLE_POSTGRES_EXTERNAL_VOLUME) "
        "must both be TRUE. Run `check-account-params` to confirm — if either is "
        "missing, work with your Snowflake account admin (ACCOUNTADMIN) to enable "
        "the feature; they can escalate to Snowflake support if needed.",
    ),
    "pg_instance_pg_lake_not_supported": (
        # Distinct from feature_not_enabled (account-level flag off): here
        # the account accepts the DDL syntax, but the instance layer rejects
        # it because the server-side maintenance operation that enables
        # pg_lake for catalog integration hasn't run on this instance.
        re.compile(
            r"604061\s*\(22000\):\s*POSTGRES INSTANCE '(?P<instance>[^']+)' "
            r"does not support use of pg_lake\.\s*"
            r"Please run a Postgres maintenance operation on your instance\.",
            re.IGNORECASE | re.DOTALL,
        ),
        "POSTGRES_INSTANCE '{instance}' exists but has not been enabled for "
        "pg_lake on the Snowflake-managed path. This is a server-side "
        "maintenance operation — no client SQL will fix it, and elevating "
        "the role does not help (this is not a privilege issue). Surface "
        "the raw error to the user and have them work with their Snowflake "
        "account admin (ACCOUNTADMIN) or check current Snowflake docs for "
        "the maintenance procedure. Once the maintenance completes, retry "
        "`create-integration`.",
    ),
    "object_already_exists": (
        re.compile(
            r"002002\s*\(42710\):\s*SQL compilation error:\s*"
            r"Object '(?P<name>[^']+)' already exists\.",
            re.IGNORECASE | re.DOTALL,
        ),
        "An object named '{name}' already exists. If it's a stale artefact "
        "from a prior run, inspect with `describe-integration --name {name}` "
        "(or SHOW ICEBERG TABLES LIKE '{name}') and drop it before retrying.",
    ),
    "object_not_found": (
        re.compile(
            r"002003\s*\(02000\):\s*SQL compilation error:\s*"
            r"(?P<kind>Integration|Iceberg table|Database) '(?P<name>[^']+)' "
            r"does not exist or not authorized\.",
            re.IGNORECASE | re.DOTALL,
        ),
        "{kind} '{name}' does not exist, or your current role lacks privileges on it. "
        "For integrations, run `check-account-params` to see visible integrations; "
        "for iceberg tables, run `list-pg-iceberg`; for databases, SHOW DATABASES. "
        "If a role issue, retry with --use-role ACCOUNTADMIN.",
    ),
    "missing_external_volume": (
        re.compile(
            r"393923\s*\(42601\):\s*Iceberg table (?P<table>\w+) must have "
            r"the table parameter EXTERNAL_VOLUME defined",
            re.IGNORECASE | re.DOTALL,
        ),
        "create-iceberg-table for '{table}' failed with a misleading "
        "EXTERNAL_VOLUME error. **You do NOT need to create an external "
        "volume.** This error means the --catalog value points at a "
        "catalog integration that does not exist (or your role can't see "
        "it). Snowflake fell through to the standard Iceberg-table path "
        "and now expects EXTERNAL_VOLUME, but that's the wrong fix. "
        "Verify the integration name with "
        "`describe-integration --name <catalog>`; if it doesn't exist, "
        "create it first (or use the correct existing name). Do not add "
        "EXTERNAL_VOLUME to your CREATE ICEBERG TABLE statement.",
    ),
    "refresh_interval_out_of_range": (
        re.compile(
            r"001008\s*\(22023\):\s*SQL compilation error:\s*"
            r"invalid value \[(?P<value>-?\d+)\] for parameter "
            r"'REFRESH_INTERVAL_SECONDS'",
            re.IGNORECASE | re.DOTALL,
        ),
        f"REFRESH_INTERVAL_SECONDS={{value}} is out of range. Valid range is "
        f"{REFRESH_INTERVAL_MIN} to {REFRESH_INTERVAL_MAX} seconds inclusive "
        f"({REFRESH_INTERVAL_MIN}s minimum, 24h maximum). Common choices: "
        "30, 60, 300 (5min), 3600 (1h).",
    ),
    "cld_allowed_write_missing": (
        re.compile(
            r"094124\s*\(22023\):\s*SQL Compilation Error:\s*"
            r"SNOWFLAKE_POSTGRES catalog-linked databases must explicitly specify "
            r"ALLOWED_WRITE_OPERATIONS",
            re.IGNORECASE | re.DOTALL,
        ),
        "SNOWFLAKE_POSTGRES catalog-linked databases require "
        "ALLOWED_WRITE_OPERATIONS = NONE in the LINKED_CATALOG clause. "
        "The `create-cld` subcommand always sets this automatically — if you "
        "hit this error via raw SQL, add ', ALLOWED_WRITE_OPERATIONS = NONE' "
        "inside the LINKED_CATALOG parens.",
    ),
    "cld_allowed_write_wrong_value": (
        re.compile(
            r"094123\s*\(22023\):\s*SQL Compilation Error:\s*"
            r"SNOWFLAKE_POSTGRES catalog-linked databases must be read-only\.\s*"
            r"ALLOWED_WRITE_OPERATIONS must be set to NONE, but "
            r"'(?P<value>[^']+)' was provided\.",
            re.IGNORECASE | re.DOTALL,
        ),
        "ALLOWED_WRITE_OPERATIONS = '{value}' is not permitted — SNOWFLAKE_POSTGRES "
        "catalog-linked databases are read-only by design. The only accepted value "
        "is NONE. The `create-cld` subcommand enforces this; use it instead of raw SQL.",
    ),
}


# ---------------------------------------------------------------------------
# Identifier validation (T011)
# ---------------------------------------------------------------------------

def _validate_unquoted_identifier(value: str, field_name: str) -> str:
    """
    Reject anything that could inject SQL via an unquoted identifier slot.

    Allows ASCII letters, digits, underscore, dollar sign; must start with
    a letter or underscore. Length cap prevents pathological inputs.
    """
    if value is None or value == "":
        raise ValueError(f"{field_name} cannot be empty")
    if len(value) > _MAX_IDENTIFIER_LEN:
        raise ValueError(
            f"{field_name}={value!r} exceeds max length {_MAX_IDENTIFIER_LEN}"
        )
    # Fast-path rejects of known injection vectors before regex for clearer errors.
    for bad in (";", "--", "/*", "*/", "'", '"', "\x00"):
        if bad in value:
            raise ValueError(
                f"{field_name}={value!r} contains prohibited characters"
            )
    if not _UNQUOTED_IDENTIFIER_RE.match(value):
        raise ValueError(
            f"{field_name}={value!r} is not a valid unquoted identifier "
            "(must match ^[A-Za-z_][A-Za-z0-9_$]*$)"
        )
    return value


def validate_catalog_name(name: str) -> str:
    """Validate a PG database name that flows into CATALOG_NAME = '<name>'."""
    return _validate_unquoted_identifier(name, "catalog_name")


def validate_integration_name(name: str) -> str:
    """Validate a Snowflake catalog integration object name."""
    return _validate_unquoted_identifier(name, "integration_name")


def validate_table_name(name: str) -> str:
    """Validate an iceberg table name on either the PG or SF side."""
    return _validate_unquoted_identifier(name, "table_name")


def validate_namespace(name: str) -> str:
    """Validate a PG schema / Snowflake CATALOG_NAMESPACE identifier."""
    return _validate_unquoted_identifier(name, "namespace")


def build_auto_refresh_cost_warning(
    table_count: int,
    interval_seconds: int = REFRESH_INTERVAL_MIN,
    threshold: int = AUTO_REFRESH_COST_WARNING_THRESHOLD,
    suggested_interval: int = AUTO_REFRESH_COST_SUGGESTED_INTERVAL,
) -> dict[str, Any]:
    """
    Return a cost-warning struct for the READ-FROM-SNOWFLAKE workflow.

    Snowpipe metadata refresh is billed per-table — the aggregate cost at
    30s intervals across many tables surprises users who expect CATALOG
    INTEGRATION auto-refresh to be free. The skill workflow surfaces this
    BEFORE the user confirms a bulk-create + `--auto-refresh` pass.

    At or above `threshold`, `warn=True` and the payload carries prose
    the agent can embed directly in a stopping-point prompt plus a
    concrete `set-refresh-interval` recovery command. Below threshold,
    `warn=False` and the rest of the payload stays populated for auditing.
    """
    warn = table_count >= threshold
    message = (
        f"AUTO_REFRESH = TRUE on {table_count} iceberg tables at "
        f"REFRESH_INTERVAL_SECONDS={interval_seconds} runs a Snowpipe "
        "metadata-refresh cycle per table per interval. Across ≥"
        f"{threshold} tables this accrues non-trivial cost. Consider "
        f"raising the interval to {suggested_interval}s "
        f"(~{suggested_interval // 60} min) after the integration is "
        "created — it's an integration-level property, applies to all "
        "tables under the same integration."
    )
    recovery_command = (
        "set-refresh-interval --integration <INTEGRATION_NAME> "
        f"--seconds {suggested_interval}"
    )
    return {
        "warn": warn,
        "table_count": table_count,
        "interval_seconds": interval_seconds,
        "threshold": threshold,
        "suggested_interval": suggested_interval,
        "message": message if warn else "",
        "recovery_command": recovery_command if warn else "",
    }


def validate_refresh_interval(seconds: int) -> int:
    """
    Enforce the Snowflake-accepted REFRESH_INTERVAL_SECONDS range client-side
    so the user never sees the opaque server-side error. Bounds: [30, 86400]
    inclusive (see REFRESH_INTERVAL_MIN / REFRESH_INTERVAL_MAX).
    """
    if not isinstance(seconds, int):
        raise ValueError(
            f"refresh_interval_seconds must be an integer, got {type(seconds).__name__}"
        )
    if seconds < REFRESH_INTERVAL_MIN or seconds > REFRESH_INTERVAL_MAX:
        raise ValueError(
            f"refresh_interval_seconds={seconds} is out of range. "
            f"Valid range is {REFRESH_INTERVAL_MIN} to {REFRESH_INTERVAL_MAX} "
            f"seconds inclusive. Common choices: 30, 60, 300, 3600."
        )
    return seconds


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------

def translate_error(sql_error_str: str) -> str | None:
    """
    Match a raw Snowflake / Postgres error string against known patterns
    captured from live probes. Returns a friendly message if one of the
    ERROR_PATTERNS matches, or None if no pattern applies (caller should
    surface the raw string in that case).
    """
    if not sql_error_str:
        return None
    for _key, (pattern, template) in ERROR_PATTERNS.items():
        match = pattern.search(sql_error_str)
        if match:
            return template.format(**match.groupdict())
    return None


# ---------------------------------------------------------------------------
# Snowflake connection helper
# ---------------------------------------------------------------------------

def get_snowflake_connection(
    connection_name: str | None = None,
):
    """
    Get a Snowflake connection. Returns a `connector.SnowflakeConnection`
    on the connector backend, or a `sf_session._SessionConnAdapter` on the
    `snow` CLI backend — both expose the `.cursor()` / `.fetchall()` /
    `.description` / `.close()` surface this module relies on.

    Priority:
    1. SNOWFLAKE_ACCOUNT + SNOWFLAKE_USER env vars (plus SNOWFLAKE_AUTHENTICATOR
       / SNOWFLAKE_PASSWORD / SNOWFLAKE_ROLE) — connector backend only;
       gated by `check_snowflake_connector`.
    2. Named connection from ~/.snowflake/connections.toml — works on both
       backends via `sf_session.open_snowflake_connection`. Key-pair auth
       (private_key_path) is handled by the underlying resolver on the
       connector path, and by snow itself on the CLI path.
    """
    env_account = os.environ.get("SNOWFLAKE_ACCOUNT")
    env_user = os.environ.get("SNOWFLAKE_USER")
    if env_account and env_user:
        pg_common.check_snowflake_connector()
        connect_args: dict[str, Any] = {
            "account": env_account,
            "user": env_user,
        }
        if os.environ.get("SNOWFLAKE_AUTHENTICATOR"):
            connect_args["authenticator"] = os.environ["SNOWFLAKE_AUTHENTICATOR"]
        elif os.environ.get("SNOWFLAKE_PASSWORD"):
            connect_args["password"] = os.environ["SNOWFLAKE_PASSWORD"]
        if os.environ.get("SNOWFLAKE_ROLE"):
            connect_args["role"] = os.environ["SNOWFLAKE_ROLE"]
        return snowflake.connector.connect(**connect_args)

    from sf_session import open_snowflake_connection
    return open_snowflake_connection(connection=connection_name)


def _resolve_connect_kwargs(connect_str: str) -> dict[str, Any]:
    """Translate a connect_str (URI or service=NAME) into kwargs for pg_common.connect()."""
    if connect_str.startswith(("postgres://", "postgresql://")):
        parsed = urllib.parse.urlparse(connect_str)
        qs = urllib.parse.parse_qs(parsed.query)
        # Default sslmode=prefer matches libpq: try TLS, fall back to
        # plaintext if the server refuses. Keeps localhost / internal-PG
        # development flows working. Explicit `?sslmode=require` (or stricter)
        # in the URI forces TLS. On the pg8000 fallback path (Windows ARM64)
        # `prefer` cannot transparently downgrade — users connecting to a
        # plaintext server there should pass `?sslmode=disable`.
        kwargs: dict[str, Any] = {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 5432,
            "dbname": (parsed.path or "/").lstrip("/") or "postgres",
            "user": parsed.username or "",
            "password": parsed.password or "",
            "sslmode": qs["sslmode"][0] if "sslmode" in qs else "prefer",
        }
        if "sslrootcert" in qs:
            kwargs["sslrootcert"] = qs["sslrootcert"][0]
        return kwargs

    if connect_str.startswith("service="):
        name = connect_str[len("service="):]
        entry = pg_common.get_service_entry(name)
        if entry is None:
            raise ValueError(
                f"Service '{name}' not found in ~/.pg_service.conf"
            )
        pw_entry = pg_common.find_pgpass_entry(
            entry["host"], entry["port"], entry["database"], entry["user"],
        )
        return {
            "host": entry["host"],
            "port": entry["port"],
            "dbname": entry["database"],
            "user": entry["user"],
            "password": pw_entry["password"] if pw_entry else "",
            "sslmode": entry.get("sslmode"),
            "sslrootcert": entry.get("sslrootcert"),
        }

    raise ValueError(
        f"Unrecognised connect_str format: {connect_str!r}. "
        "Expected a postgres:// URI or service=NAME."
    )


def get_pg_connection(
    connection_name: str | None = None,
    dsn: str | None = None,
):
    """Get a Postgres connection via pg_service.conf or a full DSN."""
    if not dsn and not connection_name:
        raise ValueError("Provide connection_name or dsn")
    connect_str = dsn if dsn else f"service={connection_name}"
    return pg_common.connect(**_resolve_connect_kwargs(connect_str), connect_timeout=30)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def _not_implemented(subcommand: str, **context: Any) -> dict[str, Any]:
    """
    Uniform fallback body for any subcommand wired into the dispatcher
    without an implementation yet. Returns success=False + a status the
    main() exit-code logic recognises so callers don't mistake a stub
    for a completed action.
    """
    return {
        "success": False,
        "subcommand": subcommand,
        "status": "not_implemented",
        "context": context,
    }


def cmd_check_account_params(args: argparse.Namespace) -> dict[str, Any]:
    """
    Pre-flight diagnostic for the READ-FROM-SNOWFLAKE workflow.

    Returns a payload with 4 independent sections, each wrapped in try/except
    so one failed query degrades gracefully (e.g. network policy blocking
    one metadata query shouldn't kill the whole pre-flight):

      - account_params: SHOW PARAMETERS for required + preferred params
      - current_role / available_roles: for the role-picker workflow
      - instances_visible: SHOW POSTGRES INSTANCES names
      - instance_visibility_note: disambiguates the "0 rows" case (either
        no instances exist OR role lacks USAGE — SHOW filters silently)

    The `--use-role` flag is honored because role-visibility is precisely
    the axis this diagnostic exposes. CAVEAT: `USE ROLE X` only changes the
    primary role — secondary roles inherit by default, which can mask a
    role's true isolation. A user running as a role with inherited
    ACCOUNTADMIN (via secondary roles) will still see all instances. The
    isolated-role case (truly no USAGE anywhere) is what triggers the
    visibility note.
    """
    conn = get_snowflake_connection(args.snowflake_connection)
    try:
        if args.use_role:
            _use_role(conn, args.use_role)
        return _gather_account_param_payload(conn)
    finally:
        conn.close()


def _use_role(conn, role: str) -> None:
    """Apply a session role override. Validated to prevent SQL injection."""
    safe_role = _validate_unquoted_identifier(role, "use_role")
    with conn.cursor() as cur:
        cur.execute(f"USE ROLE {safe_role}")


def _run_query_safely(
    conn, sql: str, transform: Any,
) -> dict[str, Any]:
    """
    Execute `sql`, pass raw rows to `transform(rows)`, return
    `{"status": "ok", "result": <transformed>}` on success or
    `{"status": "error", "error": <str>}` on failure.

    Never re-raises — callers rely on graceful degradation when one metadata
    query fails due to network policy, row-access policy, or Snowflake-side
    hiccup. The overall check-account-params call stays useful even when
    one of the four queries errors out.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        return {"status": "ok", "result": transform(rows)}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": str(e)[:500]}


def _extract_param_value(rows: list) -> dict[str, Any] | None:
    """
    SHOW PARAMETERS returns one row per matched param. Columns:
    key, value, default, level, description, type.

    Returns {value, default, level} or None if the param didn't exist on
    the account (empty rows — this happens for preview params toggled off).
    """
    if not rows:
        return None
    row = rows[0]
    return {
        "value": row[1] if len(row) > 1 else None,
        "default": row[2] if len(row) > 2 else None,
        "level": row[3] if len(row) > 3 else None,
    }


def _extract_instance_names(rows: list, description: list | None) -> list[str]:
    """
    SHOW POSTGRES INSTANCES row shape depends on Snowflake version — first
    column might be `name`, `created_on`, or something else. Find the name
    column by cursor.description, fall back to column index 1 (common for
    SHOW commands that lead with a timestamp), then column 0.
    """
    if not rows:
        return []
    name_idx = 1  # common default for SHOW commands
    if description:
        for idx, col in enumerate(description):
            col_name = (col[0] if col else "").lower()
            if col_name == "name":
                name_idx = idx
                break
    return [row[name_idx] for row in rows if name_idx < len(row)]


def _rank_available_roles(
    roles: list[str], current: str | None,
) -> list[dict[str, str]]:
    """
    Rank roles for the picker workflow. Order matches manage/SKILL.md Step 4:
    ACCOUNTADMIN > *ADMIN* > others, current role flagged separately.
    """
    ranked: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(role: str, label: str) -> None:
        if role not in seen:
            ranked.append({"role": role, "label": label})
            seen.add(role)

    for role in roles:
        if role.upper() == "ACCOUNTADMIN":
            _add(role, "Recommended")
    for role in roles:
        upper = role.upper()
        if upper != "ACCOUNTADMIN" and "ADMIN" in upper:
            _add(role, "Likely works")
    for role in roles:
        if role.upper() == (current or "").upper():
            _add(role, "Current role")
    for role in roles:
        _add(role, "May lack privileges")

    return ranked


def _param_is_true(param_payload: dict[str, Any] | None) -> bool:
    """SHOW PARAMETERS value is returned as a string, typically 'true'/'false'."""
    if not param_payload:
        return False
    value = param_payload.get("value")
    if value is None:
        return False
    return str(value).strip().lower() == "true"


def _param_known_status(param_result: Any) -> str:
    """
    Classify a param query result as "true", "false", or "unknown".

    Distinguishing "unknown" from "false" matters: some accounts don't surface
    ENABLE_SNOWFLAKE_POSTGRES via SHOW PARAMETERS even when the feature is
    enabled — the param is a platform-level flag that isn't always readable
    this way. We mustn't block the workflow on missing rows; the server is
    the source of truth and `create-integration` returns a clean
    feature_not_enabled error if the feature is actually off.

    Returns:
      "true"    — SHOW PARAMETERS returned a row with value = 'true'
      "false"   — SHOW PARAMETERS returned a row with value = 'false'
      "unknown" — Query errored OR returned no rows OR value isn't true/false
    """
    if not isinstance(param_result, dict):
        return "unknown"
    if param_result.get("status") != "ok":
        return "unknown"
    payload = param_result.get("result")
    if not isinstance(payload, dict):
        return "unknown"  # covers None (0 rows) and unexpected shapes
    value = payload.get("value")
    if value is None:
        return "unknown"
    val_lower = str(value).strip().lower()
    if val_lower == "true":
        return "true"
    if val_lower == "false":
        return "false"
    return "unknown"


def _gather_account_param_payload(conn) -> dict[str, Any]:
    """
    Build the pre-flight payload. Every query is wrapped in try/except so
    a single failure doesn't poison the whole diagnostic.
    """
    payload: dict[str, Any] = {
        "success": True,
        "subcommand": "check-account-params",
        "account_params": {},
        "current_role": None,
        "available_roles": [],
        "instances_visible": [],
        "instance_visibility_note": None,
        "cautions": [],
    }

    for param_name in (*REQUIRED_ACCOUNT_PARAMS, *PREFERRED_ACCOUNT_PARAMS):
        result = _run_query_safely(
            conn,
            f"SHOW PARAMETERS LIKE '{param_name}' IN ACCOUNT",
            _extract_param_value,
        )
        payload["account_params"][param_name] = result

    role_result = _run_query_safely(
        conn,
        "SELECT CURRENT_ROLE()",
        lambda rows: rows[0][0] if rows and rows[0] else None,
    )
    if role_result.get("status") == "ok":
        payload["current_role"] = role_result["result"]
    else:
        payload["account_params"]["_current_role_error"] = role_result

    roles_result = _run_query_safely(
        conn,
        "SELECT CURRENT_AVAILABLE_ROLES()",
        lambda rows: rows[0][0] if rows and rows[0] else None,
    )
    if roles_result.get("status") == "ok" and roles_result.get("result"):
        try:
            roles_list = json.loads(roles_result["result"])
            if isinstance(roles_list, list):
                payload["available_roles"] = _rank_available_roles(
                    roles_list, current=payload["current_role"],
                )
        except (json.JSONDecodeError, TypeError):
            payload["cautions"].append(
                "CURRENT_AVAILABLE_ROLES() returned non-JSON; role picker unavailable."
            )

    # Instance list needs cursor.description access so it's handled inline.
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW POSTGRES INSTANCES")
            rows = cur.fetchall()
            description = cur.description
        payload["instances_visible"] = _extract_instance_names(rows, description)
    except Exception as e:  # noqa: BLE001
        payload["instances_visible"] = {"status": "error", "error": str(e)[:500]}

    if isinstance(payload["instances_visible"], list) and not payload["instances_visible"]:
        payload["instance_visibility_note"] = (
            f"No Postgres instances visible to role "
            f"{payload['current_role'] or '<unknown>'}. This could mean "
            "(a) no instances exist on this account, OR (b) your role lacks "
            "USAGE on all instances (SHOW POSTGRES INSTANCES filters silently "
            "by role). Retry with --use-role ACCOUNTADMIN to see all."
        )

    # Classify each required param: definitively true, definitively false, or
    # unknown. SHOW PARAMETERS can return 0 rows on accounts where the feature
    # is enabled but the param isn't surfaced through that interface — treat
    # that as "unknown" and don't block. Only definitive FALSE gates the
    # workflow; the server will return feature_not_enabled from
    # create-integration if the feature is actually off.
    definitively_false = [
        p for p in REQUIRED_ACCOUNT_PARAMS
        if _param_known_status(payload["account_params"].get(p)) == "false"
    ]
    unverified = [
        p for p in REQUIRED_ACCOUNT_PARAMS
        if _param_known_status(payload["account_params"].get(p)) == "unknown"
    ]

    payload["ok"] = len(definitively_false) == 0
    payload["unverified_params"] = unverified

    if definitively_false:
        payload["cautions"].append(
            f"{', '.join(definitively_false)} returned FALSE on this account. "
            "CATALOG_SOURCE = SNOWFLAKE_POSTGRES workflows will not work. "
            "Work with your Snowflake account admin (ACCOUNTADMIN) to enable it; "
            "they can escalate to Snowflake support if the feature isn't "
            "available on this account."
        )
    elif unverified:
        payload["cautions"].append(
            f"Could not verify {', '.join(unverified)} via SHOW PARAMETERS — "
            "the param returned no rows. This can happen on accounts where "
            "the feature is enabled but the param isn't surfaced through "
            "SHOW PARAMETERS. Proceeding is safe; create-integration returns "
            "a clear feature_not_enabled error if the feature is actually off."
        )

    return payload


def cmd_list_pg_iceberg(args: argparse.Namespace) -> dict[str, Any]:
    """
    List Postgres-side pg_lake iceberg tables — the input set for CREATE
    ICEBERG TABLE (per-table path) or for sanity-checking a Catalog-Linked
    Database.

    Returns `(catalog_name, namespace, table_name, metadata_location)`
    triples ordered deterministically for reproducible eval output.
    """
    conn = get_pg_connection(connection_name=args.connection_name)
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT catalog_name, table_namespace, table_name, "
                    "metadata_location FROM iceberg_tables ORDER BY 1, 2, 3"
                )
                rows = cur.fetchall()
            except pg_common.PgError as e:
                sqlstate = getattr(e, "pgcode", None)
                if sqlstate is None and e.args and isinstance(e.args[0], dict):
                    sqlstate = e.args[0].get("C")
                if sqlstate != "42P01":
                    raise
                # pg_lake ships the `iceberg_tables` view as part of the
                # pg_lake_iceberg extension. Missing view ⇒ extension not
                # installed. Friendly message points at the fix path.
                return {
                    "success": False,
                    "subcommand": "list-pg-iceberg",
                    "error": str(e).strip(),
                    "friendly_error": (
                        "The `iceberg_tables` view does not exist on this "
                        "Postgres instance — this almost always means the "
                        "pg_lake extension is not installed. Install it with: "
                        "`uv run --project snowflake-postgres python "
                        "snowflake-postgres/scripts/pg_lake_setup.py "
                        f"--connection-name {args.connection_name} --enable` "
                        "(or check status with `--status`)."
                    ),
                }
    finally:
        conn.close()

    tables = [
        {
            "catalog_name": row[0],
            "namespace": row[1],
            "table_name": row[2],
            "metadata_location": row[3],
        }
        for row in rows
    ]
    return {
        "success": True,
        "subcommand": "list-pg-iceberg",
        "connection": args.connection_name,
        "count": len(tables),
        "tables": tables,
    }


def cmd_create_integration(args: argparse.Namespace) -> dict[str, Any]:
    """
    CREATE CATALOG INTEGRATION ... CATALOG_SOURCE = SNOWFLAKE_POSTGRES.

    All three user-supplied identifiers are validated against the
    unquoted-identifier regex before interpolation — no raw string
    passthrough, no shell-style quoting tricks.

    `already_exists` is soft-failed: returns success=False + a flag the
    caller can branch on, not a raised exception. Matches the sibling
    pattern in pg_lake_storage.py so agent behavior is consistent across
    the two scripts.
    """
    integration_name = validate_integration_name(args.name)
    instance_name = _validate_unquoted_identifier(
        args.postgres_instance, "postgres_instance",
    )
    database = validate_catalog_name(args.database)

    sql = (
        f"CREATE CATALOG INTEGRATION {integration_name} "
        "CATALOG_SOURCE = SNOWFLAKE_POSTGRES "
        "TABLE_FORMAT = ICEBERG "
        "REST_CONFIG = ("
        f"POSTGRES_INSTANCE = '{instance_name}', "
        f"CATALOG_NAME = '{database}', "
        "ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS"
        ") ENABLED = TRUE"
    )

    conn = get_snowflake_connection(args.snowflake_connection)
    try:
        if args.use_role:
            _use_role(conn, args.use_role)
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
        except _snowflake_query_errors() as e:
            if "already exists" in str(e):
                return {
                    "success": False,
                    "subcommand": "create-integration",
                    "name": integration_name,
                    "already_exists": True,
                    "error": f"Catalog integration '{integration_name}' already exists.",
                    "hint": (
                        "Use `describe-integration --name "
                        f"{integration_name}` to inspect, or "
                        f"`drop-integration --name {integration_name} --confirm` "
                        "to replace."
                    ),
                }
            raise
    finally:
        conn.close()

    return {
        "success": True,
        "subcommand": "create-integration",
        "name": integration_name,
        "postgres_instance": instance_name,
        "database": database,
        "sql": sql,
    }


def cmd_describe_integration(args: argparse.Namespace) -> dict[str, Any]:
    """
    DESCRIBE CATALOG INTEGRATION <name> — returns a 4-column property set:
    (property, property_type, property_value, property_default). The
    structured payload lets callers branch on ENABLED / REFRESH_INTERVAL_SECONDS
    / REST_CONFIG without regex-parsing pretty output.
    """
    integration_name = validate_integration_name(args.name)

    conn = get_snowflake_connection(args.snowflake_connection)
    try:
        if args.use_role:
            _use_role(conn, args.use_role)
        with conn.cursor() as cur:
            cur.execute(f"DESCRIBE CATALOG INTEGRATION {integration_name}")
            rows = cur.fetchall()
            description = cur.description
    finally:
        conn.close()

    col_names = (
        [col[0] for col in description] if description
        else ["property", "property_type", "property_value", "property_default"]
    )

    properties: dict[str, dict[str, Any]] = {}
    rows_list = []
    for row in rows:
        row_dict = {
            col_names[i]: (str(row[i]) if row[i] is not None else None)
            for i in range(min(len(col_names), len(row)))
        }
        rows_list.append(row_dict)
        prop = row_dict.get("property")
        if prop:
            properties[prop] = {
                "type": row_dict.get("property_type"),
                "value": row_dict.get("property_value"),
                "default": row_dict.get("property_default"),
            }

    return {
        "success": True,
        "subcommand": "describe-integration",
        "name": integration_name,
        "columns": col_names,
        "rows": rows_list,
        "properties": properties,
    }


def cmd_drop_integration(args: argparse.Namespace) -> dict[str, Any]:
    """
    DROP CATALOG INTEGRATION IF EXISTS <name>. Destructive — requires the
    explicit `--confirm` flag. Without it, the command dry-runs: prints the
    exact SQL that would execute and returns success=False so CI / agent
    pipelines can distinguish "not confirmed" from "actually dropped".

    Note: dropping an integration that's still referenced by iceberg tables
    or CLDs raises a server-side error at DROP time. There is no specific
    translator for this case yet — the raw error surfaces directly, which
    is a safe fallback (the message names the dependent object).
    """
    integration_name = validate_integration_name(args.name)
    sql = f"DROP CATALOG INTEGRATION IF EXISTS {integration_name}"

    if not args.confirm:
        return {
            "success": False,
            "subcommand": "drop-integration",
            "name": integration_name,
            "confirmed": False,
            "would_execute": sql,
            "hint": (
                "Destructive operation — re-run with --confirm to actually "
                "drop. Consider `describe-integration --name "
                f"{integration_name}` first if you want to confirm what "
                "you're about to lose."
            ),
        }

    conn = get_snowflake_connection(args.snowflake_connection)
    try:
        if args.use_role:
            _use_role(conn, args.use_role)
        with conn.cursor() as cur:
            cur.execute(sql)
    finally:
        conn.close()

    return {
        "success": True,
        "subcommand": "drop-integration",
        "name": integration_name,
        "confirmed": True,
        "sql": sql,
    }


def cmd_create_iceberg_table(args: argparse.Namespace) -> dict[str, Any]:
    """
    CREATE ICEBERG TABLE ... with CATALOG_TABLE_NAME + CATALOG_NAMESPACE.

    The SF-side table name, catalog integration name, and namespace are all
    validated as unquoted identifiers. The PG-side catalog_table_name goes
    into a quoted string literal, but is still run through the same
    identifier validator so single-quote / null-byte injection is rejected.
    Quoted/mixed-case PG table names are intentionally not supported here;
    relax the validator if a real-world PG table uses characters it rejects.

    AUTO_REFRESH is an optional append — omitted by default because the
    cost warning (≥AUTO_REFRESH_COST_WARNING_THRESHOLD tables at 30s default)
    is easier to handle at the workflow level than inside every CREATE.

    `already_exists` is soft-failed (same pattern as create-integration).
    """
    table_name = validate_table_name(args.name)
    integration_name = validate_integration_name(args.catalog)
    pg_table_name = _validate_unquoted_identifier(
        args.catalog_table_name, "catalog_table_name",
    )
    namespace = validate_namespace(args.catalog_namespace)

    sql_parts = [
        f"CREATE ICEBERG TABLE {table_name}",
        f"CATALOG = '{integration_name}'",
        f"CATALOG_TABLE_NAME = '{pg_table_name}'",
        f"CATALOG_NAMESPACE = '{namespace}'",
    ]
    if args.auto_refresh:
        sql_parts.append("AUTO_REFRESH = TRUE")
    sql = " ".join(sql_parts)

    conn = get_snowflake_connection(args.snowflake_connection)
    try:
        if args.use_role:
            _use_role(conn, args.use_role)
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
        except _snowflake_query_errors() as e:
            if "already exists" in str(e):
                return {
                    "success": False,
                    "subcommand": "create-iceberg-table",
                    "name": table_name,
                    "already_exists": True,
                    "error": f"Iceberg table '{table_name}' already exists.",
                    "hint": (
                        f"Use `DESCRIBE ICEBERG TABLE {table_name}` to inspect, "
                        f"or drop and recreate it."
                    ),
                }
            raise
    finally:
        conn.close()

    return {
        "success": True,
        "subcommand": "create-iceberg-table",
        "name": table_name,
        "catalog": integration_name,
        "catalog_table_name": pg_table_name,
        "catalog_namespace": namespace,
        "auto_refresh": bool(args.auto_refresh),
        "sql": sql,
    }


def cmd_create_cld(args: argparse.Namespace) -> dict[str, Any]:
    """
    CREATE DATABASE ... LINKED_CATALOG = (CATALOG = ..., ALLOWED_WRITE_OPERATIONS = NONE).

    SNOWFLAKE_POSTGRES catalog-linked databases require
    `ALLOWED_WRITE_OPERATIONS = NONE` (hard server-side constraint, not
    configurable). This subcommand always emits it — the user never needs
    to know about it. Any hypothetical `--allowed-writes` flag would only
    add a way to pick the one accepted value.

    Propagation window: ~30-35s for new PG iceberg tables to appear via
    the CLD (matches default REFRESH_INTERVAL_SECONDS = 30). Callers
    waiting on table visibility should poll `cld-status` with a ≥ 60s
    budget.
    """
    db_name = validate_catalog_name(args.name)
    integration_name = validate_integration_name(args.catalog)

    sql = (
        f"CREATE DATABASE {db_name} "
        f"LINKED_CATALOG = ("
        f"CATALOG = '{integration_name}', "
        "ALLOWED_WRITE_OPERATIONS = NONE"
        ")"
    )

    conn = get_snowflake_connection(args.snowflake_connection)
    try:
        if args.use_role:
            _use_role(conn, args.use_role)
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
        except _snowflake_query_errors() as e:
            if "already exists" in str(e):
                return {
                    "success": False,
                    "subcommand": "create-cld",
                    "name": db_name,
                    "already_exists": True,
                    "error": f"Database '{db_name}' already exists.",
                    "hint": (
                        f"Use `cld-status --name {db_name}` to inspect, or "
                        "drop the database first if you want to recreate "
                        "it against a different catalog integration."
                    ),
                }
            raise
    finally:
        conn.close()

    return {
        "success": True,
        "subcommand": "create-cld",
        "name": db_name,
        "catalog": integration_name,
        "allowed_write_operations": "NONE",
        "sql": sql,
        "propagation_note": (
            "New PG iceberg tables appear via this CLD within ~30-35s "
            "(default REFRESH_INTERVAL_SECONDS = 30). Poll cld-status if "
            "waiting for a specific table to surface."
        ),
    }


def cmd_cld_status(args: argparse.Namespace) -> dict[str, Any]:
    """
    SYSTEM$CATALOG_LINK_STATUS + SHOW TABLES IN DATABASE for a CLD.

    SYSTEM$CATALOG_LINK_STATUS returns a JSON string with `executionState`
    / `failureDetails` / `lastLinkAttemptStartTime`. The healthy steady
    state is `executionState: RUNNING` even during idle periods — don't
    mistake that for "something is actively refreshing".

    `tables` is filtered to Iceberg tables (the only kind that surface via
    a SNOWFLAKE_POSTGRES CLD), parsed to structured rows the agent can
    iterate without column-position juggling.
    """
    db_name = validate_catalog_name(args.name)

    conn = get_snowflake_connection(args.snowflake_connection)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT SYSTEM$CATALOG_LINK_STATUS('{db_name}')")
            status_row = cur.fetchone()
            raw_status = status_row[0] if status_row else None

            cur.execute(f"SHOW TABLES IN DATABASE {db_name}")
            table_rows = cur.fetchall()
            table_description = cur.description
    finally:
        conn.close()

    parsed_status: dict[str, Any] | None = None
    if isinstance(raw_status, str):
        try:
            parsed_status = json.loads(raw_status)
        except json.JSONDecodeError:
            parsed_status = None

    col_names = (
        [col[0].lower() for col in table_description] if table_description else []
    )
    iceberg_tables = _extract_iceberg_tables_from_show(table_rows, col_names)

    execution_state = (
        parsed_status.get("executionState") if parsed_status else None
    )
    healthy = execution_state == "RUNNING"

    return {
        "success": True,
        "subcommand": "cld-status",
        "name": db_name,
        "execution_state": execution_state,
        "healthy": healthy,
        "failure_details": (
            parsed_status.get("failureDetails", []) if parsed_status else []
        ),
        "last_link_attempt_start_time": (
            parsed_status.get("lastLinkAttemptStartTime") if parsed_status else None
        ),
        "raw_status": raw_status,
        "iceberg_tables": iceberg_tables,
        "iceberg_table_count": len(iceberg_tables),
    }


def _extract_iceberg_tables_from_show(
    rows: list, col_names: list[str],
) -> list[dict[str, Any]]:
    """
    Parse SHOW TABLES IN DATABASE <cld> output down to the iceberg-table
    subset + the schema/name fields the agent actually needs. Defensive
    about column layout across Snowflake versions — resolves positions
    from cursor.description each call.
    """
    if not rows or not col_names:
        return []

    def col(name: str) -> int | None:
        try:
            return col_names.index(name)
        except ValueError:
            return None

    name_idx = col("name")
    schema_idx = col("schema_name")
    kind_idx = col("kind")
    is_iceberg_idx = col("is_iceberg")
    rows_idx = col("rows")

    out: list[dict[str, Any]] = []
    for row in rows:
        def _get(idx: int | None) -> Any:
            return row[idx] if idx is not None and idx < len(row) else None

        is_iceberg_val = _get(is_iceberg_idx)
        kind_val = _get(kind_idx)

        is_iceberg = (
            (isinstance(is_iceberg_val, str)
             and is_iceberg_val.strip().upper() in {"Y", "YES", "TRUE"})
            or is_iceberg_val is True
            or (isinstance(kind_val, str) and "ICEBERG" in kind_val.upper())
        )
        if not is_iceberg:
            continue

        out.append({
            "schema": _get(schema_idx),
            "name": _get(name_idx),
            "rows": _get(rows_idx),
        })

    return out


def cmd_refresh(args: argparse.Namespace) -> dict[str, Any]:
    """ALTER ICEBERG TABLE <name> REFRESH — manual one-shot refresh."""
    table_name = validate_table_name(args.name)
    sql = f"ALTER ICEBERG TABLE {table_name} REFRESH"

    conn = get_snowflake_connection(args.snowflake_connection)
    try:
        if args.use_role:
            _use_role(conn, args.use_role)
        with conn.cursor() as cur:
            cur.execute(sql)
    finally:
        conn.close()

    return {
        "success": True,
        "subcommand": "refresh",
        "name": table_name,
        "sql": sql,
    }


def cmd_set_auto_refresh(args: argparse.Namespace) -> dict[str, Any]:
    """ALTER ICEBERG TABLE <name> SET AUTO_REFRESH = {TRUE|FALSE}."""
    table_name = validate_table_name(args.name)
    # argparse `choices=["true", "false"]` already normalises; upper-case
    # for readable SQL. The boolean is what callers want in the payload.
    enabled_bool = args.enabled.lower() == "true"
    sql = f"ALTER ICEBERG TABLE {table_name} SET AUTO_REFRESH = {'TRUE' if enabled_bool else 'FALSE'}"

    conn = get_snowflake_connection(args.snowflake_connection)
    try:
        if args.use_role:
            _use_role(conn, args.use_role)
        with conn.cursor() as cur:
            cur.execute(sql)
    finally:
        conn.close()

    return {
        "success": True,
        "subcommand": "set-auto-refresh",
        "name": table_name,
        "enabled": enabled_bool,
        "sql": sql,
    }


def cmd_set_refresh_interval(args: argparse.Namespace) -> dict[str, Any]:
    """
    ALTER CATALOG INTEGRATION <integration> SET REFRESH_INTERVAL_SECONDS.

    Interval is an integration-level property — it applies to every
    iceberg table under this integration, not per-table. Range is
    validated client-side; the friendly error precedes any round-trip.
    """
    integration_name = validate_integration_name(args.integration)
    seconds = validate_refresh_interval(args.seconds)
    sql = (
        f"ALTER CATALOG INTEGRATION {integration_name} "
        f"SET REFRESH_INTERVAL_SECONDS = {seconds}"
    )

    conn = get_snowflake_connection(args.snowflake_connection)
    try:
        if args.use_role:
            _use_role(conn, args.use_role)
        with conn.cursor() as cur:
            cur.execute(sql)
    finally:
        conn.close()

    return {
        "success": True,
        "subcommand": "set-refresh-interval",
        "integration": integration_name,
        "seconds": seconds,
        "sql": sql,
    }


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    """
    Combined refresh status for an iceberg table:
      - SYSTEM$AUTO_REFRESH_STATUS: current AUTO_REFRESH execution state
      - ICEBERG_TABLE_SNAPSHOT_REFRESH_HISTORY: last 10 refresh attempts

    `healthy` is derived from the status string so agents don't reparse.
    """
    table_name = validate_table_name(args.name)

    conn = get_snowflake_connection(args.snowflake_connection)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT SYSTEM$AUTO_REFRESH_STATUS('{table_name}')")
            status_row = cur.fetchone()
            raw_status = status_row[0] if status_row else None

            cur.execute(
                "SELECT * FROM TABLE(INFORMATION_SCHEMA"
                ".ICEBERG_TABLE_SNAPSHOT_REFRESH_HISTORY("
                f"TABLE_NAME => '{table_name}'"
                ")) ORDER BY REFRESHED_ON DESC LIMIT 10"
            )
            history_rows = cur.fetchall()
            history_description = cur.description
    finally:
        conn.close()

    parsed_status: dict[str, Any] | None = None
    if isinstance(raw_status, str):
        try:
            parsed_status = json.loads(raw_status)
        except json.JSONDecodeError:
            parsed_status = None

    execution_state = (
        parsed_status.get("executionState") if parsed_status else None
    )

    col_names = (
        [col[0].lower() for col in history_description] if history_description else []
    )
    history = [
        {col_names[i]: (str(row[i]) if row[i] is not None else None)
         for i in range(min(len(col_names), len(row)))}
        for row in history_rows
    ]

    return {
        "success": True,
        "subcommand": "status",
        "name": table_name,
        "execution_state": execution_state,
        "healthy": execution_state == "RUNNING",
        "raw_status": raw_status,
        "refresh_history": history,
        "refresh_history_count": len(history),
    }


# ---------------------------------------------------------------------------
# argparse + dispatch (T010)
# ---------------------------------------------------------------------------

def _add_sf_connection_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--snowflake-connection",
        help="Named Snowflake connection (defaults to env or connections.toml default)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit structured JSON output (default: pretty-printed).",
    )


def _add_use_role_arg(parser: argparse.ArgumentParser) -> None:
    """
    Session-role override for the duration of this invocation only; no config
    file mutation. Matches the `manage/SKILL.md` role-picker workflow.
    Use for subcommands that may require privileges beyond the session default
    (CREATE CATALOG INTEGRATION ON ACCOUNT, CREATE DATABASE ON ACCOUNT,
    OWNERSHIP on integration / iceberg table, etc.).
    """
    parser.add_argument(
        "--use-role",
        help=(
            "Snowflake session role to use for this invocation "
            "(e.g. ACCOUNTADMIN). Overrides the connection's default role "
            "without modifying any config files."
        ),
    )


def _add_pg_connection_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--connection-name",
        required=True,
        help="Named Postgres connection from ~/.pg_service.conf",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit structured JSON output (default: pretty-printed).",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pg_lake_catalog.py",
        description=(
            "Manage CATALOG_SOURCE = SNOWFLAKE_POSTGRES catalog integrations, "
            "iceberg tables, and catalog-linked databases. Pair with a "
            "pg_lake-enabled Postgres instance on the same Snowflake account."
        ),
    )
    subparsers = parser.add_subparsers(dest="command")

    # 1. check-account-params (SF) — read-only, but accepts --use-role because
    #    role visibility IS the primary diagnostic axis (SHOW POSTGRES INSTANCES
    #    filters silently by role, so re-running as ACCOUNTADMIN is the fastest
    #    way to disambiguate the 0-rows case).
    p = subparsers.add_parser(
        "check-account-params",
        help="Verify required Snowflake account parameters are enabled",
    )
    _add_sf_connection_arg(p)
    _add_use_role_arg(p)

    # 2. list-pg-iceberg (PG)
    p = subparsers.add_parser(
        "list-pg-iceberg",
        help="Query pg_lake.iceberg_tables and return (catalog, namespace, table) triples",
    )
    _add_pg_connection_arg(p)

    # 3. create-integration (SF) — needs CREATE CATALOG INTEGRATION ON ACCOUNT
    #    + USAGE ON POSTGRES INSTANCE <name>. NOTE: CATALOG_NAMESPACE (PG
    #    schema) is a CREATE ICEBERG TABLE property, not an integration
    #    property.
    p = subparsers.add_parser(
        "create-integration",
        help="CREATE CATALOG INTEGRATION ... CATALOG_SOURCE = SNOWFLAKE_POSTGRES",
    )
    p.add_argument("--name", required=True, help="Catalog integration name")
    p.add_argument(
        "--postgres-instance", required=True,
        help="Postgres instance name (goes into POSTGRES_INSTANCE)",
    )
    p.add_argument(
        "--database", required=True,
        help="Postgres database name (goes into CATALOG_NAME)",
    )
    _add_sf_connection_arg(p)
    _add_use_role_arg(p)

    # 4. describe-integration (SF) — needs OWNERSHIP or MONITOR on the integration
    p = subparsers.add_parser(
        "describe-integration",
        help="DESCRIBE CATALOG INTEGRATION <name>",
    )
    p.add_argument("--name", required=True)
    _add_sf_connection_arg(p)
    _add_use_role_arg(p)

    # 5. drop-integration (SF) — needs OWNERSHIP on the integration
    p = subparsers.add_parser(
        "drop-integration",
        help="DROP CATALOG INTEGRATION (destructive — requires --confirm)",
    )
    p.add_argument("--name", required=True)
    p.add_argument(
        "--confirm", action="store_true",
        help="Required for destructive drop; without it, the command prints what would happen and exits non-zero",
    )
    _add_sf_connection_arg(p)
    _add_use_role_arg(p)

    # 6. create-iceberg-table (SF) — needs USAGE on integration + CREATE ICEBERG TABLE on schema
    p = subparsers.add_parser(
        "create-iceberg-table",
        help="CREATE ICEBERG TABLE pointing at a pg_lake iceberg table",
    )
    p.add_argument("--name", required=True, help="Iceberg table name in Snowflake")
    p.add_argument("--catalog", required=True, help="Catalog integration name")
    p.add_argument(
        "--catalog-table-name", required=True,
        help="Table name on the PG side (from list-pg-iceberg)",
    )
    p.add_argument(
        "--catalog-namespace", default="public",
        help="PG schema (default: public)",
    )
    p.add_argument(
        "--auto-refresh", action="store_true",
        help="Enable AUTO_REFRESH = TRUE on the iceberg table",
    )
    _add_sf_connection_arg(p)
    _add_use_role_arg(p)

    # 7. create-cld (SF) — needs CREATE DATABASE ON ACCOUNT + USAGE on integration
    p = subparsers.add_parser(
        "create-cld",
        help="CREATE DATABASE ... LINKED_CATALOG (with ALLOWED_WRITE_OPERATIONS = NONE)",
    )
    p.add_argument("--name", required=True, help="Catalog-linked database name")
    p.add_argument("--catalog", required=True, help="Catalog integration name")
    _add_sf_connection_arg(p)
    _add_use_role_arg(p)

    # 8. cld-status (SF)
    p = subparsers.add_parser(
        "cld-status",
        help="Report SYSTEM$CATALOG_LINK_STATUS and SHOW TABLES for a CLD",
    )
    p.add_argument("--name", required=True, help="CLD database name")
    _add_sf_connection_arg(p)

    # 9. refresh (SF) — needs OWNERSHIP on iceberg table
    p = subparsers.add_parser(
        "refresh",
        help="ALTER ICEBERG TABLE <name> REFRESH",
    )
    p.add_argument("--name", required=True)
    _add_sf_connection_arg(p)
    _add_use_role_arg(p)

    # 10. set-auto-refresh (SF) — needs OWNERSHIP on iceberg table
    p = subparsers.add_parser(
        "set-auto-refresh",
        help="ALTER ICEBERG TABLE <name> SET AUTO_REFRESH = {TRUE|FALSE}",
    )
    p.add_argument("--name", required=True)
    p.add_argument(
        "--enabled", required=True, choices=["true", "false"],
        help="Set AUTO_REFRESH state",
    )
    _add_sf_connection_arg(p)
    _add_use_role_arg(p)

    # 11. set-refresh-interval (SF, integration-level — applies to every
    #     iceberg table under this integration) — needs OWNERSHIP on the
    #     catalog integration
    p = subparsers.add_parser(
        "set-refresh-interval",
        help=(
            "ALTER CATALOG INTEGRATION <integration> SET REFRESH_INTERVAL_SECONDS. "
            "Applies to ALL iceberg tables under the integration — interval is "
            "stored at the integration level, not per table."
        ),
    )
    p.add_argument("--integration", required=True, help="Catalog integration name")
    p.add_argument(
        "--seconds", required=True, type=int,
        help="New REFRESH_INTERVAL_SECONDS value (default on the SF side is 30)",
    )
    _add_sf_connection_arg(p)
    _add_use_role_arg(p)

    # 12. status (SF)
    p = subparsers.add_parser(
        "status",
        help=(
            "SYSTEM$AUTO_REFRESH_STATUS + recent ICEBERG_TABLE_SNAPSHOT_REFRESH_HISTORY"
        ),
    )
    p.add_argument("--name", required=True, help="Iceberg table name")
    _add_sf_connection_arg(p)

    return parser


_DISPATCH = {
    "check-account-params":  cmd_check_account_params,
    "list-pg-iceberg":       cmd_list_pg_iceberg,
    "create-integration":    cmd_create_integration,
    "describe-integration":  cmd_describe_integration,
    "drop-integration":      cmd_drop_integration,
    "create-iceberg-table":  cmd_create_iceberg_table,
    "create-cld":            cmd_create_cld,
    "cld-status":            cmd_cld_status,
    "refresh":               cmd_refresh,
    "set-auto-refresh":      cmd_set_auto_refresh,
    "set-refresh-interval":  cmd_set_refresh_interval,
    "status":                cmd_status,
}


def _emit(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        for key, value in result.items():
            if isinstance(value, (dict, list)):
                print(f"{key}:")
                print("  " + json.dumps(value, indent=2, default=str).replace("\n", "\n  "))
            else:
                print(f"{key}: {value}")


def main(argv: list[str] | None = None) -> int:
    pg_common.check_driver()
    parser = _build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if not args.command:
        parser.print_help()
        return 1

    handler = _DISPATCH[args.command]
    try:
        result = handler(args)
    except ValueError as e:
        # Identifier validation and other argument errors.
        err = {"success": False, "subcommand": args.command, "error": str(e)}
        _emit(err, getattr(args, "json", False))
        return 2
    except Exception as e:  # noqa: BLE001
        raw = str(e)
        friendly = translate_error(raw)
        err = {
            "success": False,
            "subcommand": args.command,
            "error": raw,
        }
        if friendly:
            err["friendly_error"] = friendly
        _emit(err, getattr(args, "json", False))
        return 1

    _emit(result, getattr(args, "json", False))
    # Stubs (any subcommand wired without an implementation) return
    # success=False + status=not_implemented; surface that as exit 2 so
    # callers can't mistake it for a completed action.
    if result.get("status") == "not_implemented":
        return 2
    return 0 if result.get("success", False) else 1


if __name__ == "__main__":
    sys.exit(main())
