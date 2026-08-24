#!/usr/bin/env python3
"""ontology_source_registry.py — CRUD for the temporary ontology source registry.

TEMPORARY: Manages a ontology_sources.yaml file in a Snowflake internal stage
until native backend source storage is implemented.
Migration path: replace _load_registry/_save_registry with backend API calls; keep
all CLI subcommands and JSON output shapes identical so callers need no changes.

Storage: @<DB>.<SCHEMA>.ONTOLOGY_SOURCES/ontology_sources.yaml
  DB      = ONTOLOGY_REGISTRY_DB env var, default TEMP
  SCHEMA  = ONTOLOGY_REGISTRY_SCHEMA env var, default BUSINESS_ONTOLOGY

Domain model:
  Each source has a `domains` array (list of {name, id} objects). A source with
  an empty `domains` array (or containing only {name: "Default"}) is generic —
  it applies to all domains. A source with specific domains only applies to those.

Subcommands
-----------
doctor          Pre-flight: verify snow CLI and provision the registry stage.
add             Register a new stage file or stage prefix as an ontology source.
list            List registered sources, optionally filtered by domain or status.
update          Update a source's status, domains, monitoring_mode, or timestamps.
get_by_domain   Fetch active sources relevant to a domain (matching + generic).

Output is always JSON to stdout (single object for add/update/doctor, array for
list/get_by_domain). Errors go to stderr with a non-zero exit code.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_DB = "TEMP"
_DEFAULT_SCHEMA = "BUSINESS_ONTOLOGY"
_STAGE_NAME = "ONTOLOGY_SOURCES"
_REGISTRY_FILE = "ontology_sources.yaml"
_SQL_TIMEOUT_SECONDS = 60

_STAGE_URI_RE = re.compile(r"^@[\w$][\w$]*\.[\w$][\w$]*\.[\w$][\w$]*(/.+)?$")


class RegistryError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Storage layer — Snowflake stage via snow CLI
# ---------------------------------------------------------------------------

def _resolve_storage() -> tuple[str, str]:
    db = os.environ.get("ONTOLOGY_REGISTRY_DB", _DEFAULT_DB)
    schema = os.environ.get("ONTOLOGY_REGISTRY_SCHEMA", _DEFAULT_SCHEMA)
    return db.upper(), schema.upper()


def _fqsn() -> str:
    db, schema = _resolve_storage()
    return f"{db}.{schema}.{_STAGE_NAME}"


def _exec_sql(sql: str, connection: str | None = None) -> subprocess.CompletedProcess[str]:
    cmd = ["snow", "sql", "-q", sql, "--format", "json"]
    if connection:
        cmd += ["-c", connection]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=_SQL_TIMEOUT_SECONDS)
    except FileNotFoundError as e:
        raise RegistryError(
            "the Snowflake CLI (snow) is not installed or not on PATH."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RegistryError(f"snow sql timed out after {_SQL_TIMEOUT_SECONDS}s") from e


def _run_sql(sql: str, connection: str | None = None) -> None:
    result = _exec_sql(sql, connection)
    if result.returncode != 0:
        raise RegistryError(f"SQL failed: {result.stderr.strip() or result.stdout.strip()}")


def _provision(connection: str | None = None) -> None:
    db, schema = _resolve_storage()
    _run_sql(f"CREATE DATABASE IF NOT EXISTS {db}", connection)
    _run_sql(f"CREATE SCHEMA IF NOT EXISTS {db}.{schema}", connection)
    fqsn = f"{db}.{schema}.{_STAGE_NAME}"
    _run_sql(
        f"CREATE STAGE IF NOT EXISTS {fqsn} "
        f"COMMENT = 'Business Ontology source registry (temporary)'",
        connection,
    )


def _load_registry(connection: str | None = None) -> dict[str, Any]:
    fqsn = _fqsn()
    with tempfile.TemporaryDirectory() as tmp:
        result = _exec_sql(f"GET '@{fqsn}/{_REGISTRY_FILE}' 'file://{tmp}/'", connection)
        if result.returncode != 0:
            return {"sources": []}
        files = list(Path(tmp).iterdir())
        if not files:
            return {"sources": []}
        text = files[0].read_text()
        data = yaml.safe_load(text) or {}
        data.setdefault("sources", [])
        return data


def _save_registry(data: dict[str, Any], connection: str | None = None) -> None:
    fqsn = _fqsn()
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        out_file = tmpdir / _REGISTRY_FILE
        out_file.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
        )
        _run_sql(
            f"PUT 'file://{out_file}' '@{fqsn}/' AUTO_COMPRESS=FALSE OVERWRITE=TRUE",
            connection,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _infer_source_type(uri: str) -> str:
    tail = uri.rsplit("/", 1)[-1] if "/" in uri else ""
    return "stage_prefix" if (uri.endswith("/") or "." not in tail) else "stage_file"


def _is_generic(src: dict[str, Any]) -> bool:
    """A source is generic if it has no domains or only the Default domain."""
    domains = src.get("domains", [])
    if not domains:
        return True
    return all(d.get("name", "").lower() == "default" for d in domains)


def _matches_domain(src: dict[str, Any], domain: str) -> bool:
    """A source matches a domain if it's generic OR has the domain in its list."""
    if _is_generic(src):
        return True
    for d in src.get("domains", []):
        if d.get("name", "").lower() == domain.lower():
            return True
        if d.get("id") and d.get("id") == domain:
            return True
    return False


