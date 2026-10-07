"""
Live end-to-end integration test for the READ-FROM-SNOWFLAKE workflow.

Exercises both code paths against a real Snowflake account paired with a
pg_lake-enabled Postgres instance:

    Per-table path:
        check-account-params → list-pg-iceberg → create-integration →
        describe-integration → create-iceberg-table →
        SELECT count(*) via snowflake-connector → drop-integration

    CLD path:
        create-integration → create-cld → poll cld-status until healthy +
        iceberg table surfaces → SELECT via CLD-qualified name →
        drop CLD → drop-integration

Every resource created during the test is cleaned up in a try/finally so a
partial failure doesn't leave orphan catalog integrations, iceberg tables,
or linked databases on the test account.

Run with:
    pytest --live snowflake-postgres/tests/integration/test_catalog_integration_live.py -v
"""
from __future__ import annotations

import json
import time
import uuid

import pytest

from pg_lake_catalog import (
    get_snowflake_connection,
    main,
)


pytestmark = pytest.mark.live


# CLD propagation typically completes within one REFRESH_INTERVAL_SECONDS
# cycle (default 30s). Budget 90s to tolerate scheduler jitter without flakes;
# poll every 5s so a healthy CLD is confirmed quickly and a stuck one fails fast.
_CLD_PROPAGATION_BUDGET_SECONDS = 90
_CLD_POLL_INTERVAL_SECONDS = 5


@pytest.fixture
def unique_integration_name() -> str:
    # Short suffix keeps Snowflake identifier under the 255-char cap and
    # stays readable in any orphan-cleanup inspection.
    return f"per_table_live_{uuid.uuid4().hex[:10]}"


@pytest.fixture
def unique_iceberg_table_name() -> str:
    return f"per_table_live_ib_{uuid.uuid4().hex[:10]}"


@pytest.fixture
def unique_cld_name() -> str:
    return f"cld_live_{uuid.uuid4().hex[:10]}"


def _run(capsys, argv: list[str]) -> dict:
    """Run main(argv) and return the parsed JSON payload."""
    main(argv)
    out = capsys.readouterr().out
    return json.loads(out)


