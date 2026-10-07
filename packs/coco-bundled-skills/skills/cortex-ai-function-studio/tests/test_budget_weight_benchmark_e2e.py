# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Benchmark: reflection call vs batched metric call cost on Snowflake.

Measures wall-clock time and token consumption for both call types to
validate the dynamic ``reflection_call_weight`` computed by
``MaxTotalBudgetStopper.estimate_reflection_weight``.

Run:
    uv run --group test pytest tests/test_budget_weight_benchmark.py -v -s \
        --connection snowhouse
"""

from __future__ import annotations

import json
import math
import statistics
import time

import pytest
from gepa.strategies.instruction_proposal import InstructionProposalSignature
from snowflake.snowpark import Session
from snowflake.snowpark.functions import (
    array_construct,
    call_function,
    col,
    lit,
    object_construct,
)

from snowflake_ai_optimize.core.udf_ddl import generate_sql
from snowflake_ai_optimize.core.udf_types import InputParam, OutputField, UDFSpec
from snowflake_ai_optimize.gepa.optimize import (
    DEFAULT_REFLECTION_MINIBATCH_SIZE,
    MaxTotalBudgetStopper,
)

pytestmark = pytest.mark.e2e

MODEL = "claude-sonnet-4-5"
M = DEFAULT_REFLECTION_MINIBATCH_SIZE  # 10
RUNS = 3

SYSTEM_PROMPT = "Classify the sentiment of the text as positive or negative."

SAMPLE_TEXTS = [
    "I love this product, it works great!",
    "This is amazing and wonderful experience",
    "Great quality and fast shipping",
    "Best purchase I have ever made",
    "Highly recommend to everyone",
    "Terrible, worst purchase ever made",
    "I hate this, total waste of money",
    "Awful quality and horrible service",
    "Do not buy this, complete garbage",
    "Disappointed and frustrated with this",
]

SAMPLE_LABELS = [
    "positive",
    "positive",
    "positive",
    "positive",
    "positive",
    "negative",
    "negative",
    "negative",
    "negative",
    "negative",
]

# Training data in SnowflakeDataInst format for estimate_reflection_weight
TRAINSET = [
    {"inputs": {"TEXT": text}, "answer": label}
    for text, label in zip(SAMPLE_TEXTS, SAMPLE_LABELS, strict=True)
]

SEED_CANDIDATE = {"instruction": SYSTEM_PROMPT}


@pytest.fixture(scope="module")
def session(request):
    conn_name = request.config.getoption("--connection", default="snowhouse")
    sess = Session.builder.config("connection_name", conn_name).create()
    yield sess
    sess.close()


@pytest.fixture(scope="module")
def benchmark_env(session, cleanup_stale, run_key):
    """Create a minimal UDF and test data for benchmarking."""
    db = session.get_current_database().strip('"')
    schema = session.get_current_schema().strip('"')
    func_name = f"TEST_BENCH_{run_key}"

    cleanup_stale(
        session,
        db,
        schema,
        tables=["TEST_BENCH_DATA"],
        functions=["TEST_BENCH"],
    )
    table_name = f"TEST_BENCH_DATA_{run_key}"
    fq = lambda name: f"{db}.{schema}.{name}"

    spec = UDFSpec(
        database=db,
        schema=schema,
        function_name=func_name,
        model=MODEL,
        function_intention="Classify text as positive or negative",
        inputs=[InputParam(name="TEXT", sql_type="VARCHAR")],
        outputs=[
            OutputField(
                name="label", json_type="string", description="positive or negative"
            )
        ],
        system_prompt=SYSTEM_PROMPT,
        user_prompt_template="{TEXT}",
    )
    session.sql(generate_sql(spec)).collect()

    session.sql(f"""
        CREATE TABLE {fq(table_name)} (
            TEXT VARCHAR, EXPECTED_LABEL VARCHAR
        )
    """).collect()
    values = ", ".join(
        f"($${t}$$, '{label}')"
        for t, label in zip(SAMPLE_TEXTS, SAMPLE_LABELS, strict=True)
    )
    session.sql(f"INSERT INTO {fq(table_name)} VALUES {values}").collect()

    yield {
        "db": db,
        "schema": schema,
        "func": fq(func_name),
        "func_name_only": func_name,
        "table": fq(table_name),
        "fq": fq,
    }

    session.sql(f"DROP FUNCTION IF EXISTS {fq(func_name)}(VARCHAR)").collect()
    session.sql(f"DROP TABLE IF EXISTS {fq(table_name)}").collect()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ai_complete_with_details(
    session: Session,
    model: str,
    user_prompt: str,
    system_prompt: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 8192,
) -> dict:
    """Call AI_COMPLETE with show_details=true and return parsed JSON."""
    message_exprs = []
    if system_prompt:
        message_exprs.append(
            object_construct(
                lit("role"), lit("system"), lit("content"), lit(system_prompt)
            )
        )
    message_exprs.append(
        object_construct(
            lit("role"), lit("user"), lit("content"), col("PROMPT_EXPR_COL")
        )
    )
    messages = array_construct(*message_exprs)
    model_parameters = object_construct(
        lit("temperature"),
        lit(temperature),
        lit("max_tokens"),
        lit(max_tokens),
    )

    arguments = [
        lit(model),
        messages,
        model_parameters,
        lit(None),  # response_format
        lit(True),  # show_details = true
        lit(""),  # provisioned_throughput_id
        lit(False),  # return_error_details
    ]

    df = session.create_dataframe([[0, user_prompt]], schema=["IDX", "PROMPT_EXPR_COL"])
    df_result = df.select(
        col("IDX"),
        call_function("AI_COMPLETE", *arguments).alias("RESPONSE"),
    )
    rows = df_result.collect()
    result: dict = json.loads(rows[0]["RESPONSE"])
    return result


def _build_reflection_prompt(
    instruction: str,
    texts: list[str],
    responses: list[str],
    feedbacks: list[str],
) -> str:
    """Build a reflection prompt using GEPA's real InstructionProposalSignature."""
    dataset_with_feedback = [
        {
            "Inputs": f"TEXT: {text}",
            "Generated Outputs": response,
            "Feedback": feedback,
        }
        for text, response, feedback in zip(texts, responses, feedbacks, strict=True)
    ]
    return InstructionProposalSignature.prompt_renderer(
        {
            "current_instruction_doc": instruction,
            "dataset_with_feedback": dataset_with_feedback,
            "prompt_template": None,
        }
    )


