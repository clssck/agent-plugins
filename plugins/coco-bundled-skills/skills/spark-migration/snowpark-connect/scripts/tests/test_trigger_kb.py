"""Tests for the offline trigger-KB RAG backend (rag/trigger_kb.py)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rag import SCOSSearchResult, SCOSTriggerRAG  # noqa: E402
from rag.trigger_kb import SEVERITY_SCORE, TriggerKB, _rule_decidable  # noqa: E402


@pytest.fixture(scope="module")
def kb() -> TriggerKB:
    return TriggerKB.load()


def _anchors(matches) -> set[str]:
    return {m.anchor for m in matches}


def test_kb_loads_rules(kb: TriggerKB) -> None:
    assert len(kb.rules) > 100
    # every rule carries the unified schema fields
    for r in kb.rules[:50]:
        assert {"rule_id", "anchor", "match_tokens", "severity",
                "disposition", "note", "trigger_kind"} <= set(r)


def test_python_call_anchor_fires(kb: TriggerKB) -> None:
    code = 'res = df.agg(F.approx_count_distinct("c", rsd=0.05))'
    matches = kb.detect(code)
    assert "approx_count_distinct" in _anchors(matches)


def test_dotted_path_anchor_fires(kb: TriggerKB) -> None:
    code = 'v = dbutils.notebook.run("./child", 60)'
    matches = kb.detect(code)
    assert any("dbutils.notebook.run" in a for a in _anchors(matches))


def test_bare_function_fires_as_python_and_sql(kb: TriggerKB) -> None:
    """A bare function anchor must fire both as a PySpark call and as a SQL function."""
    py = kb.detect('r = df.select(F.try_multiply("a", "b"))')
    assert "try_multiply" in _anchors(py)
    sql = kb.detect('df = spark.sql("SELECT try_multiply(a, b) FROM t")')
    assert "try_multiply" in _anchors(sql)


def test_function_anchor_labelled_python_or_sql(kb: TriggerKB) -> None:
    """Bare function names (valid in both Python and SQL) are not mislabeled
    sql_construct: they are either ``python_or_sql`` or, when the API-catalog
    miner supplies a documented signature, the more precise ``signature`` kind
    (both are call-aware). Only true SQL clauses keep the ``sql_construct`` label."""
    by_anchor = {r["anchor"]: r for r in kb.rules}
    tt = by_anchor.get("try_to_timestamp")
    assert tt is not None and tt["trigger_kind"] in ("python_or_sql", "signature")
    # a real SQL-only clause stays sql_construct
    assert any(r["trigger_kind"] == "sql_construct" and " " not in r["anchor"]
               for r in kb.rules)


def test_manual_rules_sorted_last(kb: TriggerKB) -> None:
    kinds = [r["trigger_kind"] for r in kb.rules]
    first_manual = next((i for i, k in enumerate(kinds) if k == "manual"), len(kinds))
    last_auto = max((i for i, k in enumerate(kinds) if k != "manual"), default=-1)
    assert first_manual > last_auto


@pytest.mark.parametrize("code,anchor", [
    ('spark.sql("SELECT dept AS dept, avg(sal) FROM emp GROUP BY dept")',
     "SELECT alias collides with column name (LCA)"),
    ('spark.sql("SELECT SUM(CASE WHEN x>0 THEN 1 ELSE 0 END) OVER (PARTITION BY y) FROM t")',
     "CASE expression as window aggregate"),
    ('spark.sql("SELECT * FROM a LEFT OUTER JOIN b ON a.id=b.id AND a.k IN (SELECT k FROM c)")',
     "IN (SELECT ...) in LEFT JOIN ON clause"),
    ('spark.sql("SELECT CAST(n AS INTERVAL DAY) FROM t")',
     "CAST to INTERVAL type"),
])
def test_structural_detectors_fire(kb: TriggerKB, code: str, anchor: str) -> None:
    assert anchor in _anchors(kb.detect(code))


def test_spark_conf_set_gated_to_databricks(kb: TriggerKB) -> None:
    """spark.conf.set only fires for spark.databricks.* configs, not generic
    spark.sql.* tuning (which were false positives)."""
    assert "spark.conf.set" not in _anchors(
        kb.detect('spark.conf.set("spark.sql.shuffle.partitions", "200")'))
    assert "spark.conf.set" not in _anchors(
        kb.detect('spark.conf.set("spark.sql.streaming.ui.retainedProgressUpdates", "100")'))
    assert "spark.conf.set" in _anchors(
        kb.detect('spark.conf.set("spark.databricks.delta.optimizeWrite.enabled", "true")'))


def test_structural_detectors_no_overfire(kb: TriggerKB) -> None:
    benign = 'spark.sql("SELECT a, b FROM t WHERE c > 1 GROUP BY a, b")'
    detector_hits = [a for a in _anchors(kb.detect(benign))
                     if a.startswith(("SELECT alias", "CASE expr", "IN (SELECT", "CAST to"))]
    assert detector_hits == []


def test_sql_construct_fires_inside_spark_sql(kb: TriggerKB) -> None:
    code = 'df = spark.sql("SELECT a FROM t QUALIFY row_number() OVER (ORDER BY a)=1")'
    matches = kb.detect(code)
    assert "QUALIFY" in _anchors(matches)


def test_benign_code_does_not_overfire(kb: TriggerKB) -> None:
    # Plain arithmetic / generic ops must not trip any rule.
    code = "x = 1 + 2\ny = [i for i in range(10)]\nz = sum(y)"
    assert kb.detect(code) == []


def test_generic_keywords_are_reference_only(kb: TriggerKB) -> None:
    # A bare SELECT/COUNT/PARTITION must not fire (those rules are 'manual').
    code = 'df = spark.sql("SELECT COUNT(*) FROM t GROUP BY a")'
    anchors = _anchors(kb.detect(code))
    assert "MIN" not in anchors and "count" not in anchors


def test_every_match_token_is_present(kb: TriggerKB) -> None:
    code = (
        'from pyspark.sql import functions as F\n'
        'm = F.create_map(F.lit(1), F.lit("a"))\n'
        'd = df.hint("broadcast")\n'
    )
    for m in kb.detect(code):
        assert m.matched_token.lower() in code.lower()


def test_applies_when_gates_on_argument(kb: TriggerKB) -> None:
    # The binary-file rule is anchored on spark.read.format but must only fire
    # for .format("binaryFile") — not for other formats like "snowflake".
    snowflake = 'df = spark.read.format("snowflake").option("query", "select 1").load()'
    binary = 'df = spark.read.format("binaryFile").load("/imgs")'
    assert "spark.read.format" not in {m.anchor for m in kb.detect(snowflake)}
    assert "spark.read.format" in {m.anchor for m in kb.detect(binary)}


def test_backend_search_returns_severity_scores() -> None:
    rag = SCOSTriggerRAG()
    results = rag.search('d = df.hint("broadcast")', limit=5)
    assert results and isinstance(results[0], SCOSSearchResult)
    assert results[0].score in SEVERITY_SCORE.values()
    assert results[0].root_cause  # makes will_likely_fail True


def test_backend_predict_failure_shape() -> None:
    rag = SCOSTriggerRAG()
    pred = rag.predict_failure('df.hint("broadcast")', limit=3)
    assert pred["failure_likelihood"] > 0
    assert pred["root_cause"]
    empty = rag.predict_failure("x = 1 + 2", limit=3)
    assert empty["failure_likelihood"] == 0.0
    assert empty["similar_patterns"] == []


# --------------------------------------------------------------------------
# Decidability: confidence (is the match a guaranteed true positive?) is
# orthogonal to severity. These exercise the gate the analyzer relies on.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("rule,expected", [
    # Unconditional triggers — decidable regardless of severity.
    ({"kind": "python_attribute", "status": "Unsupported", "severity": "high"}, True),
    ({"kind": "python_or_sql", "status": "Unsupported", "severity": "low"}, True),
    ({"kind": "signature", "status": "Partial", "severity": "high"}, True),
    ({"trigger_kind": "signature", "status": "Partial", "severity": "low"}, True),  # new key
    # Behavioral / context-dependent — NOT decidable even at high severity.
    ({"kind": "python_or_sql", "status": None, "severity": "high"}, False),
    ({"kind": "python_method", "severity": "high"}, False),
    ({"kind": "sql_construct", "status": None, "severity": "high"}, False),
])
def test_rule_decidable_is_orthogonal_to_severity(rule: dict, expected: bool) -> None:
    assert _rule_decidable(rule) is expected


@pytest.mark.parametrize("code,rule_id,severity", [
    ("v = data.treeAggregate(z, s, c)", "rdd_guide:treeAggregate", "medium"),
    ("v = rdd.treeReduce(add)", "rdd_guide:treeReduce", "medium"),
    ("m = rdd.collectAsMap()", "rdd_guide:collectAsMap", "medium"),
    ("n = rdd.countApprox(1000)", "rdd_guide:countApprox", "medium"),
    ("d = rdd.countApproxDistinct()", "rdd_guide:countApproxDistinct", "low"),
    ("x = rdd.meanApprox(1000)", "rdd_guide:meanApprox", "medium"),
    ("x = rdd.sumApprox(1000)", "rdd_guide:sumApprox", "medium"),
    ("r = rdd.collectWithJobGroup('g', 'd')", "rdd_guide:collectWithJobGroup", "medium"),
    ("p = rdd.mapPartitionsWithSplit(fn)", "rdd_guide:mapPartitionsWithSplit", "medium"),
    ("q = rdd.repartitionAndSortWithinPartitions(8)", "rdd_guide:repartitionAndSortWithinPartitions", "medium"),
    ("rdd.saveAsPickleFile('/p')", "rdd_guide:saveAsPickleFile", "medium"),
    ("rdd.saveAsObjectFile('/p')", "rdd_guide:saveAsObjectFile", "medium"),
    ("lvl = rdd.getStorageLevel()", "rdd_guide:getStorageLevel", "medium"),
    ("dbg = rdd.toDebugString()", "rdd_guide:toDebugString", "medium"),
    ("a = sc.collectionAccumulator()", "rdd_guide:collectionAccumulator", "medium"),
])
def test_rdd_migration_guide_rules_fire(kb: TriggerKB, code, rule_id, severity) -> None:
    """The hand-added RDD aggregate/accumulator/§10 rules fire on their token and
    point the fixer at references/python/rdd-conversion.md."""
    matches = [m for m in kb.detect(code) if m.rule_id == rule_id]
    assert matches, f"{rule_id} did not fire on {code!r}"
    m = matches[0]
    assert m.severity == severity
    assert "rdd-conversion.md" in m.note


def test_saveasobjectfile_rule_does_not_overfire_on_reader(kb: TriggerKB) -> None:
    """rdd_guide:saveAsObjectFile is the [Partial] SAVE op — it must NOT fire on
    the no-equivalent reader entry point sc.objectFile (distinct method name)."""
    reader_rules = [
        m for m in kb.detect('rdd = sc.objectFile("/p")')
        if m.rule_id == "rdd_guide:saveAsObjectFile"
    ]
    assert not reader_rules, "saveAsObjectFile rule over-fired on the objectFile reader"


def test_rdd_match_is_decidable(kb: TriggerKB) -> None:
    """The `.rdd` gateway (python_attribute, Unsupported) is statically certain."""
    matches = kb.detect("out = df.rdd.map(lambda r: r)")
    rdd = [m for m in matches if "rdd" in (m.matched_token + m.anchor).lower()]
    assert rdd and any(m.decidable for m in rdd)


def test_structural_detector_match_not_decidable(kb: TriggerKB) -> None:
    """Detector-based (structural-but-behavioral) matches stay on the LLM path."""
    code = 'spark.sql("SELECT dept AS dept, avg(sal) FROM emp GROUP BY dept")'
    det = [m for m in kb.detect(code) if m.anchor.startswith("SELECT alias")]
    assert det and not any(m.decidable for m in det)


def test_search_surfaces_decidable_flag() -> None:
    rag = SCOSTriggerRAG()
    results = rag.search("out = df.rdd.map(lambda r: r)", limit=5)
    assert results and any(r.decidable for r in results)


def test_fuzzy_result_defaults_not_decidable() -> None:
    """A non-trigger backend result (no decidable kwarg) defaults to False."""
    r = SCOSSearchResult.from_response({"code": "x", "root_cause": "y"})
    assert r.decidable is False


# --------------------------------------------------------------------------
# behavioral:1.7 (F.lit decimal precision) must only fire on numeric literals
# --------------------------------------------------------------------------


@pytest.mark.parametrize("code", [
    "x = F.lit(5)",
    "x = F.lit(3.14)",
    "x = F.lit(0)",
    "x = F.lit(-1.5)",
    'from decimal import Decimal\nx = F.lit(Decimal("1.2"))',
    'import decimal\nx = F.lit(decimal.Decimal("9.99"))',
])
def test_behavioral_1_7_fires_on_numeric_lit(kb: TriggerKB, code: str) -> None:
    """behavioral:1.7 fires when F.lit wraps a numeric literal."""
    matches = kb.detect(code)
    assert any(m.rule_id == "behavioral:1.7" for m in matches), (
        f"Expected behavioral:1.7 to fire on: {code!r}")


@pytest.mark.parametrize("code", [
    "x = F.lit('')",
    "x = F.lit('UNK')",
    'x = F.lit("hello")',
    "x = F.lit(True)",
    "x = F.lit(False)",
    "x = F.lit(None)",
    "x = F.lit(some_var)",
    "x = F.lit(get_value())",
])
def test_behavioral_1_7_does_not_fire_on_non_numeric(kb: TriggerKB, code: str) -> None:
    """behavioral:1.7 must NOT fire on string/bool/None/variable args."""
    matches = kb.detect(code)
    assert not any(m.rule_id == "behavioral:1.7" for m in matches), (
        f"behavioral:1.7 should NOT fire on: {code!r}")


# --------------------------------------------------------------------------
# noarg_method gate — apicat:dataframe-count-perf
# --------------------------------------------------------------------------


@pytest.mark.parametrize("code", [
    "n = df.count()",
    "result = my_dataframe.count()",
    "if spark.table('t').count() > 0: pass",
    "x = self.df.count()",
])
def test_count_perf_fires_on_noarg_method(kb: TriggerKB, code: str) -> None:
    """apicat:dataframe-count-perf fires on DataFrame.count() (no args)."""
    matches = kb.detect(code)
    assert any(m.rule_id == "apicat:dataframe-count-perf" for m in matches), (
        f"Expected apicat:dataframe-count-perf to fire on: {code!r}")


@pytest.mark.parametrize("code", [
    "x = F.count('*')",
    "x = F.count(F.expr('*'))",
    "x = functions.count(col_name)",
    "x = F.count(F.col('id'))",
    "from pyspark.sql import functions\nx = functions.count('x')",
    "df.agg(F.count('id').alias('cnt'))",
    "df.groupBy('a').agg(F.count('b'))",
])
def test_count_perf_does_not_fire_on_F_count(kb: TriggerKB, code: str) -> None:
    """apicat:dataframe-count-perf must NOT fire on F.count(...) aggregate."""
    matches = kb.detect(code)
    assert not any(m.rule_id == "apicat:dataframe-count-perf" for m in matches), (
        f"apicat:dataframe-count-perf should NOT fire on: {code!r}")


# --------------------------------------------------------------------------
# behavioral:12.10 (saveAsTable format-dropped) must NOT fire on iceberg
# --------------------------------------------------------------------------


@pytest.mark.parametrize("code", [
    'df.write.format("iceberg").saveAsTable("my_table")',
    "df.write.format('iceberg').saveAsTable('t')",
    'df.write.format("iceberg").mode("overwrite").saveAsTable("t")',
    'df.write.format("iceberg").partitionBy("col").saveAsTable("t")',
])
def test_saveastable_format_dropped_not_fired_for_iceberg(kb: TriggerKB, code: str) -> None:
    """behavioral:12.10 must NOT fire when .format("iceberg") is in the writer chain."""
    matches = kb.detect(code)
    assert not any(m.rule_id == "behavioral:12.10" for m in matches), (
        f"behavioral:12.10 should NOT fire on iceberg writer: {code!r}")


@pytest.mark.parametrize("code", [
    'df.write.format("parquet").saveAsTable("t")',
    'df.write.format("json").saveAsTable("t")',
    'df.write.saveAsTable("t", format="parquet")',
])
def test_saveastable_format_dropped_still_fires_for_unsupported(kb: TriggerKB, code: str) -> None:
    """behavioral:12.10 must still fire for non-iceberg format chains."""
    matches = kb.detect(code)
    assert any(m.rule_id == "behavioral:12.10" for m in matches), (
        f"behavioral:12.10 should fire on: {code!r}")


# --------------------------------------------------------------------------
# Line anchoring: embedded SQL findings map to the spark.sql() Python line
# --------------------------------------------------------------------------


def test_embedded_sql_finding_anchors_to_spark_sql_line(kb: TriggerKB) -> None:
    """An embedded SQL function finding (e.g. PERCENTILE_CONT) anchors to the
    Python line of the spark.sql(...) call, not a random unrelated line."""
    code = (
        "import os\n"                                     # line 1
        "x = 42\n"                                        # line 2
        "result = spark.sql(\"SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY sal) FROM emp\")\n"  # line 3
        "y = datetime.now().date()\n"                     # line 4
    )
    matches = kb.detect(code)
    sql_funcs = [m for m in matches if "percentile" in m.anchor.lower()
                 or "percentile" in m.matched_token.lower()]
    assert sql_funcs, "Expected at least one PERCENTILE finding"
    for m in sql_funcs:
        assert m.line == 3, (
            f"SQL finding '{m.anchor}' should anchor to line 3 (spark.sql call), "
            f"got line {m.line}")


def test_multiple_findings_preserve_line_order(kb: TriggerKB) -> None:
    """Multiple findings on different lines retain their correct line numbers."""
    code = (
        "a = df.rdd.map(lambda r: r)\n"            # line 1: .rdd finding
        "b = 1\n"                                    # line 2: no finding
        "c = df.write.format(\"parquet\").saveAsTable(\"t\")\n"  # line 3: saveAsTable
    )
    matches = kb.detect(code)
    rdd_matches = [m for m in matches if "rdd" in (m.anchor + m.matched_token).lower()]
    sat_matches = [m for m in matches if m.rule_id == "behavioral:12.10"]
    assert rdd_matches and rdd_matches[0].line == 1
    assert sat_matches and sat_matches[0].line == 3


# --------------------------------------------------------------------------
# gaps:`date`/`timestamp` not support — must NOT fire on bare date() calls;
# must fire on percentile_cont/percentile_disc with date/timestamp context.
# --------------------------------------------------------------------------

RULE_DATE_PERCENTILE = "gaps:`date`/`timestamp` not support"


@pytest.mark.parametrize("code", [
    "d = datetime.date(2024, 1, 10)",
    "from datetime import date\nd = date(2024, 1, 10)",
    "d = date(year, month, day)",
    "today = current_date()",
    "import datetime\ndt = datetime.date.today()",
    "x = date(2024, 6, 30)\ny = x.strftime('%Y-%m-%d')",
])
def test_date_rule_does_not_fire_on_bare_date_constructor(kb: TriggerKB, code: str) -> None:
    """The date/timestamp-in-percentile rule must NOT fire on Python date constructors."""
    matches = kb.detect(code)
    assert not any(m.rule_id == RULE_DATE_PERCENTILE for m in matches), (
        f"{RULE_DATE_PERCENTILE} should NOT fire on: {code!r}")


@pytest.mark.parametrize("code", [
    'df = spark.sql("SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY date_col) FROM t")',
    'df = spark.sql("SELECT PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY timestamp_col) FROM t")',
    'result = F.percentile_cont(date_col, 0.5)',
    'result = F.percentile_disc(timestamp_field, 0.5)',
])
def test_date_rule_fires_on_percentile_with_date_context(kb: TriggerKB, code: str) -> None:
    """The date/timestamp-in-percentile rule MUST fire when percentile uses date/timestamp."""
    matches = kb.detect(code)
    assert any(m.rule_id == RULE_DATE_PERCENTILE for m in matches), (
        f"{RULE_DATE_PERCENTILE} should fire on: {code!r}")


@pytest.mark.parametrize("code", [
    'result = F.percentile_cont(salary_col, 0.5)',
    'spark.sql("SELECT PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY amount) FROM t")',
])
def test_date_rule_does_not_fire_on_percentile_without_date_context(kb: TriggerKB, code: str) -> None:
    """The date/timestamp-in-percentile rule must NOT fire on numeric-only percentile usage."""
    matches = kb.detect(code)
    assert not any(m.rule_id == RULE_DATE_PERCENTILE for m in matches), (
        f"{RULE_DATE_PERCENTILE} should NOT fire on numeric percentile: {code!r}")