def _parse_domains_arg(domains_json: str | None) -> list[dict[str, str]]:
    """Parse --domains JSON argument into list of {name, id} objects."""
    if not domains_json:
        return []
    try:
        parsed = json.loads(domains_json)
        if isinstance(parsed, list):
            return [{"name": d.get("name", d) if isinstance(d, dict) else d,
                     "id": d.get("id", "") if isinstance(d, dict) else ""}
                    for d in parsed]
        return []
    except (json.JSONDecodeError, TypeError):
        # Treat as a single domain name
        return [{"name": domains_json, "id": ""}]


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_doctor(args: argparse.Namespace) -> None:
    snow_cli = "ok" if shutil.which("snow") else "missing"
    db, schema = _resolve_storage()
    report: dict[str, Any] = {
        "snow_cli": snow_cli,
        "database": db,
        "schema": schema,
        "stage": _STAGE_NAME,
        "storage_location": f"@{db}.{schema}.{_STAGE_NAME}/{_REGISTRY_FILE}",
    }
    if snow_cli == "missing":
        report["storage_ready"] = False
        print(json.dumps(report))
        return
    try:
        _provision(args.connection if hasattr(args, "connection") else None)
        report["storage_ready"] = True
    except RegistryError as e:
        report["storage_ready"] = False
        report["error"] = str(e)
    print(json.dumps(report))


def cmd_add(args: argparse.Namespace) -> None:
    uri = args.stage_uri.strip()
    if not _STAGE_URI_RE.match(uri):
        print(
            json.dumps({"error": f"Invalid stage URI: {uri!r}. Expected @DB.SCHEMA.STAGE[/path] where each segment starts with a letter, underscore, or dollar sign."}),
            file=sys.stderr,
        )
        sys.exit(1)

    _provision(args.connection)
    registry = _load_registry(args.connection)
    for src in registry["sources"]:
        if src["stage_uri"] == uri:
            print(
                json.dumps({"error": f"Source already registered: {uri}", "source_id": src["source_id"]}),
                file=sys.stderr,
            )
            sys.exit(1)

    domains = _parse_domains_arg(args.domains)

    entry: dict[str, Any] = {
        "source_id": str(uuid.uuid4()),
        "domains": domains,
        "source_type": args.source_type or _infer_source_type(uri),
        "stage_uri": uri,
        "added_by": args.added_by or "",
        "status": "active",
        "monitoring_mode": "none",
        "last_imported_at": "",
        "last_sense_processed_at": "",
        "last_seen_fingerprint": "",
        "notes": args.notes or "",
        "registered_at": _now(),
    }
    registry["sources"].append(entry)
    _save_registry(registry, args.connection)
    print(json.dumps(entry))


