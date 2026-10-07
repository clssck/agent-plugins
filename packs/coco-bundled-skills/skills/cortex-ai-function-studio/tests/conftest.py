# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Shared fixtures for cortex-ai-function-studio integration tests."""

from __future__ import annotations

import os
import re
import sys
import time
import warnings
from pathlib import Path

import pytest
from snowflake.snowpark import Session
from snowflake.snowpark.exceptions import SnowparkSQLException

# ---------------------------------------------------------------------------
# Make the vendored ``openevolve`` package importable for in-process tests.
#
# ``openevolve`` lives inside the evolve package
# (``.../evolve/openevolve``) and is shipped to Snowflake via the SPROC
# ``IMPORTS`` list as a top-level module — it is NOT pip-installable.  In
# the Snowflake runtime it is already on the path; locally / in CI it is
# not, so the evolve / evolve_agent modes silently fail to register.
#
# Adding the evolve package dir to ``sys.path`` here lets ``import
# openevolve`` resolve in-process so the all-modes benchmark e2e test can
# exercise every mode.  Guarded by an existence check so this is a no-op
# in environments where the vendored package isn't present.
# ---------------------------------------------------------------------------
_EVOLVE_PKG_DIR = (
    Path(__file__).resolve().parent.parent
    / "packages"
    / "snowflake-ai-optimize-evolve"
    / "src"
    / "snowflake_ai_optimize"
    / "evolve"
)
if _EVOLVE_PKG_DIR.is_dir() and str(_EVOLVE_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(_EVOLVE_PKG_DIR))


def pytest_addoption(parser):
    parser.addoption(
        "--connection",
        action="store",
        default="snowhouse",
        help="Snowflake connection name from ~/.snowflake/config.toml",
    )


# ---------------------------------------------------------------------------
# Run identity: branch slug + run ID make each CI run's objects unique and
# allow cleanup to be scoped per-branch (no cross-branch interference).
# ---------------------------------------------------------------------------


def _resolve_run_env():
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if run_id:
        branch = os.environ.get("GITHUB_HEAD_REF") or os.environ.get(
            "GITHUB_REF_NAME", ""
        )
        branch_slug = re.sub(r"[^A-Za-z0-9]", "_", branch)[:30].upper()
    else:
        branch_slug = "LOCAL"
        run_id = str(int(time.time()))
    # When pytest-xdist distributes tests across workers each worker gets its
    # own process and therefore its own module-level state.  Append the worker
    # id (gw0, gw1, …) so Snowflake objects created by different workers never
    # share the same name and race each other during setup/teardown.
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "")
    if worker_id:
        worker_suffix = re.sub(r"[^A-Za-z0-9]", "_", worker_id).upper()
        run_id = f"{run_id}_{worker_suffix}"
    return branch_slug, run_id


_BRANCH_SLUG, _RUN_ID = _resolve_run_env()
_RUN_KEY = f"{_BRANCH_SLUG}_{_RUN_ID}"
# The raw GitHub Actions run ID, without any worker suffix.  Used by the
# cleanup helper to avoid dropping live objects that belong to a sibling
# worker running in the same CI job.
_GITHUB_RUN_ID = os.environ.get("GITHUB_RUN_ID", "")


@pytest.fixture(scope="session")
def run_key():
    """Return the unique identifier for this test run.

    ``{branch}_{run_id}`` in CI, ``local_{ts}`` locally.
    """
    return _RUN_KEY


# ---------------------------------------------------------------------------
# Per-module stale-object cleanup
# ---------------------------------------------------------------------------