class TestReadFromSnowflakeE2E:
    """
    The canonical per-table happy path. If this passes against a live SF +
    pg_lake pair, the skill can drive a cold user from "I have pg_lake iceberg
    tables" to "I can query them from Snowflake" without a single line of raw SQL.
    """

    def test_end_to_end_per_table_path(
        self,
        capsys,
        live_sf_connection: str,
        live_pg_connection: str,
        live_pg_instance: str,
        live_pg_catalog: str,
        live_pg_namespace: str,
        live_pg_table: str,
        unique_integration_name: str,
        unique_iceberg_table_name: str,
    ):
        pre = _run(capsys, [
            "check-account-params",
            "--snowflake-connection", live_sf_connection,
            "--json",
        ])
        assert pre["ok"] is True, (
            f"Account {live_sf_connection} isn't ready: {pre.get('cautions')}"
        )
        assert live_pg_instance in pre.get("instances_visible", []), (
            f"{live_pg_instance} not visible to current role. "
            f"instance_visibility_note: {pre.get('instance_visibility_note')}"
        )

        pg_list = _run(capsys, [
            "list-pg-iceberg",
            "--connection-name", live_pg_connection,
            "--json",
        ])
        assert pg_list["success"] is True
        matching = [
            t for t in pg_list["tables"]
            if t["catalog_name"] == live_pg_catalog
            and t["namespace"] == live_pg_namespace
            and t["table_name"] == live_pg_table
        ]
        assert matching, (
            f"PG fixture table {live_pg_catalog}.{live_pg_namespace}."
            f"{live_pg_table} not found. Got: {pg_list['tables']}"
        )

        created_integration = False
        created_iceberg = False
        try:
            ci = _run(capsys, [
                "create-integration",
                "--name", unique_integration_name,
                "--postgres-instance", live_pg_instance,
                "--database", live_pg_catalog,
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            assert ci["success"] is True, ci
            created_integration = True

            described = _run(capsys, [
                "describe-integration",
                "--name", unique_integration_name,
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            assert described["success"] is True
            assert described["properties"]["ENABLED"]["value"] == "true"
            rest_config = described["properties"]["REST_CONFIG"]["value"]
            assert live_pg_instance in rest_config
            assert live_pg_catalog in rest_config

            it = _run(capsys, [
                "create-iceberg-table",
                "--name", unique_iceberg_table_name,
                "--catalog", unique_integration_name,
                "--catalog-table-name", live_pg_table,
                "--catalog-namespace", live_pg_namespace,
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            assert it["success"] is True, it
            created_iceberg = True

            # End-to-end check via the Snowflake connector. We don't add a
            # dedicated subcommand for SELECT — the agent / user queries
            # directly once the iceberg table is in place.
            conn = get_snowflake_connection(live_sf_connection)
            try:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT COUNT(*) FROM {unique_iceberg_table_name}")
                    row_count = cur.fetchone()[0]
                    cur.execute(
                        f"SELECT * FROM {unique_iceberg_table_name} "
                        "ORDER BY 1 LIMIT 10"
                    )
                    sample = cur.fetchall()
            finally:
                conn.close()

            assert row_count >= 1, (
                f"Expected ≥ 1 row from {live_pg_table}, got {row_count}. "
                "Was the test-fixture data removed from the PG instance?"
            )
            assert len(sample) <= 10
        finally:
            if created_iceberg:
                conn = get_snowflake_connection(live_sf_connection)
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            f"DROP ICEBERG TABLE IF EXISTS {unique_iceberg_table_name}"
                        )
                finally:
                    conn.close()
            if created_integration:
                _run(capsys, [
                    "drop-integration",
                    "--name", unique_integration_name,
                    "--confirm",
                    "--snowflake-connection", live_sf_connection,
                    "--json",
                ])

    def test_already_exists_soft_fail_is_idempotent(
        self,
        capsys,
        live_sf_connection: str,
        live_pg_instance: str,
        live_pg_catalog: str,
        unique_integration_name: str,
    ):
        """
        Second `create-integration` on an existing name returns
        already_exists=True instead of raising — the agent can retry
        safely. Verified live rather than mock-only because Snowflake's
        exact ProgrammingError message is what we pattern-match on.
        """
        created = False
        try:
            first = _run(capsys, [
                "create-integration",
                "--name", unique_integration_name,
                "--postgres-instance", live_pg_instance,
                "--database", live_pg_catalog,
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            assert first["success"] is True
            created = True

            second = _run(capsys, [
                "create-integration",
                "--name", unique_integration_name,
                "--postgres-instance", live_pg_instance,
                "--database", live_pg_catalog,
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            assert second["success"] is False
            assert second.get("already_exists") is True
            assert "describe-integration" in second["hint"]
            assert "drop-integration" in second["hint"]
        finally:
            if created:
                _run(capsys, [
                    "drop-integration",
                    "--name", unique_integration_name,
                    "--confirm",
                    "--snowflake-connection", live_sf_connection,
                    "--json",
                ])

    def test_drop_without_confirm_is_a_no_op(
        self,
        capsys,
        live_sf_connection: str,
        live_pg_instance: str,
        live_pg_catalog: str,
        unique_integration_name: str,
    ):
        """
        `drop-integration` without `--confirm` must not execute any SQL.
        Verified live: create integration, dry-run drop, verify it still
        exists via describe-integration, real drop with --confirm.
        """
        _run(capsys, [
            "create-integration",
            "--name", unique_integration_name,
            "--postgres-instance", live_pg_instance,
            "--database", live_pg_catalog,
            "--snowflake-connection", live_sf_connection,
            "--json",
        ])
        try:
            dry = _run(capsys, [
                "drop-integration",
                "--name", unique_integration_name,
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            assert dry["success"] is False
            assert dry["confirmed"] is False
            assert "DROP CATALOG INTEGRATION" in dry["would_execute"]

            still_there = _run(capsys, [
                "describe-integration",
                "--name", unique_integration_name,
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            assert still_there["success"] is True, (
                "Dry-run drop should leave the integration intact."
            )
        finally:
            _run(capsys, [
                "drop-integration",
                "--name", unique_integration_name,
                "--confirm",
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])


class TestReadFromSnowflakeCldE2E:
    """
    Catalog-Linked Database path. One DDL (`create-cld`) exposes every
    iceberg table on the PG side via the integration; `cld-status` polls
    until the propagation window closes and the tables surface.
    """

    def test_cld_happy_path(
        self,
        capsys,
        live_sf_connection: str,
        live_pg_instance: str,
        live_pg_catalog: str,
        live_pg_namespace: str,
        live_pg_table: str,
        unique_integration_name: str,
        unique_cld_name: str,
    ):
        created_integration = False
        created_cld = False
        try:
            ci = _run(capsys, [
                "create-integration",
                "--name", unique_integration_name,
                "--postgres-instance", live_pg_instance,
                "--database", live_pg_catalog,
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            assert ci["success"] is True, ci
            created_integration = True

            cld = _run(capsys, [
                "create-cld",
                "--name", unique_cld_name,
                "--catalog", unique_integration_name,
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            assert cld["success"] is True, cld
            # create-cld always emits ALLOWED_WRITE_OPERATIONS = NONE —
            # verify the server accepted our DDL and didn't silently
            # rewrite it to a different value.
            assert cld["allowed_write_operations"] == "NONE"
            created_cld = True

            # Poll cld-status until the iceberg table surfaces OR the budget
            # is exhausted. Propagation typically completes within one
            # REFRESH_INTERVAL_SECONDS cycle (default 30s); 90s gives
            # comfortable headroom without flakes.
            deadline = time.monotonic() + _CLD_PROPAGATION_BUDGET_SECONDS
            status = None
            visible_tables: list[str] = []
            while time.monotonic() < deadline:
                status = _run(capsys, [
                    "cld-status",
                    "--name", unique_cld_name,
                    "--snowflake-connection", live_sf_connection,
                    "--json",
                ])
                assert status["execution_state"] in {"RUNNING", "INITIALIZING"}, status
                visible_tables = [t["name"] for t in status["iceberg_tables"]]
                if any(t.lower() == live_pg_table.lower() for t in visible_tables):
                    break
                time.sleep(_CLD_POLL_INTERVAL_SECONDS)
            else:
                pytest.fail(
                    f"CLD {unique_cld_name} never exposed {live_pg_table} "
                    f"within {_CLD_PROPAGATION_BUDGET_SECONDS}s. "
                    f"Last status: {status}"
                )

            assert status is not None
            assert status["healthy"] is True
            assert status["execution_state"] == "RUNNING"

            # Cross-DB qualified SELECT — the CLD is a real database from
            # the SF side, not a rebranded integration.
            conn = get_snowflake_connection(live_sf_connection)
            try:
                qualified = (
                    f"{unique_cld_name}.{live_pg_namespace}.{live_pg_table}"
                )
                with conn.cursor() as cur:
                    cur.execute(f"SELECT COUNT(*) FROM {qualified}")
                    row_count = cur.fetchone()[0]
            finally:
                conn.close()

            assert row_count >= 1, (
                f"Expected ≥ 1 row from CLD-backed {qualified}, got {row_count}. "
                "Was the test-fixture data removed from the PG instance?"
            )
        finally:
            # Cleanup order: DROP DATABASE first (removes the LINKED_CATALOG
            # dependency), then drop-integration. Without this order the
            # integration drop would fail because the CLD still references it.
            if created_cld:
                conn = get_snowflake_connection(live_sf_connection)
                try:
                    with conn.cursor() as cur:
                        cur.execute(f"DROP DATABASE IF EXISTS {unique_cld_name}")
                finally:
                    conn.close()
            if created_integration:
                _run(capsys, [
                    "drop-integration",
                    "--name", unique_integration_name,
                    "--confirm",
                    "--snowflake-connection", live_sf_connection,
                    "--json",
                ])

    def test_refresh_flow(
        self,
        capsys,
        live_sf_connection: str,
        live_pg_instance: str,
        live_pg_catalog: str,
        live_pg_namespace: str,
        live_pg_table: str,
        unique_integration_name: str,
        unique_iceberg_table_name: str,
    ):
        """
        Refresh / auto-refresh / interval round-trip:
          - Create integration + one iceberg table
          - `set-refresh-interval 60` (verify via describe-integration)
          - `set-auto-refresh --enabled false` then `true` (both SQL paths)
          - `refresh` — manual one-shot
          - `status` — confirm executionState returned, history shape
          - cleanup

        The interval change is the most cost-sensitive operation surfaced
        in the workflow — verifying it lives green ensures `build_auto_refresh_cost_warning`'s
        recovery command actually works as advertised.
        """
        created_integration = False
        created_iceberg = False
        try:
            _run(capsys, [
                "create-integration",
                "--name", unique_integration_name,
                "--postgres-instance", live_pg_instance,
                "--database", live_pg_catalog,
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            created_integration = True

            _run(capsys, [
                "create-iceberg-table",
                "--name", unique_iceberg_table_name,
                "--catalog", unique_integration_name,
                "--catalog-table-name", live_pg_table,
                "--catalog-namespace", live_pg_namespace,
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            created_iceberg = True

            set_interval = _run(capsys, [
                "set-refresh-interval",
                "--integration", unique_integration_name,
                "--seconds", "60",
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            assert set_interval["success"] is True
            assert set_interval["seconds"] == 60

            # describe-integration should now reflect the new interval.
            describe = _run(capsys, [
                "describe-integration",
                "--name", unique_integration_name,
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            assert describe["properties"]["REFRESH_INTERVAL_SECONDS"]["value"] == "60"

            # Toggle auto-refresh off, then on. Both SQL paths live-exercise.
            off = _run(capsys, [
                "set-auto-refresh",
                "--name", unique_iceberg_table_name,
                "--enabled", "false",
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            assert off["success"] is True
            assert off["enabled"] is False

            on = _run(capsys, [
                "set-auto-refresh",
                "--name", unique_iceberg_table_name,
                "--enabled", "true",
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            assert on["success"] is True
            assert on["enabled"] is True

            manual = _run(capsys, [
                "refresh",
                "--name", unique_iceberg_table_name,
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            assert manual["success"] is True
            assert "REFRESH" in manual["sql"]

            # `status` can return execution_state None during the first
            # second after a state change — we only assert structural
            # correctness, not a specific state value.
            status = _run(capsys, [
                "status",
                "--name", unique_iceberg_table_name,
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            assert status["success"] is True
            assert "refresh_history" in status
            assert isinstance(status["refresh_history_count"], int)
        finally:
            if created_iceberg:
                conn = get_snowflake_connection(live_sf_connection)
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            f"DROP ICEBERG TABLE IF EXISTS {unique_iceberg_table_name}"
                        )
                finally:
                    conn.close()
            if created_integration:
                _run(capsys, [
                    "drop-integration",
                    "--name", unique_integration_name,
                    "--confirm",
                    "--snowflake-connection", live_sf_connection,
                    "--json",
                ])

    def test_cld_missing_allowed_writes_is_impossible_via_cli(
        self,
        capsys,
        live_sf_connection: str,
        live_pg_instance: str,
        live_pg_catalog: str,
        unique_integration_name: str,
        unique_cld_name: str,
    ):
        """
        The `create-cld` subcommand always emits ALLOWED_WRITE_OPERATIONS
        = NONE — there's no flag to drop it. This test verifies the live
        DDL round-trips through Snowflake's validation without ever
        hitting `cld_allowed_write_missing`. If Snowflake changes the
        server-side rule, the other tests keep passing while this one
        continues to assert the CLI surface stays airtight.
        """
        created_integration = False
        created_cld = False
        try:
            _run(capsys, [
                "create-integration",
                "--name", unique_integration_name,
                "--postgres-instance", live_pg_instance,
                "--database", live_pg_catalog,
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            created_integration = True

            result = _run(capsys, [
                "create-cld",
                "--name", unique_cld_name,
                "--catalog", unique_integration_name,
                "--snowflake-connection", live_sf_connection,
                "--json",
            ])
            created_cld = result.get("success") is True
            assert result["success"] is True
            # The one-line contract: user never sees the error we worked
            # so hard to translate.
            assert "ALLOWED_WRITE_OPERATIONS" in result["sql"]
            assert "NONE" in result["sql"]
        finally:
            if created_cld:
                conn = get_snowflake_connection(live_sf_connection)
                try:
                    with conn.cursor() as cur:
                        cur.execute(f"DROP DATABASE IF EXISTS {unique_cld_name}")
                finally:
                    conn.close()
            if created_integration:
                _run(capsys, [
                    "drop-integration",
                    "--name", unique_integration_name,
                    "--confirm",
                    "--snowflake-connection", live_sf_connection,
                    "--json",
                ])
