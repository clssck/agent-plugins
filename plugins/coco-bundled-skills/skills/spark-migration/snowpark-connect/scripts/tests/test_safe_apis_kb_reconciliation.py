"""Tests for the safe_apis.json / kb_rules.json reconciliation fix.

40+ APIs (groupBy, join, dropDuplicates, row_number, ...) are marked "fully
supported" in safe_apis.json but have a real, sometimes high-severity
divergence documented in kb_rules.json for the same name. Without
reconciliation, a block whose only calls are safe-listed short-circuits
before the KB is ever queried, silently dropping the divergence.
reconcile_safe_apis() removes those APIs from the safe set once, at load
time, so every downstream caller of is_block_safe (unchanged signature)
gets the corrected set for free.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pytest

from analyze_pyspark import (  # noqa: E402
    CodeBlock,
    _process_single_block,
    is_block_safe,
    load_kb_anchor_leaves,
    load_safe_apis,
    reconcile_safe_apis,
)
from rag.trigger_kb import SCOSTriggerRAG, TriggerKB  # noqa: E402


# ---------------------------------------------------------------------------
# load_kb_anchor_leaves
# ---------------------------------------------------------------------------


def test_load_kb_anchor_leaves_returns_nonempty_set():
    anchors = load_kb_anchor_leaves()
    assert isinstance(anchors, set)
    assert len(anchors) > 0


def test_kb_anchor_leaves_contains_known_overlap_apis():
    """The APIs named in the bug report must resolve as KB anchors."""
    anchors = load_kb_anchor_leaves()
    for api in ("groupby", "join", "dropduplicates", "row_number", "current_date"):
        assert api in anchors, f"{api!r} should be a KB anchor leaf"


def test_kb_anchor_leaves_includes_manual_kind_rules():
    """join's divergence rule is kind='manual' (never auto-fired) — it must
    still show up here, since the divergence is real either way."""
    kb = TriggerKB.load()
    join_rules = [r for r in kb.rules if r.get("api") == ["join"] or r.get("api") == "join"]
    assert join_rules, "expected a kb_rules.json entry with api == 'join'"
    assert any(r.get("kind") == "manual" for r in join_rules), (
        "fixture assumption changed: join's rule is no longer kind='manual', "
        "update this test"
    )
    anchors = load_kb_anchor_leaves()
    assert "join" in anchors


def test_kb_anchor_leaves_excludes_dotted_anchor_namespace_collisions():
    """Dotted anchors (dbutils.fs.head, F.lit, SnowflakeSession.sql) must not
    be leaf-stripped — that would wrongly flag unrelated bare methods like
    DataFrame.head() or spark.sql()."""
    anchors = load_kb_anchor_leaves()
    for false_positive_risk in ("head", "sql", "lit", "select", "alias", "read"):
        assert false_positive_risk not in anchors


def test_kb_anchor_leaves_excludes_sql_keyword_tokens():
    anchors = load_kb_anchor_leaves()
    assert "SELECT" not in anchors
    assert "GROUP BY" not in anchors


def test_load_kb_anchor_leaves_missing_file_returns_empty_set(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    anchors = load_kb_anchor_leaves(missing)
    assert anchors == set()


# ---------------------------------------------------------------------------
# reconcile_safe_apis
# ---------------------------------------------------------------------------


def test_reconcile_safe_apis_drops_kb_flagged_entries():
    reconciled = reconcile_safe_apis({"select", "groupBy", "join"}, {"groupby", "join"})
    assert reconciled == {"select"}


def test_reconcile_safe_apis_keeps_entries_with_no_kb_anchor():
    reconciled = reconcile_safe_apis({"select", "filter"}, {"groupby", "join"})
    assert reconciled == {"select", "filter"}


def test_reconcile_safe_apis_is_case_insensitive():
    reconciled = reconcile_safe_apis({"groupBy"}, {"groupby"})
    assert reconciled == set()


def test_reconcile_safe_apis_noop_when_no_kb_anchors():
    safe = {"select", "filter", "groupBy"}
    assert reconcile_safe_apis(safe, set()) == safe


def test_reconcile_safe_apis_against_real_data_removes_documented_overlaps():
    """End-to-end with the real files: every API named in the bug report
    must be gone from the reconciled set."""
    reconciled = reconcile_safe_apis(load_safe_apis(), load_kb_anchor_leaves())
    for api in ("groupBy", "join", "dropDuplicates", "row_number", "current_date"):
        assert api not in reconciled, f"{api!r} should be removed by reconciliation"
    # Common, genuinely safe calls must survive.
    for api in ("select", "filter"):
        assert api in reconciled


# ---------------------------------------------------------------------------
# is_block_safe — unchanged signature, verified with a reconciled safe set
# ---------------------------------------------------------------------------


def test_is_block_safe_false_when_api_was_reconciled_away():
    """The bug's exact repro: groupBy is on the raw safe list, but once the
    list is reconciled, is_block_safe (unchanged) correctly rejects it."""
    safe_apis = load_safe_apis()
    assert "groupBy" in safe_apis  # bug precondition
    reconciled = reconcile_safe_apis(safe_apis, load_kb_anchor_leaves())
    assert is_block_safe(["groupBy", "min"], reconciled) is False


@pytest.mark.parametrize(
    "api", ["groupBy", "join", "dropDuplicates", "row_number", "current_date", "isin", "like"]
)
def test_is_block_safe_false_for_every_documented_overlap_api(api):
    """Regression guard for the full overlap set named in the bug report."""
    reconciled = reconcile_safe_apis(load_safe_apis(), load_kb_anchor_leaves())
    assert is_block_safe([api], reconciled) is False


def test_is_block_safe_still_true_for_genuinely_safe_apis():
    """select/filter have no KB anchor and must still skip — reconciliation
    shouldn't regress the performance optimization."""
    reconciled = reconcile_safe_apis(load_safe_apis(), load_kb_anchor_leaves())
    assert is_block_safe(["select", "filter"], reconciled) is True


