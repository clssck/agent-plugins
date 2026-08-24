"""Tests for filter_vendor_dump.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "migrate" / "scripts" / "filter_vendor_dump.py"
)


def _run_filter(sql: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=sql,
        text=True,
        capture_output=True,
        check=False,
    )


def test_filters_explicit_neon_platform_roles():
    result = _run_filter(
        "\n".join(
            [
                "CREATE ROLE neon_superuser;",
                "GRANT neon_service TO app_user;",
                "COMMENT ON ROLE cloud_admin IS 'managed';",
                "CREATE ROLE app_user;",
                "ALTER ROLE app_user WITH LOGIN;",
                "",
            ]
        )
    )

    assert result.returncode == 0
    assert "neon_superuser" not in result.stdout
    assert "neon_service" not in result.stdout
    assert "cloud_admin" not in result.stdout
    assert "CREATE ROLE app_user;" in result.stdout
    assert "ALTER ROLE app_user WITH LOGIN;" in result.stdout


def test_stats_are_written_to_stderr_not_stdout():
    result = _run_filter("CREATE ROLE neon_service;\nSELECT 1;\n", "--stats")

    assert result.returncode == 0
    assert result.stdout.strip() == "SELECT 1;"
    assert "FILTER STATISTICS" in result.stderr
    assert "Neon commands filtered:" in result.stderr
