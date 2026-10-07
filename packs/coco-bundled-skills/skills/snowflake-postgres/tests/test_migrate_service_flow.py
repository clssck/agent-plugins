"""End-to-end --source-service / --target-service wiring tests.

The pg_common contract: when a user passes --source-service NAME with no
--host etc, _apply_source_service mutates args from ~/.pg_service.conf BEFORE
connect_source resolves the password. The same is true for --target-service.

But several scripts validated args.host / args.target_host BEFORE calling
connect_source / connect_target, so --source-service alone failed with
"Source connection params required" before _apply_*_service ever ran. Other
scripts (migration_monitor.py) bypassed connect_source/target entirely and
called connect() with raw args, so even a populated service profile got
ignored. run_assessment.py never wired in --source-service at all.

These tests pin the contract end-to-end: invoke each script's main() with
ONLY --source-service / --target-service flags, assert the service profile
flows through validation into connect_*. Sentinel exception in connect_*
proves the validation gate let us through.

Pre-fix: these tests fail with SystemExit (parser.error) before the sentinel.
Post-fix: SentinelReachedConnect propagates cleanly.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest


# --- Shared fixtures ---


class SentinelReachedConnect(Exception):
    """Raised by mocked connect_source / connect_target / connect to signal
    the script reached the connect call (proving validation passed)."""


@pytest.fixture
def service_conf(tmp_path, monkeypatch):
    """Stub ~/.pg_service.conf with prod_source + sf_target entries; patch
    pg_common to read from it. Also stubs ~/.pgpass to a known empty file
    so password resolution doesn't error on the missing-file path."""
    conf = tmp_path / ".pg_service.conf"
    conf.write_text(
        "[prod_source]\n"
        "host=src.example.com\n"
        "port=5432\n"
        "dbname=proddb\n"
        "user=migrator\n"
        "[sf_target]\n"
        "host=sf-pg.example.com\n"
        "port=5432\n"
        "dbname=postgres\n"
        "user=admin\n"
    )
    pgpass = tmp_path / ".pgpass"
    pgpass.write_text(
        "src.example.com:5432:proddb:migrator:src_pw\n"
        "sf-pg.example.com:5432:postgres:admin:tgt_pw\n"
    )
    pgpass.chmod(0o600)
    monkeypatch.setattr("pg_common.PG_SERVICE_FILE", conf)
    monkeypatch.setattr("pg_common.PGPASS_FILE", pgpass)
    # Strip stray env vars that could mask the test
    for var in (
        "SOURCE_PGHOST", "SOURCE_PGPORT", "SOURCE_PGDATABASE", "SOURCE_PGUSER",
        "TARGET_PGHOST", "TARGET_PGPORT", "TARGET_PGDATABASE", "TARGET_PGUSER",
        "PGPASSWORD", "SOURCE_PGPASSWORD", "TARGET_PGPASSWORD",
        "SOURCE_PG_SERVICE", "TARGET_PG_SERVICE",
    ):
        monkeypatch.delenv(var, raising=False)
    return conf


def _argv(*args):
    return ["script.py", *args]


def _trip_on_connect(monkeypatch, module_name, *attrs):
    """Patch each attr (e.g., 'connect_source') on the named script module
    to raise SentinelReachedConnect when called. Skip silently if attr not
    present so per-script tests can share the same helper."""
    mod = sys.modules.get(module_name)
    if mod is None:
        return
    for attr in attrs:
        if hasattr(mod, attr):
            monkeypatch.setattr(f"{module_name}.{attr}", lambda *a, **kw: (_ for _ in ()).throw(SentinelReachedConnect()))


# --- validate_migration.py ---


class TestValidateMigrationServiceFlow:
    def test_service_only_args_reach_connect_source(self, service_conf, monkeypatch):
        import validate_migration
        monkeypatch.setattr(
            validate_migration, "connect_source",
            lambda args: (_ for _ in ()).throw(SentinelReachedConnect("src reached")),
        )
        monkeypatch.setattr(sys, "argv", _argv(
            "--source-service", "prod_source",
            "--target-service", "sf_target",
        ))
        with pytest.raises(SentinelReachedConnect, match="src reached"):
            validate_migration.main()


