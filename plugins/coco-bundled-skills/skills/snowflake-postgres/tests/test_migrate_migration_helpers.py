"""
Tests for migration_helpers.py.

Covers four subcommand handlers:
  - cmd_postgis: PostGIS assessment
  - cmd_vector_indexes: pgvector index inventory
  - cmd_blockers: logical replication blocker detection
  - cmd_replication_check: replication readiness check

All DB interactions are mocked via patching migration_helpers.query,
migration_helpers.scalar, and migration_helpers.connect_source, since
those symbols are imported into the module namespace at import time.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import migration_helpers
from migration_helpers import (
    cmd_blockers,
    cmd_postgis,
    cmd_replication_check,
    cmd_vector_indexes,
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _make_args(**overrides):
    defaults = dict(
        host="h", port=5432, dbname="d", user="u", password="", sslmode=None,
        output=None, verbose=False, schemas=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _fake_scalar_factory(mapping):
    """Build a scalar() stub that matches on a substring of the SQL.

    Longest fragment wins to avoid ambiguity when one fragment is a
    substring of another.
    """
    sorted_mapping = sorted(mapping, key=lambda kv: len(kv[0]), reverse=True)

    def scalar_stub(conn, sql, params=None):
        for frag, val in sorted_mapping:
            if frag in sql:
                if callable(val):
                    return val()
                return val
        return None
    return scalar_stub


def _fake_query_factory(mapping):
    """Build a query() stub keyed on substrings of the SQL text.

    Longest fragment wins (so more-specific keys beat less-specific ones
    that happen to be substrings of the same SQL).
    """
    sorted_mapping = sorted(mapping, key=lambda kv: len(kv[0]), reverse=True)

    def query_stub(conn, sql, params=None):
        for frag, rows in sorted_mapping:
            if frag in sql:
                return rows if not callable(rows) else rows(params)
        return []
    return query_stub


def _postgis_scalar_stub(version="3.4.0", full_ver="full", has_raster=None,
                          has_topology=None):
    """Consistent scalar stub for the cmd_postgis flow."""
    def scalar_stub(conn, sql, params=None):
        if "extname = 'postgis_raster'" in sql:
            return has_raster
        if "extname = 'postgis_topology'" in sql:
            return has_topology
        if "PostGIS_Full_Version" in sql:
            return full_ver
        if "extversion FROM pg_extension WHERE extname = 'postgis'" in sql:
            return version
        if "extname = 'postgis'" in sql:
            return 1
        return None
    return scalar_stub


def _vector_scalar_stub(version="0.7.0"):
    def scalar_stub(conn, sql, params=None):
        if "extversion FROM pg_extension WHERE extname = 'vector'" in sql:
            return version
        if "extname = 'vector'" in sql:
            return 1
        return None
    return scalar_stub


# ==========================================================================
# cmd_postgis
# ==========================================================================


class TestCmdPostgisDetection:
    """PostGIS detection gate."""

    def test_no_postgis_exits_early(self, capsys):
        conn = MagicMock()
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar", return_value=None), \
             patch("migration_helpers.query", return_value=[]), \
             patch("migration_helpers.check_driver"):
            cmd_postgis(_make_args())
        out = capsys.readouterr().out
        assert "PostGIS is not installed" in out
        conn.close.assert_called_once()

    def test_postgis_detected_prints_version(self, capsys):
        conn = MagicMock()
        scalar_stub = _postgis_scalar_stub(version="3.4.0", full_ver="POSTGIS=3.4.0 full info")
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar", side_effect=scalar_stub), \
             patch("migration_helpers.query", return_value=[]), \
             patch("migration_helpers.check_driver"):
            cmd_postgis(_make_args())
        out = capsys.readouterr().out
        assert "POSTGIS MIGRATION ASSESSMENT" in out
        assert "PostGIS version: 3.4.0" in out
        assert "Full version:    POSTGIS=3.4.0 full info" in out

    def test_postgis_full_version_failure_is_tolerated(self, capsys):
        conn = MagicMock()
        def scalar_stub(conn, sql, params=None):
            if "extname = 'postgis'" in sql and "extversion" not in sql:
                return 1
            if "extversion" in sql:
                return "3.4.0"
            if "PostGIS_Full_Version" in sql:
                raise RuntimeError("function not found")
            return None
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar", side_effect=scalar_stub), \
             patch("migration_helpers.query", return_value=[]), \
             patch("migration_helpers.check_driver"):
            cmd_postgis(_make_args())
        out = capsys.readouterr().out
        assert "PostGIS version: 3.4.0" in out
        assert "Full version" not in out


class TestCmdPostgisColumnsAndIndexes:
    def test_lists_geometry_and_geography_columns(self, capsys):
        conn = MagicMock()
        scalar_stub = _postgis_scalar_stub()
        def query_stub(conn, sql, params=None):
            # Order matters: the used_srids query contains "geometry_columns"
            # as a substring, so match the WITH clause first.
            if "used_srids" in sql:
                return []
            if "geometry_columns" in sql and "f_geometry_column" in sql:
                return [{"table_name": "public.pts", "column_name": "geom",
                         "geometry_type": "POINT", "srid": 4326, "dims": 2}]
            if "geography_columns" in sql:
                return [{"table_name": "public.regions", "column_name": "geog",
                         "geography_type": "POLYGON", "srid": 4326}]
            if "pg_indexes" in sql:
                return []
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar", side_effect=scalar_stub), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_postgis(_make_args())
        out = capsys.readouterr().out
        assert "public.pts.geom" in out
        assert "POINT" in out
        assert "public.regions.geog" in out
        assert "POLYGON" in out

    def test_custom_srid_triggers_export_block(self, capsys):
        conn = MagicMock()
        scalar_stub = _postgis_scalar_stub()
        def query_stub(conn, sql, params=None):
            # Match used_srids first; that query contains "geography_columns"
            # and "geometry_columns" as substrings too.
            if "spatial_ref_sys WHERE srid" in sql:
                return [{
                    "srid": 900001, "auth_name": "custom", "auth_srid": 900001,
                    "srtext": 'PROJCS["foo"]', "proj4text": "+proj=merc"
                }]
            if "used_srids" in sql:
                return [{"srid": 900001, "authority": "custom:x", "status": "CUSTOM"}]
            if "f_geometry_column" in sql:
                return []
            if "f_geography_column" in sql:
                return []
            if "pg_indexes" in sql:
                return []
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar", side_effect=scalar_stub), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_postgis(_make_args())
        out = capsys.readouterr().out
        assert "Custom SRID Export" in out
        assert "INSERT INTO spatial_ref_sys" in out
        assert "900001" in out
        assert "CUSTOM" in out

    def test_spatial_index_rebuild_block(self, capsys):
        conn = MagicMock()
        scalar_stub = _postgis_scalar_stub()
        def query_stub(conn, sql, params=None):
            # Match used_srids before geometry/geography (substring overlap).
            if "used_srids" in sql:
                return []
            if "f_geometry_column" in sql:
                return [{"table_name": "public.pts", "column_name": "geom",
                         "geometry_type": "POINT", "srid": 4326, "dims": 2}]
            if "f_geography_column" in sql:
                return []
            if "pg_indexes" in sql:
                return [{
                    "table_name": "public.pts", "indexname": "idx_geom",
                    "indexdef": "CREATE INDEX idx_geom ON public.pts USING gist (geom)",
                    "size": "16 kB",
                }]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar", side_effect=scalar_stub), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_postgis(_make_args())
        out = capsys.readouterr().out
        assert "type=GiST" in out
        assert "Index Rebuild Commands" in out
        assert "CREATE INDEX CONCURRENTLY idx_geom" in out
        assert "DROP INDEX IF EXISTS public.idx_geom" in out
        assert "ANALYZE public.pts" in out
        assert "ST_IsValid(geom)" in out

    def test_writes_json_when_output_arg(self, tmp_path):
        conn = MagicMock()
        scalar_stub = _postgis_scalar_stub()
        query_stub = _fake_query_factory([
            ("geometry_columns", []),
            ("geography_columns", []),
            ("used_srids", []),
            ("pg_indexes", []),
        ])
        outfile = tmp_path / "postgis.json"
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar", side_effect=scalar_stub), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_postgis(_make_args(output=str(outfile)))
        data = json.loads(outfile.read_text())
        assert data["postgis_version"] == "3.4.0"
        assert data["geometry_columns"] == []
        assert data["custom_srids"] == []


# ==========================================================================
# cmd_vector_indexes
# ==========================================================================


class TestCmdVectorIndexes:
    def test_no_vector_extension_exits_early(self, capsys):
        conn = MagicMock()
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar", return_value=None), \
             patch("migration_helpers.query", return_value=[]), \
             patch("migration_helpers.check_driver"):
            cmd_vector_indexes(_make_args())
        out = capsys.readouterr().out
        assert "pgvector is not installed" in out

    def test_lists_vector_columns_and_indexes(self, capsys):
        conn = MagicMock()
        scalar_stub = _vector_scalar_stub()
        def query_stub(conn, sql, params=None):
            if "'vector'::regtype" in sql:
                return [{"table_name": "public.docs", "column_name": "embedding",
                         "data_type": "vector(1536)", "table_size": "100 MB"}]
            if "pg_indexes" in sql:
                return [{
                    "table_name": "public.docs", "indexname": "idx_doc_vec",
                    "indexdef": "CREATE INDEX idx_doc_vec ON public.docs USING hnsw (embedding vector_cosine_ops)",
                    "index_size": "50 MB",
                }]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar", side_effect=scalar_stub), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_vector_indexes(_make_args())
        out = capsys.readouterr().out
        assert "pgvector version: 0.7.0" in out
        assert "public.docs.embedding" in out
        assert "type=HNSW" in out
        assert "distance=Cosine" in out
        assert "DROP INDEX IF EXISTS public.idx_doc_vec" in out
        assert "CREATE INDEX CONCURRENTLY idx_doc_vec" in out
        assert "Tuning Guidance" in out

    def test_ivfflat_and_inner_product(self, capsys):
        conn = MagicMock()
        scalar_stub = _vector_scalar_stub()
        def query_stub(conn, sql, params=None):
            if "'vector'::regtype" in sql:
                return []
            if "pg_indexes" in sql:
                return [{
                    "table_name": "s.t", "indexname": "ivf_ip",
                    "indexdef": "CREATE INDEX ivf_ip ON s.t USING ivfflat (emb vector_ip_ops)",
                    "index_size": "8 kB",
                }]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar", side_effect=scalar_stub), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_vector_indexes(_make_args())
        out = capsys.readouterr().out
        assert "type=IVFFlat" in out
        assert "distance=Inner Product" in out

    def test_l2_default_distance(self, capsys):
        conn = MagicMock()
        scalar_stub = _vector_scalar_stub()
        def query_stub(conn, sql, params=None):
            if "'vector'::regtype" in sql:
                return []
            if "pg_indexes" in sql:
                return [{
                    "table_name": "s.t", "indexname": "hnsw_l2",
                    "indexdef": "CREATE INDEX hnsw_l2 ON s.t USING hnsw (emb vector_l2_ops)",
                    "index_size": "8 kB",
                }]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar", side_effect=scalar_stub), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_vector_indexes(_make_args())
        out = capsys.readouterr().out
        assert "distance=L2" in out

    def test_summary_counts_ivf_and_hnsw(self, capsys):
        conn = MagicMock()
        scalar_stub = _vector_scalar_stub()
        def query_stub(conn, sql, params=None):
            if "'vector'::regtype" in sql:
                return []
            if "pg_indexes" in sql:
                return [
                    {"table_name": "s.t", "indexname": "i1",
                     "indexdef": "CREATE INDEX i1 ON s.t USING ivfflat (e vector_l2_ops)",
                     "index_size": "1 kB"},
                    {"table_name": "s.t", "indexname": "i2",
                     "indexdef": "CREATE INDEX i2 ON s.t USING hnsw (e vector_l2_ops)",
                     "index_size": "1 kB"},
                ]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar", side_effect=scalar_stub), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_vector_indexes(_make_args())
        out = capsys.readouterr().out
        assert "IVFFlat indexes: 1" in out
        assert "HNSW indexes:    1" in out

    def test_writes_json_output(self, tmp_path):
        conn = MagicMock()
        scalar_stub = _vector_scalar_stub()
        query_stub = _fake_query_factory([
            ("'vector'::regtype", []),
            ("pg_indexes", []),
        ])
        outfile = tmp_path / "vec.json"
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar", side_effect=scalar_stub), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_vector_indexes(_make_args(output=str(outfile)))
        data = json.loads(outfile.read_text())
        assert data["pgvector_version"] == "0.7.0"
        assert data["vector_columns"] == []
        assert data["vector_indexes"] == []


# ==========================================================================
# cmd_blockers
# ==========================================================================


class TestCmdBlockersEmpty:
    def test_all_queries_empty(self, capsys):
        conn = MagicMock()
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.detect_pg_version", return_value=160000), \
             patch("migration_helpers.scalar", return_value=0), \
             patch("migration_helpers.query", return_value=[]), \
             patch("migration_helpers.check_driver"):
            cmd_blockers(_make_args())
        out = capsys.readouterr().out
        assert "LOGICAL REPLICATION BLOCKERS DETECTION" in out
        assert "Found 0 items" in out
        assert "LOGICAL REPLICATION VIABLE" in out


class TestCmdBlockersUnloggedTable:
    def test_detects_unlogged_tables(self, capsys):
        conn = MagicMock()
        def query_stub(conn, sql, params=None):
            if "relpersistence = 'u'" in sql:
                return [{"schema_name": "public", "object_name": "scratch", "size": "128 MB"}]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.detect_pg_version", return_value=160000), \
             patch("migration_helpers.scalar", return_value=0), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_blockers(_make_args())
        out = capsys.readouterr().out
        assert "UNLOGGED_TABLE" in out
        assert "public.scratch" in out
        assert "HYBRID MIGRATION REQUIRED" in out
        assert "ALTER TABLE public.scratch SET LOGGED" in out


class TestCmdBlockersNoPrimaryKey:
    def test_no_pk_with_default_replica_identity_is_high(self, capsys):
        conn = MagicMock()
        def query_stub(conn, sql, params=None):
            if "pk.oid IS NULL" in sql and "relpersistence = 'p'" in sql:
                return [{
                    "schema_name": "public", "object_name": "logs",
                    "size": "1 GB", "replica_identity": "default",
                }]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.detect_pg_version", return_value=160000), \
             patch("migration_helpers.scalar", return_value=0), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_blockers(_make_args())
        out = capsys.readouterr().out
        assert "NO_PRIMARY_KEY" in out
        assert "public.logs" in out
        assert "HIGH" in out

    def test_no_pk_with_full_identity_is_medium(self, capsys):
        conn = MagicMock()
        def query_stub(conn, sql, params=None):
            if "pk.oid IS NULL" in sql and "relpersistence = 'p'" in sql:
                return [{
                    "schema_name": "s", "object_name": "t",
                    "size": "1 MB", "replica_identity": "full",
                }]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.detect_pg_version", return_value=160000), \
             patch("migration_helpers.scalar", return_value=0), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_blockers(_make_args())
        out = capsys.readouterr().out
        assert "MEDIUM" in out
        assert "NO_PRIMARY_KEY" in out

    def test_no_pk_with_index_identity_is_low(self, capsys):
        conn = MagicMock()
        def query_stub(conn, sql, params=None):
            if "pk.oid IS NULL" in sql and "relpersistence = 'p'" in sql:
                return [{
                    "schema_name": "s", "object_name": "t",
                    "size": "1 MB", "replica_identity": "index",
                }]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.detect_pg_version", return_value=160000), \
             patch("migration_helpers.scalar", return_value=0), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_blockers(_make_args())
        out = capsys.readouterr().out
        assert "LOW" in out
        assert "NO_PRIMARY_KEY" in out


class TestCmdBlockersInheritance:
    def test_detects_inheritance(self, capsys):
        conn = MagicMock()
        def query_stub(conn, sql, params=None):
            if "pg_inherits" in sql:
                return [{
                    "schema_name": "public", "object_name": "events",
                    "size": "5 GB", "child_count": 12,
                }]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.detect_pg_version", return_value=160000), \
             patch("migration_helpers.scalar", return_value=0), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_blockers(_make_args())
        out = capsys.readouterr().out
        assert "TABLE_INHERITANCE" in out
        assert "HIGH" in out
        assert "HYBRID MIGRATION REQUIRED" in out


class TestCmdBlockersForeignTable:
    def test_detects_foreign_tables(self, capsys):
        conn = MagicMock()
        def query_stub(conn, sql, params=None):
            if "information_schema.foreign_tables" in sql:
                return [{"schema_name": "public", "object_name": "ext_t", "server": "fdw1"}]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.detect_pg_version", return_value=160000), \
             patch("migration_helpers.scalar", return_value=0), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_blockers(_make_args())
        out = capsys.readouterr().out
        assert "FOREIGN_TABLE" in out
        assert "MEDIUM" in out

    def test_foreign_table_schema_filter(self, capsys):
        conn = MagicMock()
        def query_stub(conn, sql, params=None):
            if "information_schema.foreign_tables" in sql:
                return [
                    {"schema_name": "keep", "object_name": "a", "server": "s"},
                    {"schema_name": "drop", "object_name": "b", "server": "s"},
                ]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.detect_pg_version", return_value=160000), \
             patch("migration_helpers.scalar", return_value=0), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_blockers(_make_args(schemas="keep"))
        out = capsys.readouterr().out
        # Only 1 foreign table (from 'keep') should be in the totals
        assert "Found 1 items" in out


class TestCmdBlockersLargeObjects:
    def test_detects_large_objects(self, capsys):
        conn = MagicMock()
        def scalar_stub(conn, sql, params=None):
            if "count(*) FROM pg_largeobject_metadata" in sql:
                return 42
            if "pg_lo_size" in sql:
                return "500 MB"
            return 0
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.detect_pg_version", return_value=160000), \
             patch("migration_helpers.scalar", side_effect=scalar_stub), \
             patch("migration_helpers.query", return_value=[]), \
             patch("migration_helpers.check_driver"):
            cmd_blockers(_make_args())
        out = capsys.readouterr().out
        assert "LARGE_OBJECTS" in out
        assert "Found 1 items" in out

    def test_zero_large_objects_skipped(self, capsys):
        conn = MagicMock()
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.detect_pg_version", return_value=160000), \
             patch("migration_helpers.scalar", return_value=0), \
             patch("migration_helpers.query", return_value=[]), \
             patch("migration_helpers.check_driver"):
            cmd_blockers(_make_args())
        out = capsys.readouterr().out
        assert "LARGE_OBJECTS" not in out


class TestCmdBlockersMaterializedView:
    def test_detects_matview(self, capsys):
        conn = MagicMock()
        def query_stub(conn, sql, params=None):
            if "relkind = 'm'" in sql:
                return [{"schema_name": "public", "object_name": "mv", "size": "10 MB"}]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.detect_pg_version", return_value=160000), \
             patch("migration_helpers.scalar", return_value=0), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_blockers(_make_args())
        out = capsys.readouterr().out
        assert "MATERIALIZED_VIEW" in out
        assert "LOW" in out


class TestCmdBlockersSequences:
    def test_detects_sequences_as_info(self, capsys):
        conn = MagicMock()
        def query_stub(conn, sql, params=None):
            if "relkind = 'S'" in sql:
                return [{"schema_name": "public", "object_name": "users_id_seq"}]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.detect_pg_version", return_value=160000), \
             patch("migration_helpers.scalar", return_value=0), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_blockers(_make_args())
        out = capsys.readouterr().out
        assert "SEQUENCE" in out
        assert "INFO" in out
        # Sequences shouldn't block; INFO-only should report VIABLE
        assert "LOGICAL REPLICATION VIABLE" in out


class TestCmdBlockersEventTrigger:
    def test_detects_event_trigger(self, capsys):
        conn = MagicMock()
        def query_stub(conn, sql, params=None):
            if "pg_event_trigger" in sql:
                return [{"object_name": "audit_trg", "event": "ddl_command_end"}]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.detect_pg_version", return_value=160000), \
             patch("migration_helpers.scalar", return_value=0), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_blockers(_make_args())
        out = capsys.readouterr().out
        assert "EVENT_TRIGGER" in out


class TestCmdBlockersHybridVsActionRequired:
    def test_unlogged_means_hybrid(self, capsys):
        conn = MagicMock()
        def query_stub(conn, sql, params=None):
            if "relpersistence = 'u'" in sql:
                return [{"schema_name": "s", "object_name": "t", "size": "1 MB"}]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.detect_pg_version", return_value=160000), \
             patch("migration_helpers.scalar", return_value=0), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_blockers(_make_args())
        out = capsys.readouterr().out
        assert "HYBRID MIGRATION REQUIRED" in out

    def test_high_but_not_unlogged_or_inheritance_is_action_required(self, capsys):
        """A HIGH-severity NO_PRIMARY_KEY (not unlogged/inheritance) -> ACTION REQUIRED."""
        conn = MagicMock()
        def query_stub(conn, sql, params=None):
            if "pk.oid IS NULL" in sql and "relpersistence = 'p'" in sql:
                return [{
                    "schema_name": "s", "object_name": "t",
                    "size": "1 MB", "replica_identity": "default",
                }]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.detect_pg_version", return_value=160000), \
             patch("migration_helpers.scalar", return_value=0), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_blockers(_make_args())
        out = capsys.readouterr().out
        assert "ACTION REQUIRED" in out


class TestCmdBlockersSchemaFilter:
    def test_schema_list_is_parsed_and_passed_as_params(self, capsys):
        conn = MagicMock()
        seen_params = []
        def query_stub(conn, sql, params=None):
            seen_params.append((sql[:80], params))
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.detect_pg_version", return_value=160000), \
             patch("migration_helpers.scalar", return_value=0), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_blockers(_make_args(schemas="public, analytics"))
        # At least one schema-filtered query should have params=['public','analytics']
        assert any(p == ["public", "analytics"] for _, p in seen_params)


class TestCmdBlockersJsonOutput:
    def test_writes_json(self, tmp_path):
        conn = MagicMock()
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.detect_pg_version", return_value=160000), \
             patch("migration_helpers.scalar", return_value=0), \
             patch("migration_helpers.query", return_value=[]), \
             patch("migration_helpers.check_driver"):
            outfile = tmp_path / "blk.json"
            cmd_blockers(_make_args(output=str(outfile)))
        assert json.loads(outfile.read_text()) == []


# ==========================================================================
# cmd_replication_check
# ==========================================================================


def _rep_scalar_stub(wal_level="logical", max_slots="10", used_slots="0",
                     max_senders="10", active_senders="0"):
    def scalar_stub(conn, sql, params=None):
        if "wal_level" in sql:
            return wal_level
        if "max_replication_slots" in sql:
            return max_slots
        if "count(*) FROM pg_replication_slots" in sql:
            return used_slots
        if "max_wal_senders" in sql:
            return max_senders
        if "count(*) FROM pg_stat_replication" in sql:
            return active_senders
        return None
    return scalar_stub


class TestCmdReplicationCheckReady:
    def test_all_green(self, capsys):
        conn = MagicMock()
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar", side_effect=_rep_scalar_stub()), \
             patch("migration_helpers.query", return_value=[]), \
             patch("migration_helpers.check_driver"):
            cmd_replication_check(_make_args())
        out = capsys.readouterr().out
        assert "[PASS] WAL level = logical" in out
        assert "[PASS] Replication slots: 0/10" in out
        assert "[PASS] WAL senders: 0/10" in out
        assert "RESULT: READY" in out


class TestCmdReplicationCheckFail:
    def test_wal_level_not_logical(self, capsys):
        conn = MagicMock()
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar",
                   side_effect=_rep_scalar_stub(wal_level="replica")), \
             patch("migration_helpers.query", return_value=[]), \
             patch("migration_helpers.check_driver"):
            cmd_replication_check(_make_args())
        out = capsys.readouterr().out
        assert "[FAIL] WAL level = replica" in out
        assert "RESULT: NOT READY" in out
        assert "ALTER SYSTEM SET wal_level = logical" in out

    def test_replication_slots_exhausted(self, capsys):
        conn = MagicMock()
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar",
                   side_effect=_rep_scalar_stub(max_slots="3", used_slots="3")), \
             patch("migration_helpers.query", return_value=[]), \
             patch("migration_helpers.check_driver"):
            cmd_replication_check(_make_args())
        out = capsys.readouterr().out
        assert "[FAIL] Replication slots: 3/3" in out
        assert "Increase max_replication_slots" in out

    def test_wal_senders_exhausted(self, capsys):
        conn = MagicMock()
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar",
                   side_effect=_rep_scalar_stub(max_senders="2", active_senders="2")), \
             patch("migration_helpers.query", return_value=[]), \
             patch("migration_helpers.check_driver"):
            cmd_replication_check(_make_args())
        out = capsys.readouterr().out
        assert "[FAIL] WAL senders: 2/2" in out
        assert "Increase max_wal_senders" in out

    def test_tables_without_pk_cause_fail(self, capsys):
        conn = MagicMock()
        def query_stub(conn, sql, params=None):
            if "pk.oid IS NULL" in sql:
                return [{"table_name": "public.t", "replica_identity": "default"}]
            if "pg_publication" in sql:
                return []
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar", side_effect=_rep_scalar_stub()), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_replication_check(_make_args(verbose=True))
        out = capsys.readouterr().out
        assert "Tables needing PK/identity: 1" in out
        assert "[FAIL]" in out
        assert "public.t" in out
        assert "identity=default" in out
        assert "RESULT: NOT READY" in out


class TestCmdReplicationCheckPublications:
    def test_lists_existing_publications(self, capsys):
        conn = MagicMock()
        def query_stub(conn, sql, params=None):
            if "pk.oid IS NULL" in sql:
                return []
            if "pg_publication" in sql:
                return [{
                    "pubname": "my_pub", "all_tables": False,
                    "pubinsert": True, "pubupdate": True, "pubdelete": True,
                }]
            return []
        with patch("migration_helpers.connect_source", return_value=conn), \
             patch("migration_helpers.scalar", side_effect=_rep_scalar_stub()), \
             patch("migration_helpers.query", side_effect=query_stub), \
             patch("migration_helpers.check_driver"):
            cmd_replication_check(_make_args())
        out = capsys.readouterr().out
        assert "Existing Publications" in out
        assert "my_pub" in out
        assert "all_tables=False" in out
