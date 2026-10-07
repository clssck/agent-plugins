#!/usr/bin/env python3
"""Filter vendor-specific commands from pg_dump output.

Supports: Crunchy Bridge, AWS RDS, Azure Database, Google Cloud SQL, Neon.

Usage:
    pg_dump ... | python filter_vendor_dump.py > clean_dump.sql
    python filter_vendor_dump.py input.sql > clean_dump.sql
    python filter_vendor_dump.py --stats input.sql > clean_dump.sql

Filters (in order):
  - Crunchy Bridge / PG 17+: \\restrict, \\unrestrict psql meta-commands
  - AWS RDS: rds.* functions, rds_* roles, "Dumped by ... rds" comments
  - Azure: azure.* functions, azure_* roles
  - Google Cloud SQL: cloudsql* roles
  - Neon: cloud_admin, neon_service, neon_superuser role manipulations
  - Generic: strips SUPERUSER, NOSUPERUSER, REPLICATION, NOREPLICATION,
    BYPASSRLS, NOBYPASSRLS from CREATE/ALTER ROLE lines (unsupported in
    Snowflake Postgres)

Cross-platform notes:
  - stdin/stdout are reconfigured with newline="\\n" so output is LF on every
    OS (matches the bash source on Linux/macOS and avoids CRLF on Windows).
  - No bash builtins, no temp files, no platform-specific paths. Runs on
    native Windows, macOS, Linux, and WSL with no changes.
"""
from __future__ import annotations

import argparse
import re
import sys
from typing import Iterable, TextIO

ROLE_ATTRIBUTES_TO_STRIP = (
    " SUPERUSER",
    " NOSUPERUSER",
    " REPLICATION",
    " NOREPLICATION",
    " BYPASSRLS",
    " NOBYPASSRLS",
)

NEON_ROLES = r"(cloud_admin|neon_service|neon_superuser)"

_CRUNCHY_RE = re.compile(r"^\\(restrict|unrestrict)\b")

_RDS_SELECT_RE = re.compile(r"^\s*SELECT\s+rds\.")
_RDS_CREATE_ROLE_RE = re.compile(r"CREATE ROLE rds_")
_RDS_GRANT_TO_RE = re.compile(r"GRANT.*TO rds_")
_RDS_COMMENT_RE = re.compile(r"^--.*rds")
_RDS_TRIGGER_RE = re.compile(r"rds\.|Dumped by.*rds|rds_")

_AZURE_SELECT_RE = re.compile(r"^\s*SELECT\s+azure\.")
_AZURE_CREATE_ROLE_RE = re.compile(r"CREATE ROLE azure_")
_AZURE_GRANT_TO_RE = re.compile(r"GRANT.*TO azure_")
_AZURE_TRIGGER_RE = re.compile(r"azure\.|azure_")

_GCP_CREATE_ROLE_RE = re.compile(r"CREATE ROLE cloudsql")
_GCP_GRANT_RE = re.compile(r"GRANT.*cloudsql")
_GCP_TRIGGER_RE = re.compile(r"cloudsql")

_NEON_CREATE_ROLE_RE = re.compile(rf'^CREATE ROLE\s+"?{NEON_ROLES}"?')
_NEON_ALTER_ROLE_RE = re.compile(rf'^ALTER ROLE\s+"?{NEON_ROLES}"?')
_NEON_COMMENT_RE = re.compile(rf'^COMMENT ON ROLE\s+"?{NEON_ROLES}"?')
_NEON_GRANT_RE = re.compile(rf"^GRANT\s+.*{NEON_ROLES}")
_NEON_REVOKE_RE = re.compile(rf"^REVOKE\s+.*{NEON_ROLES}")
_NEON_TRIGGER_RE = re.compile(NEON_ROLES)

_ROLE_HEADER_RE = re.compile(r"^(CREATE|ALTER) ROLE\b")


def _strip_role_attrs(line: str) -> str:
    out = line
    for attr in ROLE_ATTRIBUTES_TO_STRIP:
        out = out.replace(attr, "")
    return out


class Stats:
    """Per-category filter counters; output format matches the bash source."""

    def __init__(self) -> None:
        self.crunchy = 0
        self.rds = 0
        self.azure = 0
        self.gcp = 0
        self.neon = 0
        self.role_attrs = 0

    def render(self) -> str:
        bar = "═" * 63
        return (
            "\n"
            f"{bar}\n"
            "FILTER STATISTICS\n"
            f"{bar}\n"
            f"  Crunchy Bridge commands filtered: {self.crunchy}\n"
            f"  AWS RDS commands filtered:        {self.rds}\n"
            f"  Azure commands filtered:          {self.azure}\n"
            f"  Google Cloud SQL filtered:        {self.gcp}\n"
            f"  Neon commands filtered:           {self.neon}\n"
            f"  Role attributes modified:         {self.role_attrs}\n"
            f"{bar}\n"
        )