# --- validate_schema_compatibility.py ---


class TestValidateSchemaCompatibilityServiceFlow:
    def test_service_only_args_reach_connect(self, service_conf, monkeypatch):
        import validate_schema_compatibility
        # Source-only script — uses connect() not connect_source
        monkeypatch.setattr(
            validate_schema_compatibility, "connect",
            lambda *a, **kw: (_ for _ in ()).throw(SentinelReachedConnect()),
        )
        monkeypatch.setattr(sys, "argv", _argv("--source-service", "prod_source"))
        with pytest.raises(SentinelReachedConnect):
            validate_schema_compatibility.main()


# --- generate_hybrid_plan.py ---


class TestGenerateHybridPlanServiceFlow:
    def test_service_only_args_reach_connect(self, service_conf, monkeypatch, tmp_path):
        import generate_hybrid_plan
        monkeypatch.setattr(
            generate_hybrid_plan, "connect",
            lambda *a, **kw: (_ for _ in ()).throw(SentinelReachedConnect()),
        )
        monkeypatch.setattr(sys, "argv", _argv(
            "--source-service", "prod_source",
            "--output", str(tmp_path / "plan"),
        ))
        with pytest.raises(SentinelReachedConnect):
            generate_hybrid_plan.main()


# --- cutover_tools.py ---


class TestCutoverToolsServiceFlow:
    def test_sequences_subcommand_service_only(self, service_conf, monkeypatch, tmp_path):
        import cutover_tools
        monkeypatch.setattr(
            cutover_tools, "connect_source",
            lambda args: (_ for _ in ()).throw(SentinelReachedConnect()),
        )
        monkeypatch.setattr(sys, "argv", _argv(
            "sequences",
            "--source-service", "prod_source",
            "-o", str(tmp_path / "sync.sql"),
        ))
        with pytest.raises(SentinelReachedConnect):
            cutover_tools.main()


# --- prepare_target.py ---


class TestPrepareTargetServiceFlow:
    def test_preflight_target_service_only(self, service_conf, monkeypatch):
        import prepare_target
        monkeypatch.setattr(
            prepare_target, "connect_target",
            lambda args: (_ for _ in ()).throw(SentinelReachedConnect()),
        )
        monkeypatch.setattr(sys, "argv", _argv(
            "preflight-check",
            "--target-service", "sf_target",
            "--schemas", "public,analytics",
        ))
        with pytest.raises(SentinelReachedConnect):
            prepare_target.main()

    def test_extensions_dual_service_only(self, service_conf, monkeypatch):
        import prepare_target
        monkeypatch.setattr(
            prepare_target, "connect_source",
            lambda args: (_ for _ in ()).throw(SentinelReachedConnect("src reached")),
        )
        monkeypatch.setattr(sys, "argv", _argv(
            "extensions",
            "--source-service", "prod_source",
            "--target-service", "sf_target",
        ))
        with pytest.raises(SentinelReachedConnect, match="src reached"):
            prepare_target.main()

    def test_check_data_target_service_only(self, service_conf, monkeypatch):
        import prepare_target
        monkeypatch.setattr(
            prepare_target, "connect_target",
            lambda args: (_ for _ in ()).throw(SentinelReachedConnect()),
        )
        monkeypatch.setattr(sys, "argv", _argv(
            "check-data",
            "--target-service", "sf_target",
            "--schemas", "public",
        ))
        with pytest.raises(SentinelReachedConnect):
            prepare_target.main()

    def test_clean_schemas_target_service_only(self, service_conf, monkeypatch):
        import prepare_target
        monkeypatch.setattr(
            prepare_target, "connect_target",
            lambda args: (_ for _ in ()).throw(SentinelReachedConnect()),
        )
        monkeypatch.setattr(sys, "argv", _argv(
            "clean-schemas",
            "--target-service", "sf_target",
            "--schemas", "analytics",
            "--confirm",
        ))
        with pytest.raises(SentinelReachedConnect):
            prepare_target.main()