def _cleanup_stale_objects(
    session, db, schema, *, stages=None, tables=None, functions=None, experiments=None
):
    """Drop stale test objects from previous runs **on the same branch**.

    Pass base names without any suffix (e.g. ``"TEST_CLI_E2E_STAGE"``).
    The function automatically constructs a LIKE pattern scoped to the
    current branch (``{base}_{branch_slug}_%``).

    Cross-branch objects are never matched, so concurrent CI runs on
    different branches cannot interfere with each other.

    Same-run objects (ending with ``_{_RUN_ID}``) are ALSO dropped here
    because GitHub Actions retains the same ``GITHUB_RUN_ID`` across
    workflow re-runs.  A previous attempt of the same workflow run that
    failed mid-setup (e.g. CREATE FUNCTION succeeded but a subsequent
    SET TAG raced with another test's teardown) would leak its
    half-created objects under the current run's name; the next attempt
    would then hit ``Object 'X_RUNID' already exists`` errors when its
    fixture tried to create the same name.  Earlier code skipped the
    ``_RUN_ID`` suffix here to avoid races within a single attempt, but
    cleanup_stale runs at fixture START — BEFORE the test creates its
    objects — so dropping a same-name object can only match a previous
    attempt's orphan.  The DROP IF EXISTS is a no-op in the happy
    path.  See PR #2324 for the rerun-flake reproduction.

    When pytest-xdist runs tests in parallel, different workers each set
    up their own module fixtures and therefore create their own Snowflake
    objects (names include the worker suffix, e.g. ``_GW0``, ``_GW1``).
    Objects belonging to a *sibling* worker of the current CI run must
    NOT be dropped — only objects from previous runs or from the current
    worker's own run (re-run scenario) are eligible.
    """
    fq = lambda name: f"{db}.{schema}.{name}"

    def _is_sibling_worker_object(obj_name: str) -> bool:
        """Return True when *obj_name* belongs to another worker of this run.

        We must keep those objects alive so the sibling worker can use them.
        """
        if not _GITHUB_RUN_ID:
            # Not running under GitHub Actions — no parallel workers.
            return False
        # If this CI run's ID doesn't appear in the name it's from a prior run.
        if _GITHUB_RUN_ID not in obj_name:
            return False
        # The name contains our run ID.  If it also matches the current
        # worker's full run key (_RUN_ID includes the worker suffix) then it's
        # *our own* object from a previous attempt — safe to drop.
        return not obj_name.upper().endswith(f"_{_RUN_ID}")

    for base in stages or []:
        pattern = f"{base}_{_BRANCH_SLUG}_%"
        for row in session.sql(
            f"SHOW STAGES LIKE '{pattern}' IN SCHEMA {db}.{schema}"
        ).collect():
            if _is_sibling_worker_object(row["name"]):
                continue
            try:
                session.sql(f"DROP STAGE IF EXISTS {fq(row['name'])}").collect()
            except SnowparkSQLException as exc:
                warnings.warn(
                    f"cleanup: failed to drop stage {row['name']}: {exc}", stacklevel=2
                )

    for base in tables or []:
        pattern = f"{base}_{_BRANCH_SLUG}_%"
        for row in session.sql(
            f"SHOW TABLES LIKE '{pattern}' IN SCHEMA {db}.{schema}"
        ).collect():
            if _is_sibling_worker_object(row["name"]):
                continue
            try:
                session.sql(f"DROP TABLE IF EXISTS {fq(row['name'])}").collect()
            except SnowparkSQLException as exc:
                warnings.warn(
                    f"cleanup: failed to drop table {row['name']}: {exc}", stacklevel=2
                )

    for base in functions or []:
        pattern = f"{base}_{_BRANCH_SLUG}_%"
        for row in session.sql(
            f"SHOW USER FUNCTIONS LIKE '{pattern}' IN SCHEMA {db}.{schema}"
        ).collect():
            args = row["arguments"]
            name = args[: args.index("(")]
            if _is_sibling_worker_object(name):
                continue
            sig = args[args.index("(") : args.index(" RETURN ")]
            try:
                session.sql(f"DROP FUNCTION IF EXISTS {fq(name)}{sig}").collect()
            except SnowparkSQLException as exc:
                warnings.warn(
                    f"cleanup: failed to drop function {name}{sig}: {exc}", stacklevel=2
                )

    for base in experiments or []:
        pattern = f"{base}_{_BRANCH_SLUG}_%"
        try:
            rows = session.sql(
                f"SHOW EXPERIMENTS LIKE '{pattern}' IN SCHEMA {db}.{schema}"
            ).collect()
        except SnowparkSQLException:
            continue
        for row in rows:
            if _is_sibling_worker_object(row["name"]):
                continue
            try:
                session.sql(f"DROP EXPERIMENT IF EXISTS {fq(row['name'])}").collect()
            except SnowparkSQLException as exc:
                warnings.warn(
                    f"cleanup: failed to drop experiment {row['name']}: {exc}",
                    stacklevel=2,
                )


@pytest.fixture(scope="session")
def cleanup_stale():
    """Provide a per-module cleanup callable to test fixtures."""
    return _cleanup_stale_objects


# ---------------------------------------------------------------------------
# Shared e2e helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def session(request):
    conn_name = request.config.getoption("--connection", default="snowhouse")
    sess = Session.builder.config("connection_name", conn_name).create()
    yield sess
    sess.close()
