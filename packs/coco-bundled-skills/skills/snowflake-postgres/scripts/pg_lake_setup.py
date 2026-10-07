#!/usr/bin/env python3
"""
pg_lake extension setup and management for Postgres.

Handles extension checks, enablement, S3 configuration, Iceberg table
verification, and catalog queries. Uses pg_common for driver-agnostic
connections via pg_service.conf — no Snowflake dependencies.

Scope: the --set-config flag and test-table helper validate an `s3://`
prefix (AWS/S3). Azure pg_lake instances use `azure://` prefixes and a
different storage integration shape — for Azure, set the
pg_lake_iceberg.default_location_prefix GUC directly in psql and create
iceberg tables with an explicit `azure://` location. See
https://docs.snowflake.com/en/user-guide/data-load-azure-config for the
Azure storage integration side.

Connection options:
1. --connection-name: Named connection from ~/.pg_service.conf
2. --dsn: Direct libpq connection string
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# Make ./shared/ importable when this script is run directly (pytest already
# injects it via pythonpath). Mirrors the bootstrap in pg_connect.py.
_SHARED_DIR = Path(__file__).resolve().parent / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

import urllib.parse

import pg_common  # noqa: E402

_S3_LOCATION_RE = re.compile(r"^s3://[a-z0-9][\w.\-]{1,61}[a-z0-9](/[\w.\-/]*)?$")


# Extensions that pg_lake CASCADE installs
PG_LAKE_EXTENSIONS = [
    "pg_lake",
    "pg_lake_table",
    "pg_lake_iceberg",
    "pg_lake_engine",
    "pg_lake_copy",
]


CONNECT_TIMEOUT_SECS = 30
MAX_RETRIES = 3
RETRY_BACKOFF = [5, 15, 30]


def _resolve_connect_kwargs(connect_str: str) -> dict:
    """Translate a connect_str (URI or service=NAME DSN) into kwargs for pg_common.connect().

    Two forms are supported:
    - postgres:// or postgresql:// URI -> parsed with urllib.parse
    - service=NAME -> resolved via pg_service.conf + pgpass
    """
    if connect_str.startswith(("postgres://", "postgresql://")):
        parsed = urllib.parse.urlparse(connect_str)
        qs = urllib.parse.parse_qs(parsed.query)
        # Default sslmode=prefer matches libpq: try TLS, fall back to
        # plaintext if the server refuses it. Keeps localhost / internal-PG
        # development flows working. Explicit `?sslmode=require` (or stricter)
        # in the URI forces TLS. On the pg8000 fallback path (Windows ARM64)
        # `prefer` cannot transparently downgrade — users connecting to a
        # plaintext server there should pass `?sslmode=disable`.
        kw: dict = {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 5432,
            "dbname": (parsed.path or "/").lstrip("/") or "postgres",
            "user": parsed.username or "",
            "password": parsed.password or "",
            "sslmode": qs["sslmode"][0] if "sslmode" in qs else "prefer",
        }
        if "sslrootcert" in qs:
            kw["sslrootcert"] = qs["sslrootcert"][0]
        return kw

    if connect_str.startswith("service="):
        name = connect_str[len("service="):]
        entry = pg_common.get_service_entry(name)
        if entry is None:
            raise ValueError(f"Service '{name}' not found in ~/.pg_service.conf")
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
        f"Unsupported connect_str format: {connect_str!r}. "
        "Expected a postgres:// URI or service=NAME DSN."
    )


def get_connection(
    connection_name: str | None = None,
    dsn: str | None = None,
    retries: int = MAX_RETRIES,
):
    """
    Connect to Postgres with timeout and retry.

    Retries with exponential backoff handle the common case where a
    suspended instance is resuming (3-5 min). Each attempt uses
    connect_timeout so we don't hang indefinitely.
    """
    if not dsn and not connection_name:
        raise ValueError("Provide --connection-name or --dsn")

    connect_str = dsn if dsn else f"service={connection_name}"
    last_error = None

    for attempt in range(retries):
        try:
            conn = pg_common.connect(**_resolve_connect_kwargs(connect_str),
                                     connect_timeout=CONNECT_TIMEOUT_SECS)
            if attempt > 0:
                print(f"Connected on attempt {attempt + 1}", file=sys.stderr)
            return conn
        except pg_common.PgOperationalError as e:
            last_error = e
            error_str = str(e).lower()
            is_transient = (
                "timeout" in error_str
                or "timed out" in error_str
                or "connection refused" in error_str
                or "could not connect" in error_str
            )
            if not is_transient or attempt == retries - 1:
                break
            wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
            print(
                f"Connection attempt {attempt + 1}/{retries} failed, "
                f"retrying in {wait}s... ({_short_error(e)})",
                file=sys.stderr,
            )
            time.sleep(wait)

    msg = _connection_failure_message(last_error, connection_name)
    raise ConnectionError(msg) from last_error


def _short_error(e: Exception) -> str:
    """First line of an error for compact retry messages."""
    return str(e).strip().split("\n")[0][:120]


def _connection_failure_message(error: Exception, connection_name: str | None) -> str:
    """Actionable error message after all retries exhausted."""
    error_str = str(error).lower()
    base = f"Connection failed after {MAX_RETRIES} attempts: {_short_error(error)}"

    if "timeout" in error_str or "timed out" in error_str:
        return (
            f"{base}\n\n"
            "The instance may be suspended or resuming. Check state with:\n"
            f"  DESCRIBE POSTGRES INSTANCE <name>;\n"
            "If SUSPENDED, resume and wait for READY (3-5 min):\n"
            f"  ALTER POSTGRES INSTANCE <name> RESUME;"
        )
    if "connection refused" in error_str or "could not connect" in error_str:
        return (
            f"{base}\n\n"
            "Possible causes:\n"
            "  - Instance is SUSPENDED (check with DESCRIBE POSTGRES INSTANCE)\n"
            "  - Your IP is not in the network policy\n"
            "  - Firewall blocking port 5432"
        )
    if "authentication" in error_str or "password" in error_str:
        return (
            f"{base}\n\n"
            "Authentication failed. Reset credentials with:\n"
            "  pg_connect.py --reset --instance-name <name>"
        )
    return base


def check_extensions(conn) -> dict:
    """
    Check pg_lake extension availability and installation status.
    
    Queries pg_available_extensions for all pg_lake-related extensions
    and reports which are available vs installed.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT name, default_version, installed_version, comment
            FROM pg_available_extensions
            WHERE name LIKE 'pg_lake%%'
            ORDER BY name
        """)
        rows = cur.fetchall()

    extensions = []
    for name, default_ver, installed_ver, comment in rows:
        extensions.append({
            "name": name,
            "default_version": default_ver,
            "installed_version": installed_ver,
            "installed": installed_ver is not None,
            "comment": comment,
        })

    available_names = {e["name"] for e in extensions}
    installed_names = {e["name"] for e in extensions if e["installed"]}

    return {
        "extensions": extensions,
        "pg_lake_available": "pg_lake" in available_names,
        "pg_lake_installed": "pg_lake" in installed_names,
        "all_installed": all(
            ext in installed_names for ext in PG_LAKE_EXTENSIONS
            if ext in available_names
        ),
        "available_count": len(available_names),
        "installed_count": len(installed_names),
    }


def enable_extensions(conn) -> dict:
    """
    Enable pg_lake via CREATE EXTENSION pg_lake CASCADE.
    
    CASCADE automatically installs all sub-extensions
    (pg_lake_table, pg_lake_iceberg, pg_lake_engine, pg_lake_copy).
    """
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pg_lake CASCADE")
    conn.commit()

    result = check_extensions(conn)
    result["action"] = "enable"
    result["success"] = result["pg_lake_installed"]
    return result


def check_config(conn) -> dict:
    """
    Check current pg_lake GUC settings.
    
    Returns pg_lake_iceberg.default_location_prefix and other pg_lake-specific
    configuration values from pg_settings.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT name, setting, unit, source, boot_val, reset_val
            FROM pg_settings
            WHERE name LIKE 'pg_lake%%'
               OR name = 'pg_lake_iceberg.default_location_prefix'
            ORDER BY name
        """)
        rows = cur.fetchall()

    settings = []
    default_location = None
    for name, setting, unit, source, boot_val, reset_val in rows:
        entry = {
            "name": name,
            "value": setting,
            "unit": unit,
            "source": source,
            "boot_value": boot_val,
            "reset_value": reset_val,
        }
        settings.append(entry)
        if name == "pg_lake_iceberg.default_location_prefix":
            default_location = setting

    return {
        "settings": settings,
        "default_location_prefix": default_location,
        "is_configured": bool(default_location and default_location.startswith("s3://")),
    }


def set_config(conn, prefix: str) -> dict:
    """
    Set pg_lake_iceberg.default_location_prefix for the current session.

    This GUC is PGC_SUSET (superuser-only, session-level). It cannot be
    persisted via ALTER DATABASE/ROLE SET. In managed Snowflake Postgres,
    the platform handles persistence via postgresql.conf when the storage
    integration is attached.

    If the value is already set (e.g., by the platform), reports that.
    """
    # Verify the GUC exists before trying to set it
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM pg_settings
            WHERE name = 'pg_lake_iceberg.default_location_prefix'
        """)
        if not cur.fetchone():
            return {
                "success": False,
                "action": "set_config",
                "error": (
                    "pg_lake_iceberg.default_location_prefix parameter not found. "
                    "This usually means pg_lake extensions are not fully loaded. "
                    "Ensure the storage integration is attached (Step 4), "
                    "then reconnect and retry."
                ),
                "hint": "Try: --enable-extensions first, or reconnect after attaching the storage integration",
            }

    with conn.cursor() as cur:
        # Check reset_val before SET — if it already matches, the platform
        # has persisted this in postgresql.conf and it survives reconnects.
        cur.execute("""
            SELECT reset_val FROM pg_settings
            WHERE name = 'pg_lake_iceberg.default_location_prefix'
        """)
        row = cur.fetchone()
        platform_value = row[0] if row and row[0] else None

        cur.execute("SET pg_lake_iceberg.default_location_prefix = %s", (prefix,))
        conn.commit()

    result = check_config(conn)
    result["action"] = "set_config"
    result["requested_prefix"] = prefix
    result["success"] = result["default_location_prefix"] == prefix

    if platform_value and platform_value.rstrip("/") == prefix.rstrip("/"):
        result["persisted_by_platform"] = True
    else:
        result["persisted_by_platform"] = False
        result["note"] = (
            "Set for this session only. In managed Snowflake Postgres, "
            "the platform typically persists this via postgresql.conf "
            "when the storage integration is attached."
        )

    return result


