"""Tests for generate_hybrid_plan.py.

Green baseline against the upstream UNTOUCHED script — these tests encode the
current behavior of:

- the MigrationObject / MigrationPlan dataclasses,
- generate_plan() which routes each blocker-analysis entry to a migration
  method (logical_replication / pg_dump) and builds the ordered phase list,
- generate_html_report / generate_shell_script / JSON output shape.

No live DB — get_blocker_analysis is exercised with the conftest `mock_conn`
fixture. generate_plan is fed hand-built `blockers` dicts that mirror the
output shape.
"""
from __future__ import annotations

import argparse
import json
import re
from typing import Dict, List

import pytest

from generate_hybrid_plan import (
    MigrationObject,
    MigrationPlan,
    generate_html_report,
    generate_plan,
    generate_shell_script,
    get_blocker_analysis,
)


# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------


def _empty_blockers() -> Dict[str, List]:
    """A blocker dict with every expected key present and empty."""
    return {
        "unlogged_tables": [],
        "no_pk_tables": [],
        "inherited_tables": [],
        "inherited_children": [],
        "partitioned_tables": [],
        "foreign_tables": [],
        "large_objects": [{"count": 0, "size": 0}],
        "materialized_views": [],
        "sequences": [],
        "replicable_tables": [],
    }