# --- post_migration_cleanup.py ---


class TestPostMigrationCleanupServiceFlow:
    def test_target_only_service_flow(self, service_conf, monkeypatch, capsys):
        """--target-only + --target-service only should NOT silently skip work
        because args.target_host is empty pre-service-resolution. After fix,
        _apply_target_service fills target_host and the cleanup runs."""
        import post_migration_cleanup
        monkeypatch.setattr(
            post_migration_cleanup, "connect_target",
            lambda args: (_ for _ in ()).throw(SentinelReachedConnect()),
        )
        monkeypatch.setattr(sys, "argv", _argv(
            "--target-service", "sf_target",
            "--target-only",
            "--dry-run",
        ))
        with pytest.raises(SentinelReachedConnect):
            post_migration_cleanup.main()

    def test_source_only_service_flow(self, service_conf, monkeypatch, capsys):
        import post_migration_cleanup
        monkeypatch.setattr(
            post_migration_cleanup, "connect_source",
            lambda args: (_ for _ in ()).throw(SentinelReachedConnect()),
        )
        monkeypatch.setattr(sys, "argv", _argv(
            "--source-service", "prod_source",
            "--source-only",
            "--dry-run",
        ))
        with pytest.raises(SentinelReachedConnect):
            post_migration_cleanup.main()


# --- migration_monitor.py ---


class TestMigrationMonitorServiceFlow:
    """migration_monitor.py used to call bare connect(args.host, ...) — bypassing
    both _apply_*_service AND resolve_*_password. After fix, the service profile
    must populate args.host / args.target_host before connect runs.

    cmd_sync / cmd_replication wrap connect() in a `while True:` loop with a
    broad `except Exception` that swallows + retries every 5s. To break out
    cleanly in tests, we raise KeyboardInterrupt — explicitly handled at line
    117 with a `break`. Then we inspect the captured args to verify the
    service profile was actually applied (pre-fix: args.host = ''; post-fix:
    args.host = service-resolved value)."""

    def test_sync_subcommand_resolves_target_host_from_service(self, service_conf, monkeypatch):
        """Post-fix: --target-service sf_target populates args.target_host
        from ~/.pg_service.conf so connect() gets the right host. Pre-fix:
        args.target_host stays empty and connect() gets called with ''."""
        import migration_monitor
        captured = {}

        def trip_bare(host, port, dbname, user, pw, sslmode, sslrootcert=None, hostaddr=None):
            captured['host'] = host
            captured['dbname'] = dbname
            captured['user'] = user
            captured['sslrootcert'] = sslrootcert
            captured['hostaddr'] = hostaddr
            raise KeyboardInterrupt()

        monkeypatch.setattr(migration_monitor, "connect", trip_bare)
        monkeypatch.setattr(sys, "argv", _argv(
            "sync",
            "--target-service", "sf_target",
        ))
        # main returns normally after KeyboardInterrupt break in cmd_sync
        migration_monitor.main()
        assert captured.get('host') == 'sf-pg.example.com', (
            f"Expected target host from service file, got: {captured.get('host')!r}"
        )
        assert captured['dbname'] == 'postgres'
        assert captured['user'] == 'admin'

    def test_replication_subcommand_resolves_source_host_from_service(self, service_conf, monkeypatch):
        import migration_monitor
        captured = {}

        def trip_bare(host, port, dbname, user, pw, sslmode, sslrootcert=None, hostaddr=None):
            captured['host'] = host
            captured['dbname'] = dbname
            captured['user'] = user
            captured['sslrootcert'] = sslrootcert
            captured['hostaddr'] = hostaddr
            raise KeyboardInterrupt()

        monkeypatch.setattr(migration_monitor, "connect", trip_bare)
        monkeypatch.setattr(sys, "argv", _argv(
            "replication",
            "--source-service", "prod_source",
        ))
        migration_monitor.main()
        assert captured.get('host') == 'src.example.com', (
            f"Expected source host from service file, got: {captured.get('host')!r}"
        )
        assert captured['dbname'] == 'proddb'
        assert captured['user'] == 'migrator'


