"""Step 3 helper — sizing advisor.

Implements the CDC connector bin-packing sizing heuristic. Always sizes against
`active_tables`, never `tables_in_scope`, and always shows both numbers
explicitly so the customer can sanity-check the active-fraction assumption.

The EPS / latency ceiling only applies to **continuous** replication. For a
connector on a scheduled merge (a non-empty, non-"continuous" Merge Task
Schedule), end-to-end latency is not a meaningful constraint, so the per-
connector EPS hard-block is skipped — such connectors are sized on table count
and throughput only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .config_loader import Config, ConnectorEntry


RuntimeSize = Literal["Small", "Medium", "Large"]

# Runtime ceilings, denominated in active tables.
_RUNTIME_CEILINGS: dict[RuntimeSize, dict[str, float]] = {
    "Small":  {"active_tables_p90": 100,  "active_tables_max": 100,   "throughput_mb_s": 40,  "soft_cap_connectors": 2},
    "Medium": {"active_tables_p90": 300,  "active_tables_max": 1200,  "throughput_mb_s": 100, "soft_cap_connectors": 8},
    "Large":  {"active_tables_p90": 400,  "active_tables_max": 3000,  "throughput_mb_s": 150, "soft_cap_connectors": 18},
}

DEFAULT_ACTIVE_FRACTION = 0.30
DEFAULT_EPS_PER_CONNECTOR = 100
VERY_HIGH_EPS_PER_CONNECTOR = 15_000     # hard-block (continuous only): isolate this connector
HIGH_ACTIVE_FRACTION_WARN = 0.50         # warn: atypical for bin-pack target audience


@dataclass
class ConnectorSizing:
    name: str
    tables_in_scope: int
    active_fraction: float
    active_tables: int
    eps: int
    continuous: bool = True


@dataclass
class SizingAdvice:
    runtime_current_size: RuntimeSize
    runtime_recommended_size: RuntimeSize
    aggregate_tables_in_scope: int
    aggregate_active_tables: int
    aggregate_eps: int
    per_connector: list[ConnectorSizing]
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def needs_resize(self) -> bool:
        return self.runtime_current_size != self.runtime_recommended_size


def advise(
    cfg: Config,
    *,
    runtime_size: RuntimeSize,
    runtime_node_count: int = 1,
) -> SizingAdvice:
    # Normalize input case: callers pass "MEDIUM" / "medium" / "Medium" — match
    # the canonical mixed-case form used by _RUNTIME_CEILINGS so the
    # `current != recommended` warning doesn't fire on a pure case mismatch.
    runtime_size = _normalize_size(runtime_size)
    shared_sizing = (cfg.shared.get("sizing") or {})
    default_active = float(shared_sizing.get("active_fraction", DEFAULT_ACTIVE_FRACTION))
    default_eps = int(shared_sizing.get("eps_per_connector", DEFAULT_EPS_PER_CONNECTOR))

    per_connector: list[ConnectorSizing] = []
    for c in cfg.connectors:
        c_sizing = c.sizing or {}
        active_fraction = float(c_sizing.get("active_fraction", default_active))
        eps = int(c_sizing.get("eps_per_connector", default_eps))
        tables_in_scope = _count_tables(c)
        active_tables = max(1, round(tables_in_scope * active_fraction))
        per_connector.append(ConnectorSizing(
            name=c.name,
            tables_in_scope=tables_in_scope,
            active_fraction=active_fraction,
            active_tables=active_tables,
            eps=eps,
            continuous=_is_continuous(cfg, c),
        ))

    agg_tables_in_scope = sum(p.tables_in_scope for p in per_connector)
    agg_active = sum(p.active_tables for p in per_connector)
    agg_eps = sum(p.eps for p in per_connector)

    recommended = _recommend_size(
        agg_active=agg_active,
        connector_count=len(per_connector),
    )
    blockers, warnings = _check_thresholds(
        per_connector=per_connector,
        agg_active=agg_active,
        recommended=recommended,
        runtime_size=runtime_size,
    )

    notes: list[str] = []
    if any(p.active_fraction > HIGH_ACTIVE_FRACTION_WARN for p in per_connector):
        notes.append(
            f"At least one connector pins active_fraction > {HIGH_ACTIVE_FRACTION_WARN:.0%} — "
            "atypical for the bin-packing target audience (multi-tenant SaaS, fleet-of-DBs). "
            "Consider whether bin packing is the right pattern, or isolate the busy source on a dedicated runtime."
        )
    if all(p.active_fraction == DEFAULT_ACTIVE_FRACTION for p in per_connector):
        notes.append(
            f"Active-fraction estimate uses the default ({DEFAULT_ACTIVE_FRACTION:.0%}). "
            "If your workload is significantly different, set `shared.sizing.active_fraction` and re-plan — "
            "sizing on all tables (instead of active tables) overshoots by 3–10×."
        )
    if any(not p.continuous for p in per_connector):
        notes.append(
            "One or more connectors use a scheduled merge (not continuous). For those, "
            "the EPS / latency ceiling does not apply and was skipped — they are sized on "
            "table count and throughput only."
        )

    return SizingAdvice(
        runtime_current_size=runtime_size,
        runtime_recommended_size=recommended,
        aggregate_tables_in_scope=agg_tables_in_scope,
        aggregate_active_tables=agg_active,
        aggregate_eps=agg_eps,
        per_connector=per_connector,
        blockers=blockers,
        warnings=warnings,
        notes=notes,
    )


def _normalize_size(s: str) -> RuntimeSize:
    """Map any-case runtime size string to the canonical mixed-case form."""
    table = {"small": "Small", "medium": "Medium", "large": "Large"}
    return table.get((s or "").lower(), s)  # type: ignore[return-value]


def _recommend_size(*, agg_active: int, connector_count: int) -> RuntimeSize:
    """Pick the smallest size whose P90-relaxed (aka active_tables_max) ceiling
    fits aggregate active tables AND whose soft cap fits the connector count."""
    for size in ("Small", "Medium", "Large"):
        ceil = _RUNTIME_CEILINGS[size]  # type: ignore[index]
        if agg_active <= ceil["active_tables_max"] and connector_count <= ceil["soft_cap_connectors"]:
            return size  # type: ignore[return-value]
    return "Large"


def _check_thresholds(
    *,
    per_connector: list[ConnectorSizing],
    agg_active: int,
    recommended: RuntimeSize,
    runtime_size: RuntimeSize,
) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    ceil = _RUNTIME_CEILINGS[recommended]

    for p in per_connector:
        # The EPS ceiling is a latency guard — only meaningful for continuous
        # replication. Skip it for connectors on a scheduled merge.
        if p.continuous and p.eps > VERY_HIGH_EPS_PER_CONNECTOR:
            blockers.append(
                f"connector {p.name!r}: {p.eps:,} EPS exceeds the recommended max sustained "
                f"EPS for a single connector ({VERY_HIGH_EPS_PER_CONNECTOR:,}) — isolate on a dedicated runtime"
            )

    if agg_active > 2 * ceil["active_tables_max"]:
        blockers.append(
            f"aggregate active tables {agg_active:,} exceeds 2× the {recommended} runtime's "
            f"max-latency ceiling ({int(ceil['active_tables_max']):,}) — size up or split"
        )
    if len(per_connector) > 2 * int(ceil["soft_cap_connectors"]):
        blockers.append(
            f"connector count {len(per_connector)} exceeds 2× the {recommended} runtime's soft cap "
            f"({int(ceil['soft_cap_connectors'])}) — size up or split"
        )

    if recommended != runtime_size:
        warnings.append(
            f"current runtime is {runtime_size}; recommend resize to {recommended} before apply"
        )

    return blockers, warnings


def _count_tables(c: ConnectorEntry) -> int:
    if c.tables:
        return len(c.tables)
    return 50 if c.tables_regex else 0


def _is_continuous(cfg: Config, c: ConnectorEntry) -> bool:
    """True if the connector replicates continuously (latency matters), False if
    it runs on a scheduled merge (latency does not apply, so EPS ceilings are
    skipped).

    Reads "Merge Task Schedule" from the per-connector overrides, then the shared
    ingestion block. A connector is treated as continuous when no schedule is set,
    when it is blank, or when it is explicitly "continuous". Any other value (e.g.
    a cron expression like "* * * * * ?") is a scheduled merge.
    """
    def _lookup(d: dict) -> object:
        if not isinstance(d, dict):
            return None
        for key in ("Merge Task Schedule", "merge_task_schedule"):
            if key in d and d[key] is not None:
                return d[key]
        return None

    sched = _lookup(c.overrides)
    if sched is None:
        sched = _lookup(cfg.shared.get("ingestion") or {})
    if sched is None:
        return True
    s = str(sched).strip().lower()
    return s == "" or s == "continuous"