def _make_args(**overrides) -> argparse.Namespace:
    """Default argparse.Namespace the generator expects."""
    defaults = dict(
        host="src.example.com",
        port=5432,
        dbname="appdb",
        user="pgadmin",
        target_host="tgt.snowflakecomputing.com",
        source_service="",
        target_service="",
        dump_timing="now",
        schemas=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.fixture
def empty_blockers():
    return _empty_blockers()


@pytest.fixture
def args_now():
    return _make_args(dump_timing="now")


@pytest.fixture
def args_cutover():
    return _make_args(dump_timing="cutover")


@pytest.fixture
def mini_schema_blockers():
    """A realistic mini-schema covering most routing branches.

    - 1 replicable table (has PK, logged, not inherited)
    - 1 unlogged table
    - 1 no-PK table
    - 1 inherited parent + 2 children (one with PK → replicable, one without → dump)
    - 1 partitioned parent (children replicate as leaves)
    - 1 foreign table
    - 1 materialized view
    - 1 sequence
    """
    b = _empty_blockers()
    b["replicable_tables"] = [
        {"schema": "public", "name": "orders", "size": 1024 * 1024},  # 1 MB
    ]
    b["unlogged_tables"] = [
        {"schema": "public", "name": "scratch", "size": 512},
    ]
    b["no_pk_tables"] = [
        {"schema": "public", "name": "events", "size": 2048, "replica_identity": "d"},
    ]
    b["inherited_tables"] = [
        {"schema": "public", "name": "legacy_parent", "size": 8192, "children": 2},
    ]
    b["inherited_children"] = [
        {
            "schema": "public",
            "name": "legacy_child_pk",
            "size": 256,
            "parent": "public.legacy_parent",
            "has_pk": True,
        },
        {
            "schema": "public",
            "name": "legacy_child_nopk",
            "size": 128,
            "parent": "public.legacy_parent",
            "has_pk": False,
        },
    ]
    b["partitioned_tables"] = [
        {"schema": "public", "name": "metrics", "size": 0, "children": 12},
    ]
    b["foreign_tables"] = [
        {"schema": "ext", "name": "remote_users", "server": "fdw_srv"},
    ]
    b["materialized_views"] = [
        {"schema": "public", "name": "daily_summary", "size": 4096},
    ]
    b["sequences"] = [
        {"schema": "public", "name": "orders_id_seq", "last_value": 42},
    ]
    return b


# ---------------------------------------------------------------------------
# Dataclass invariants
# ---------------------------------------------------------------------------


class TestMigrationObjectDataclass:
    """MigrationObject defaults + field shapes."""

    def test_required_fields_assigned(self):
        obj = MigrationObject(
            schema="public",
            name="t",
            object_type="table",
            size_bytes=100,
            method="pg_dump",
            reason="because",
            order=1,
        )
        assert obj.schema == "public"
        assert obj.name == "t"
        assert obj.object_type == "table"
        assert obj.size_bytes == 100
        assert obj.method == "pg_dump"
        assert obj.reason == "because"
        assert obj.order == 1

    def test_default_lists_are_independent(self):
        """Two instances must not share mutable default lists."""
        a = MigrationObject("s", "a", "table", 0, "pg_dump", "r", 0)
        b = MigrationObject("s", "b", "table", 0, "pg_dump", "r", 0)
        a.commands.append("cmd")
        a.notes.append("note")
        a.dependencies.append("dep")
        assert b.commands == []
        assert b.notes == []
        assert b.dependencies == []

    def test_default_lists_empty(self):
        obj = MigrationObject("s", "n", "table", 0, "pg_dump", "r", 0)
        assert obj.dependencies == []
        assert obj.commands == []
        assert obj.notes == []

    def test_accepts_all_documented_methods(self):
        """Docstring lists four valid methods. None should be rejected."""
        for method in ("logical_replication", "pg_dump", "copy", "manual"):
            obj = MigrationObject("s", "n", "table", 0, method, "r", 0)
            assert obj.method == method


class TestMigrationPlanDataclass:
    """MigrationPlan defaults + field shapes."""

    def test_required_fields(self):
        plan = MigrationPlan(
            database="db",
            source_host="src",
            target_host="tgt",
            generated_at="2026-01-01",
            total_size_bytes=0,
            complexity_score=0,
            recommended_method="hybrid",
        )
        assert plan.database == "db"
        assert plan.source_host == "src"
        assert plan.target_host == "tgt"
        assert plan.generated_at == "2026-01-01"

    def test_default_dump_timing_is_now(self):
        plan = MigrationPlan(
            database="db",
            source_host="s",
            target_host="t",
            generated_at="now",
            total_size_bytes=0,
            complexity_score=0,
            recommended_method="hybrid",
        )
        assert plan.dump_timing == "now"

    def test_default_collections_independent(self):
        a = MigrationPlan("a", "s", "t", "now", 0, 0, "hybrid")
        b = MigrationPlan("b", "s", "t", "now", 0, 0, "hybrid")
        a.phases.append({"phase": 1})
        a.objects.append(MigrationObject("s", "n", "table", 0, "pg_dump", "r", 0))
        a.pre_migration_commands.append("cmd")
        assert b.phases == []
        assert b.objects == []
        assert b.pre_migration_commands == []
        assert b.post_migration_commands == []
        assert b.validation_commands == []


# ---------------------------------------------------------------------------
# Object classification / routing (generate_plan populates plan.objects)
# ---------------------------------------------------------------------------


def _objects_by_key(plan, attr="name"):
    return {getattr(o, attr): o for o in plan.objects}


class TestClassifyObject:
    """Verify each blocker entry routes to the correct migration method."""

    def test_replicable_table_uses_logical_replication(self, args_now, empty_blockers):
        empty_blockers["replicable_tables"] = [
            {"schema": "public", "name": "orders", "size": 1024}
        ]
        plan = generate_plan(empty_blockers, args_now)
        orders = _objects_by_key(plan)["orders"]
        assert orders.method == "logical_replication"
        assert orders.object_type == "table"
        assert orders.size_bytes == 1024

    def test_unlogged_table_routes_to_pg_dump(self, args_now, empty_blockers):
        empty_blockers["unlogged_tables"] = [
            {"schema": "public", "name": "scratch", "size": 512}
        ]
        plan = generate_plan(empty_blockers, args_now)
        scratch = _objects_by_key(plan)["scratch"]
        assert scratch.method == "pg_dump"
        assert scratch.object_type == "unlogged_table"
        assert "Unlogged" in scratch.reason

    def test_no_pk_table_routes_to_pg_dump(self, args_now, empty_blockers):
        empty_blockers["no_pk_tables"] = [
            {"schema": "public", "name": "events", "size": 2048, "replica_identity": "d"}
        ]
        plan = generate_plan(empty_blockers, args_now)
        events = _objects_by_key(plan)["events"]
        assert events.method == "pg_dump"
        assert events.object_type == "no_pk_table"
        assert "primary key" in events.reason.lower()

    def test_inherited_parent_routes_to_pg_dump(self, args_now, empty_blockers):
        empty_blockers["inherited_tables"] = [
            {"schema": "public", "name": "parent", "size": 8192, "children": 3}
        ]
        plan = generate_plan(empty_blockers, args_now)
        parent = _objects_by_key(plan)["parent"]
        assert parent.method == "pg_dump"
        assert parent.object_type == "inherited_parent"
        assert "3 children" in parent.reason

    def test_inherited_child_with_pk_is_replicable(self, args_now, empty_blockers):
        empty_blockers["inherited_children"] = [
            {
                "schema": "public",
                "name": "child_pk",
                "size": 64,
                "parent": "public.parent",
                "has_pk": True,
            }
        ]
        plan = generate_plan(empty_blockers, args_now)
        child = _objects_by_key(plan)["child_pk"]
        assert child.method == "logical_replication"
        assert child.object_type == "partition_child"
        assert "public.parent" in child.reason

    def test_inherited_child_without_pk_routes_to_pg_dump(self, args_now, empty_blockers):
        empty_blockers["inherited_children"] = [
            {
                "schema": "public",
                "name": "child_nopk",
                "size": 64,
                "parent": "public.parent",
                "has_pk": False,
            }
        ]
        plan = generate_plan(empty_blockers, args_now)
        child = _objects_by_key(plan)["child_nopk"]
        assert child.method == "pg_dump"
        assert child.object_type == "inherited_child"
        assert "public.parent" in child.reason

    def test_partitioned_parent_routes_to_logical_replication(self, args_now, empty_blockers):
        empty_blockers["replicable_tables"] = [
            {"schema": "public", "name": "seed", "size": 1}  # needed to create the LR phase
        ]
        empty_blockers["partitioned_tables"] = [
            {"schema": "public", "name": "metrics", "size": 0, "children": 12}
        ]
        plan = generate_plan(empty_blockers, args_now)
        metrics = _objects_by_key(plan)["metrics"]
        assert metrics.method == "logical_replication"
        assert metrics.object_type == "partitioned_parent"
        assert "12 partitions" in metrics.reason
        # partitioned parent size is always recorded as 0 (leaves are replicated)
        assert metrics.size_bytes == 0

    def test_mini_schema_routes_every_object(self, args_now, mini_schema_blockers):
        """All expected objects appear with the expected method."""
        plan = generate_plan(mini_schema_blockers, args_now)
        by_name = _objects_by_key(plan)
        # replicable
        assert by_name["orders"].method == "logical_replication"
        assert by_name["legacy_child_pk"].method == "logical_replication"
        assert by_name["metrics"].method == "logical_replication"
        # pg_dump
        assert by_name["scratch"].method == "pg_dump"
        assert by_name["events"].method == "pg_dump"
        assert by_name["legacy_parent"].method == "pg_dump"
        assert by_name["legacy_child_nopk"].method == "pg_dump"

    def test_foreign_tables_are_not_in_objects_list(self, args_now, mini_schema_blockers):
        """Foreign tables factor into complexity but are not emitted as objects."""
        plan = generate_plan(mini_schema_blockers, args_now)
        names = [o.name for o in plan.objects]
        assert "remote_users" not in names

    def test_materialized_views_are_not_in_objects_list(self, args_now, mini_schema_blockers):
        plan = generate_plan(mini_schema_blockers, args_now)
        names = [o.name for o in plan.objects]
        assert "daily_summary" not in names

    def test_sequences_are_not_in_objects_list(self, args_now, mini_schema_blockers):
        plan = generate_plan(mini_schema_blockers, args_now)
        names = [o.name for o in plan.objects]
        assert "orders_id_seq" not in names

    def test_object_order_reflects_phase(self, args_now, mini_schema_blockers):
        """Replicable objects have order < pg_dump objects (phases are strictly monotonic)."""
        plan = generate_plan(mini_schema_blockers, args_now)
        by_name = _objects_by_key(plan)
        assert by_name["orders"].order < by_name["scratch"].order
        assert by_name["legacy_child_pk"].order < by_name["legacy_parent"].order


# ---------------------------------------------------------------------------
# Complexity score + recommended method selection
# ---------------------------------------------------------------------------


class TestComplexityAndMethod:
    def test_empty_db_is_logical_replication(self, args_now, empty_blockers):
        plan = generate_plan(empty_blockers, args_now)
        assert plan.recommended_method == "logical_replication"
        assert plan.complexity_score == 0
        assert plan.total_size_bytes == 0

    def test_only_non_replicable_picks_pg_dump(self, args_now, empty_blockers):
        empty_blockers["unlogged_tables"] = [
            {"schema": "public", "name": "a", "size": 1000}
        ]
        plan = generate_plan(empty_blockers, args_now)
        assert plan.recommended_method == "pg_dump"

    def test_mixed_picks_hybrid(self, args_now, mini_schema_blockers):
        plan = generate_plan(mini_schema_blockers, args_now)
        assert plan.recommended_method == "hybrid"

    def test_replicable_only_with_inheritance_still_hybrid(self, args_now, empty_blockers):
        """When inheritance exists alongside replicable tables, route to hybrid:
        inheritance can't replicate, the rest can."""
        empty_blockers["replicable_tables"] = [
            {"schema": "public", "name": "t", "size": 100}
        ]
        empty_blockers["inherited_tables"] = [
            {"schema": "public", "name": "p", "size": 0, "children": 1}
        ]
        plan = generate_plan(empty_blockers, args_now)
        assert plan.recommended_method == "hybrid"

    def test_zero_size_unlogged_still_routes_to_pg_dump(self, args_now, empty_blockers):
        """Pre-fix: a database of unlogged tables with size=0 routed to
        'logical_replication' even though unlogged tables can never replicate.
        The fix is to drive method selection from object COUNTS, not byte
        sizes."""
        empty_blockers["unlogged_tables"] = [
            {"schema": "public", "name": "tmp", "size": 0}
        ]
        plan = generate_plan(empty_blockers, args_now)
        assert plan.recommended_method == "pg_dump"

    def test_zero_size_inherited_parent_with_replicable_routes_to_hybrid(self, args_now, empty_blockers):
        """Pre-fix: inheritance parents with size=0 fell into the hybrid
        bucket alongside replicable tables — that's still hybrid (correct),
        but only because we now key off counts. Lock that in."""
        empty_blockers["replicable_tables"] = [
            {"schema": "public", "name": "ok", "size": 1000}
        ]
        empty_blockers["inherited_tables"] = [
            {"schema": "public", "name": "p", "size": 0, "children": 1}
        ]
        plan = generate_plan(empty_blockers, args_now)
        assert plan.recommended_method == "hybrid"

    def test_complexity_score_weights(self, args_now, empty_blockers):
        """Score is a sum of per-category weights."""
        empty_blockers["unlogged_tables"] = [
            {"schema": "s", "name": f"u{i}", "size": 0} for i in range(2)
        ]  # 2 * 10 = 20
        empty_blockers["no_pk_tables"] = [
            {"schema": "s", "name": "np", "size": 0, "replica_identity": "d"}
        ]  # 1 * 5 = 5
        empty_blockers["inherited_tables"] = [
            {"schema": "s", "name": "ih", "size": 0, "children": 0}
        ]  # 1 * 8 = 8
        empty_blockers["foreign_tables"] = [
            {"schema": "s", "name": "ft", "server": "srv"}
        ]  # 1 * 3 = 3
        empty_blockers["materialized_views"] = [
            {"schema": "s", "name": "mv", "size": 0}
        ]  # 1 * 2 = 2
        plan = generate_plan(empty_blockers, args_now)
        assert plan.complexity_score == 20 + 5 + 8 + 3 + 2  # == 38

    def test_complexity_score_large_objects_bonus(self, args_now, empty_blockers):
        """Large objects (count > 0) add 15 to the score."""
        empty_blockers["large_objects"] = [{"count": 5, "size": 99999}]
        plan = generate_plan(empty_blockers, args_now)
        assert plan.complexity_score == 15

    def test_complexity_score_no_large_objects_bonus_when_zero(
        self, args_now, empty_blockers
    ):
        empty_blockers["large_objects"] = [{"count": 0, "size": 0}]
        plan = generate_plan(empty_blockers, args_now)
        assert plan.complexity_score == 0

    def test_total_size_sums_replicable_and_non_replicable(
        self, args_now, mini_schema_blockers
    ):
        plan = generate_plan(mini_schema_blockers, args_now)
        expected = (
            1024 * 1024  # orders (replicable)
            + 256        # legacy_child_pk (replicable)
            + 512        # scratch (unlogged)
            + 2048       # events (no_pk)
            + 8192       # legacy_parent (inherited)
            + 128        # legacy_child_nopk (dump child)
        )
        assert plan.total_size_bytes == expected


# ---------------------------------------------------------------------------
# Phase assignment
# ---------------------------------------------------------------------------


def _phase_names(plan):
    return [p["name"] for p in plan.phases]


class TestPhaseAssignment:
    def test_always_has_three_setup_phases(self, args_now, empty_blockers):
        plan = generate_plan(empty_blockers, args_now)
        names = _phase_names(plan)
        assert names[0] == "Pre-Migration Setup"
        assert names[1] == "Migrate Roles (Optional)"
        assert names[2] == "Migrate Schema DDL"

    def test_always_ends_with_validation(self, args_now, empty_blockers):
        plan = generate_plan(empty_blockers, args_now)
        assert plan.phases[-1]["name"] == "Validation"

    def test_phase_numbers_are_monotonic_starting_at_1(self, args_now, mini_schema_blockers):
        plan = generate_plan(mini_schema_blockers, args_now)
        nums = [p["phase"] for p in plan.phases]
        assert nums == list(range(1, len(nums) + 1))

    def test_logical_replication_phase_omitted_when_nothing_replicable(
        self, args_now, empty_blockers
    ):
        empty_blockers["unlogged_tables"] = [
            {"schema": "s", "name": "u", "size": 0}
        ]
        plan = generate_plan(empty_blockers, args_now)
        assert "Logical Replication" not in _phase_names(plan)

    def test_logical_replication_phase_present_when_replicable(
        self, args_now, empty_blockers
    ):
        empty_blockers["replicable_tables"] = [
            {"schema": "s", "name": "t", "size": 100}
        ]
        plan = generate_plan(empty_blockers, args_now)
        assert "Logical Replication" in _phase_names(plan)

    def test_logical_replication_counts_children_with_pk(self, args_now, empty_blockers):
        empty_blockers["replicable_tables"] = [
            {"schema": "s", "name": "t", "size": 100}
        ]
        empty_blockers["inherited_children"] = [
            {
                "schema": "s",
                "name": "c1",
                "size": 10,
                "parent": "s.p",
                "has_pk": True,
            }
        ]
        plan = generate_plan(empty_blockers, args_now)
        rep_phase = next(
            p for p in plan.phases if p["name"] == "Logical Replication"
        )
        assert rep_phase["table_count"] == 2
        assert rep_phase["total_size"] == 110

    def test_pg_dump_phase_present_when_dump_timing_now(
        self, args_now, mini_schema_blockers
    ):
        plan = generate_plan(mini_schema_blockers, args_now)
        names = _phase_names(plan)
        assert "pg_dump for Non-Replicable Objects" in names

    def test_pg_dump_phase_absent_when_dump_timing_cutover(
        self, args_cutover, mini_schema_blockers
    ):
        plan = generate_plan(mini_schema_blockers, args_cutover)
        names = _phase_names(plan)
        assert "pg_dump for Non-Replicable Objects" not in names

    def test_mv_phase_present_when_mvs_exist(self, args_now, empty_blockers):
        empty_blockers["materialized_views"] = [
            {"schema": "s", "name": "mv", "size": 0}
        ]
        plan = generate_plan(empty_blockers, args_now)
        assert "Recreate Materialized Views" in _phase_names(plan)

    def test_mv_refresh_commands_quote_schema_and_name(self, args_now, empty_blockers):
        empty_blockers["materialized_views"] = [
            {"schema": 'Mixed Schema', "name": 'Order Summary"', "size": 0}
        ]
        plan = generate_plan(empty_blockers, args_now)
        mv_phase = next(p for p in plan.phases if p["name"] == "Recreate Materialized Views")
        assert mv_phase["commands"] == [
            'REFRESH MATERIALIZED VIEW "Mixed Schema"."Order Summary""";'
        ]

    def test_mv_phase_absent_when_no_mvs(self, args_now, empty_blockers):
        plan = generate_plan(empty_blockers, args_now)
        assert "Recreate Materialized Views" not in _phase_names(plan)

    def test_sequence_phase_present_when_sequences_exist(self, args_now, empty_blockers):
        empty_blockers["sequences"] = [
            {"schema": "s", "name": "seq", "last_value": 1}
        ]
        plan = generate_plan(empty_blockers, args_now)
        assert "Sync Sequences (FINAL STEP)" in _phase_names(plan)

    def test_cutover_phase_combines_dump_and_sequences(self, args_cutover, empty_blockers):
        empty_blockers["unlogged_tables"] = [
            {"schema": "s", "name": "u", "size": 0}
        ]
        empty_blockers["sequences"] = [
            {"schema": "s", "name": "seq", "last_value": 1}
        ]
        plan = generate_plan(empty_blockers, args_cutover)
        names = _phase_names(plan)
        assert any("Cutover:" in n for n in names)

    def test_pre_migration_is_repeatable_and_pausable(self, args_now, empty_blockers):
        plan = generate_plan(empty_blockers, args_now)
        pre = plan.phases[0]
        assert pre["pause_after"] is True
        assert pre["repeatable"] is True

    def test_pre_migration_prefers_service_profiles_when_present(self, empty_blockers):
        args = _make_args(source_service="prod_source", target_service="sf_target")
        plan = generate_plan(empty_blockers, args)
        pre = plan.phases[0]
        joined = "\n".join(pre["commands"])
        assert "--source-service prod_source" in joined
        assert "--target-service sf_target" in joined
        assert "--target-host $TARGET_PGHOST" not in joined

    def test_logical_replication_is_not_repeatable(self, args_now, empty_blockers):
        empty_blockers["replicable_tables"] = [
            {"schema": "s", "name": "t", "size": 1}
        ]
        plan = generate_plan(empty_blockers, args_now)
        rep = next(p for p in plan.phases if p["name"] == "Logical Replication")
        assert rep["repeatable"] is False

    def test_cutover_dump_phase_is_not_pausable(self, args_cutover, empty_blockers):
        empty_blockers["unlogged_tables"] = [
            {"schema": "s", "name": "u", "size": 0}
        ]
        empty_blockers["sequences"] = [
            {"schema": "s", "name": "seq", "last_value": 0}
        ]
        plan = generate_plan(empty_blockers, args_cutover)
        cutover = next(p for p in plan.phases if "Cutover:" in p["name"])
        assert cutover["pause_after"] is False

    def test_validation_is_pausable_and_repeatable(self, args_now, empty_blockers):
        plan = generate_plan(empty_blockers, args_now)
        val = plan.phases[-1]
        assert val["name"] == "Validation"
        assert val["pause_after"] is True
        assert val["repeatable"] is True

    def test_logical_replication_publication_has_partition_root_option(
        self, args_now, empty_blockers
    ):
        """Quirk: partitioned tables add WITH (publish_via_partition_root = true)."""
        empty_blockers["replicable_tables"] = [
            {"schema": "s", "name": "t", "size": 1}
        ]
        empty_blockers["partitioned_tables"] = [
            {"schema": "s", "name": "p", "size": 0, "children": 3}
        ]
        plan = generate_plan(empty_blockers, args_now)
        rep = next(p for p in plan.phases if p["name"] == "Logical Replication")
        joined = "\n".join(rep["commands"])
        assert "publish_via_partition_root = true" in joined

    def test_logical_replication_no_partition_option_when_no_partitioned_tables(
        self, args_now, empty_blockers
    ):
        empty_blockers["replicable_tables"] = [
            {"schema": "s", "name": "t", "size": 1}
        ]
        plan = generate_plan(empty_blockers, args_now)
        rep = next(p for p in plan.phases if p["name"] == "Logical Replication")
        joined = "\n".join(rep["commands"])
        assert "publish_via_partition_root" not in joined

    def test_logical_replication_uses_safe_subscription_wrapper(self, args_now, empty_blockers):
        empty_blockers["replicable_tables"] = [
            {"schema": "s", "name": "t", "size": 1}
        ]
        plan = generate_plan(empty_blockers, args_now)
        rep = next(p for p in plan.phases if p["name"] == "Logical Replication")
        joined = "\n".join(rep["commands"])
        assert "setup_replication.py create-subscription" in joined
        assert "CONNECTION 'host=" not in joined
        assert "password=***" not in joined

    def test_pg_dump_commands_use_pgservice_when_service_profiles_present(self, empty_blockers):
        args = _make_args(source_service="prod_source", target_service="sf_target")
        empty_blockers["unlogged_tables"] = [
            {"schema": "public", "name": "scratch", "size": 1}
        ]
        plan = generate_plan(empty_blockers, args)
        dump_phase = next(p for p in plan.phases if p["name"] == "pg_dump for Non-Replicable Objects")
        joined = "\n".join(dump_phase["commands"])
        assert "PGSERVICE=prod_source pg_dump" in joined
        assert "PGSERVICE=sf_target psql" in joined

    def test_pg_dumpall_role_commands_use_pgservice_when_service_profiles_present(self, empty_blockers):
        args = _make_args(source_service="prod_source", target_service="sf_target")
        plan = generate_plan(empty_blockers, args)
        roles_phase = next(p for p in plan.phases if p["name"] == "Migrate Roles (Optional)")
        joined = "\n".join(roles_phase["commands"])
        assert "PGSERVICE=prod_source pg_dumpall --globals-only" in joined
        assert "PGSERVICE=sf_target psql" in joined

    def test_pg_dumpall_fallback_includes_port_and_database(self, empty_blockers):
        plan = generate_plan(empty_blockers, _make_args())
        roles_phase = next(p for p in plan.phases if p["name"] == "Migrate Roles (Optional)")
        joined = "\n".join(roles_phase["commands"])
        assert "pg_dumpall -h src.example.com -p 5432 -U pgadmin" in joined
        assert "--database=appdb --globals-only" in joined

    def test_scoped_plan_uses_for_table_publication(self, empty_blockers):
        args = _make_args(schemas="public, app")
        empty_blockers["replicable_tables"] = [
            {"schema": "public", "name": "orders", "size": 1},
            {"schema": "app", "name": "users", "size": 1},
        ]
        plan = generate_plan(empty_blockers, args)
        rep = next(p for p in plan.phases if p["name"] == "Logical Replication")
        joined = "\n".join(rep["commands"])
        assert "CREATE PUBLICATION migration_pub FOR TABLE" in joined
        assert '"public"."orders"' in joined
        assert '"app"."users"' in joined
        assert "FOR ALL TABLES" not in joined

    def test_scoped_plan_normalizes_schema_flags_in_emitted_commands(self, empty_blockers):
        args = _make_args(schemas="public, app")
        empty_blockers["replicable_tables"] = [
            {"schema": "public", "name": "orders", "size": 1},
        ]
        empty_blockers["sequences"] = [
            {"schema": "public", "name": "orders_id_seq", "last_value": 42},
        ]
        plan = generate_plan(empty_blockers, args)

        pre = plan.phases[0]
        schema_phase = next(p for p in plan.phases if p["name"] == "Migrate Schema DDL")
        seq_phase = next(p for p in plan.phases if "Sequence" in p["name"])
        validation_phase = next(p for p in plan.phases if p["name"] == "Validation")

        assert "--schemas public,app" in "\n".join(pre["commands"])
        assert "--schema=public --schema=app" in "\n".join(schema_phase["commands"])
        assert "--schemas public,app" in "\n".join(seq_phase["commands"])
        assert "--schemas public,app" in "\n".join(validation_phase["commands"])


# ---------------------------------------------------------------------------
# get_blocker_analysis against mock_conn (SQL paths exercised via pg_common)
# ---------------------------------------------------------------------------


def _make_query_router(responses_by_keyword):
    """Return a cursor.execute side-effect that picks a response by SQL keyword."""

    def side_effect(sql, params=None):
        pass  # no-op: the router consults responses during fetchall

    return side_effect


class TestBlockerAnalysisMocked:
    """Exercise get_blocker_analysis via mocked cursors.

    Rather than feed a per-query response map, we use a tiny scripted cursor
    that returns empty result sets with a valid description shape. That
    exercises the query-loop machinery and confirms get_blocker_analysis
    returns the expected top-level key set.
    """

    def test_returns_all_expected_keys_with_empty_cursor(self, mock_conn, mock_cursor):
        # Every query returns 0 rows. The large_objects branch wraps in try/except,
        # so we give it a realistic `description` for the SELECT count(*) path.
        def fake_execute(sql, params=None):
            if "pg_largeobject_metadata" in sql:
                mock_cursor.description = [("cnt",), ("sz",)]
                mock_cursor.fetchall.return_value = [(0, 0)]
            else:
                mock_cursor.description = [("schema",), ("name",), ("size",)]
                mock_cursor.fetchall.return_value = []

        mock_cursor.execute.side_effect = fake_execute

        blockers = get_blocker_analysis(mock_conn)
        expected_keys = {
            "unlogged_tables",
            "no_pk_tables",
            "inherited_tables",
            "inherited_children",
            "partitioned_tables",
            "foreign_tables",
            "large_objects",
            "materialized_views",
            "sequences",
            "replicable_tables",
        }
        assert set(blockers.keys()) == expected_keys

    def test_empty_cursor_produces_empty_lists(self, mock_conn, mock_cursor):
        def fake_execute(sql, params=None):
            mock_cursor.description = [("schema",), ("name",), ("size",)]
            mock_cursor.fetchall.return_value = []

        mock_cursor.execute.side_effect = fake_execute
        blockers = get_blocker_analysis(mock_conn)
        for key in (
            "unlogged_tables",
            "no_pk_tables",
            "inherited_tables",
            "inherited_children",
            "foreign_tables",
            "materialized_views",
            "sequences",
            "replicable_tables",
        ):
            assert blockers[key] == []

    def test_large_objects_exception_falls_back_to_zero(self, mock_conn, mock_cursor):
        """Quirk: pg_largeobject_metadata access failure yields count=0, size=0."""

        def fake_execute(sql, params=None):
            if "pg_largeobject_metadata" in sql:
                raise RuntimeError("permission denied for pg_largeobject_metadata")
            mock_cursor.description = [("schema",), ("name",), ("size",)]
            mock_cursor.fetchall.return_value = []

        mock_cursor.execute.side_effect = fake_execute
        blockers = get_blocker_analysis(mock_conn)
        assert blockers["large_objects"] == [{"count": 0, "size": 0}]

    def test_schema_filter_injects_quoted_list(self, mock_conn, mock_cursor):
        """When schemas=['a','b'] is passed, SQL strings contain the quoted names."""
        seen_sql: List[str] = []

        def fake_execute(sql, params=None):
            seen_sql.append(sql)
            mock_cursor.description = [("schema",), ("name",), ("size",)]
            mock_cursor.fetchall.return_value = []

        mock_cursor.execute.side_effect = fake_execute
        get_blocker_analysis(mock_conn, schemas=["a", "b"])
        joined = "\n".join(seen_sql)
        assert "'a'" in joined
        assert "'b'" in joined
        # And the filter must appear in at least one pg_class query
        assert "IN ('a', 'b')" in joined


# ---------------------------------------------------------------------------
# JSON output shape
# ---------------------------------------------------------------------------


class TestJsonOutput:
    """JSON serialization happens in main(); we reconstruct its payload shape."""

    def _json_payload(self, plan):
        """Mirror the dict main() writes to the .json file."""
        return {
            "database": plan.database,
            "source_host": plan.source_host,
            "target_host": plan.target_host,
            "generated_at": plan.generated_at,
            "total_size_bytes": plan.total_size_bytes,
            "complexity_score": plan.complexity_score,
            "recommended_method": plan.recommended_method,
            "dump_timing": plan.dump_timing,
            "phases": plan.phases,
            "objects": [
                {
                    "schema": o.schema,
                    "name": o.name,
                    "type": o.object_type,
                    "size_bytes": o.size_bytes,
                    "method": o.method,
                    "reason": o.reason,
                }
                for o in plan.objects
            ],
        }

    def test_json_payload_is_serializable(self, args_now, mini_schema_blockers):
        plan = generate_plan(mini_schema_blockers, args_now)
        s = json.dumps(self._json_payload(plan))
        assert "database" in s
        assert plan.database in s

    def test_json_top_level_keys(self, args_now, mini_schema_blockers):
        plan = generate_plan(mini_schema_blockers, args_now)
        payload = self._json_payload(plan)
        expected = {
            "database",
            "source_host",
            "target_host",
            "generated_at",
            "total_size_bytes",
            "complexity_score",
            "recommended_method",
            "dump_timing",
            "phases",
            "objects",
        }
        assert set(payload.keys()) == expected

    def test_json_phase_ordering_preserved(self, args_now, mini_schema_blockers):
        plan = generate_plan(mini_schema_blockers, args_now)
        payload = self._json_payload(plan)
        phase_numbers = [p["phase"] for p in payload["phases"]]
        assert phase_numbers == sorted(phase_numbers)

    def test_json_object_entries_have_expected_keys(
        self, args_now, mini_schema_blockers
    ):
        plan = generate_plan(mini_schema_blockers, args_now)
        payload = self._json_payload(plan)
        required_keys = {"schema", "name", "type", "size_bytes", "method", "reason"}
        for obj in payload["objects"]:
            assert set(obj.keys()) == required_keys

    def test_json_dump_timing_reflects_args(self, args_cutover, mini_schema_blockers):
        plan = generate_plan(mini_schema_blockers, args_cutover)
        payload = self._json_payload(plan)
        assert payload["dump_timing"] == "cutover"


# ---------------------------------------------------------------------------
# HTML output — structural assertions only (no byte-for-byte matching).
# ---------------------------------------------------------------------------


class TestGenerateHTMLReport:
    def test_html_is_written(self, tmp_path, args_now, mini_schema_blockers):
        plan = generate_plan(mini_schema_blockers, args_now)
        out = tmp_path / "plan.html"
        generate_html_report(plan, str(out))
        assert out.exists()
        assert out.stat().st_size > 0

    def test_html_has_doctype_and_container(self, tmp_path, args_now, empty_blockers):
        plan = generate_plan(empty_blockers, args_now)
        out = tmp_path / "plan.html"
        generate_html_report(plan, str(out))
        content = out.read_text()
        assert content.lower().startswith("<!doctype html>")
        assert '<div class="container">' in content
        assert "</html>" in content

    def test_html_contains_all_phase_names(self, tmp_path, args_now, mini_schema_blockers):
        plan = generate_plan(mini_schema_blockers, args_now)
        out = tmp_path / "plan.html"
        generate_html_report(plan, str(out))
        content = out.read_text()
        for phase in plan.phases:
            assert phase["name"] in content

    def test_html_has_summary_section(self, tmp_path, args_now, mini_schema_blockers):
        plan = generate_plan(mini_schema_blockers, args_now)
        out = tmp_path / "plan.html"
        generate_html_report(plan, str(out))
        content = out.read_text()
        assert '<div class="summary">' in content
        assert "Total Size" in content
        assert "Complexity Score" in content
        assert "Migration Method" in content
        assert "Dump Timing" in content
        assert "Total Phases" in content

    def test_html_renders_objects_table_when_objects_present(
        self, tmp_path, args_now, mini_schema_blockers
    ):
        plan = generate_plan(mini_schema_blockers, args_now)
        out = tmp_path / "plan.html"
        generate_html_report(plan, str(out))
        content = out.read_text()
        assert "Objects by Migration Method" in content
        assert '<table class="object-table">' in content
        # Each object appears as schema.name
        for obj in plan.objects:
            expected = f"{obj.schema}.{obj.name}"
            assert expected in content

    def test_html_object_table_row_count_matches_objects(
        self, tmp_path, args_now, mini_schema_blockers
    ):
        plan = generate_plan(mini_schema_blockers, args_now)
        out = tmp_path / "plan.html"
        generate_html_report(plan, str(out))
        content = out.read_text()
        # Each data row begins with <tr>\n            <td>schema.name</td>
        # Count td-method-tag occurrences as a proxy for object rows.
        tag_count = content.count('class="method-tag ')
        assert tag_count == len(plan.objects)

    def test_html_omits_objects_table_when_no_objects(
        self, tmp_path, args_now, empty_blockers
    ):
        """When plan.objects is empty, the 'Objects by Migration Method' section is skipped."""
        plan = generate_plan(empty_blockers, args_now)
        assert plan.objects == []
        out = tmp_path / "plan.html"
        generate_html_report(plan, str(out))
        content = out.read_text()
        assert "Objects by Migration Method" not in content

    def test_html_method_classes_map_correctly(
        self, tmp_path, args_now, mini_schema_blockers
    ):
        plan = generate_plan(mini_schema_blockers, args_now)
        out = tmp_path / "plan.html"
        generate_html_report(plan, str(out))
        content = out.read_text()
        # At least one of each tag class should appear for this mini-schema
        assert "method-logical" in content
        assert "method-pgdump" in content

    def test_html_database_name_in_title(self, tmp_path, args_now, mini_schema_blockers):
        plan = generate_plan(mini_schema_blockers, args_now)
        out = tmp_path / "plan.html"
        generate_html_report(plan, str(out))
        content = out.read_text()
        assert f"<title>Hybrid Migration Plan - {plan.database}</title>" in content

    def test_html_phase_badges(self, tmp_path, args_now, mini_schema_blockers):
        plan = generate_plan(mini_schema_blockers, args_now)
        out = tmp_path / "plan.html"
        generate_html_report(plan, str(out))
        content = out.read_text()
        # At least one PAUSE OK badge should exist
        assert "PAUSE OK" in content
        # Validation phase is repeatable → REPEATABLE badge should exist
        assert "REPEATABLE" in content


# ---------------------------------------------------------------------------
# Shell script output
# ---------------------------------------------------------------------------


class TestGenerateShellScript:
    def test_script_is_written(self, tmp_path, args_now, mini_schema_blockers):
        plan = generate_plan(mini_schema_blockers, args_now)
        out = tmp_path / "plan.sh"
        generate_shell_script(plan, str(out))
        assert out.exists()

    def test_script_has_shebang_and_set_e(self, tmp_path, args_now, empty_blockers):
        plan = generate_plan(empty_blockers, args_now)
        out = tmp_path / "plan.sh"
        generate_shell_script(plan, str(out))
        content = out.read_text()
        assert content.startswith("#!/bin/bash")
        assert "\nset -e\n" in content

    def test_script_is_executable(self, tmp_path, args_now, empty_blockers):
        plan = generate_plan(empty_blockers, args_now)
        out = tmp_path / "plan.sh"
        generate_shell_script(plan, str(out))
        mode = out.stat().st_mode & 0o777
        assert mode & 0o100  # owner execute

    def test_script_mentions_every_phase(self, tmp_path, args_now, mini_schema_blockers):
        plan = generate_plan(mini_schema_blockers, args_now)
        out = tmp_path / "plan.sh"
        generate_shell_script(plan, str(out))
        content = out.read_text()
        for phase in plan.phases:
            assert phase["name"] in content
            assert f"Phase {phase['phase']}:" in content

    def test_script_has_migration_complete_footer(
        self, tmp_path, args_now, empty_blockers
    ):
        plan = generate_plan(empty_blockers, args_now)
        out = tmp_path / "plan.sh"
        generate_shell_script(plan, str(out))
        content = out.read_text()
        assert "MIGRATION COMPLETE" in content
