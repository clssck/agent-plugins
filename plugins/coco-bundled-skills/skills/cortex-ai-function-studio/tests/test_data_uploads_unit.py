# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for the connector-based PUT/REFRESH behavior in
``generate_sec_filing_data.upload_pdfs``.

These tests pin down the recent migration from ``snow sql -q "PUT ..."``
subprocess calls to direct ``cursor.execute(...)`` calls on a Snowflake
connector connection. They run fully offline using ``unittest.mock`` --
no Snowflake connection required.

Run:
    uv run --group test pytest tests/test_data_uploads_unit.py -v
"""  # noqa: D205

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from data_generators.generate_sec_filing_data import upload_pdfs

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conn():
    """Build a fake SnowflakeConnection whose ``cursor()`` returns a single
    shared MagicMock cursor (so callers can inspect every executed SQL).
    """  # noqa: D205
    cur = MagicMock(name="cursor")
    conn = MagicMock(name="connection")
    conn.cursor.return_value = cur
    return conn, cur


def _executed_sql(cur) -> list[str]:
    """Flatten all positional SQL strings passed to ``cur.execute``."""
    out = []
    for call in cur.execute.call_args_list:
        args, _ = call
        if args:
            out.append(args[0])
    return out


# ===========================================================================
# generate_sec_filing_data.upload_pdfs
# ===========================================================================


class TestUploadPdfsSec:
    """Covers the ``upload_pdfs`` change: signature dropped
    ``connection_name`` in favor of taking a live connection, and the body
    switched from ``snow sql`` subprocess calls to ``cursor.execute``.
    """  # noqa: D205

    def _entries(self, paths: list[str]) -> list[dict]:
        return [{"pdf_name": Path(p).name, "pdf_path": p} for p in paths]

    # ---- happy path -------------------------------------------------------

    def test_one_put_per_entry_then_refresh(self):
        entries = self._entries(["/tmp/a.pdf", "/tmp/b.pdf", "/tmp/c.pdf"])
        conn, cur = _make_conn()

        upload_pdfs(conn, "DB.SCHEMA.STAGE", entries)

        sqls = _executed_sql(cur)
        put_sqls = [s for s in sqls if s.startswith("PUT ")]
        assert len(put_sqls) == len(entries)

        for entry, sql in zip(entries, put_sqls, strict=True):
            # File path must be quoted with single quotes (paths can contain
            # spaces / special chars in real datasets).
            assert f"PUT 'file://{entry['pdf_path']}' @DB.SCHEMA.STAGE/" in sql
            assert "AUTO_COMPRESS=FALSE" in sql
            assert "OVERWRITE=TRUE" in sql

        assert sqls[-1] == "ALTER STAGE DB.SCHEMA.STAGE REFRESH"

    def test_empty_entries_still_refreshes(self):
        conn, cur = _make_conn()

        upload_pdfs(conn, "DB.S.STG", [])

        assert _executed_sql(cur) == ["ALTER STAGE DB.S.STG REFRESH"]

    def test_reuses_single_cursor(self):
        entries = self._entries(["/tmp/a.pdf", "/tmp/b.pdf"])
        conn, _ = _make_conn()

        upload_pdfs(conn, "DB.S.STG", entries)

        assert conn.cursor.call_count == 1

    def test_does_not_shell_out(self, monkeypatch):
        entries = self._entries(["/tmp/a.pdf"])
        conn, _ = _make_conn()

        run_spy = MagicMock(name="subprocess.run")
        popen_spy = MagicMock(name="subprocess.Popen")
        monkeypatch.setattr(subprocess, "run", run_spy)
        monkeypatch.setattr(subprocess, "Popen", popen_spy)

        upload_pdfs(conn, "DB.S.STG", entries)

        run_spy.assert_not_called()
        popen_spy.assert_not_called()

    def test_no_legacy_snow_sql_strings(self):
        entries = self._entries(["/tmp/a.pdf", "/tmp/b.pdf"])
        conn, cur = _make_conn()

        upload_pdfs(conn, "DB.S.STG", entries)

        for sql in _executed_sql(cur):
            assert "snow sql" not in sql
            assert "--connection" not in sql
            assert not sql.rstrip().endswith(";"), f"unexpected ';': {sql!r}"

    def test_handles_paths_with_spaces(self):
        entries = self._entries(["/tmp/path with spaces/file.pdf"])
        conn, cur = _make_conn()

        upload_pdfs(conn, "DB.S.STG", entries)

        put_sqls = [s for s in _executed_sql(cur) if s.startswith("PUT ")]
        assert len(put_sqls) == 1
        # Single-quoting must wrap the full file:// path.
        assert "PUT 'file:///tmp/path with spaces/file.pdf' @DB.S.STG/" in put_sqls[0]

    # ---- signature compatibility -----------------------------------------

    def test_signature_takes_connection_not_name(self):
        """The first positional arg must now be a *connection*, not a
        connection name string. This is the backwards-incompatible part of
        the change.
        """  # noqa: D205
        import inspect

        sig = inspect.signature(upload_pdfs)
        params = list(sig.parameters)
        assert params[0] == "conn"
        # Old name should be gone.
        assert "connection_name" not in sig.parameters

    def test_old_calling_convention_breaks_loudly(self):
        """Calling with a string (the old ``connection_name`` API) should
        fail fast on ``conn.cursor()`` rather than silently no-op.
        """  # noqa: D205
        with pytest.raises(AttributeError):
            upload_pdfs(
                "snowhouse",
                "DB.S.STG",
                [{"pdf_path": "/tmp/x.pdf", "pdf_name": "x.pdf"}],
            )
