#!/usr/bin/env python3
"""
sv_concept_extractor.py — Extract business concepts from Semantic Views with
cross-SV dedup, importance scoring, and noise filtering.

Reads the output of sv_estate_scan.py and applies:
  1. Canonical key normalization (strip SUM_/TOTAL_/NUM_ prefix+suffix)
  2. Sibling dedup (merge same-canonical-key → accumulate synonyms)
  3. Noise filter (skip infrastructure dimensions, identifiers)
  4. Cross-SV repetition scoring
  5. VQR backing (boost concepts mentioned in verified queries)
  6. Score floor (emit only high-signal concepts)

Can also invoke sv_estate_scan.py directly if --database/--schema are given.

Usage:
  # Two-step: scan then extract
  python sv_estate_scan.py -c conn -d SNOWSCIENCE -s SEMANTIC_VIEWS -o /tmp/estate.json --include-facts
  python sv_concept_extractor.py --input /tmp/estate.json --output /tmp/concepts.json

  # One-step: scan + extract
  python sv_concept_extractor.py --database SNOWSCIENCE --schema SEMANTIC_VIEWS \\
      --connection conn --warehouse WH --output /tmp/concepts.json

Output format (array of candidate objects, same as other extractors):
  [{"name": "...", "description": "...", "domainName": "...",
    "itemKind": "METRIC|TERM|ENTITY", "tags": [], "synonyms": [...],
    "formula": "...", "_score": N, "_sv_count": N, "_svs": [...]}]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Account infrastructure dimensions — appear in every SV as join keys, not product concepts
INFRA_SKIP = {
    "agreement_type", "agreement_source", "snowflake_account_type", "industry",
    "sub_industry", "billing_country", "service_level", "cloud", "segment",
    "is_active_capacity_finance", "is_active_paying_customer_finance",
    "is_internal_organization", "salesforce_account_name", "dm", "rvp",
    "sales_engineer", "se_director", "se_manager", "se_vp", "gvp",
    "account_executive", "account_owner", "account_status",
    "district_name", "patch_name", "region_name", "snowflake_deployment",
    "account_id", "user_id", "user_name", "snowflake_account_id",
    "salesforce_account_id", "organization_id", "organization_name",
    "snowflake_account_name", "ds", "deployment", "general_date",
    # generic noise
    "type", "source", "city", "rating", "warehouse_type", "warehouse_size",
    "view_url", "os_version", "device_type", "tools_config",
    "scheduled", "data", "event", "feature", "use_case", "name", "id",
}

HARD_SKIP_SUFFIX = {"id", "key", "uuid", "at", "date", "time", "flag", "name"}

# Aggregation prefixes/suffixes to strip for canonical key
AGG_PREFIX = re.compile(r"^(sum_|total_|num_|count_|distinct_|avg_|cumulative_|is_|has_)+")
AGG_SUFFIX = re.compile(r"_(sum|total|count|distinct|avg|daily|weekly|monthly|cumulative)$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm(name: str) -> str:
    return re.sub(r"[^\w]", "_", name.lower()).strip("_")


def _canonical_key(name: str) -> str:
    n = _norm(name)
    n = AGG_PREFIX.sub("", n)
    n = AGG_SUFFIX.sub("", n)
    n = AGG_PREFIX.sub("", n)  # double-prefixed: sum_total_ → stripped twice
    return n.strip("_") or _norm(name)


def _is_noise(name: str) -> bool:
    raw = _norm(name)
    if raw in INFRA_SKIP:
        return True
    parts = raw.split("_")
    if len(parts) >= 2 and parts[-1] in HARD_SKIP_SUFFIX:
        return True
    if len(raw) <= 3:
        return True
    return False


def _humanize(name: str) -> str:
    return name.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Parse sv_estate.json
# ---------------------------------------------------------------------------

def _load_estate(path: str) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def _extract_raw_concepts(estate: dict[str, Any]) -> tuple[list[dict], str]:
    """Extract all candidate concepts and build VQR corpus from the estate scan output."""
    concepts: list[dict[str, Any]] = []
    vqr_questions: list[str] = []

    for sv_rec in estate.get("semantic_views", []):
        sv_name = sv_rec.get("name", "")
        sv_fqn = sv_rec.get("fqn", "")

        for cand in sv_rec.get("candidates", []):
            field_kind = cand.get("field_kind", "")
            item_kind = cand.get("itemKind", "METRIC")
            # Normalize itemKind from sv-ingest format
            if item_kind in ("MEASURE_CONCEPT", "METRIC"):
                item_kind = "METRIC"
            elif item_kind == "DIMENSION_CONCEPT":
                item_kind = "TERM"

            concepts.append({
                "name": cand.get("name", ""),
                "_raw_name": cand.get("field_name", ""),
                "itemKind": item_kind,
                "description": cand.get("description", "") or "",
                "expression": cand.get("formula_text", "") or "",
                "synonyms": cand.get("synonyms", []),
                "_sv": sv_name,
                "_sv_fqn": sv_fqn,
                "_field_kind": field_kind,
                "_base_table": cand.get("base_table_fqn", ""),
            })

        # Collect VQR questions for scoring corpus
        for vq in sv_rec.get("verified_queries", []):
            q = vq.get("question", "")
            if q:
                vqr_questions.append(q.lower())

    vqr_corpus = " ".join(vqr_questions)
    return concepts, vqr_corpus


# ---------------------------------------------------------------------------
# Cross-SV dedup with canonical key
# ---------------------------------------------------------------------------

def _dedup_and_score(
    concepts: list[dict[str, Any]],
    vqr_corpus: str,
    score_floor: int,
) -> list[dict[str, Any]]:
    """Group by canonical key, merge siblings, score, filter."""

    # Group by canonical key
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in concepts:
        if _is_noise(c.get("_raw_name", "") or c.get("name", "")):
            continue
        # For METRICs: require formula or multi-SV (speculative otherwise)
        key = _canonical_key(c.get("_raw_name", "") or c.get("name", ""))
        groups[key].append(c)

    # Merge each group into one representative
    merged: list[dict[str, Any]] = []
    for key, group in groups.items():
        svs = list({c["_sv"] for c in group})
        sv_fqns = list({c["_sv_fqn"] for c in group if c.get("_sv_fqn")})

        # Pick best representative: prefer METRIC, then has formula, then longest desc
        winner = max(group, key=lambda c: (
            c["itemKind"] == "METRIC",
            bool(c.get("expression", "").strip()),
            len(c.get("description", "")),
        ))
        result = {
            "name": winner["name"],
            "description": winner.get("description", ""),
            "domainName": "HAMID_PDS",
            "itemKind": winner["itemKind"],
            "tags": [],
            "synonyms": [],
            "formula": winner.get("expression", ""),
            "_sv_count": len(svs),
            "_svs": svs,
            "_sv_fqns": sv_fqns,
            "_merged_from": [],
            "_base_table": winner.get("_base_table", ""),
        }

        # Fill description/formula from siblings if winner is empty
        for c in group:
            if not result["description"] and c.get("description"):
                result["description"] = c["description"]
            if not result["formula"] and c.get("expression"):
                result["formula"] = c["expression"]

        # Collect synonyms from all siblings
        seen_syns: set[str] = {result["name"].lower()}
        for c in group:
            alt = c["name"]
            if alt.lower() not in seen_syns:
                result["synonyms"].append({"text": alt})
                seen_syns.add(alt.lower())
            raw = c.get("_raw_name", "")
            if raw and raw.lower() not in seen_syns:
                result["synonyms"].append({"text": raw})
                seen_syns.add(raw.lower())
            for s in c.get("synonyms", []):
                st = s if isinstance(s, str) else s
                if isinstance(st, str) and st.lower() not in seen_syns:
                    result["synonyms"].append({"text": st})
                    seen_syns.add(st.lower())

        # Track merged names (excluding winner)
        for c in group:
            if c["name"] != result["name"]:
                result["_merged_from"].append(c["name"])

        merged.append(result)

    # Score
    for c in merged:
        kind_pts = {"METRIC": 5, "TERM": 2, "ENTITY": 2}.get(c["itemKind"], 1)
        formula_pts = 7 if c.get("formula", "").strip() else 0
        sv_pts = c["_sv_count"] * 4
        desc_pts = min(3, len(c.get("description", "")) // 40)
        sib_pts = min(6, len(c.get("_merged_from", [])) * 2)
        # VQR backing
        vqr_pts = 0
        if vqr_corpus:
            cname = _norm(c["name"]).replace("_", " ")
            words = [w for w in cname.split() if len(w) > 3]
            if cname in vqr_corpus:
                vqr_pts = 6
            elif words:
                matches = sum(1 for w in words if w in vqr_corpus)
                vqr_pts = min(4, matches * 2)
        # Penalty: single-SV TERM with no formula
        penalty = -3 if (c["itemKind"] == "TERM" and c["_sv_count"] == 1 and not c.get("formula")) else 0

        c["_score"] = kind_pts + formula_pts + sv_pts + desc_pts + sib_pts + vqr_pts + penalty

    # Filter by floor and sort
    merged = [c for c in merged if c["_score"] >= score_floor]
    merged.sort(key=lambda c: -c["_score"])

    # Final: filter single-SV METRICs with no formula (too speculative)
    merged = [c for c in merged if not (
        c["itemKind"] == "METRIC" and c["_sv_count"] == 1 and not c.get("formula", "").strip()
    )]

    return merged


# ---------------------------------------------------------------------------
# Run sv_estate_scan.py if needed
# ---------------------------------------------------------------------------

def _run_estate_scan(
    connection: str,
    database: str,
    schema: str,
    warehouse: str,
    output_path: str,
) -> str:
    script = Path(__file__).resolve().parent / "sv_estate_scan.py"
    project = Path(__file__).resolve().parent.parent
    cmd = [
        "uv", "run", "--project", str(project),
        "python", str(script),
        "--database", database,
        "--schema", schema,
        "--output", output_path,
        "--include-facts",
        "--no-lineage",  # skip lineage for speed — we only need concepts
    ]
    if connection:
        cmd += ["--connection", connection]
    if warehouse:
        cmd += ["--warehouse", warehouse]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"sv_estate_scan.py failed: {proc.stderr[:300]}")
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract ranked business concepts from Semantic Views."
    )
    parser.add_argument("--input", default="", help="Path to sv_estate.json (from sv_estate_scan.py)")
    parser.add_argument("--database", "-d", default="", help="Run sv_estate_scan.py on this database")
    parser.add_argument("--schema", "-s", default="", help="Schema to scan")
    parser.add_argument("--connection", "-c", default="", help="snow CLI connection")
    parser.add_argument("--warehouse", "-w", default="", help="Warehouse for queries")
    parser.add_argument("--output", "-o", default="/tmp/sv_concepts.json", help="Output JSON path")
    parser.add_argument(
        "--score-floor", type=int, default=20,
        help="Minimum score to include. Guidelines: ~20 for ≤10 SVs, ~25 for 50+ SVs (default: 20)",
    )
    parser.add_argument("--domain", default="", help="Domain name to assign (default: inferred from SV location)")
    parser.add_argument("--emit-associations", action="store_true", help="Also emit SV association records in output")
    args = parser.parse_args()

    # Validate warehouse identifier if provided
    if args.warehouse and not _SAFE_IDENTIFIER.match(args.warehouse):
        print(f"Error: --warehouse contains unsafe characters: {args.warehouse!r}", file=sys.stderr)
        return 1

    # Resolve input
    if args.input:
        estate_path = args.input
    elif args.database:
        estate_path = "/tmp/_sv_estate_tmp.json"
        try:
            _run_estate_scan(args.connection, args.database, args.schema, args.warehouse, estate_path)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    else:
        print("Error: provide --input or --database", file=sys.stderr)
        return 1

    # Load and process
    estate = _load_estate(estate_path)
    raw_concepts, vqr_corpus = _extract_raw_concepts(estate)
    print(f"Raw concepts from SVs: {len(raw_concepts)}", file=sys.stderr)
    if vqr_corpus:
        print(f"  VQR corpus: {len(vqr_corpus.split())} words from verified queries", file=sys.stderr)

    # Dedup + score + filter
    final = _dedup_and_score(raw_concepts, vqr_corpus, args.score_floor)

    # Override domain if specified
    if args.domain:
        for c in final:
            c["domainName"] = args.domain

    # Build output payload
    output_payload = final

    # Emit associations if requested
    if args.emit_associations:
        associations = []
        for c in final:
            for sv_fqn in c.get("_sv_fqns", []):
                if sv_fqn:
                    associations.append({
                        "termName": c["name"],
                        "objectType": "SEMANTIC_VIEW",
                        "objectName": sv_fqn,
                        "associationRole": "RELATED_SEMANTIC_VIEW",
                    })
        output_payload = {"concepts": final, "associations": associations}
        print(f"  associations: {len(associations)}", file=sys.stderr)

    # Write output
    Path(args.output).write_text(json.dumps(output_payload, indent=2))
    print(f"Wrote {len(final)} concept(s) to {args.output}", file=sys.stderr)

    # Summary
    from collections import Counter
    kinds = Counter(c["itemKind"] for c in final)
    svs = Counter(c["_sv_count"] for c in final)
    print(f"  itemKind: {dict(kinds)}", file=sys.stderr)
    print(f"  sv_count: {dict(sorted(svs.items(), reverse=True))}", file=sys.stderr)
    if final:
        print(f"  top 5:", file=sys.stderr)
        for c in final[:5]:
            print(f"    [{c['_score']:>3}] {c['name']} ({c['_sv_count']} SVs)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
