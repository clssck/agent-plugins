"""
Live integration-test fixtures + --live gate.

Live tests run actual SQL against a Snowflake account paired with a
pg_lake-enabled Postgres instance. They're skipped by default to keep
`pytest snowflake-postgres/tests/` fast and network-free. Enable with:

    pytest --live snowflake-postgres/tests/integration/

Defaults are obvious placeholders; override via env vars to point at your
own connections + instance + iceberg table:
    PG_LAKE_LIVE_SF_CONNECTION  — Snowflake connection name in
                                  ~/.snowflake/connections.toml
    PG_LAKE_LIVE_PG_CONNECTION  — Postgres connection name in pg_service.conf
    PG_LAKE_LIVE_PG_INSTANCE    — Postgres instance name on Snowflake
    PG_LAKE_LIVE_PG_CATALOG     — PG database / catalog (default: postgres)
    PG_LAKE_LIVE_PG_NAMESPACE   — PG schema (default: public)
    PG_LAKE_LIVE_PG_TABLE       — PG iceberg table name to query

If the env vars aren't set, the placeholder defaults are intentionally
non-existent so the connection step fails fast with a clear message rather
than silently running against the wrong account.
"""
from __future__ import annotations

import os

import pytest


# --live gate + skip logic lives in the parent tests/conftest.py so it
# covers both unit tests (test_migrate_*) and integration tests uniformly.


@pytest.fixture(scope="session")
def live_sf_connection() -> str:
    return os.environ.get("PG_LAKE_LIVE_SF_CONNECTION", "my_sf_connection")


@pytest.fixture(scope="session")
def live_pg_connection() -> str:
    return os.environ.get("PG_LAKE_LIVE_PG_CONNECTION", "my_pg_connection")


@pytest.fixture(scope="session")
def live_pg_instance() -> str:
    return os.environ.get("PG_LAKE_LIVE_PG_INSTANCE", "MY_PG_INSTANCE")


@pytest.fixture(scope="session")
def live_pg_catalog() -> str:
    return os.environ.get("PG_LAKE_LIVE_PG_CATALOG", "postgres")


@pytest.fixture(scope="session")
def live_pg_namespace() -> str:
    return os.environ.get("PG_LAKE_LIVE_PG_NAMESPACE", "public")


@pytest.fixture(scope="session")
def live_pg_table() -> str:
    return os.environ.get("PG_LAKE_LIVE_PG_TABLE", "my_iceberg_table")