def verify_s3_access(conn, prefix: str | None = None) -> dict:
    """
    Verify S3 access by listing files via lake_file.list().
    
    Uses the provided prefix or falls back to current pg_lake_iceberg.default_location_prefix.
    A successful listing (even empty) confirms the S3 trust policy is working.
    """
    prefix_from_arg = prefix is not None

    with conn.cursor() as cur:
        if not prefix:
            cur.execute("SHOW pg_lake_iceberg.default_location_prefix")
            row = cur.fetchone()
            prefix = row[0] if row else None
            if not prefix:
                return {
                    "success": False,
                    "error": (
                        "No pg_lake_iceberg.default_location_prefix set and no --prefix provided. "
                        "Each script invocation is a separate connection, so --set-config values "
                        "don't carry over. Use --prefix explicitly."
                    ),
                    "files": [],
                }

        try:
            cur.execute("SELECT * FROM lake_file.list(%s) LIMIT 20", (prefix,))
            files = []
            columns = [desc[0] for desc in cur.description] if cur.description else []
            for row in cur.fetchall():
                files.append(dict(zip(columns, row)))
        except pg_common.PgError as e:
            error_msg = str(e).strip()
            result = {
                "success": False,
                "error": error_msg,
                "prefix": prefix,
                "files": [],
            }
            if "403" in error_msg and not prefix_from_arg:
                result["hint"] = (
                    "Got 403 using the session default prefix. This may not be your "
                    "S3 bucket — try passing --prefix s3://your-bucket/path/ explicitly."
                )
            return result

    return {
        "success": True,
        "prefix": prefix,
        "file_count": len(files),
        "files": files,
    }