def process_line(
    line: str,
    stats: Stats,
    out: TextIO,
    err: TextIO,
    verbose: bool,
) -> None:
    """Apply the filter chain to a single line; write result to out, audit to err.

    Order: Crunchy → RDS → Azure → GCP → Neon → role-attr stripping →
    passthrough. First match wins for the filter-out branches; role-attr
    stripping rewrites and passes through.
    """
    if _CRUNCHY_RE.search(line):
        stats.crunchy += 1
        if verbose:
            err.write(f"-- [FILTERED:CRUNCHY] {line}\n")
        return

    if _RDS_TRIGGER_RE.search(line) and (
        _RDS_SELECT_RE.search(line)
        or _RDS_CREATE_ROLE_RE.search(line)
        or _RDS_GRANT_TO_RE.search(line)
        or _RDS_COMMENT_RE.search(line)
    ):
        stats.rds += 1
        if verbose:
            err.write(f"-- [FILTERED:RDS] {line}\n")
        return

    if _AZURE_TRIGGER_RE.search(line) and (
        _AZURE_SELECT_RE.search(line)
        or _AZURE_CREATE_ROLE_RE.search(line)
        or _AZURE_GRANT_TO_RE.search(line)
    ):
        stats.azure += 1
        if verbose:
            err.write(f"-- [FILTERED:AZURE] {line}\n")
        return

    if _GCP_TRIGGER_RE.search(line) and (
        _GCP_CREATE_ROLE_RE.search(line) or _GCP_GRANT_RE.search(line)
    ):
        stats.gcp += 1
        if verbose:
            err.write(f"-- [FILTERED:GCP] {line}\n")
        return

    if _NEON_TRIGGER_RE.search(line) and (
        _NEON_CREATE_ROLE_RE.search(line)
        or _NEON_ALTER_ROLE_RE.search(line)
        or _NEON_COMMENT_RE.search(line)
        or _NEON_GRANT_RE.search(line)
        or _NEON_REVOKE_RE.search(line)
    ):
        stats.neon += 1
        if verbose:
            err.write(f"-- [FILTERED:NEON] {line}\n")
        return

    if _ROLE_HEADER_RE.search(line):
        filtered = _strip_role_attrs(line)
        if filtered != line:
            stats.role_attrs += 1
            if verbose:
                err.write(f"-- [MODIFIED:ROLE_ATTRS] Original: {line}\n")
            out.write(f"{filtered}\n")
            return

    out.write(f"{line}\n")


def process_stream(
    lines: Iterable[str],
    stats: Stats,
    out: TextIO,
    err: TextIO,
    verbose: bool,
) -> None:
    for raw in lines:
        line = raw.rstrip("\n").rstrip("\r")
        process_line(line, stats, out, err, verbose)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="filter_vendor_dump.py",
        description=(
            "Filter vendor-specific commands from pg_dump output for "
            "Snowflake Postgres compatibility."
        ),
        epilog=(
            "Filters: Crunchy Bridge \\restrict, AWS RDS rds_/rds.*, Azure "
            "azure_/azure.*, Google Cloud SQL cloudsql*, Neon platform roles, "
            "and SUPERUSER/REPLICATION/BYPASSRLS attributes on CREATE/ALTER "
            "ROLE."
        ),
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show what was filtered (writes audit lines to stderr).",
    )
    parser.add_argument(
        "-s", "--stats", action="store_true",
        help="Print filter statistics to stderr at end.",
    )
    parser.add_argument(
        "input_file", nargs="?",
        help="Input SQL file. Reads stdin if omitted.",
    )

    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(newline="\n")
        sys.stderr.reconfigure(newline="\n")
    except AttributeError:
        pass

    stats = Stats()

    if args.input_file:
        try:
            with open(args.input_file, "r", newline="\n") as fh:
                process_stream(fh, stats, sys.stdout, sys.stderr, args.verbose)
        except FileNotFoundError:
            sys.stderr.write(f"filter_vendor_dump: input file not found: {args.input_file}\n")
            return 1
    else:
        try:
            sys.stdin.reconfigure(newline="\n")
        except AttributeError:
            pass
        process_stream(sys.stdin, stats, sys.stdout, sys.stderr, args.verbose)

    if args.stats:
        sys.stderr.write(stats.render())

    return 0


if __name__ == "__main__":
    sys.exit(main())
