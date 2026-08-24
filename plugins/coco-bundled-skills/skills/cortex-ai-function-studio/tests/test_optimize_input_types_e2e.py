# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""E2E: optimize AI-function input types; assert each experiment's run tree.

For each scenario YAML under ``tests/e2e_scenarios/optimize_input_types/`` the
test creates the AI function + a typed training table, runs a real in-process
``run_body_optimization`` (demo budget, one cheap model, a dozen rows) against a
live Snowflake session, then reads the resulting experiment into the tree::

    {experiment_name: {run_name: {metrics, parameters, metadata}}}

logs it, and asserts the schema-v4 global invariants (single ``SEED`` run
carrying the input model + summed totals + per_model_stats; every other run a
global ``ITER_<N>`` with a ``run_type`` label).  These per-scenario assertions
are deterministic, so no separate structural schema pass is needed.

The scenarios cover the distinct SQL input-type families (VARCHAR / NUMBER /
FLOAT / BOOLEAN / ARRAY / OBJECT / VARIANT) plus a FILE (multimodal) input that
reads an image from a stage via ``TO_FILE`` — the loader provisions a
server-side-encrypted stage (AI file reads reject client-side encryption) and
uploads the fixture images for that one.

Gated by ``@pytest.mark.e2e`` (needs a live connection + the ``run-e2e-test``
PR label).  Note: with the repo's ``--dist=loadfile`` xdist policy the
scenarios run sequentially on one worker (in parallel with other e2e files);
each uses the smallest viable optimize config to keep that bounded.

Run:
    uv run --group test pytest tests/test_optimize_input_types_e2e.py
"""

from __future__ import annotations

import logging

import pytest
from _experiment_tree import (
    build_experiment_tree,
    render_experiment_tree,
)
from _optimize_scenario import (
    drop_scenario_objects,
    load_scenarios,
    run_scenario_optimization,
)
from snowflake.snowpark import Session

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.e2e

_SCENARIOS = load_scenarios()
_IDS = [s["name"] for s in _SCENARIOS]


@pytest.fixture(scope="module")
def session(request):
    conn_name = request.config.getoption("--connection", default="snowhouse")
    sess = Session.builder.config("connection_name", conn_name).create()
    yield sess
    sess.close()


@pytest.mark.parametrize("scenario", _SCENARIOS, ids=_IDS)
def test_optimize_input_type_experiment_tree(session, run_key, scenario):
    db = session.get_current_database().strip('"')
    schema = session.get_current_schema().strip('"')

    handles = None
    try:
        handles = run_scenario_optimization(session, db, schema, scenario, run_key)
        experiment = handles["experiment"]

        tree = build_experiment_tree(session, experiment)
        logger.info(
            "[%s] experiment JSON tree:\n%s",
            scenario["name"],
            render_experiment_tree(tree),
        )

        runs = tree[experiment]

        # --- schema-v4 global run-structure invariants ---
        assert "SEED" in runs, f"[{scenario['name']}] no single SEED run: {list(runs)}"
        seed = runs["SEED"]
        assert seed["parameters"].get("run_type") == "seed"
        # SEED.model is the INPUT function's own model.
        assert seed["parameters"].get("model") == scenario["seed_model"], (
            f"[{scenario['name']}] SEED.model={seed['parameters'].get('model')!r} "
            f"!= input model {scenario['seed_model']!r}"
        )
        # SEED is the global summary anchor: summed totals + per-model JSON.
        assert "total_candidates" in seed["parameters"]
        assert "per_model_stats" in seed["parameters"]

        # Every non-SEED run is a global ITER_<N> with a role label; there are
        # NO legacy per-model (<MODEL>_SEED / <MODEL>_ITER_ / *_REJECTED_*) names.
        for name, run in runs.items():
            if name == "SEED":
                continue
            assert name.startswith("ITER_"), (
                f"[{scenario['name']}] unexpected non-global run name {name!r}"
            )
            run_type = run["parameters"].get("run_type")
            assert run_type in ("iteration", "rejected"), (
                f"[{scenario['name']}] {name} run_type={run_type!r}"
            )
    finally:
        if handles is not None:
            drop_scenario_objects(session, handles)
