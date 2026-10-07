# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for ``run_optimization``'s ``create_experiment_if_missing`` forwarding.

The spec-driven / EXECUTE EXPERIMENT handler passes
``create_experiment_if_missing=False`` so the optimizer attaches its runs to an
experiment the DDL layer already created, instead of creating it here. The flag
is caller-scoped, not mode-scoped: ``run_optimization`` forwards it to every
optimize mode (all mode handlers accept and honor it), and it defaults to True
so the standalone ``OPTIMIZE_AI_FUNCTION`` path keeps auto-creating.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from handlers import optimize_handler


def _call(optimize_mode: str, **overrides):
    """Invoke run_optimization with a capturing fake mode handler."""
    captured: dict = {}

    def fake_handler(**kwargs):
        captured.update(kwargs)
        return {"status": "ok"}

    with patch.object(optimize_handler, "resolve_mode", return_value=fake_handler):
        optimize_handler.run_optimization(
            MagicMock(),
            "db.s.fn(VARCHAR)",
            "db.s.train",
            "label",
            ["col"],
            "exact_match",
            ["mistral-7b"],
            "claude-opus-4-7",
            optimize_mode=optimize_mode,
            **overrides,
        )
    return captured


@pytest.mark.parametrize("mode", ["body", "prompt", "evolve", "coco_one_shot"])
def test_forwards_false_to_every_mode(mode):
    # The toggle is caller-scoped, not mode-scoped: it must reach whichever
    # mode handler the spec-driven caller dispatches to.
    captured = _call(mode, create_experiment_if_missing=False)
    assert captured["create_experiment_if_missing"] is False


@pytest.mark.parametrize("mode", ["body", "prompt", "evolve", "coco_one_shot"])
def test_defaults_true_for_every_mode(mode):
    # Standalone OPTIMIZE_AI_FUNCTION path leaves it at the default (auto-create).
    captured = _call(mode)
    assert captured["create_experiment_if_missing"] is True
