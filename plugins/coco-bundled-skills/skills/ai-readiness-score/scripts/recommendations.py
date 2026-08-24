"""
recommendations.py — Gap classification, recommendation text, and improvement items.

Pure Python; no Snowflake connector dependency.  All functions take pre-fetched
data (lists/dicts from db.py) and return structured results for report.py.
"""

from __future__ import annotations


def classify_gap(
    pct_demand_coverage: float | None,
    n_cr_tables: int,
    pct_sv_coverage: float,
    avg_sv_quality: float,
) -> str:
    """Waterfall gap classification (mirrors customer_recommendation_overview.sql).

    Returns one of:
      BUILD_CR_TABLES    — fewer than 50% of reads land on consumption-ready tables
      BUILD_SVS          — no semantic views exist for any CR table
      EXPAND_SV_COVERAGE — SVs exist but cover < 50% of CR tables
      IMPROVE_SV_QUALITY — coverage is good but average quality is < 0.5
      HEALTHY            — all dimensions meet the healthy threshold
    """
    if pct_demand_coverage is None or n_cr_tables == 0:
        return "BUILD_CR_TABLES"
    if pct_demand_coverage < 0.5:
        return "BUILD_CR_TABLES"
    if pct_sv_coverage == 0:
        return "BUILD_SVS"
    if pct_sv_coverage < 0.5:
        return "EXPAND_SV_COVERAGE"
    if avg_sv_quality < 0.5:
        return "IMPROVE_SV_QUALITY"
    return "HEALTHY"


def build_recommendation(
    account_name: str,
    composite: float,
    gap: str,
    pct_demand_coverage: float | None,
    n_cr_tables: int,
    pct_sv_coverage: float,
    n_sv_covered: int,
    avg_sv_quality: float,
    top_targets: list[str],
    missing_dims: list[str],
) -> str:
    """Generate a natural-language recommendation paragraph.

    Mirrors the logic in customer_recommendation_overview.sql from the
    canonical datascience-airflow dbt pipeline.  Each sentence covers one
    dimension (overall score, demand coverage, SV coverage, SV quality) and
    ends with an actionable priority statement.
    """
    parts: list[str] = []

    # Sentence 1: overall score and primary gap
    score_str = f"{composite:.0f}/100"
    if gap == "HEALTHY":
        parts.append(f"{account_name} scores {score_str} — all dimensions are healthy.")
    else:
        parts.append(
            f"{account_name} scores {score_str} (primary gap: {gap.replace('_', ' ')})."
        )

    # Sentence 2: demand coverage interpretation
    dc_pct = round((pct_demand_coverage or 0) * 100)
    if pct_demand_coverage is not None and pct_demand_coverage >= 0.7:
        parts.append(
            f"Demand coverage is strong at {dc_pct}% ({n_cr_tables} CR tables)."
        )
    elif pct_demand_coverage is not None and pct_demand_coverage >= 0.5:
        parts.append(
            f"Demand coverage is moderate at {dc_pct}% ({n_cr_tables} CR tables)."
        )
    elif n_cr_tables == 0:
        parts.append("No consumption-ready tables exist.")
    else:
        top_str = ("; top areas: " + ", ".join(top_targets)) if top_targets else ""
        parts.append(
            f"Demand coverage is low at {dc_pct}% — most reads land on non-CR tables{top_str}."
        )

    # Sentence 3: SV coverage
    if n_cr_tables > 0:
        sv_pct = round((pct_sv_coverage or 0) * 100)
        uncovered = n_cr_tables - n_sv_covered
        if (pct_sv_coverage or 0) == 0:
            parts.append(f"No semantic views cover any of the {n_cr_tables} CR tables.")
        elif pct_sv_coverage < 0.5:
            top_str = (
                ("; top uncovered: " + ", ".join(top_targets))
                if gap in ("BUILD_SVS", "EXPAND_SV_COVERAGE") and top_targets
                else ""
            )
            parts.append(
                f"SV coverage is low at {sv_pct}% — {uncovered} CR tables lack semantic views{top_str}."
            )
        else:
            parts.append(
                f"SV coverage is good at {sv_pct}% ({n_sv_covered} of {n_cr_tables} CR tables)."
            )

    # Sentence 4: SV quality
    if avg_sv_quality > 0:
        qual_str = f"{avg_sv_quality:.2f}/1.0"
        if avg_sv_quality < 0.5:
            dims_str = (
                (f" — common gaps: {', '.join(missing_dims)}") if missing_dims else ""
            )
            parts.append(f"SV quality averages {qual_str}{dims_str}.")
        else:
            parts.append(f"SV quality is good at {qual_str}.")

    # Priority sentence
    priorities = {
        "BUILD_CR_TABLES": "Priority: increase consumption-ready table coverage.",
        "BUILD_SVS": f"Priority: build semantic views for the {n_cr_tables} CR tables.",
        "EXPAND_SV_COVERAGE": f"Priority: expand SV coverage to the {n_cr_tables - n_sv_covered} uncovered CR tables.",
        "IMPROVE_SV_QUALITY": f"Priority: improve SV quality{(' — add ' + ', '.join(missing_dims)) if missing_dims else ''}.",
        "HEALTHY": "No immediate action needed.",
    }
    parts.append(priorities.get(gap, ""))

    return " ".join(p for p in parts if p)