# --- test_connectivity.py ---


class TestConnectivityServiceFlow:
    def test_service_only_args_reach_probes(self, service_conf, monkeypatch):
        """test_connectivity uses bare probes (probe_dns, probe_tcp, etc.).
        Before _apply_*_service, args.host is empty → probes are skipped.
        After fix, probes fire against the service-resolved host."""
        import test_connectivity
        # probe_dns is the first thing called when args.host is set
        monkeypatch.setattr(
            test_connectivity, "probe_dns",
            lambda host: (_ for _ in ()).throw(SentinelReachedConnect(f"dns:{host}")),
        )
        monkeypatch.setattr(sys, "argv", _argv(
            "--source-service", "prod_source",
        ))
        with pytest.raises(SentinelReachedConnect, match="dns:src.example.com"):
            test_connectivity.main()


# --- run_assessment.py ---


class TestRunAssessmentServiceFlow:
    """run_assessment.py used its own custom argparse with no --source-service
    flag at all. After fix, it uses add_source_args (which provides the flag)
    plus _apply_source_service before validation."""

    def test_source_service_flag_parses(self, service_conf, monkeypatch):
        """The --source-service flag must exist (added via add_source_args).
        Pre-fix, argparse rejects the unknown flag → SystemExit (this is the
        signal the bug is present). Post-fix, the flag parses + the script
        proceeds to call run_assessment(args.host, ...) with the resolved host."""
        import run_assessment
        # Stub the inner run_assessment function so we don't actually connect
        monkeypatch.setattr(
            run_assessment, "run_assessment",
            lambda *a, **kw: (_ for _ in ()).throw(SentinelReachedConnect()),
        )
        monkeypatch.setattr(sys, "argv", _argv(
            "--source-service", "prod_source",
            "--no-open",  # don't try to open the browser even on early exit
        ))
        with pytest.raises(SentinelReachedConnect):
            run_assessment.main()

    def test_source_service_resolves_host(self, service_conf, monkeypatch):
        """Post-fix: --source-service prod_source must populate args.host
        from ~/.pg_service.conf so run_assessment(host, ...) gets the right
        value. Captures the host arg and asserts it matches the service entry."""
        import run_assessment
        captured = {}

        def capture(host, port, dbname, user, password, sslmode, schemas,
                    sslrootcert=None, hostaddr=None):
            captured['host'] = host
            captured['port'] = port
            captured['dbname'] = dbname
            captured['user'] = user
            captured['sslrootcert'] = sslrootcert
            captured['hostaddr'] = hostaddr
            raise SentinelReachedConnect()

        monkeypatch.setattr(run_assessment, "run_assessment", capture)
        monkeypatch.setattr(sys, "argv", _argv(
            "--source-service", "prod_source",
            "--no-open",
        ))
        with pytest.raises(SentinelReachedConnect):
            run_assessment.main()
        assert captured['host'] == 'src.example.com', (
            f"Expected host from service file, got: {captured.get('host')!r}"
        )
        assert captured['dbname'] == 'proddb'
        assert captured['user'] == 'migrator'


