"""Driver-agnostic Snowflake SQL session.

Prefers the in-process Python connector (`snowflake.connector`); falls back
to the `snow` CLI (`snow sql --format json`) when the connector isn't
installed. The CLI fallback covers Windows ARM64, where
`snowflake-connector-python` has no pre-built wheel — see
`references/windows.md`.

Both backends read auth from the same `~/.snowflake/connections.toml`, so
the saved-connection name is the uniform identity across them.

Usage:

    from sf_session import SnowflakeSession

    with SnowflakeSession(connection="prod", role="ACCOUNTADMIN") as sf:
        rows = sf.execute("DESCRIBE POSTGRES INSTANCE myinst")
        # rows is list[dict] with lowercased column names on both backends.

Result-shape contract:

    Every .execute() returns list[dict[str, Any]]. Column names are
    lowercased so callers don't branch on backend. Numeric / timestamp /
    JSON column types are returned as whatever the underlying backend
    produced; on the CLI path that's whatever json.loads decoded
    (strings for most types — Snowflake's JSON output is conservative).
    Callers that need typed values should cast at the call site.

Backend selection at .execute() time is decided once in __init__.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Any


CONNECTOR = "connector"
CLI = "cli"


class SnowflakeError(RuntimeError):
    """Raised when a Snowflake SQL statement fails (either backend).

    The connector raises ProgrammingError / DatabaseError subclasses with
    rich attributes (sqlstate, sfqid); the CLI surfaces only stderr text.
    We normalise to a single exception type with the failing SQL and the
    backend that produced the error attached for downstream handling.
    """

    def __init__(self, message: str, *, sql: str = "", backend: str = ""):
        super().__init__(message)
        self.sql = sql
        self.backend = backend


def detect_snowflake_backend() -> str | None:
    """Return 'connector', 'cli', or None.

    Connector is preferred: in-process, no per-statement subprocess overhead,
    supports env-var auth flows (SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER / ...).
    The CLI fallback only fires when the connector is unimportable.
    """
    try:
        import snowflake.connector  # noqa: F401
        return CONNECTOR
    except ImportError:
        pass
    if shutil.which("snow") is not None:
        return CLI
    return None


def require_snowflake_backend() -> str:
    """detect_snowflake_backend() but exits with an actionable error.

    Use at entry points that need to run SQL against Snowflake. The error
    points the user at both install options so they can pick the path that
    fits their platform; on WoA the connector path will keep failing until
    Snowflake publishes a `win_arm64` wheel, so the CLI is the answer.
    """
    backend = detect_snowflake_backend()
    if backend:
        return backend

    print("ERROR: no Snowflake backend available.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Install ONE of:", file=sys.stderr)
    print("  - snowflake-connector-python  (preferred — in-process, fast)", file=sys.stderr)
    print("      pip install snowflake-connector-python", file=sys.stderr)
    print("      (no wheel on Windows ARM64 — use the CLI fallback instead)", file=sys.stderr)
    print("  - snow CLI  (CLI fallback; required on Windows ARM64)", file=sys.stderr)
    print("      winget install Snowflake.SnowflakeCLI    (Windows)", file=sys.stderr)
    print("      brew install snowflake-cli              (macOS)", file=sys.stderr)
    print("      pip install snowflake-cli               (anywhere)", file=sys.stderr)
    sys.exit(1)


class SnowflakeSession:
    """Driver-agnostic Snowflake SQL session, used as a context manager.

    The connector backend opens one TCP connection at __enter__ and reuses it
    across .execute() calls — important for polling loops where the alternative
    is re-authenticating every iteration. The CLI backend shells out per
    .execute(); each invocation pays auth cost but otherwise behaves
    identically from the caller's perspective.

    Args:
        connection: Saved connection name from ~/.snowflake/connections.toml.
            Used by both backends. Required for the CLI backend; the connector
            backend can also pick up env-var auth (SNOWFLAKE_ACCOUNT,
            SNOWFLAKE_USER, ...) when this is omitted.
        role: Session role override. Applied via `--role <name>` on the CLI
            backend and via the connector's `role=` connect arg on the
            in-process backend.
        authenticator: Authenticator override; connector path only. The CLI
            inherits whatever the connections.toml entry specifies.
    """

    def __init__(
        self,
        connection: str | None = None,
        role: str | None = None,
        authenticator: str | None = None,
    ):
        self._connection = connection
        self._role = role
        self._authenticator = authenticator
        self._backend = require_snowflake_backend()
        self._conn: Any = None

    @property
    def backend(self) -> str:
        return self._backend

    def __enter__(self) -> "SnowflakeSession":
        if self._backend == CONNECTOR:
            self._conn = self._open_connector_conn()
        elif self._backend == CLI:
            if not self._connection and not os.environ.get("SNOWFLAKE_DEFAULT_CONNECTION_NAME"):
                # snow sql needs a connection identity. Env-var auth works for
                # the connector but `snow` reads from connections.toml; an
                # unnamed CLI invocation falls back to the "default" entry
                # which may not exist on this machine.
                print(
                    "WARNING: SnowflakeSession on CLI backend with no connection name. "
                    "`snow sql` will use the default connection from "
                    "~/.snowflake/connections.toml, which may not be set.",
                    file=sys.stderr,
                )
        return self

    def execute(self, sql: str) -> list[dict[str, Any]]:
        """Run a single SQL statement; return rows as list[dict].

        Empty result sets (DDL, statements without a result rowset) return [].
        """
        if self._backend == CONNECTOR:
            return self._execute_connector(sql)
        return self._execute_cli(sql)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None
        return False

    def _open_connector_conn(self) -> Any:
        """Open a connector connection. Imported here so the module is
        importable on hosts that have the CLI but no connector."""
        # Lazy import so module load succeeds when the connector is absent
        # (this is the whole point of the CLI fallback).
        from pg_connect import get_snowflake_connection  # type: ignore[import-not-found]

        return get_snowflake_connection(
            connection_name=self._connection,
            authenticator=self._authenticator,
            role=self._role,
        )

    def _execute_connector(self, sql: str) -> list[dict[str, Any]]:
        if self._conn is None:
            raise SnowflakeError(
                "SnowflakeSession not opened — use as a context manager",
                sql=sql,
                backend=CONNECTOR,
            )
        with self._conn.cursor() as cur:
            cur.execute(sql)
            if cur.description is None:
                return []
            cols = [c[0].lower() for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def _execute_cli(self, sql: str) -> list[dict[str, Any]]:
        cmd = ["snow", "sql", "--format", "json", "-q", sql]
        if self._connection:
            cmd.extend(["--connection", self._connection])
        if self._role:
            cmd.extend(["--role", self._role])

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            stderr_tail = (proc.stderr or "").strip().splitlines()[-5:]
            raise SnowflakeError(
                "snow sql failed (exit {code}): {tail}".format(
                    code=proc.returncode,
                    tail=" / ".join(stderr_tail) or (proc.stdout or "").strip(),
                ),
                sql=sql,
                backend=CLI,
            )

        out = (proc.stdout or "").strip()
        if not out:
            return []
        return _parse_snow_json(out)


class _SessionCursorAdapter:
    """DB-API cursor shim backed by `SnowflakeSession.execute()`.

    Exists so legacy call sites that do `with conn.cursor() as cur:
    cur.execute(sql); rows = cur.fetchall()` keep working even when the
    underlying backend is the `snow` CLI (no real connector cursor). For
    new code, call `session.execute(sql)` directly — it returns list[dict]
    and skips the tuple/description reshaping below.

    DB-API compatibility:
      - `execute(sql)` runs the query and buffers the entire result set
        (the CLI backend has no streaming; rows arrive as one JSON blob)
      - `fetchone()` pops and returns the next row, or None when drained
      - `fetchall()` returns all remaining rows and drains the buffer
      - iteration (`for row in cur:`) is equivalent to repeated fetchone
      - `description` mimics the DB-API shape `[(name, type, ...)]` with
        only `name` populated; persists across fetch* calls (set by
        execute, not cleared by drain) so it remains valid after the
        rowset is consumed
    """

    def __init__(self, session: "SnowflakeSession"):
        self._session = session
        self._rows: list[dict[str, Any]] = []
        # Column order is locked at execute() time and persists after
        # fetch* drain the buffer — matches connector cursor semantics
        # where `description` survives once results are fully consumed.
        self._columns: list[str] = []
        self._executed: bool = False

    def __enter__(self) -> "_SessionCursorAdapter":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False

    def execute(self, sql: str) -> None:
        self._rows = self._session.execute(sql)
        self._executed = True
        self._columns = list(self._rows[0].keys()) if self._rows else []

    def fetchone(self) -> tuple[Any, ...] | None:
        if not self._rows:
            return None
        row = self._rows.pop(0)
        return tuple(row.get(c) for c in self._columns)

    def fetchall(self) -> list[tuple[Any, ...]]:
        if not self._columns:
            return []
        out = [tuple(r.get(c) for c in self._columns) for r in self._rows]
        self._rows = []
        return out

    def __iter__(self):
        """Iterate rows as tuples, consuming the buffer one row at a
        time. Mirrors `for row in cursor:` on the real connector cursor."""
        while True:
            row = self.fetchone()
            if row is None:
                return
            yield row

    @property
    def description(self):
        if not self._executed or not self._columns:
            return None
        # DB-API 7-tuple; only `name` is meaningful here.
        return [
            (col, None, None, None, None, None, None)
            for col in self._columns
        ]

    def close(self) -> None:
        self._rows = []
        self._columns = []


class _SessionConnAdapter:
    """`snowflake.connector.SnowflakeConnection`-compatible shim around a
    `SnowflakeSession`. Use `open_snowflake_connection()` instead of
    constructing this directly — the helper handles entering the
    underlying context manager.

    Limitations of the shim (intentional, documented so callers don't
    expect more):
      - `cursor()` returns a fresh `_SessionCursorAdapter` each call but
        they all share the same underlying SnowflakeSession. Cursors are
        therefore independent only in terms of buffered rows.
      - No transaction control (`commit`, `rollback`, `autocommit`).
        Snowflake auto-commits each statement; the CLI fallback can't
        express multi-statement transactions across `snow sql`
        invocations anyway, and the connector branch doesn't use them
        in this skill.
      - No `cursor.executemany`, `cursor.rowcount`, or async paths.
    """

    def __init__(self, session: "SnowflakeSession"):
        self._session = session

    def cursor(self) -> _SessionCursorAdapter:
        return _SessionCursorAdapter(self._session)

    def close(self) -> None:
        self._session.__exit__(None, None, None)


def open_snowflake_connection(
    connection: str | None = None,
    role: str | None = None,
    authenticator: str | None = None,
) -> Any:
    """Return a connection-like object that works on both backends.

    On the connector backend this enters the SnowflakeSession context and
    returns the underlying `snowflake.connector.SnowflakeConnection` so
    callers get full connector functionality (transactions, executemany,
    etc.) for free.

    On the CLI backend it returns a `_SessionConnAdapter` that quacks like
    a connector connection for the narrow surface this skill uses
    (`.cursor()`, `.cursor().execute()`, `.cursor().fetchall()`,
    `.cursor().description`, `.close()`). Patterns beyond that surface
    fall back to opening a `SnowflakeSession` directly and using
    `session.execute()`.

    Caller is responsible for calling `.close()` (or using try/finally).
    """
    session = SnowflakeSession(
        connection=connection,
        role=role,
        authenticator=authenticator,
    )
    session.__enter__()
    if session.backend == CONNECTOR and session._conn is not None:
        # Take ownership of the underlying connector connection. The
        # SnowflakeSession wrapper is no longer needed — the connector
        # connection has the same lifecycle and richer API.
        conn = session._conn
        session._conn = None  # prevent SnowflakeSession.__exit__ from closing it
        return conn
    return _SessionConnAdapter(session)


def _parse_snow_json(stdout: str) -> list[dict[str, Any]]:
    """Parse `snow sql --format json` stdout into list[dict].

    `snow sql` returns:
      - JSON array of objects when there are result rows: [{"COL": val, ...}]
      - JSON array containing a status row for DDL/no-rowset statements
      - Empty string when there's nothing to print
    The shape is permissive across `snow` versions; we degrade gracefully
    rather than parse-bomb on a future format tweak.
    """
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        # Some `snow` builds emit a banner before the JSON. Find the first
        # '[' or '{' and try again from there.
        for idx, ch in enumerate(stdout):
            if ch in "[{":
                try:
                    data = json.loads(stdout[idx:])
                    break
                except json.JSONDecodeError:
                    continue
        else:
            return []

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []

    out: list[dict[str, Any]] = []
    for row in data:
        if isinstance(row, dict):
            out.append({k.lower(): v for k, v in row.items()})
    return out