def create_test_table(conn, prefix: str | None = None) -> dict:
    """
    Create a test Iceberg table to verify the full pg_lake pipeline.
    
    Creates pg_lake_test_iceberg with a single row, queries it back,
    and verifies it appears in the iceberg_tables catalog view.
    Cleans up afterwards.
    """
    table_name = "pg_lake_test_iceberg"

    with conn.cursor() as cur:
        # Drop if leftover from previous test
        cur.execute(f"DROP TABLE IF EXISTS {table_name}")

        # Build CREATE TABLE with optional location
        create_sql = (
            f"CREATE TABLE {table_name} (id int, name text) USING iceberg"
        )
        if prefix:
            if not _S3_LOCATION_RE.match(prefix.rstrip("/")):
                return {
                    "success": False,
                    "step": "validate",
                    "error": (
                        f"Invalid S3 prefix format: {prefix!r}. "
                        f"AWS/S3 only — for Azure, run "
                        f"CREATE TABLE ... USING iceberg directly in psql "
                        f"with an azure:// location."
                    ),
                }
            location = f"{prefix.rstrip('/')}/{table_name}"
            create_sql += f" WITH (location = '{location}')"

        try:
            cur.execute(create_sql)
            conn.commit()
        except pg_common.PgError as e:
            conn.rollback()
            return {
                "success": False,
                "step": "create_table",
                "error": str(e).strip(),
            }

        # Insert test data
        try:
            cur.execute(
                f"INSERT INTO {table_name} (id, name) VALUES (1, 'pg_lake_test')"
            )
            conn.commit()
        except pg_common.PgError as e:
            conn.rollback()
            cur.execute(f"DROP TABLE IF EXISTS {table_name}")
            conn.commit()
            return {
                "success": False,
                "step": "insert",
                "error": str(e).strip(),
            }

        # Query back and check catalog, ensuring cleanup on any failure
        rows = []
        in_catalog = False
        try:
            cur.execute(f"SELECT id, name FROM {table_name}")
            rows = cur.fetchall()

            cur.execute(
                "SELECT table_name FROM iceberg_tables WHERE table_name = %s",
                (table_name,),
            )
            in_catalog = cur.fetchone() is not None
        except pg_common.PgError as e:
            conn.rollback()
            return {
                "success": False,
                "step": "verify",
                "error": str(e).strip(),
                "cleaned_up": False,
            }
        finally:
            try:
                cur.execute(f"DROP TABLE IF EXISTS {table_name}")
                conn.commit()
            except pg_common.PgError:
                conn.rollback()

    return {
        "success": len(rows) == 1 and rows[0] == (1, "pg_lake_test"),
        "table_created": True,
        "row_returned": rows[0] if rows else None,
        "in_catalog": in_catalog,
        "cleaned_up": True,
    }