class TestRunAssessmentMetadata:
    def test_detect_platform_recognizes_neon(self, monkeypatch):
        import run_assessment

        def fake_scalar(_conn, sql, params=None):
            if "neon.timeline_id" in sql:
                return "timeline-123"
            return None

        monkeypatch.setattr(run_assessment, "scalar", fake_scalar)
        assert run_assessment.detect_platform(object()) == "Neon"

    def test_collect_report_metadata_prefers_configured_endpoint(self, monkeypatch):
        import run_assessment

        monkeypatch.setattr(
            run_assessment,
            "query",
            lambda _conn, _sql, params=None: [{
                "generated_at": "2026-05-12 09:00:00 UTC",
                "source_host": "169.254.254.254/32",
                "source_port": 5432,
                "database": "neondb",
                "connected_user": "neondb_owner",
                "pg_version": "PostgreSQL 17.8",
                "pg_version_num": 170008,
            }],
        )
        monkeypatch.setattr(run_assessment, "detect_platform", lambda _conn: "Neon")

        meta = run_assessment.collect_report_metadata(
            object(),
            170008,
            display_host="ep-twilight-poetry-anuw746p.c-6.us-east-1.aws.neon.tech",
            display_port=5432,
            display_hostaddr="100.51.95.243",
        )

        assert meta["source_host"] == (
            "ep-twilight-poetry-anuw746p.c-6.us-east-1.aws.neon.tech "
            "(via 100.51.95.243)"
        )
        assert meta["source_hostaddr"] == "100.51.95.243"
        assert meta["source_port"] == 5432
        assert meta["source_platform"] == "Neon"


class TestRunAssessmentRecommendations:
    VALID_COMPUTE_FAMILIES = {
        "BURST_XS", "BURST_S", "BURST_M",
        "STANDARD_M", "STANDARD_L", "STANDARD_XL", "STANDARD_2XL",
        "STANDARD_4XL", "STANDARD_8XL", "STANDARD_12XL", "STANDARD_24XL",
        "HIGHMEM_L", "HIGHMEM_XL", "HIGHMEM_2XL", "HIGHMEM_4XL",
        "HIGHMEM_8XL", "HIGHMEM_12XL", "HIGHMEM_16XL", "HIGHMEM_24XL",
        "HIGHMEM_32XL", "HIGHMEM_48XL",
    }

    def test_recommendations_use_valid_compute_families(self):
        import run_assessment

        recs = run_assessment.calculate_instance_recommendations({
            "database_overview": {"size_bytes": 75 * 1024**3, "table_count": 120},
            "complexity_score": 75,
            "postgis_info": {"installed": False, "geometry_columns": 0},
            "extensions": [],
        })

        families = {recs["compute_pool"]["recommended"]}
        families.update(alt["pool"] for alt in recs["compute_pool"]["alternatives"])

        assert families <= self.VALID_COMPUTE_FAMILIES, (
            f"Found invalid compute family recommendations: {sorted(families - self.VALID_COMPUTE_FAMILIES)}"
        )

    @pytest.mark.parametrize(
        ("postgis_info", "extensions"),
        [
            ({"installed": True, "geometry_columns": 12}, []),
            ({"installed": False, "geometry_columns": 0}, [{"name": "vector", "version": "0.8.0"}]),
        ],
    )
    def test_memory_heavy_workloads_require_intent_before_recommending_ha(
        self, postgis_info, extensions
    ):
        import run_assessment

        recs = run_assessment.calculate_instance_recommendations({
            "database_overview": {"size_bytes": 20 * 1024**3, "table_count": 50},
            "complexity_score": 25,
            "postgis_info": postgis_info,
            "extensions": extensions,
        })

        assert recs["high_availability"]["recommended"] is False
        assert (
            recs["high_availability"]["timing"]
            == "after validation, before cutover if target is production"
        )
        assert "confirm intent" in recs["high_availability"]["rationale"]
        expected_signal = "PostGIS" if postgis_info["installed"] else "pgvector"
        assert expected_signal in recs["high_availability"]["rationale"]

    def test_production_target_recommends_ha_after_validation(self):
        import run_assessment

        recs = run_assessment.calculate_instance_recommendations({
            "database_overview": {"size_bytes": 20 * 1024**3, "table_count": 50},
            "complexity_score": 25,
            "postgis_info": {"installed": True, "geometry_columns": 12},
            "extensions": [],
            "migration_context": {"target_role": "production"},
        })

        assert recs["high_availability"]["recommended"] is True
        assert recs["high_availability"]["timing"] == "after validation, before cutover"
        assert "production" in recs["high_availability"]["rationale"].lower()
        assert "PostGIS" in recs["high_availability"]["rationale"]


