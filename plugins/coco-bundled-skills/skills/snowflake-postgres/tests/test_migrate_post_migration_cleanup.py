"""
Tests for post_migration_cleanup.py.

Covers:
- cleanup_target: drops migration-named subscriptions, test tables, foreign servers
- cleanup_source: drops migration-named publications and inactive replication slots
- dry-run mode (no side-effect queries executed)
- active slot skipping
- error capture
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from post_migration_cleanup import cleanup_source, cleanup_target


def _configure_cursor_sequence(cursor, result_sequences):
    """Each call to execute() consumes one (columns, rows) result or (cols, rows, raise)."""
    states = iter(result_sequences)

    def _on_execute(sql, params=None):
        try:
            payload = next(states)
        except StopIteration:
            cursor.description = None
            cursor.fetchall.return_value = []
            return
        if payload is None:
            cursor.description = None
            cursor.fetchall.return_value = []
            return
        if isinstance(payload, Exception):
            raise payload
        cols, rows = payload
        if cols is None:
            cursor.description = None
            cursor.fetchall.return_value = []
        else:
            cursor.description = [(c,) for c in cols]
            cursor.fetchall.return_value = rows

    cursor.execute.side_effect = _on_execute


class TestCleanupTargetDryRun:
    """In dry-run mode cleanup_target lists DROP SQL without mutating."""

    def test_dry_run_lists_subscription_drops(self, mock_conn, mock_cursor):
        # Discovery query returns enabled subscription rows; subsequent
        # drop/mutation SQL is NOT executed under dry_run=True.
        _configure_cursor_sequence(
            mock_cursor,
            [
                (["subname"], [("my_migration_sub",), ("migrate_it",)]),
            ],
        )
        results, errors = cleanup_target(mock_conn, dry_run=True)
        # With dry_run=True, the DROP SUBSCRIPTION SQL is appended but NOT executed.
        # Identifier quoting is applied via quote_ident.
        assert 'DROP SUBSCRIPTION IF EXISTS "my_migration_sub"' in results
        assert 'DROP SUBSCRIPTION IF EXISTS "migrate_it"' in results
        # migration test tables always listed
        assert 'DROP TABLE IF EXISTS "_migration_conn_test"' in results
        assert 'DROP TABLE IF EXISTS "_migration_test_table"' in results
        # migration connectivity test server
        assert 'DROP SERVER IF EXISTS "_migration_connectivity_test" CASCADE' in results
        assert errors == []

    def test_dry_run_no_execute_calls_beyond_initial_select(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (["subname"], [("sub1",)]),
            ],
        )
        cleanup_target(mock_conn, dry_run=True)
        executed = [c.args[0] for c in mock_cursor.execute.call_args_list]
        # Only the enabled-subscription discovery query should have been executed;
        # DROP statements stay in `results`.
        assert any("pg_stat_subscription" in s for s in executed)
        assert not any("DROP SUBSCRIPTION IF EXISTS" in s for s in executed)
        assert not any("DROP TABLE IF EXISTS \"_migration" in s for s in executed)
        assert not any("DROP SERVER IF EXISTS \"_migration" in s for s in executed)

    def test_dry_run_includes_test_objects_even_without_subs(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(mock_cursor, [(["subname"], [])])
        results, errors = cleanup_target(mock_conn, dry_run=True)
        # With no enabled workers, cleanup falls back to the documented default
        # migration subscription names.
        assert 'DROP SUBSCRIPTION IF EXISTS "migration_sub"' in results
        assert 'DROP SUBSCRIPTION IF EXISTS "migrate_from_source"' in results
        # Still schedules the test-object cleanups
        assert 'DROP TABLE IF EXISTS "_migration_conn_test"' in results
        assert 'DROP SERVER IF EXISTS "_migration_connectivity_test" CASCADE' in results
        assert errors == []


class TestCleanupTargetExecute:
    """Non-dry-run cleanup_target actually issues DROP statements."""

    def test_executes_drop_subscription(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (["subname"], [("mig_sub",)]),
                None,  # DROP SUBSCRIPTION (clean path succeeds, no fallback)
                None,  # DROP TABLE _migration_conn_test
                None,  # DROP TABLE _migration_test_table
                None,  # DROP SERVER _migration_connectivity_test
            ],
        )
        cleanup_target(mock_conn, dry_run=False)
        executed = [c.args[0] for c in mock_cursor.execute.call_args_list]
        assert any('DROP SUBSCRIPTION IF EXISTS "mig_sub"' in s for s in executed)
        # Clean path: no ALTER SUBSCRIPTION calls made
        assert not any("ALTER SUBSCRIPTION" in s for s in executed)
        assert any('DROP TABLE IF EXISTS "_migration_conn_test"' in s for s in executed)
        assert any('DROP SERVER IF EXISTS "_migration_connectivity_test" CASCADE' in s for s in executed)

    def test_subscription_drop_falls_back_when_initial_drop_fails(self, mock_conn, mock_cursor):
        """When the optimistic DROP fails (typically: publisher unreachable),
        cleanup_target falls back to DISABLE + slot_name=NONE + DROP. The
        subscription is removed from the target catalog and the slot is
        orphaned on the publisher (cleanup_source handles that, or the
        operator runs pg_drop_replication_slot manually).
        """
        _configure_cursor_sequence(
            mock_cursor,
            [
                (["subname"], [("flaky_sub",)]),
                RuntimeError("could not connect to publisher"),  # initial DROP
                None,  # ALTER SUBSCRIPTION DISABLE
                None,  # ALTER SUBSCRIPTION SET (slot_name = NONE)
                None,  # DROP SUBSCRIPTION (fallback path, no IF EXISTS)
                None,  # DROP TABLE _migration_conn_test
                None,  # DROP TABLE _migration_test_table
                None,  # DROP SERVER _migration_connectivity_test
            ],
        )
        results, errors = cleanup_target(mock_conn, dry_run=False)
        executed = [c.args[0] for c in mock_cursor.execute.call_args_list]
        assert any("DROP SUBSCRIPTION IF EXISTS" in s for s in executed)
        assert any('ALTER SUBSCRIPTION "flaky_sub" DISABLE' in s for s in executed)
        assert any("SET (slot_name = NONE)" in s for s in executed)
        # Fallback succeeded -> no errors collected, but result log shows fallback ran
        assert errors == []
        assert any("falling back" in line for line in results)
        assert any("dropped via fallback" in line for line in results)
        assert any("pg_replication_slots" in line for line in results)
        assert any("pg_drop_replication_slot('<slot_name>')" in line for line in results)

    def test_subscription_drop_surfaces_recovery_when_both_paths_fail(self, mock_conn, mock_cursor):
        """If even the disassociate-then-drop fallback fails, the error
        message must give the operator an exact recovery sequence.
        """
        _configure_cursor_sequence(
            mock_cursor,
            [
                (["subname"], [("flaky_sub",)]),
                RuntimeError("could not connect to publisher"),  # initial DROP
                RuntimeError("permission denied"),  # ALTER DISABLE fails too
                None,  # DROP TABLE _migration_conn_test
                None,  # DROP TABLE _migration_test_table
                None,  # DROP SERVER _migration_connectivity_test
            ],
        )
        results, errors = cleanup_target(mock_conn, dry_run=False)
        assert any("ERROR (fallback)" in line for line in results)
        assert len(errors) == 1
        recovery = errors[0]
        # Initial + fallback errors both surface
        assert "could not connect to publisher" in recovery
        assert "permission denied" in recovery
        # Manual recovery commands present
        assert "ALTER SUBSCRIPTION flaky_sub DISABLE" in recovery
        assert "SET (slot_name = NONE)" in recovery
        assert "DROP SUBSCRIPTION flaky_sub" in recovery
        assert "pg_replication_slots" in recovery
        assert "pg_drop_replication_slot('<slot_name>')" in recovery

    def test_test_object_drop_errors_now_surface_in_errors(self, mock_conn, mock_cursor):
        """Pre-fix, DROP TABLE / DROP SERVER errors were silently swallowed
        (`except: pass`) so cleanup printed CLEANUP COMPLETE while artifacts
        remained. Now they surface in the returned errors list."""
        _configure_cursor_sequence(
            mock_cursor,
            [
                (["subname"], [("migration_sub",)]),
                None,  # DROP SUBSCRIPTION IF EXISTS "migration_sub"
                RuntimeError("no such table"),  # DROP TABLE _migration_conn_test
                RuntimeError("no such table"),  # DROP TABLE _migration_test_table
                RuntimeError("no such server"),  # DROP SERVER
            ],
        )
        results, errors = cleanup_target(
            mock_conn, dry_run=False, subscription_names=["migration_sub"]
        )
        # ERROR comments now appear inline in the results script
        assert any("-- ERROR" in line for line in results)
        # And they're collected into the errors list
        assert len(errors) == 3
        assert any("_migration_conn_test" in e for e in errors)
        assert any("_migration_test_table" in e for e in errors)
        assert any("_migration_connectivity_test" in e for e in errors)


class TestCleanupTargetNoMigrationArtifacts:
    """When no migration-named subscriptions exist, still runs test-object cleanups."""

    def test_empty_subscriptions(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(mock_cursor, [(["subname"], [])])
        results, errors = cleanup_target(mock_conn, dry_run=True)
        sub_lines = [r for r in results if "DROP SUBSCRIPTION" in r]
        assert sub_lines == [
            'DROP SUBSCRIPTION IF EXISTS "migration_sub"',
            'DROP SUBSCRIPTION IF EXISTS "migrate_from_source"',
            'DROP SUBSCRIPTION IF EXISTS "reverse_sub"',
        ]

    def test_explicit_subscription_names_override_default_fallback(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(mock_cursor, [(["subname"], [])])
        results, errors = cleanup_target(
            mock_conn, dry_run=True, subscription_names=["custom_sub"]
        )
        sub_lines = [r for r in results if "DROP SUBSCRIPTION" in r]
        assert sub_lines == ['DROP SUBSCRIPTION IF EXISTS "custom_sub"']
        assert errors == []


class TestCleanupSourceDryRun:
    """cleanup_source in dry-run mode."""

    def test_lists_publications_and_slots(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (["pubname"], [("migrate_pub",), ("snowflake_pub",)]),
                (["slot_name", "active"], [("migrate_slot", False), ("migrate_active", True)]),
            ],
        )
        results, errors = cleanup_source(mock_conn, dry_run=True)
        assert 'DROP PUBLICATION IF EXISTS "migrate_pub"' in results
        assert 'DROP PUBLICATION IF EXISTS "snowflake_pub"' in results
        # inactive slot -> drop queued (slot name is a SQL literal here, not an identifier)
        assert "SELECT pg_drop_replication_slot('migrate_slot')" in results
        # active slot -> skipped with SKIPPED comment
        assert any("SKIPPED (active): migrate_active" in r for r in results)
        assert "SELECT pg_drop_replication_slot('migrate_active')" not in results
        assert errors == []

    def test_dry_run_does_not_execute_drops(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (["pubname"], [("p1",)]),
                (["slot_name", "active"], [("s1", False)]),
            ],
        )
        cleanup_source(mock_conn, dry_run=True)
        executed = [c.args[0] for c in mock_cursor.execute.call_args_list]
        # Only the two SELECTs should have been executed
        assert len([s for s in executed if "pg_publication" in s]) == 1
        assert len([s for s in executed if "pg_replication_slots" in s]) == 1
        assert not any("DROP PUBLICATION" in s for s in executed)
        assert not any("pg_drop_replication_slot" in s for s in executed)


class TestCleanupSourceExecute:
    """cleanup_source in execute mode."""

    def test_drops_publications_and_inactive_slots(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (["pubname"], [("migrate_pub",)]),
                # DROP PUBLICATION
                None,
                (["slot_name", "active"], [("migrate_slot", False), ("active_slot", True)]),
                # pg_drop_replication_slot for the inactive one only
                None,
            ],
        )
        results, errors = cleanup_source(mock_conn, dry_run=False)
        executed = [c.args[0] for c in mock_cursor.execute.call_args_list]
        assert any('DROP PUBLICATION IF EXISTS "migrate_pub"' in s for s in executed)
        assert any("pg_drop_replication_slot('migrate_slot')" in s for s in executed)
        assert not any("pg_drop_replication_slot('active_slot')" in s for s in executed)
        assert any("SKIPPED (active): active_slot" in r for r in results)
        assert errors == []

    def test_publication_drop_error_captured(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (["pubname"], [("flaky_pub",)]),
                RuntimeError("cant drop"),  # DROP PUBLICATION raises
                (["slot_name", "active"], []),
            ],
        )
        results, errors = cleanup_source(mock_conn, dry_run=False)
        assert any("-- ERROR: cant drop" in line for line in results)
        assert any("flaky_pub" in e for e in errors)

    def test_slot_drop_error_captured(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (["pubname"], []),
                (["slot_name", "active"], [("bad_slot", False)]),
                RuntimeError("slot busy"),  # pg_drop_replication_slot raises
            ],
        )
        results, errors = cleanup_source(mock_conn, dry_run=False)
        assert any("-- ERROR: slot busy" in line for line in results)
        assert any("bad_slot" in e for e in errors)

    def test_no_publications_or_slots(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (["pubname"], []),
                (["slot_name", "active"], []),
            ],
        )
        results, errors = cleanup_source(mock_conn, dry_run=False)
        assert results == []
        assert errors == []


class TestCleanupSourceSlotActiveDictBehavior:
    """Lock in the `slot.get('active')` check."""

    def test_active_true_means_skip(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (["pubname"], []),
                (["slot_name", "active"], [("active_s", True)]),
            ],
        )
        results, errors = cleanup_source(mock_conn, dry_run=True)
        assert any("SKIPPED (active): active_s" in r for r in results)

    def test_active_false_means_drop(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (["pubname"], []),
                (["slot_name", "active"], [("inactive_s", False)]),
            ],
        )
        results, errors = cleanup_source(mock_conn, dry_run=True)
        assert "SELECT pg_drop_replication_slot('inactive_s')" in results


class TestCleanupQueryPatterns:
    """Lock the queries used to identify migration artifacts."""

    def test_target_subscription_discovery_uses_pg_stat_subscription(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(mock_cursor, [(["subname"], [])])
        cleanup_target(mock_conn, dry_run=True)
        sql = mock_cursor.execute.call_args_list[0].args[0]
        assert "pg_stat_subscription" in sql
        assert "subname" in sql
        assert "ILIKE '%migrat%'" in sql
        assert "ILIKE '%migrate%'" in sql
        assert "ILIKE '%reverse%'" in sql

    def test_source_publication_filter_uses_migrat_and_snowflake(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(
            mock_cursor, [(["pubname"], []), (["slot_name", "active"], [])]
        )
        cleanup_source(mock_conn, dry_run=True)
        pub_sql = mock_cursor.execute.call_args_list[0].args[0]
        assert "pg_publication" in pub_sql
        assert "'%migrat%'" in pub_sql
        assert "'%snowflake%'" in pub_sql

    def test_source_slot_filter_uses_migrat_and_migrate(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(
            mock_cursor, [(["pubname"], []), (["slot_name", "active"], [])]
        )
        cleanup_source(mock_conn, dry_run=True)
        slot_sql = mock_cursor.execute.call_args_list[1].args[0]
        assert "pg_replication_slots" in slot_sql
        assert "'%migrat%'" in slot_sql
        assert "'%migrate%'" in slot_sql
