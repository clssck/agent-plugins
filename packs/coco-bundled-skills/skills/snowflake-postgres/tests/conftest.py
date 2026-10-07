"""
Shared fixtures + --live gate for pg-to-spg-migration tests.

Mirrors the pattern used in our snowflake-postgres skill: @pytest.mark.live
tests are skipped unless --live is passed. Mocked-cursor fixtures are
provided for unit tests that simulate DB behavior without a real PG.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run live tests against a real Postgres pair.",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip_live = pytest.mark.skip(reason="live tests disabled; pass --live to enable")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture
def mock_cursor():
    """A mocked psycopg2-style cursor. Configure .fetchone/.fetchall per-test."""
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    cursor.fetchall.return_value = []
    cursor.description = None
    cursor.rowcount = 0
    return cursor


@pytest.fixture
def mock_conn(mock_cursor):
    """A mocked psycopg2-style connection whose cursor() yields mock_cursor.

    Supports both ``conn.cursor()`` direct-call and ``with conn.cursor() as cur:``
    context-manager patterns. ``mock_cursor`` itself is returned in both cases.
    """
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = mock_cursor
    return conn
