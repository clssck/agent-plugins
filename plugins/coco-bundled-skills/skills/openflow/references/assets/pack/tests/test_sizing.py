from __future__ import annotations

import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent.parent
if str(ASSETS) not in sys.path:
    sys.path.insert(0, str(ASSETS))

from pack.config_loader import Config, ConnectorEntry
from pack import sizing


def _cfg(connectors, shared=None):
    return Config(
        runtime="rt1",
        connector_type="postgresql",
        shared=shared or {"snowflake": {}, "source": {}},
        connectors=connectors,
    )


def test_recommends_small_at_small_boundary():
    cfg = _cfg([
        ConnectorEntry(name="c1", tables=[f"public.t{i}" for i in range(99)], sizing={"active_fraction": 1.0}),
        ConnectorEntry(name="c2", tables=["public.one"], sizing={"active_fraction": 1.0}),
    ])

    advice = sizing.advise(cfg, runtime_size="small")

    assert advice.runtime_current_size == "Small"
    assert advice.runtime_recommended_size == "Small"
    assert advice.aggregate_active_tables == 100


def test_recommends_medium_when_small_connector_soft_cap_exceeded():
    cfg = _cfg([
        ConnectorEntry(name="c1", tables=["public.a"]),
        ConnectorEntry(name="c2", tables=["public.b"]),
        ConnectorEntry(name="c3", tables=["public.c"]),
    ])

    advice = sizing.advise(cfg, runtime_size="Small")

    assert advice.runtime_recommended_size == "Medium"
    assert any("recommend resize to Medium" in warning for warning in advice.warnings)


def test_recommends_large_when_medium_active_table_ceiling_exceeded():
    cfg = _cfg([
        ConnectorEntry(name="c1", tables=[f"public.t{i}" for i in range(1201)], sizing={"active_fraction": 1.0}),
    ])

    advice = sizing.advise(cfg, runtime_size="Medium")

    assert advice.runtime_recommended_size == "Large"


def test_continuous_high_eps_is_blocked():
    cfg = _cfg([
        ConnectorEntry(name="busy", tables=["public.t"], sizing={"eps_per_connector": 15001}),
    ])

    advice = sizing.advise(cfg, runtime_size="Large")

    assert any("15,001 EPS" in blocker for blocker in advice.blockers)


def test_scheduled_merge_skips_high_eps_blocker():
    cfg = _cfg(
        [ConnectorEntry(name="scheduled", tables=["public.t"], sizing={"eps_per_connector": 15001})],
        shared={
            "snowflake": {},
            "source": {},
            "ingestion": {"Merge Task Schedule": "* * * * * ?"},
        },
    )

    advice = sizing.advise(cfg, runtime_size="Large")

    assert advice.blockers == []
    assert not advice.per_connector[0].continuous
    assert any("scheduled merge" in note for note in advice.notes)


def test_connector_override_schedule_takes_precedence_over_shared_continuous():
    cfg = _cfg(
        [ConnectorEntry(
            name="scheduled",
            tables=["public.t"],
            overrides={"merge_task_schedule": "0 0 * * * ?"},
            sizing={"eps_per_connector": 15001},
        )],
        shared={"snowflake": {}, "source": {}, "ingestion": {"Merge Task Schedule": "continuous"}},
    )

    advice = sizing.advise(cfg, runtime_size="Large")

    assert advice.blockers == []
    assert not advice.per_connector[0].continuous


def test_table_regex_counts_as_fifty_tables():
    cfg = _cfg([ConnectorEntry(name="regex", tables_regex="^public\\..*")])

    advice = sizing.advise(cfg, runtime_size="Small")

    assert advice.per_connector[0].tables_in_scope == 50
    assert advice.per_connector[0].active_tables == 15