def test_is_block_safe_false_on_empty_inputs():
    assert is_block_safe([], {"select"}) is False
    assert is_block_safe(["select"], set()) is False


# ---------------------------------------------------------------------------
# _process_single_block — end-to-end: the KB must actually get queried
# ---------------------------------------------------------------------------


class _ExplodingRAG:
    """Raises if predict_failure is called — same idiom as
    test_safe_apis_java.py / test_safe_apis_scala.py."""

    def predict_failure(self, code: str) -> dict:
        raise AssertionError("predict_failure called for a safe block — RAG was not skipped")


def _block(code: str, functions: list[str]) -> CodeBlock:
    return CodeBlock(code=code, line_start=1, line_end=1, block_type="expr", functions=functions)


def test_process_single_block_surfaces_groupby_divergence_after_reconciliation():
    """End-to-end bug repro: df.groupBy("dept").min() now surfaces the KB
    finding it used to silently drop, once main() reconciles the safe list
    before it's ever passed in. Uses the real trigger KB, not a stub."""
    reconciled = reconcile_safe_apis(load_safe_apis(), load_kb_anchor_leaves())
    rag = SCOSTriggerRAG()
    block = _block('df.groupBy("dept").min()', ["groupBy", "min"])

    rdd_result, block_data = _process_single_block(
        block, rag, {}, Path("test.py"), 0.55, reconciled
    )

    assert rdd_result is None
    assert block_data is not None
    root_causes = " ".join(
        p.get("root_cause") or "" for p in block_data.get("matching_patterns", [])
    )
    assert "drops all aggregate expressions" in root_causes


def test_process_single_block_pre_reconciliation_silently_drops_groupby():
    """Documents the pre-fix path (raw, unreconciled safe list) so a future
    regression that skips reconciliation is caught here."""
    safe_apis = load_safe_apis()
    block = _block('df.groupBy("dept").min()', ["groupBy", "min"])

    rdd_result, block_data = _process_single_block(
        block, _ExplodingRAG(), {}, Path("test.py"), 0.55, safe_apis
    )

    assert rdd_result is None
    assert block_data is None


def test_process_single_block_genuinely_safe_block_still_skips_rag():
    """select/filter must still skip the RAG round-trip entirely."""
    reconciled = reconcile_safe_apis(load_safe_apis(), load_kb_anchor_leaves())
    block = _block('df.select("a").filter(df.a > 1)', ["select", "filter"])

    rdd_result, block_data = _process_single_block(
        block, _ExplodingRAG(), {}, Path("test.py"), 0.55, reconciled
    )

    assert rdd_result is None
    assert block_data is None