def cmd_list(args: argparse.Namespace) -> None:
    registry = _load_registry(args.connection)
    sources = registry["sources"]
    if args.domain:
        sources = [s for s in sources if _matches_domain(s, args.domain)]
    if args.status:
        sources = [s for s in sources if s.get("status") == args.status]
    print(json.dumps(sources))


def cmd_update(args: argparse.Namespace) -> None:
    _provision(args.connection)
    registry = _load_registry(args.connection)
    updated = None
    for src in registry["sources"]:
        if src["source_id"] == args.source_id:
            if args.status:
                src["status"] = args.status
            if args.monitoring_mode:
                src["monitoring_mode"] = args.monitoring_mode
            if args.domains is not None:
                src["domains"] = _parse_domains_arg(args.domains)
            if args.notes is not None:
                src["notes"] = args.notes
            if args.last_imported_at:
                src["last_imported_at"] = args.last_imported_at
            if args.last_sense_processed_at:
                src["last_sense_processed_at"] = args.last_sense_processed_at
            if args.last_seen_fingerprint:
                src["last_seen_fingerprint"] = args.last_seen_fingerprint
            updated = src
            break

    if updated is None:
        print(json.dumps({"error": f"Source not found: {args.source_id}"}), file=sys.stderr)
        sys.exit(1)

    _save_registry(registry, args.connection)
    print(json.dumps(updated))


def cmd_get_by_domain(args: argparse.Namespace) -> None:
    """Get sources relevant to a domain: those that explicitly list it + generic ones."""
    registry = _load_registry(args.connection)
    sources = [
        s for s in registry["sources"]
        if _matches_domain(s, args.domain) and s.get("status", "active") == "active"
    ]
    print(json.dumps(sources))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ontology source registry — TEMPORARY implementation (Snowflake stage backend) until native backend storage exists"
    )
    parser.add_argument(
        "--connection", "-c",
        help="Snowflake CLI connection profile name",
        default=os.environ.get("ONTOLOGY_REGISTRY_CONNECTION"),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="Pre-flight: verify snow CLI and provision stage")

    p_add = sub.add_parser("add", help="Register a new stage source")
    p_add.add_argument("stage_uri", help="@DB.SCHEMA.STAGE[/path]")
    p_add.add_argument("--domains", help='JSON array of {name, id} objects or a single domain name. Empty = generic (all domains).')
    p_add.add_argument("--source-type", dest="source_type", choices=["stage_file", "stage_prefix"])
    p_add.add_argument("--added-by", dest="added_by", help="Registering user or role")
    p_add.add_argument("--notes", dest="notes")

    p_list = sub.add_parser("list", help="List registered sources")
    p_list.add_argument("--domain", help="Filter: show sources relevant to this domain (matching + generic)")
    p_list.add_argument("--status", choices=["active", "paused", "deprecated"])

    p_upd = sub.add_parser("update", help="Update a source entry")
    p_upd.add_argument("source_id", help="UUID of the source to update")
    p_upd.add_argument("--status", choices=["active", "paused", "deprecated"])
    p_upd.add_argument("--monitoring-mode", dest="monitoring_mode", choices=["none", "sense_scheduled"])
    p_upd.add_argument("--domains", help='JSON array of {name, id} objects. Pass "[]" to make generic.')
    p_upd.add_argument("--notes", dest="notes")
    p_upd.add_argument("--last-imported-at", dest="last_imported_at")
    p_upd.add_argument("--last-sense-processed-at", dest="last_sense_processed_at")
    p_upd.add_argument("--last-seen-fingerprint", dest="last_seen_fingerprint")

    p_gbd = sub.add_parser("get_by_domain", help="Get active sources relevant to a domain (matching + generic)")
    p_gbd.add_argument("domain", help="Domain name or domain_id")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    dispatch = {
        "doctor": cmd_doctor,
        "add": cmd_add,
        "list": cmd_list,
        "update": cmd_update,
        "get_by_domain": cmd_get_by_domain,
    }
    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()
