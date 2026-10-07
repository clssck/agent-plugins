#!/usr/bin/env python3
"""
Postgres diagnostics runner (pg_doctor).

Runs health checks against a Postgres instance and reports status based on
thresholds from Crunchy Bridge best practices. All queries execute in readonly
mode with a statement timeout to prevent hangs.

Each check is registered in CHECKS with its own evaluator function.
Adding a check = SQL file in sql/ + evaluator function + registry entry.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from tabulate import tabulate

# Import connection helpers from pg_connect (same directory)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared"))
from pg_connect import get_connect_params, list_connections  # noqa: E402
import pg_common  # noqa: E402

# SQL directory relative to this script
SQL_DIR = Path(__file__).parent.parent / "sql"

# Default statement timeout in milliseconds (30 seconds)
DEFAULT_STATEMENT_TIMEOUT_MS = 30000


# ---------------------------------------------------------------------------
# Evaluator functions
#
# Each evaluator receives (rows, columns) from the query result and returns
# a (status, message) tuple. Status is one of: good, warning, critical.
# ---------------------------------------------------------------------------

def evaluate_cache_hit(rows: list, columns: list) -> tuple[str, str]:
    """Evaluate index and table cache hit rates.

    Reports the lower of the two rates (index vs table) since that's the
    bottleneck. The query returns two rows: 'index hit rate' and 'table hit rate'.
    """
    if not rows:
        return ("warning", "No cache data available")
    # Build a name->ratio map for readable messages
    named = {r[0]: r[1] for r in rows if r[1] is not None}
    if not named:
        return ("warning", "No cache data available")
    worst_name = min(named, key=named.get)
    worst_ratio = named[worst_name]
    if worst_ratio >= 0.99:
        status = "good"
    elif worst_ratio >= 0.95:
        status = "warning"
    else:
        status = "critical"
    return (status, f"{worst_name}: {worst_ratio:.1%}")


def evaluate_bloat(rows: list, columns: list) -> tuple[str, str]:
    """Evaluate table and index bloat ratios."""
    if not rows:
        return ("good", "No bloat detected")
    # Column index 3 is the bloat ratio
    bloat_ratios = [r[3] for r in rows if r[3] is not None]
    if not bloat_ratios:
        return ("good", "No bloat detected")
    max_bloat = max(bloat_ratios)
    if max_bloat < 1.3:
        status = "good"
    elif max_bloat <= 1.5:
        status = "warning"
    else:
        status = "critical"
    return (status, f"Max bloat: {max_bloat:.1f}x")


def evaluate_vacuum_stats(rows: list, columns: list) -> tuple[str, str]:
    """Evaluate autovacuum status across tables."""
    if not rows:
        return ("good", "Vacuum status healthy")
    # Column index 7 is expect_autovacuum ('yes' or None)
    needs_vacuum = [r for r in rows if r[7] == "yes"]
    if needs_vacuum:
        return ("warning", f"{len(needs_vacuum)} table(s) need vacuum")
    return ("good", "Vacuum status healthy")


def evaluate_connections(rows: list, columns: list) -> tuple[str, str]:
    """Evaluate connection counts."""
    if not rows:
        return ("good", "0 active connections")
    total = sum(r[0] for r in rows if r[0] is not None)
    return ("good", f"{total} active connections")


def evaluate_locks(rows: list, columns: list) -> tuple[str, str]:
    """Evaluate exclusive locks held."""
    if rows and len(rows) > 0:
        return ("warning", f"{len(rows)} exclusive locks held")
    return ("good", "No exclusive locks")


def evaluate_blocking(rows: list, columns: list) -> tuple[str, str]:
    """Evaluate blocked queries."""
    if rows and len(rows) > 0:
        return ("critical", f"{len(rows)} blocked queries")
    return ("good", "No blocking queries")


def evaluate_long_running(rows: list, columns: list) -> tuple[str, str]:
    """Evaluate long-running queries (> 5 minutes)."""
    if rows and len(rows) > 0:
        return ("warning", f"{len(rows)} long-running queries")
    return ("good", "No long-running queries")


def evaluate_outliers(rows: list, columns: list) -> tuple[str, str]:
    """Evaluate query outliers (informational)."""
    return ("good", f"Top {len(rows)} query outliers")


def evaluate_unused_indexes(rows: list, columns: list) -> tuple[str, str]:
    """Evaluate unused indexes (never scanned, not unique/constraint)."""
    if not rows:
        return ("good", "No unused indexes")
    return ("warning", f"{len(rows)} unused indexes (wasting space)")


def evaluate_table_sizes(rows: list, columns: list) -> tuple[str, str]:
    """Evaluate table sizes (informational breakdown)."""
    if not rows:
        return ("good", "No user tables")
    return ("good", f"{len(rows)} tables")


# ---------------------------------------------------------------------------
# Check registry
#
# Maps check names to metadata + evaluator. SQL file is loaded by convention:
# check name -> sql/{name}.sql
# ---------------------------------------------------------------------------

# Type alias for evaluator functions
Evaluator = Callable[[list, list], tuple[str, str]]

CHECKS: dict[str, dict[str, Any]] = {
    "cache_hit": {
        "category": "health",
        "description": "Index and table cache hit rate",
        "evaluate": evaluate_cache_hit,
    },
    "bloat": {
        "category": "health",
        "description": "Table and index bloat estimation",
        "evaluate": evaluate_bloat,
    },
    "vacuum_stats": {
        "category": "health",
        "description": "Dead rows and autovacuum status",
        "evaluate": evaluate_vacuum_stats,
    },
    "connections": {
        "category": "health",
        "description": "Connection counts per role",
        "evaluate": evaluate_connections,
    },
    "locks": {
        "category": "health",
        "description": "Exclusive locks held",
        "evaluate": evaluate_locks,
    },
    "blocking": {
        "category": "health",
        "description": "Blocked queries",
        "evaluate": evaluate_blocking,
    },
    "long_running": {
        "category": "health",
        "description": "Queries running > 5 minutes",
        "evaluate": evaluate_long_running,
    },
    "outliers": {
        "category": "health",
        "description": "Top slow queries (pg_stat_statements)",
        "evaluate": evaluate_outliers,
    },
    "unused_indexes": {
        "category": "health",
        "description": "Indexes that have never been scanned",
        "evaluate": evaluate_unused_indexes,
    },
    "table_sizes": {
        "category": "health",
        "description": "Table size breakdown (total, index, toast)",
        "evaluate": evaluate_table_sizes,
    },
}


def _is_missing_pg_stat_statements_error(check_name: str, error: Exception) -> bool:
    """Recognize the expected outliers failure when pg_stat_statements is unavailable."""
    if check_name != "outliers":
        return False

    lower = str(error).lower()
    if "pg_stat_statements" not in lower:
        return False

    known_markers = (
        'relation "pg_stat_statements" does not exist',
        "pg_stat_statements must be loaded via shared_preload_libraries",
        "pg_stat_statements is not enabled",
        "pg_stat_statements is not installed",
    )
    return any(marker in lower for marker in known_markers)


def load_sql(name: str) -> str:
    """Load a SQL query file from the sql/ directory by check name."""
    sql_file = SQL_DIR / f"{name}.sql"
    if not sql_file.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_file}")
    return sql_file.read_text()


def get_checks_for_category(category: str) -> list[str]:
    """Return check names belonging to a category."""
    return [name for name, info in CHECKS.items() if info["category"] == category]


def get_all_checks() -> list[str]:
    """Return all registered check names."""
    return list(CHECKS.keys())


def status_icon(status: str) -> str:
    """Map status string to a display icon."""
    icons = {
        "good": "✅",
        "warning": "⚠️",
        "critical": "❌",
        "unknown": "❓",
    }
    return icons.get(status, "❓")


def run_check(conn, check_name: str) -> dict[str, Any]:
    """
    Run a single diagnostic check.

    Loads the SQL file, executes it, and runs the registered evaluator to
    determine status and message.

    Returns: {name, status, rows, columns, message}
    """
    result: dict[str, Any] = {
        "name": check_name,
        "status": "unknown",
        "rows": [],
        "columns": [],
        "message": "",
    }

    if check_name not in CHECKS:
        result["status"] = "critical"
        result["message"] = f"Unknown check: {check_name}"
        return result

    try:
        sql = load_sql(check_name)

        with conn.cursor() as cur:
            cur.execute(sql)

            if cur.description:
                result["columns"] = [desc[0] for desc in cur.description]

            rows = cur.fetchall()
            result["rows"] = [list(row) for row in rows]

        # Run the registered evaluator
        evaluator = CHECKS[check_name]["evaluate"]
        status, message = evaluator(result["rows"], result["columns"])
        result["status"] = status
        result["message"] = message

    except FileNotFoundError as e:
        result["status"] = "critical"
        result["message"] = str(e)
    except pg_common.PgError as e:
        if _is_missing_pg_stat_statements_error(check_name, e):
            result["status"] = "warning"
            result["message"] = (
                "pg_stat_statements not enabled; outliers check unavailable on this instance"
            )
        else:
            result["status"] = "critical"
            result["message"] = f"Query error: {e}"
    finally:
        # Roll back the transaction after every check so one failure (e.g.
        # missing pg_stat_statements on a non-Snowflake PG) doesn't cascade
        # into "current transaction is aborted" errors on later checks.
        # All checks are read-only so rollback is semantically a no-op on
        # success and the correct recovery path on failure.
        try:
            conn.rollback()
        except pg_common.PgError:
            pass

    return result


def run_checks(conn, check_names: list[str]) -> list[dict]:
    """Run a list of diagnostic checks and return results."""
    return [run_check(conn, name) for name in check_names]


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def format_summary(results: list[dict]) -> str:
    """Format results as a compact summary table."""
    rows = []
    for r in results:
        rows.append([
            status_icon(r["status"]),
            r["name"],
            r["message"],
        ])
    return tabulate(rows, headers=["Status", "Check", "Summary"], tablefmt="simple")


def format_detailed(results: list[dict]) -> str:
    """Format results with full query output per check."""
    output = []
    for r in results:
        output.append(f"\n{status_icon(r['status'])} {r['name'].upper()}")
        output.append("-" * 40)
        output.append(f"Status: {r['status']}")
        output.append(f"Summary: {r['message']}")

        if r["rows"]:
            output.append("")
            table = tabulate(r["rows"], headers=r["columns"], tablefmt="simple")
            output.append(table)
    return "\n".join(output)


def format_json(results: list[dict], success: bool = True) -> str:
    """Format results as JSON matching cortex tool output conventions."""
    return json.dumps({"success": success, "results": results}, indent=2, default=str)


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def connect_readonly(params: dict, statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS):
    """
    Open a connection in readonly mode with a statement timeout.

    Uses Postgres session options to enforce read-only at the database level
    and prevent diagnostic queries from hanging.
    """
    options = (
        f"-c default_transaction_read_only=on "
        f"-c statement_timeout={statement_timeout_ms}"
    )

    return pg_common.connect(
        host=params["host"],
        port=params["port"],
        dbname=params["database"],
        user=params["user"],
        password=params.get("password"),
        sslmode=params.get("sslmode", "require"),
        sslrootcert=params.get("sslrootcert"),
        connect_timeout=10,
        options=options,
    )


def categorize_connection_error(error) -> str:
    """Return a user-friendly error message based on the connection failure."""
    error_str = str(error).lower()
    if "connection refused" in error_str or "could not connect" in error_str:
        return (
            "Connection refused.\n\n"
            "Possible causes:\n"
            "  - Your IP is not in the network policy allow list\n"
            "  - The instance may be suspended\n"
            "  - Firewall blocking port 5432\n\n"
            "Try: 'What's my IP?' then 'Add my IP to the network policy'"
        )
    elif "timeout" in error_str:
        return "Connection timed out. The instance may be starting up or unreachable."
    elif "authentication failed" in error_str or "password" in error_str:
        return "Authentication failed. Password may be incorrect or expired."
    elif "ssl" in error_str or "certificate" in error_str or "sslrootcert" in error_str:
        return (
            "SSL certificate error.\n\n"
            "Snowflake Postgres uses self-signed certificates.\n"
            "If cert verification is enabled (sslmode=verify-ca), ensure the\n"
            "CA cert has been fetched and sslrootcert is set in the service entry.\n\n"
            "As a workaround, sslmode=require encrypts without verifying."
        )
    else:
        return f"Connection failed: {error}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    pg_common.configure_stdio_utf8()
    pg_common.check_driver()
    parser = argparse.ArgumentParser(
        description="Run Postgres health diagnostics",
        epilog="All queries run in readonly mode with statement_timeout.",
    )
    parser.add_argument("--connection", "-c", help="Connection string (postgres://...)")
    parser.add_argument("--connection-name", "-n", help="Name of saved connection")
    parser.add_argument("--check", help="Run a specific check by name")
    parser.add_argument(
        "--category",
        default="health",
        help="Run all checks in a category (default: health)",
    )
    parser.add_argument("--all", action="store_true", help="Run every registered check")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--detailed", "-d", action="store_true", help="Show detailed output")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_STATEMENT_TIMEOUT_MS,
        help=f"Statement timeout in ms (default: {DEFAULT_STATEMENT_TIMEOUT_MS})",
    )
    parser.add_argument("--list-checks", action="store_true", help="List available checks")

    args = parser.parse_args()

    # List checks mode — no connection needed
    if args.list_checks:
        for name, info in CHECKS.items():
            print(f"  {name:20s} [{info['category']}] {info['description']}")
        return

    try:
        # Resolve connection parameters
        try:
            params = get_connect_params(args.connection, args.connection_name)
        except ValueError as e:
            available = list_connections()
            if args.json:
                print(json.dumps({"success": False, "error": str(e)}))
            else:
                print(f"Error: {e}")
                if available:
                    print(f"\nAvailable connections: {', '.join(available)}")
                else:
                    print("\nNo saved connections found.")
            sys.exit(1)

        # Connect in readonly mode with statement timeout
        try:
            conn = connect_readonly(params, args.timeout)
        except pg_common.PgOperationalError as e:
            error_msg = categorize_connection_error(e)
            if args.json:
                print(json.dumps({"success": False, "error": error_msg}))
            else:
                print(f"Error: {error_msg}")
            sys.exit(1)

        try:
            # Determine which checks to run
            if args.check:
                check_names = [args.check]
            elif args.all:
                check_names = get_all_checks()
            else:
                check_names = get_checks_for_category(args.category)

            if not check_names:
                if args.json:
                    print(format_json([], success=True))
                else:
                    print(f"No checks found for category '{args.category}'")
                return

            results = run_checks(conn, check_names)

            # Output
            if args.json:
                print(format_json(results))
            elif args.detailed:
                print(format_detailed(results))
            else:
                print(format_summary(results))

            # Non-zero exit if any critical issues found
            has_critical = any(r["status"] == "critical" for r in results)
            sys.exit(1 if has_critical else 0)

        finally:
            conn.close()

    except Exception as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}, default=str))
        else:
            print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
