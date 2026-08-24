"""
scoring.py — Shared scoring logic for AI Readiness Score.

Provides importable functions used by both the notebook cells and the CLI script.
"""

from __future__ import annotations

import math

def classify_gap(pct_demand, n_cr_tables, pct_sv_coverage, avg_sv_quality):
    """Classify the primary improvement gap."""
    if pct_demand is None or n_cr_tables == 0:
        return "BUILD_CR_TABLES"
    if pct_demand < 0.5:
        return "BUILD_CR_TABLES"
    if pct_sv_coverage == 0:
        return "BUILD_SVS"
    if pct_sv_coverage < 0.5:
        return "EXPAND_SV_COVERAGE"
    if avg_sv_quality < 0.5:
        return "IMPROVE_SV_QUALITY"
    return "HEALTHY"


def compute_composite_scores(cr_results, sv_results):
    """
    Compute all AI readiness scores from CR table results and SV quality results.

    Args:
        cr_results: list of dicts from CR tables query (keys lowercase)
        sv_results: list of dicts from SV quality query (keys lowercase)

    Returns:
        dict with all computed scores and metadata
    """
    # Build SV signals map
    sv_signals = {}
    for row in sv_results:
        fqn = str(row.get("sv_fqn") or "")
        if not fqn:
            continue
        if fqn not in sv_signals:
            sv_signals[fqn] = {
                "has_pk": int(row.get("has_pk") or 0),
                "has_synonyms": int(row.get("has_synonyms") or 0),
                "has_unique_keys": int(row.get("has_unique_keys") or 0),
                "has_distinct_ranges": int(row.get("has_distinct_ranges") or 0),
                "has_relationships": int(row.get("has_relationships") or 0),
                "has_metrics": int(row.get("has_metrics") or 0),
                "n_verified_queries": int(row.get("n_verified_queries") or 0),
                "avg_comment_length": float(row.get("avg_comment_length") or 0),
                "quality_score": float(row.get("quality_score") or 0),
                "base_tables": [],
            }
        sv_signals[fqn]["base_tables"].append({
            "database": str(row.get("base_database") or ""),
            "schema": str(row.get("base_schema") or ""),
            "table": str(row.get("base_table") or ""),
        })

    # Identify consumption-ready tables
    all_scored = cr_results
    cr_tables = [r for r in all_scored if float(r.get("consumption_readiness_score") or 0) >= 0.80]
    cr_set = {(r["database_name"], r["schema_name"], r["table_name"]) for r in cr_tables}

    # Demand coverage
    total_reads = sum(int(r.get("analytical_reads") or 0) for r in all_scored)
    reads_on_cr = sum(
        int(r.get("analytical_reads") or 0) for r in all_scored
        if (r["database_name"], r["schema_name"], r["table_name"]) in cr_set
    )
    pct_demand = (reads_on_cr / total_reads) if total_reads >= 10 else None

    # SV coverage
    sv_covered = {
        (bt["database"], bt["schema"], bt["table"])
        for sig in sv_signals.values()
        for bt in sig.get("base_tables", [])
        if (bt["database"], bt["schema"], bt["table"]) in cr_set
    }
    n_sv_covered = len(sv_covered)
    pct_sv_coverage = n_sv_covered / len(cr_set) if cr_set else 0.0

    # SV quality (average across relevant SVs)
    relevant_fqns = {
        fqn for fqn, sig in sv_signals.items()
        if any((bt["database"], bt["schema"], bt["table"]) in cr_set for bt in sig.get("base_tables", []))
    }
    avg_sv_quality = (
        sum(sv_signals[f]["quality_score"] for f in relevant_fqns) / len(relevant_fqns)
        if relevant_fqns else 0.0
    )

    # Composite scores
    dc_100 = (pct_demand or 0.0) * 100
    sv_cov_100 = pct_sv_coverage * 100
    sv_qual_100 = avg_sv_quality * 100
    sv_readiness = math.sqrt(pct_sv_coverage * avg_sv_quality) * 100
    ai_readiness = ((pct_demand or 0.0) + math.sqrt(pct_sv_coverage * avg_sv_quality)) / 2.0 * 100

    gap = classify_gap(pct_demand, len(cr_set), pct_sv_coverage, avg_sv_quality)

    # Missing dimensions
    missing_dims = [
        label for flag, label in [
            ("has_pk", "primary keys"),
            ("has_synonyms", "synonyms"),
            ("has_metrics", "metrics"),
            ("has_relationships", "relationships"),
        ]
        if relevant_fqns and sum(sv_signals[f][flag] for f in relevant_fqns) / len(relevant_fqns) < 0.5
    ]

    # Improvement items — scoped to the primary gap (mirrors dbt pipeline logic)
    sv_covered_set = set()
    for sig in sv_signals.values():
        for bt in sig.get("base_tables", []):
            key = (bt["database"], bt["schema"], bt["table"])
            if key in cr_set:
                sv_covered_set.add(key)

    items = []
    top_targets = []

    if gap == "BUILD_CR_TABLES":
        # SCHEMA_GAP: schemas with heavy reads but low CR coverage
        from collections import defaultdict
        schema_stats = defaultdict(lambda: {"total_reads": 0, "tables_read": 0, "cr_tables": 0, "cr_reads": 0})
        for r in all_scored:
            key = (r["database_name"], r["schema_name"])
            reads = int(r.get("analytical_reads") or 0)
            schema_stats[key]["total_reads"] += reads
            schema_stats[key]["tables_read"] += 1
            if (r["database_name"], r["schema_name"], r["table_name"]) in cr_set:
                schema_stats[key]["cr_tables"] += 1
                schema_stats[key]["cr_reads"] += reads

        schema_items = []
        for (db, schema), stats in schema_stats.items():
            if stats["total_reads"] < 10:
                continue
            uncovered_reads = stats["total_reads"] - stats["cr_reads"]
            schema_items.append({
                "type": "SCHEMA_GAP",
                "target": f"{db}.{schema}",
                "detail": f"{stats['total_reads']:,} reads across {stats['tables_read']} tables, {stats['cr_tables']} CR",
                "recommendation": f"Increase CR coverage — {uncovered_reads:,} reads land on non-CR tables.",
                "_sort_key": uncovered_reads,
            })
        schema_items.sort(key=lambda x: x["_sort_key"], reverse=True)
        for item in schema_items[:10]:
            del item["_sort_key"]
            items.append(item)

        # top_targets = top schemas by uncovered reads (for NL paragraph)
        top_targets = [item["target"] for item in items[:5]]

    elif gap in ("BUILD_SVS", "EXPAND_SV_COVERAGE"):
        # UNCOVERED_CR_TABLE: CR tables without any semantic view
        uncovered = [
            r for r in all_scored
            if (r["database_name"], r["schema_name"], r["table_name"]) in cr_set
            and (r["database_name"], r["schema_name"], r["table_name"]) not in sv_covered_set
        ]
        uncovered.sort(key=lambda r: int(r.get("analytical_reads") or 0), reverse=True)
        for r in uncovered[:10]:
            items.append({
                "type": "UNCOVERED_CR_TABLE",
                "target": f"{r['database_name']}.{r['schema_name']}.{r['table_name']}",
                "detail": f"{int(r.get('analytical_reads') or 0):,} reads, {int(r.get('distinct_users') or 0)} distinct users",
                "recommendation": "Create a semantic view for this table.",
            })

        # top_targets = top uncovered CR tables (for NL paragraph)
        top_targets = [item["target"] for item in items[:5]]

    elif gap == "IMPROVE_SV_QUALITY":
        # SV_QUALITY_GAP: SVs covering CR tables with quality < 0.5
        relevant_svs = [
            (fqn, sig) for fqn, sig in sv_signals.items()
            if any((bt["database"], bt["schema"], bt["table"]) in cr_set for bt in sig.get("base_tables", []))
            and sig["quality_score"] < 0.5
        ]
        relevant_svs.sort(key=lambda x: x[1]["quality_score"])
        for fqn, sig in relevant_svs[:10]:
            missing = []
            if not sig["has_pk"]:
                missing.append("primary key")
            if not sig["has_synonyms"]:
                missing.append("synonyms")
            if not sig["has_metrics"]:
                missing.append("metrics")
            if not sig["has_relationships"]:
                missing.append("relationships")
            if not sig["has_unique_keys"]:
                missing.append("unique keys")
            if not sig["n_verified_queries"]:
                missing.append("verified queries")
            items.append({
                "type": "SV_QUALITY_GAP",
                "target": fqn,
                "detail": f"Quality: {sig['quality_score'] * 100:.0f}/100",
                "recommendation": f"Add: {', '.join(missing[:4])}." if missing else "Improve SV metadata.",
            })

    # HEALTHY: no items needed (account is in good shape)

    return {
        "ai_readiness": round(ai_readiness, 2),
        "demand_coverage": round(dc_100, 2),
        "sv_readiness": round(sv_readiness, 2),
        "sv_coverage": round(sv_cov_100, 2),
        "sv_quality": round(sv_qual_100, 2),
        "n_cr_tables": len(cr_set),
        "gap": gap,
        "top_targets": top_targets,
        "missing_dims": missing_dims,
        "n_all_scored": len(all_scored),
        "n_sv": len(sv_signals),
        "n_sv_covered": n_sv_covered,
        "pct_demand_raw": pct_demand,
        "pct_sv_coverage_raw": pct_sv_coverage,
        "avg_sv_quality_raw": avg_sv_quality,
        "improvement_items": items,
    }
