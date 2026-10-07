#!/usr/bin/env python3
"""discover_ontology_domains.py — Find Business Ontology sources relevant to a Cortex Sense domain.

Runs at T=0 during setup fast-pass. Reads the ontology source registry for sources
relevant to a matched domain and returns the stage sources Cortex Sense can fold
into its build context.

Matching logic:
  A source is relevant to a domain if:
  1. It explicitly lists the domain in its `domains` array (by name or id), OR
  2. It is generic (empty `domains` array or only "Default" domain)

This means generic sources (applicable to all domains) are always returned alongside
domain-specific ones.

Usage:
    python discover_ontology_domains.py \\
        --domain "<domain_name>" \\
        --connection "<snowflake_connection>"
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_DB = "TEMP"
_DEFAULT_SCHEMA = "BUSINESS_ONTOLOGY"
_STAGE_NAME = "ONTOLOGY_SOURCES"
_REGISTRY_FILE = "ontology_sources.yaml"
_SQL_TIMEOUT_SECONDS = 60


def _resolve_storage() -> tuple[str, str]:
    db = os.environ.get("ONTOLOGY_REGISTRY_DB", _DEFAULT_DB)
    schema = os.environ.get("ONTOLOGY_REGISTRY_SCHEMA", _DEFAULT_SCHEMA)
    return db.upper(), schema.upper()


def _load_registry_from_stage(connection: str | None) -> list[dict[str, Any]]:
    db, schema = _resolve_storage()
    fqsn = f"{db}.{schema}.{_STAGE_NAME}"
    with tempfile.TemporaryDirectory() as tmp:
        cmd = ["snow", "sql", "-q", f"GET '@{fqsn}/{_REGISTRY_FILE}' 'file://{tmp}/'", "--format", "json"]
        if connection:
            cmd += ["-c", connection]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=_SQL_TIMEOUT_SECONDS)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        if result.returncode != 0:
            return []
        files = list(Path(tmp).iterdir())
        if not files:
            return []
        text = files[0].read_text()
        data = yaml.safe_load(text) or {}
        return data.get("sources", [])


def _is_generic(src: dict[str, Any]) -> bool:
    """A source is generic if it has no domains or only the Default domain."""
    domains = src.get("domains", [])
    if not domains:
        return True
    return all(d.get("name", "").lower() == "default" for d in domains)


def _matches_domain(src: dict[str, Any], domain: str, domain_id: str | None) -> bool:
    """A source matches if it's generic OR explicitly lists the queried domain."""
    if _is_generic(src):
        return True
    for d in src.get("domains", []):
        if d.get("name", "").lower() == domain.lower():
            return True
        if domain_id and d.get("id") == domain_id:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Business Ontology sources relevant to a domain (matching + generic)"
    )
    parser.add_argument("--domain", required=True, help="Domain name (matched by caller)")
    parser.add_argument("--domain-id", dest="domain_id", help="Domain UUID for exact disambiguation")
    parser.add_argument(
        "--connection", "-c",
        default=os.environ.get("ONTOLOGY_REGISTRY_CONNECTION"),
        help="Snowflake CLI connection profile name",
    )
    args = parser.parse_args()

    sources = _load_registry_from_stage(args.connection)

    matched: list[dict[str, Any]] = [
        s for s in sources
        if _matches_domain(s, args.domain, args.domain_id)
        and s.get("status", "active") == "active"
    ]

    stage_sources = [
        {
            "source_id": s["source_id"],
            "stage_uri": s["stage_uri"],
            "source_type": s.get("source_type", "stage_file"),
            "domains": s.get("domains", []),
            "is_generic": _is_generic(s),
            "last_imported_at": s.get("last_imported_at", ""),
        }
        for s in matched
    ]

    result = {
        "domain_name": args.domain,
        "domain_id": args.domain_id or "",
        "stage_sources": stage_sources,
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
