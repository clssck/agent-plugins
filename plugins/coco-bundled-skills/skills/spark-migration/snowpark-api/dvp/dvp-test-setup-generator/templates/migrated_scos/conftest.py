"""Pytest configuration for Snowpark Connect (SCOS) tests.

SCOS (Snowpark Connect for Spark) allows running PySpark code on Snowflake
with minimal changes. This conftest provides the SCOS-specific session
fixture and read logic.

Key differences from migrated (Snowpark API):
- Uses snowpark_connect.start_session() and get_session()
- DataFrame APIs are PySpark-compatible (not Snowpark)
- Infrastructure ops still go through the shared snowpark_session

Shared Snowflake infrastructure (snowpark_session, test_stage, upload,
create/load tables, cleanup) lives in the root conftest.py.
"""

import os
import pytest

from snowflake import snowpark_connect
try:
    from conftest import BaseWorkloadTest
except (ModuleNotFoundError, ImportError):
    import importlib.util
    from pathlib import Path

    _ROOT_CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"
    _spec = importlib.util.spec_from_file_location("_dvp_root_conftest", _ROOT_CONFTEST)
    _mod = importlib.util.module_from_spec(_spec)
    assert _spec and _spec.loader
    _spec.loader.exec_module(_mod)

    BaseWorkloadTest = _mod.BaseWorkloadTest


@pytest.fixture(scope="session")
def scos_spark_session(snowpark_session):
    """Create Snowpark Connect (SCOS) Spark session on top of Snowpark.

    Passes the authenticated Snowpark session to the SCOS gRPC server.
    The returned SparkSession uses PySpark-compatible DataFrame APIs
    that execute on Snowflake compute.
    """
    os.environ["SPARK_CONNECT_MODE_ENABLED"] = "1"

    snowpark_connect.start_session(snowpark_session=snowpark_session)
    spark = snowpark_connect.get_session()

    yield spark

    spark.stop()


@pytest.fixture(scope="session")
def db_session(scos_spark_session):
    """Generic session alias — SCOS SparkSession for workload and assertions."""
    return scos_spark_session


@pytest.fixture(scope="session")
def workload_session(db_session):
    """Alias used by BaseIOConfig test methods."""
    return db_session


class BaseScosWorkloadTest(BaseWorkloadTest):
    """SCOS-specific base class for Snowpark Connect migrated workload tests.

    Inherits shared properties, run_workload fixture, and test methods
    from BaseWorkloadTest.  Only _read_output differs (PySpark API).
    """

    def _read_output(self, spark, name, test_stage=None):
        """Read a migrated output — from table or stage depending on type.

        Uses PySpark DataFrame APIs compatible with Snowpark Connect.
        Table names are fully qualified via TABLE_NAMESPACE (set by
        _set_table_namespace fixture in BaseWorkloadTest) because PySpark
        sessions don't inherit Snowflake's current database/schema context.
        """
        if name in self.output_table_names:
            return spark.read.table(f"{self.TABLE_NAMESPACE}.{name}")
        return spark.read.option("header", "true").csv(f"{test_stage}/{name}")