class TestRunAssessmentBlockerMessaging:
    @staticmethod
    def _sample_assessment_data(role_name="app_superuser", source_platform="Self-managed PostgreSQL"):
        return {
            "report_metadata": {
                "database": "appdb",
                "source_host": "src.example.com",
                "source_port": 5432,
                "connected_user": "migrator",
                "source_platform": source_platform,
                "pg_version_num": 160000,
                "generated_at": "2026-05-08T12:00:00Z",
            },
            "database_overview": {
                "size_pretty": "12 GB",
                "size_bytes": 12 * 1024**3,
                "table_count": 42,
                "index_count": 84,
                "total_rows": 123456,
            },
            "replication_readiness": {
                "wal_level_ok": True,
                "wal_level": "logical",
                "used_replication_slots": 1,
                "max_replication_slots": 10,
            },
            "blockers": {
                "tables_without_pk_count": 0,
                "tables_without_pk": [],
                "large_objects": {"count": 0},
            },
            "unsupported_extensions": [],
            "unsupported_languages": [],
            "unlogged_tables": [],
            "inherited_tables": [
                {"schema": "public", "parent_table": "events", "child_table": "events_archive"}
            ],
            "sequences": [],
            "materialized_views": [],
            "foreign_tables": [],
            "extensions": [],
            "roles": [
                {
                    "name": role_name,
                    "can_login": True,
                    "superuser": True,
                    "create_db": True,
                    "replication": False,
                }
            ],
            "database_settings": [],
            "tables": [],
            "postgres_owned": [],
            "complexity_score": 80,
        }

    def test_generate_html_report_explains_superuser_and_inheritance(self, tmp_path):
        import run_assessment

        data = self._sample_assessment_data()
        out = tmp_path / "assessment.html"
        run_assessment.generate_html_report(data, str(out))
        html = out.read_text()

        assert "Blockers & Warnings" in html
        assert "snowflake_admin" in html
        assert "not a drop-in replacement" in html
        assert "different from partitioning" in html
        assert "app_superuser" in html
        assert "Potential hybrid candidate" in html
        assert "generate_hybrid_plan.py" in html

    def test_print_text_summary_explains_superuser_and_inheritance(self, capsys):
        import run_assessment

        data = self._sample_assessment_data()
        run_assessment.print_text_summary(data)
        out = capsys.readouterr().out

        assert "snowflake_admin" in out
        assert "drop-in replacement" in out
        assert "different from partitioning" in out
        assert "Potential hybrid candidate" in out
        assert "generate_hybrid_plan.py" in out

    def test_provider_managed_superuser_role_is_not_treated_as_blocker_in_html(self, tmp_path):
        import run_assessment

        data = self._sample_assessment_data(
            role_name="crunchy_superuser",
            source_platform="Crunchy Bridge",
        )
        out = tmp_path / "assessment.html"
        run_assessment.generate_html_report(data, str(out))
        html = out.read_text()

        assert "Known provider-managed admin role(s) detected" in html
        assert "crunchy_superuser" in html
        assert "not treated as customer blockers" in html
        assert "Any other SUPERUSER roles still require review" in html
        assert "not a drop-in replacement for each source superuser role" not in html

    def test_provider_managed_superuser_role_is_not_treated_as_blocker_in_text(self, capsys):
        import run_assessment

        data = self._sample_assessment_data(
            role_name="crunchy_superuser",
            source_platform="Crunchy Bridge",
        )
        run_assessment.print_text_summary(data)
        out = capsys.readouterr().out

        assert "Known provider-managed admin role(s) detected" in out
        assert "crunchy_superuser" in out
        assert "not treated as customer blockers" in out
        assert "Any other SUPERUSER roles still require review" in out
        assert "drop-in replacement" not in out