def build_improvement_items(
    all_scored: list[dict],
    cr_set: set[tuple],
    sv_signals: dict[str, dict],
) -> list[dict]:
    """Return the top improvement opportunities as a list of dicts.

    Two item types are returned (interleaved by priority):
      UNCOVERED_CR_TABLE — a CR table with no semantic view; sorted by reads
      SV_QUALITY_GAP     — an SV covering CR tables with quality_score < 0.5

    Each dict has keys: type, target, detail, recommendation.
    """
    items: list[dict] = []

    # Determine which CR tables already have at least one SV
    sv_covered: set[tuple] = set()
    for fqn, sig in sv_signals.items():
        for bt in sig.get("base_tables", []):
            key = (bt["database"], bt["schema"], bt["table"])
            if key in cr_set:
                sv_covered.add(key)

    # Top uncovered CR tables by analytical read count
    uncovered = [
        r
        for r in all_scored
        if (r["database_name"], r["schema_name"], r["table_name"]) in cr_set
        and (r["database_name"], r["schema_name"], r["table_name"]) not in sv_covered
    ]
    uncovered.sort(key=lambda r: int(r.get("analytical_reads") or 0), reverse=True)
    for r in uncovered[:10]:
        items.append(
            {
                "type": "UNCOVERED_CR_TABLE",
                "target": f"{r['database_name']}.{r['schema_name']}.{r['table_name']}",
                "detail": (
                    f"{int(r.get('analytical_reads') or 0):,} reads, "
                    f"{int(r.get('distinct_users') or 0)} distinct users"
                ),
                "recommendation": "Create a semantic view for this table.",
            }
        )

    # Low-quality SVs that cover at least one CR table
    relevant_svs = [
        (fqn, sig)
        for fqn, sig in sv_signals.items()
        if any(
            (bt["database"], bt["schema"], bt["table"]) in cr_set
            for bt in sig.get("base_tables", [])
        )
        and sig["quality_score"] < 0.5
    ]
    relevant_svs.sort(key=lambda x: x[1]["quality_score"])
    for fqn, sig in relevant_svs[:5]:
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
        items.append(
            {
                "type": "SV_QUALITY_GAP",
                "target": fqn,
                "detail": f"Quality: {sig['quality_score'] * 100:.0f}/100",
                "recommendation": (
                    f"Add: {', '.join(missing[:4])}."
                    if missing
                    else "Improve SV metadata."
                ),
            }
        )

    return items