def get_iceberg_tables(conn) -> dict:
    """
    List all Iceberg tables from the iceberg_tables catalog view.
    
    Returns table metadata including schema, name, location, format version,
    and snapshot information.
    """
    with conn.cursor() as cur:
        try:
            cur.execute("""
                SELECT *
                FROM iceberg_tables
                ORDER BY table_schema, table_name
            """)
            columns = [desc[0] for desc in cur.description] if cur.description else []
            rows = cur.fetchall()
        except pg_common.PgError as e:
            return {
                "success": False,
                "error": str(e).strip(),
                "tables": [],
            }

    tables = [dict(zip(columns, row)) for row in rows]
    return {
        "success": True,
        "table_count": len(tables),
        "tables": tables,
    }


def _json_serializer(obj):
    """Handle non-serializable types in JSON output."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    return str(obj)


def main():
    pg_common.check_driver()
    parser = argparse.ArgumentParser(
        description="pg_lake extension setup and management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  --check-extensions     Check pg_lake extension availability
  --enable-extensions    Install pg_lake (CASCADE installs all sub-extensions)
  --check-config         Show current pg_lake GUC settings
  --set-config PREFIX    Set pg_lake_iceberg.default_location_prefix (S3 path)
  --verify-s3            Verify S3 access via lake_file.list()
  --test-table           Create and query a test Iceberg table
  --list-iceberg         List all Iceberg tables

Examples:
  %(prog)s --check-extensions --connection-name my_pg --json
  %(prog)s --enable-extensions --connection-name my_pg
  %(prog)s --set-config s3://my-bucket/prefix --connection-name my_pg
  %(prog)s --verify-s3 --connection-name my_pg --json
  %(prog)s --test-table --connection-name my_pg
  %(prog)s --list-iceberg --connection-name my_pg --json
"""
    )

    # Connection options
    conn_group = parser.add_argument_group("connection options")
    conn_group.add_argument(
        "--connection-name",
        help="Connection name from ~/.pg_service.conf",
    )
    conn_group.add_argument(
        "--dsn",
        help="Direct libpq connection string",
    )

    # Commands
    cmd_group = parser.add_argument_group("commands")
    cmd_group.add_argument(
        "--check-extensions",
        action="store_true",
        help="Check pg_lake extension availability and status",
    )
    cmd_group.add_argument(
        "--enable-extensions",
        action="store_true",
        help="Install pg_lake CASCADE (all sub-extensions)",
    )
    cmd_group.add_argument(
        "--check-config",
        action="store_true",
        help="Show current pg_lake configuration",
    )
    cmd_group.add_argument(
        "--set-config",
        metavar="PREFIX",
        help=(
            "Set pg_lake_iceberg.default_location_prefix (e.g., s3://bucket/path). "
            "AWS/S3 only — for azure:// prefixes, SET the GUC directly in psql."
        ),
    )
    cmd_group.add_argument(
        "--persistent",
        action="store_true",
        help="Deprecated — ignored. The GUC is PGC_SUSET and can only be set at session level. "
             "The platform persists it via postgresql.conf when the storage integration is attached.",
    )
    cmd_group.add_argument(
        "--verify-s3",
        action="store_true",
        help="Verify S3 access via lake_file.list()",
    )
    cmd_group.add_argument(
        "--prefix",
        help="S3 prefix for --verify-s3 or --test-table (overrides pg_lake_iceberg.default_location_prefix)",
    )
    cmd_group.add_argument(
        "--test-table",
        action="store_true",
        help="Create, query, and drop a test Iceberg table",
    )
    cmd_group.add_argument(
        "--list-iceberg",
        action="store_true",
        help="List all Iceberg tables from catalog",
    )

    # Output options
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    # Require at least one command
    commands = [
        args.check_extensions,
        args.enable_extensions,
        args.check_config,
        args.set_config,
        args.verify_s3,
        args.test_table,
        args.list_iceberg,
    ]
    if not any(commands):
        parser.print_help()
        sys.exit(1)

    try:
        conn = get_connection(args.connection_name, args.dsn)
    except (ConnectionError, ValueError) as e:
        error = {"success": False, "error": str(e)}
        if args.json:
            print(json.dumps(error, indent=2))
        else:
            print(f"{e}")
        sys.exit(1)

    try:
        result = {}

        if args.check_extensions:
            result = check_extensions(conn)
            if not args.json:
                _print_extensions(result)
                return

        elif args.enable_extensions:
            result = enable_extensions(conn)
            if not args.json:
                if result["success"]:
                    print("pg_lake enabled successfully")
                    print(f"  Extensions installed: {result['installed_count']}")
                else:
                    print("Failed to enable pg_lake")
                sys.exit(0 if result["success"] else 1)
                return

        elif args.check_config:
            result = check_config(conn)
            if not args.json:
                _print_config(result)
                return

        elif args.set_config:
            result = set_config(conn, args.set_config)
            if not args.json:
                if result["success"]:
                    persisted = result.get("persisted_by_platform", False)
                    status = "persisted by platform" if persisted else "session"
                    print(f"pg_lake_iceberg.default_location_prefix set to {args.set_config} ({status})")
                else:
                    print("Failed to set config")
                sys.exit(0 if result["success"] else 1)
                return

        elif args.verify_s3:
            result = verify_s3_access(conn, args.prefix)
            if not args.json:
                _print_s3_verify(result)
                sys.exit(0 if result["success"] else 1)
                return

        elif args.test_table:
            result = create_test_table(conn, args.prefix)
            if not args.json:
                _print_test_table(result)
                sys.exit(0 if result["success"] else 1)
                return

        elif args.list_iceberg:
            result = get_iceberg_tables(conn)
            if not args.json:
                _print_iceberg_tables(result)
                return

        # JSON output path
        print(json.dumps(result, indent=2, default=_json_serializer))
        sys.exit(0 if result.get("success", True) else 1)

    except Exception as e:
        error = {"success": False, "error": str(e)}
        if args.json:
            print(json.dumps(error, indent=2))
        else:
            print(f"Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


def _print_extensions(result: dict) -> None:
    """Human-readable extension status."""
    if result["pg_lake_available"]:
        status = "installed" if result["pg_lake_installed"] else "available (not installed)"
        print(f"pg_lake: {status}")
    else:
        print("pg_lake: not available on this instance")
        sys.exit(1)

    for ext in result["extensions"]:
        icon = "+" if ext["installed"] else "-"
        ver = ext["installed_version"] or ext["default_version"] or "?"
        print(f"  {icon} {ext['name']} ({ver})")

    if result["all_installed"]:
        print(f"\nAll {result['installed_count']} extensions installed")
    else:
        print(f"\n{result['installed_count']}/{result['available_count']} installed")
        print("Run with --enable-extensions to install")


def _print_config(result: dict) -> None:
    """Human-readable config output."""
    if not result["settings"]:
        print("No pg_lake settings found")
        print("pg_lake may not be installed — run --check-extensions first")
        return

    for s in result["settings"]:
        val = s["value"] or "(not set)"
        src = f" [{s['source']}]" if s["source"] != "default" else ""
        print(f"  {s['name']} = {val}{src}")

    if result["is_configured"]:
        print(f"\nS3 location: {result['default_location_prefix']}")
    else:
        print("\npg_lake_iceberg.default_location_prefix not configured")
        print("Run --set-config s3://your-bucket/prefix to configure")


def _print_s3_verify(result: dict) -> None:
    """Human-readable S3 verification output."""
    if result["success"]:
        print(f"S3 access verified: {result['prefix']}")
        print(f"  Files found: {result['file_count']}")
        for f in result["files"][:5]:
            print(f"  - {f}")
        if result["file_count"] > 5:
            print(f"  ... and {result['file_count'] - 5} more")
    else:
        print(f"S3 access failed: {result.get('error', 'unknown error')}")
        if result.get("prefix"):
            print(f"  Prefix: {result['prefix']}")


def _print_test_table(result: dict) -> None:
    """Human-readable test table output."""
    if result["success"]:
        print("Iceberg table test passed")
        print(f"  Table created: {result['table_created']}")
        print(f"  Row returned: {result['row_returned']}")
        print(f"  In catalog: {result['in_catalog']}")
        print(f"  Cleaned up: {result['cleaned_up']}")
    else:
        print(f"Iceberg table test failed at step: {result.get('step', 'unknown')}")
        print(f"  Error: {result.get('error', 'unknown')}")


def _print_iceberg_tables(result: dict) -> None:
    """Human-readable Iceberg tables listing."""
    if not result["success"]:
        print(f"Failed to list Iceberg tables: {result.get('error')}")
        sys.exit(1)

    if not result["tables"]:
        print("No Iceberg tables found")
        return

    print(f"Iceberg tables ({result['table_count']}):")
    for t in result["tables"]:
        schema = t.get("table_schema", "public")
        name = t.get("table_name", "?")
        location = t.get("location", "")
        print(f"  {schema}.{name}")
        if location:
            print(f"    location: {location}")


if __name__ == "__main__":
    main()
