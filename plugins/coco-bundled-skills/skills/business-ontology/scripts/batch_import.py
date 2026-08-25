#!/usr/bin/env python3
"""
batch_import.py — Import business concept candidates into the Business Ontology
using batched SYSTEM$ calls for efficiency.

Reads the output of sv_concept_extractor.py (with or without --emit-associations)
and performs: domain creation, term drafting, batch approval, and association creation
in minimal subprocess invocations.

Usage:
  python batch_import.py --input /tmp/sv_concepts.json \\
      --connection snowhouse --warehouse CORTEX_CONTEXT \\
      --domain HAMID_PDS

Performance: batches 20 CALL statements per snow sql invocation, reducing
~2s/call overhead to ~2s/batch. A 130-concept import with 400 associations
completes in ~60s instead of ~15min.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from sv_common import run_snow, run_snow_batch, unwrap_procedure_json


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BATCH_SIZE = 50  # CALL statements per snow sql invocation
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _escape_json_str(s: str) -> str:
    """Escape a string for embedding inside a JSON string inside SQL."""
    return s.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", " ")


def _build_draft_sql(concept: dict[str, Any], domain: str) -> str:
    name = _escape_json_str(concept["name"])
    desc = _escape_json_str((concept.get("description", "") or "")[:500])
    kind = concept.get("itemKind", "METRIC")
    syns = []
    for s in concept.get("synonyms", [])[:5]:
        t = s.get("text", "") if isinstance(s, dict) else str(s)
        if t and t != concept["name"]:
            syns.append(_escape_json_str(t))
    syns_json = json.dumps(syns)
    formula_field = ""
    if kind == "METRIC" and concept.get("formula", "").strip():
        expr = _escape_json_str(concept["formula"][:200])
        formula_field = f', "formula": "{expr}"'
    payload = f'{{"name": "{name}", "domainName": "{domain}", "itemKind": "{kind}", "description": "{desc}", "synonyms": {syns_json}{formula_field}}}'
    return f"CALL SYSTEM$DRAFT_GLOSSARY_TERM('{payload}')"


def _build_association_sql(term_name: str, domain: str, sv_fqn: str) -> str:
    term_fqn = f"{domain}.{term_name}"
    asset_ref = json.dumps({"refType": "SEMANTIC_VIEW", "fqn": sv_fqn}).replace("'", "\\'")
    return f"CALL SYSTEM$CREATE_GLOSSARY_ASSOCIATION('{term_fqn}', '{asset_ref}', 'RELATED_SEMANTIC_VIEW')"


# ---------------------------------------------------------------------------
# Import steps
# ---------------------------------------------------------------------------

def draft_terms(
    concepts: list[dict[str, Any]], domain: str, connection: str, warehouse: str
) -> list[str]:
    """Draft all terms in batches. Returns list of termIds."""
    term_ids: list[str] = []
    errors: list[str] = []
    total = len(concepts)

    for batch_start in range(0, total, BATCH_SIZE):
        batch = concepts[batch_start:batch_start + BATCH_SIZE]
        sqls = [_build_draft_sql(c, domain) for c in batch]
        results = run_snow_batch(connection, sqls, warehouse=warehouse)

        for i, rs in enumerate(results):
            parsed = unwrap_procedure_json(rs)
            if parsed.get("error"):
                errors.append(f"{batch[i]['name']}: {parsed.get('errorMessage', '?')[:60]}")
            else:
                tid = parsed.get("termId", "")
                if tid:
                    term_ids.append(tid)

        done = min(batch_start + BATCH_SIZE, total)
        print(f"  Drafted {done}/{total} ({len(errors)} errors)", file=sys.stderr)

    if errors:
        print(f"  Draft errors (first 5):", file=sys.stderr)
        for e in errors[:5]:
            print(f"    {e}", file=sys.stderr)

    return term_ids


def approve_terms(term_ids: list[str], connection: str, warehouse: str) -> int:
    """Batch-approve all drafted terms in one call."""
    if not term_ids:
        return 0
    ids_json = json.dumps(term_ids)
    sql = f"CALL SYSTEM$APPROVE_ALL_GLOSSARY_TERMS('{ids_json}')"
    result = run_snow(connection, sql, warehouse=warehouse)
    if isinstance(result, list) and result:
        parsed = unwrap_procedure_json(result)
    elif isinstance(result, dict):
        parsed = result
    else:
        parsed = {}
    return parsed.get("approved", 0)


def create_associations(
    associations: list[dict[str, Any]], domain: str, connection: str, warehouse: str
) -> tuple[int, int]:
    """Create associations in batches. Returns (ok_count, error_count)."""
    ok = 0
    err = 0
    total = len(associations)

    for batch_start in range(0, total, BATCH_SIZE):
        batch = associations[batch_start:batch_start + BATCH_SIZE]
        sqls = [
            _build_association_sql(a["termName"], domain, a["objectName"])
            for a in batch
        ]
        results = run_snow_batch(connection, sqls, warehouse=warehouse)

        for rs in results:
            parsed = unwrap_procedure_json(rs)
            if parsed.get("error"):
                err += 1
            else:
                ok += 1

        done = min(batch_start + BATCH_SIZE, total)
        if done % 100 == 0 or done == total:
            print(f"  Associations {done}/{total} ({ok} ok, {err} err)", file=sys.stderr)

    return ok, err


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Batch-import ontology concepts from sv_concept_extractor output.")
    parser.add_argument("--input", "-i", required=True, help="Path to sv_concepts.json (from sv_concept_extractor.py)")
    parser.add_argument("--connection", "-c", required=True, help="snow CLI connection")
    parser.add_argument("--warehouse", "-w", required=True, help="Warehouse for queries")
    parser.add_argument("--domain", "-d", required=True, help="Target domain name (must already exist)")
    parser.add_argument("--skip-associations", action="store_true", help="Skip association creation")
    parser.add_argument("--batch-size", type=int, default=20, help="Statements per snow sql batch (default: 20)")
    args = parser.parse_args()

    global BATCH_SIZE
    BATCH_SIZE = args.batch_size

    # Validate identifiers passed into SQL strings
    if not _SAFE_IDENTIFIER.match(args.warehouse):
        print(f"Error: unsafe warehouse identifier: {args.warehouse!r}", file=sys.stderr)
        return 1
    if not _SAFE_IDENTIFIER.match(args.domain):
        print(f"Error: unsafe domain identifier: {args.domain!r}", file=sys.stderr)
        return 1

    # Load input
    try:
        with open(args.input) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error: could not load input file {args.input!r}: {exc}", file=sys.stderr)
        return 1

    # Handle both formats: list of concepts, or {"concepts": [...], "associations": [...]}
    if isinstance(data, list):
        concepts = data
        associations = []
    else:
        concepts = data.get("concepts", [])
        associations = data.get("associations", [])

    print(f"Import: {len(concepts)} concepts, {len(associations)} associations → {args.domain}", file=sys.stderr)

    # Step 1: Draft
    print("\n[Step 1] Drafting terms...", file=sys.stderr)
    term_ids = draft_terms(concepts, args.domain, args.connection, args.warehouse)
    print(f"  → {len(term_ids)} drafted", file=sys.stderr)

    # Step 2: Approve
    print("\n[Step 2] Approving...", file=sys.stderr)
    approved = approve_terms(term_ids, args.connection, args.warehouse)
    print(f"  → {approved} approved", file=sys.stderr)

    # Step 3: Associations
    if associations and not args.skip_associations:
        # Filter to only terms that exist in the domain
        known_names = {c["name"].lower() for c in concepts}
        valid_assocs = [a for a in associations if a["termName"].lower() in known_names]
        print(f"\n[Step 3] Creating {len(valid_assocs)} associations...", file=sys.stderr)
        ok, err = create_associations(valid_assocs, args.domain, args.connection, args.warehouse)
        print(f"  → {ok} created, {err} errors", file=sys.stderr)

    print(f"\nDone. Domain '{args.domain}': {approved} terms, {len(term_ids)} drafted.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