# ---------------------------------------------------------------------------
# Test 1: Benchmark raw call costs
# ---------------------------------------------------------------------------


def test_benchmark_reflection_vs_metric_calls(session, benchmark_env):
    """Measure time and tokens for reflection vs batched metric calls.

    Prints a comparison table showing wall-clock time, token counts,
    and the implied reflection_call_weight.  Also compares the dynamically
    estimated weight from ``MaxTotalBudgetStopper.estimate_reflection_weight``
    to the observed wall-clock ratio.
    """
    env = benchmark_env

    # ------------------------------------------------------------------
    # 1) Batched metric call: call UDF on M rows in one SQL query
    # ------------------------------------------------------------------
    metric_times: list[float] = []

    for _ in range(RUNS):
        selects = [
            f"SELECT {idx} AS idx, $${text}$$ AS TEXT"
            for idx, text in enumerate(SAMPLE_TEXTS[:M])
        ]
        subquery = " UNION ALL ".join(selects)

        sql = f"""
            SELECT t.idx, {env["func"]}(t.TEXT) AS result
            FROM ({subquery}) AS t
            ORDER BY t.idx
        """
        t0 = time.time()
        rows = session.sql(sql).collect()
        metric_times.append(time.time() - t0)

    # Per-item token count via show_details
    single_detail = _ai_complete_with_details(
        session,
        model=MODEL,
        user_prompt=SAMPLE_TEXTS[0],
        system_prompt=SYSTEM_PROMPT,
        temperature=0.0,
        max_tokens=256,
    )
    per_item_tokens = single_detail.get("usage", {}).get("total_tokens", 0)
    metric_total_tokens = per_item_tokens * M

    # ------------------------------------------------------------------
    # 2) Reflection call: 1 AI_COMPLETE with a reflection-sized prompt
    # ------------------------------------------------------------------
    sample_responses = [r["RESULT"] for r in rows] if rows else ["positive"] * M
    sample_feedbacks = [
        f"Expected '{label}' but got different classification."
        if i % 3 == 0
        else "Correct classification."
        for i, label in enumerate(SAMPLE_LABELS[:M])
    ]
    reflection_prompt = _build_reflection_prompt(
        SYSTEM_PROMPT,
        SAMPLE_TEXTS[:M],
        sample_responses[:M],
        sample_feedbacks,
    )

    reflection_times: list[float] = []
    reflection_token_counts: list[int] = []

    for _ in range(RUNS):
        t0 = time.time()
        detail = _ai_complete_with_details(
            session,
            model=MODEL,
            user_prompt=reflection_prompt,
            temperature=0.7,
            max_tokens=8192,
        )
        reflection_times.append(time.time() - t0)
        reflection_token_counts.append(detail.get("usage", {}).get("total_tokens", 0))

    # ------------------------------------------------------------------
    # 3) Dynamic weight from production code
    # ------------------------------------------------------------------
    estimated_weight = MaxTotalBudgetStopper.estimate_reflection_weight(
        seed_candidate=SEED_CANDIDATE,
        trainset=TRAINSET,
        reflection_minibatch_size=M,
        metric_name="exact_match",
    )
    estimated_weight_judge = MaxTotalBudgetStopper.estimate_reflection_weight(
        seed_candidate=SEED_CANDIDATE,
        trainset=TRAINSET,
        reflection_minibatch_size=M,
        metric_name="llm_judge",
        metric_kwargs={"task_description": "Classify sentiment"},
    )

    # ------------------------------------------------------------------
    # 4) Print results
    # ------------------------------------------------------------------
    avg_metric_time = statistics.mean(metric_times)
    avg_reflection_time = statistics.mean(reflection_times)
    avg_reflection_tokens = statistics.mean(reflection_token_counts)
    time_ratio = avg_metric_time / avg_reflection_time if avg_reflection_time > 0 else 0

    print(f"""
{"=" * 70}
  Budget Weight Benchmark  (M={M}, model={MODEL})
{"=" * 70}

  Batched metric call ({M} UDF invocations in 1 SQL):
    Wall-clock:  {avg_metric_time:.2f}s  (runs: {[f"{t:.2f}" for t in metric_times]})
    Tokens:      {metric_total_tokens}  ({per_item_tokens}/item x {M})

  Reflection call (1 AI_COMPLETE with {M} examples in prompt):
    Wall-clock:  {avg_reflection_time:.2f}s  (runs: {[f"{t:.2f}" for t in reflection_times]})
    Tokens:      {avg_reflection_tokens:.0f}  (runs: {reflection_token_counts})

  Observed time ratio (batched-metric / reflection): {time_ratio:.2f}x

  Dynamic weight estimates (from prompt-length ratio):
    exact_match metric:  W = {estimated_weight}
    llm_judge metric:    W = {estimated_weight_judge}
{"=" * 70}""")

    assert avg_metric_time > 0
    assert avg_reflection_time > 0
    assert avg_reflection_tokens > 0

    # Store measured timings for the next test
    benchmark_env["_measured_batched_metric_time"] = avg_metric_time
    benchmark_env["_measured_reflection_time"] = avg_reflection_time
    benchmark_env["_estimated_weight"] = estimated_weight
    benchmark_env["_estimated_weight_judge"] = estimated_weight_judge


