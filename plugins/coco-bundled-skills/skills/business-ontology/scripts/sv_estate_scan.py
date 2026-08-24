#!/usr/bin/env python3
"""Scan Semantic View estate via SHOW + DESC; emit sv_estate.json for sv-ingest skill.

Lineage-aware: each candidate carries its anchor logical table, physical base
table FQN, and the physical columns its expression references. Downstream drift
resolves domain/identity from that lineage before falling back to name+location.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sv_common import (
    extract_referenced_columns,
    get_table_columns,
    humanize,
    load_domain_map,
    resolve_domain,
    run_snow,
)

# object_kind values from DESC SEMANTIC VIEW (confirmed in ExecDescribe.java)
METRIC_KINDS = {"METRIC", "DERIVED_METRIC"}
DIMENSION_KINDS = {"DIMENSION"}
FACT_KINDS = {"FACT"}
FIELD_KINDS = METRIC_KINDS | DIMENSION_KINDS | FACT_KINDS


@dataclass
class SvField:
    kind: str  # METRIC | DERIVED_METRIC | DIMENSION | FACT
    name: str
    logical_table: str | None = None
    expression: str | None = None
    comment: str | None = None
    data_type: str | None = None
    synonyms: list[str] = field(default_factory=list)
    base_table_fqn: str | None = None
    base_columns: list[str] = field(default_factory=list)  # DB.SCHEMA.TABLE.COL


@dataclass
class SemanticViewRecord:
    fqn: str
    database: str
    schema: str
    name: str
    location_domain: str
    comment: str | None = None
    metrics: list[SvField] = field(default_factory=list)
    dimensions: list[SvField] = field(default_factory=list)
    facts: list[SvField] = field(default_factory=list)
    base_tables: list[str] = field(default_factory=list)


def parse_desc(fqn: str, location_domain: str, rows: list[dict[str, Any]]) -> SemanticViewRecord:
    db, schema, name = fqn.split(".", 2)
    rec = SemanticViewRecord(fqn=fqn, database=db, schema=schema, name=name, location_domain=location_domain)
    # logical table alias -> base table FQN
    table_base: dict[str, dict[str, str]] = {}

    cur_kind: str | None = None
    cur_name: str | None = None
    cur_parent: str | None = None
    props: dict[str, str] = {}
    pending: list[SvField] = []

    def flush() -> None:
        nonlocal cur_kind, cur_name, cur_parent, props
        if cur_kind in FIELD_KINDS and cur_name:
            pending.append(
                SvField(
                    kind=cur_kind,
                    name=cur_name,
                    logical_table=cur_parent,
                    expression=props.get("EXPRESSION"),
                    comment=props.get("COMMENT"),
                    data_type=props.get("DATA_TYPE"),
                    synonyms=json.loads(props["SYNONYMS"]) if props.get("SYNONYMS", "").startswith("[") else [],
                )
            )
        elif cur_kind == "TABLE" and cur_name:
            db_ = props.get("BASE_TABLE_DATABASE_NAME")
            sc_ = props.get("BASE_TABLE_SCHEMA_NAME")
            tb_ = props.get("BASE_TABLE_NAME")
            if db_ and sc_ and tb_:
                table_base[cur_name] = {"fqn": f"{db_}.{sc_}.{tb_}"}
        cur_kind = cur_name = cur_parent = None
        props = {}

    for row in rows:
        kind = row.get("object_kind")
        obj = row.get("object_name")
        parent = row.get("parent_entity")
        prop = row.get("property")
        val = row.get("property_value")
        if kind is None and prop == "COMMENT" and obj is None:
            rec.comment = val
            continue
        if kind in FIELD_KINDS or kind == "TABLE":
            if (kind, obj, parent) != (cur_kind, cur_name, cur_parent):
                flush()
                cur_kind, cur_name, cur_parent = kind, obj, parent or None
                props = {}
        if prop:
            props[prop] = val
    flush()

    rec.base_tables = sorted({t["fqn"] for t in table_base.values()})
    return _attach_fields(rec, pending, table_base)


def _attach_fields(
    rec: SemanticViewRecord, fields: list[SvField], table_base: dict[str, dict[str, str]]
) -> SemanticViewRecord:
    for f in fields:
        if f.logical_table and f.logical_table in table_base:
            f.base_table_fqn = table_base[f.logical_table]["fqn"]
        if f.kind in METRIC_KINDS:
            rec.metrics.append(f)
        elif f.kind in DIMENSION_KINDS:
            rec.dimensions.append(f)
        elif f.kind in FACT_KINDS:
            rec.facts.append(f)
    return rec


def enrich_lineage(
    rec: SemanticViewRecord, connection: str, warehouse: str, col_cache: dict[str, list[str]], role: str = ""
) -> None:
    for f in rec.metrics + rec.dimensions + rec.facts:
        if not f.base_table_fqn or not f.expression:
            continue
        if f.base_table_fqn not in col_cache:
            col_cache[f.base_table_fqn] = get_table_columns(connection, f.base_table_fqn, warehouse, role)
        cols = col_cache[f.base_table_fqn]
        referenced = extract_referenced_columns(f.expression, set(cols))
        f.base_columns = [f"{f.base_table_fqn}.{c}" for c in referenced]


def candidate_payload(f: SvField, sv: SemanticViewRecord, include_facts: bool) -> dict[str, Any] | None:
    if f.kind in METRIC_KINDS:
        item_kind = "METRIC"
    elif f.kind in DIMENSION_KINDS:
        item_kind = "DIMENSION_CONCEPT"
    elif f.kind in FACT_KINDS:
        if not include_facts:
            return None
        item_kind = "MEASURE_CONCEPT"
    else:
        return None
    return {
        "name": humanize(f.name),
        "itemKind": item_kind,
        "field_kind": f.kind,
        "field_name": f.name,
        "logical_table": f.logical_table,
        "base_table_fqn": f.base_table_fqn,
        "base_columns": f.base_columns,
        "formula_text": f.expression,
        "data_type": f.data_type,
        "synonyms": f.synonyms,
        "description": f.comment or f.expression,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection", "-c", default="", help="snow CLI connection (default: CLI default)")
    parser.add_argument("--database", "-d", default="")
    parser.add_argument("--schema", "-s", default="")
    parser.add_argument("--pattern", default="%")
    parser.add_argument("--output", "-o", default="/tmp/sv_estate.json")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--domain-map", default="")
    parser.add_argument("--warehouse", default="")
    parser.add_argument("--role", default="", help="role to run as (default: connection default)")
    parser.add_argument("--include-facts", action="store_true")
    parser.add_argument("--no-lineage", action="store_true", help="skip base-column extraction (faster)")
    args = parser.parse_args()

    skill_dir = Path(__file__).resolve().parent.parent
    map_path = args.domain_map or (skill_dir / "sv-ingest" / "domain_map.example.yaml")
    domain_map = load_domain_map(map_path if Path(map_path).exists() else None)

    show_sql = "SHOW SEMANTIC VIEWS IN ACCOUNT"
    if args.database:
        show_sql = f"SHOW SEMANTIC VIEWS IN DATABASE {args.database}"
    inventory = run_snow(args.connection, show_sql, warehouse=args.warehouse, role=args.role)

    if args.schema:
        inventory = [r for r in inventory if r.get("schema_name", "").upper() == args.schema.upper()]
    if args.pattern and args.pattern != "%":
        pat = re.compile(args.pattern.replace("%", ".*"), re.I)
        inventory = [r for r in inventory if pat.search(r.get("name", ""))]

    col_cache: dict[str, list[str]] = {}
    records: list[dict[str, Any]] = []
    for i, row in enumerate(inventory):
        if args.limit and i >= args.limit:
            break
        fqn = f"{row['database_name']}.{row['schema_name']}.{row['name']}"
        location_domain = resolve_domain(row["database_name"], row["schema_name"], row["name"], domain_map)
        desc_rows = run_snow(args.connection, f"DESC SEMANTIC VIEW {fqn}", warehouse=args.warehouse, role=args.role)
        rec = parse_desc(fqn, location_domain, desc_rows)
        if not args.no_lineage:
            enrich_lineage(rec, args.connection, args.warehouse, col_cache, args.role)
        candidates = []
        for f in rec.metrics + rec.dimensions + (rec.facts if args.include_facts else []):
            payload = candidate_payload(f, rec, args.include_facts)
            if payload:
                candidates.append(payload)
        records.append({**asdict(rec), "candidates": candidates})

    out = {
        "semantic_views": records,
        "count": len(records),
        "domain_map_source": str(map_path),
        "lineage": not args.no_lineage,
    }
    Path(args.output).write_text(json.dumps(out, indent=2))
    print(f"Wrote {args.output} ({len(records)} semantic views)")
    for rec in records:
        n_lin = sum(1 for c in rec["candidates"] if c["base_columns"])
        print(
            f"  {rec['fqn']} → location_domain={rec['location_domain']} "
            f"metrics={len(rec['metrics'])} dims={len(rec['dimensions'])} "
            f"tables={len(rec['base_tables'])} lineage_fields={n_lin}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