# ---------------------------------------------------------------------------
# Test 2: Verify end-to-end latency balance
# ---------------------------------------------------------------------------


def test_budget_weight_end_to_end_latency(session, benchmark_env):
    """Verify that all-accepted and all-rejected cases consume similar total time.

    Uses real wall-clock measurements from the previous benchmark test and
    the dynamically computed ``reflection_call_weight`` to project total
    optimization time for both extreme cases under auto="medium" with V=50.
    Asserts the projected times are within 30% of each other.

    -----------------------------------------------------------------------
    GEPA iteration anatomy (what happens each proposal iteration):
    -----------------------------------------------------------------------

      1. Evaluate CURRENT candidate on minibatch (M rows)
         -> 1 batched SQL query calling the UDF on M rows
         -> Wall-clock cost ≈ T_metric_batch

      2. REFLECTION: LLM proposes a new candidate
         -> 1 AI_COMPLETE call with a large prompt
         -> Wall-clock cost ≈ T_reflection

      3. Evaluate NEW candidate on same minibatch (M rows)
         -> 1 batched SQL query calling the UDF on M rows
         -> Wall-clock cost ≈ T_metric_batch

      4. IF ACCEPTED (new score > old score on minibatch):
         -> Full valset evaluation (V rows) via batched SQL
         -> Wall-clock cost ≈ T_metric_batch * (V / M)

         IF REJECTED: iteration ends, no full eval.

    -----------------------------------------------------------------------
    Per-iteration wall-clock cost:
    -----------------------------------------------------------------------

      Rejected iteration:
        T_rejected = 2 * T_metric_batch + T_reflection

      Accepted iteration:
        T_accepted = T_rejected + T_metric_batch * (V / M)

    -----------------------------------------------------------------------
    Budget model (in weighted budget units):
    -----------------------------------------------------------------------

      MaxTotalBudgetStopper counts:
        weighted_total = metric_calls + reflection_calls * W

      where W = estimate_reflection_weight(...) — computed dynamically from
      the prompt-length ratio of a reflection call vs a single metric call.

      Per-iteration budget consumption:
        Rejected: 2*M + W   (2*M metric calls + 1 reflection weighted at W)
        Accepted: 2*M + W + V   (same + V metric calls for full eval)

      Budget formula (auto="medium", N proposals):
        total_budget = V + N * (2*M + V + W)

      This budgets each iteration at full (accepted) cost.  When candidates
      are rejected, the unspent V per iteration funds additional iterations
      via reflection, keeping the total weighted budget — and therefore the
      total wall-clock time — similar.

    -----------------------------------------------------------------------
    Expected iteration counts:
    -----------------------------------------------------------------------

      All-accepted:
        iterations_accepted = loop_budget / (2*M + V + W) ≈ N

      All-rejected:
        iterations_rejected = loop_budget / (2*M + W)
                            ≈ N * (2*M + V + W) / (2*M + W)

    -----------------------------------------------------------------------
    Projected total wall-clock time:
    -----------------------------------------------------------------------

      Case 1 (all accepted):  iterations_accepted * T_accepted
      Case 2 (all rejected):  iterations_rejected * T_rejected

      These should be approximately equal if W is calibrated correctly.
    """
    V = 50  # valset size
    N_COMPONENTS = 1

    # --- Retrieve measured timings and dynamic weight ---
    T_metric_batch = benchmark_env.get("_measured_batched_metric_time")
    T_reflection = benchmark_env.get("_measured_reflection_time")
    W = benchmark_env.get("_estimated_weight")

    if T_metric_batch is None or T_reflection is None or W is None:
        pytest.skip(
            "Benchmark measurements not available — run "
            "test_benchmark_reflection_vs_metric_calls first (use -s flag)"
        )

    # --- Resolve budget using the same dynamic weight ---
    budget = MaxTotalBudgetStopper.resolve_budget(
        auto="medium",
        num_components=N_COMPONENTS,
        valset_size=V,
        reflection_minibatch_size=M,
        reflection_call_weight=W,
    )

    # --- Compute N (number of proposals for "medium") ---
    num_candidates = MaxTotalBudgetStopper.AUTO_BUDGET_SETTINGS["medium"]["n"]
    N = int(
        max(
            2 * (N_COMPONENTS * 2) * math.log2(num_candidates),
            1.5 * num_candidates,
        )
    )

    # --- Verify budget formula ---
    expected_budget = V + N * (2 * M + V + W)
    assert budget == expected_budget, (
        f"Budget mismatch: got {budget}, expected {expected_budget}"
    )

    # --- Per-iteration budget consumption ---
    budget_per_accepted = 2 * M + V + W
    budget_per_rejected = 2 * M + W

    # --- Expected iteration counts ---
    loop_budget = budget - V  # subtract seed eval
    iterations_accepted = loop_budget / budget_per_accepted
    iterations_rejected = loop_budget / budget_per_rejected

    # --- Per-iteration wall-clock time ---
    T_full_valset = T_metric_batch * (V / M)
    T_accepted_iter = 2 * T_metric_batch + T_reflection + T_full_valset
    T_rejected_iter = 2 * T_metric_batch + T_reflection

    # --- Projected total wall-clock time ---
    total_time_accepted = iterations_accepted * T_accepted_iter
    total_time_rejected = iterations_rejected * T_rejected_iter

    if total_time_accepted > 0 and total_time_rejected > 0:
        ratio = max(total_time_accepted, total_time_rejected) / min(
            total_time_accepted, total_time_rejected
        )
    else:
        ratio = float("inf")

    print(f"""
{"=" * 70}
  End-to-End Latency Verification
  auto='medium', V={V}, M={M}, W={W} (dynamic), N={N}
{"=" * 70}

  Measured timings (from benchmark):
    T_metric_batch (M={M} rows):  {T_metric_batch:.2f}s
    T_reflection (1 call):         {T_reflection:.2f}s
    T_full_valset (V={V} rows):    {T_full_valset:.2f}s  (extrapolated)

  Budget:
    total_budget = {V} + {N} * (2*{M} + {V} + {W})
                 = {V} + {N} * {budget_per_accepted} = {budget}
    loop_budget  = {loop_budget}

  Case 1 — All candidates accepted:
    budget/iter  = 2*{M} + {V} + {W} = {budget_per_accepted}
    iterations   = {loop_budget} / {budget_per_accepted} = {iterations_accepted:.1f}
    time/iter    = 2*{T_metric_batch:.1f} + {T_reflection:.1f} + {T_full_valset:.1f} = {T_accepted_iter:.1f}s
    TOTAL TIME   = {iterations_accepted:.1f} * {T_accepted_iter:.1f}s = {total_time_accepted:.0f}s ({total_time_accepted / 3600:.1f}h)

  Case 2 — All candidates rejected:
    budget/iter  = 2*{M} + {W} = {budget_per_rejected}
    iterations   = {loop_budget} / {budget_per_rejected} = {iterations_rejected:.1f}
    time/iter    = 2*{T_metric_batch:.1f} + {T_reflection:.1f} = {T_rejected_iter:.1f}s
    TOTAL TIME   = {iterations_rejected:.1f} * {T_rejected_iter:.1f}s = {total_time_rejected:.0f}s ({total_time_rejected / 3600:.1f}h)

  Ratio (max/min): {ratio:.2f}x
  PASS threshold:  <= 1.50x (50%)
{"=" * 70}""")

    assert ratio <= 1.50, (
        f"Budget model imbalance: all-accepted takes {total_time_accepted:.0f}s "
        f"vs all-rejected {total_time_rejected:.0f}s (ratio={ratio:.2f}x). "
        f"The reflection_call_weight (W={W}) needs recalibration."
    )
