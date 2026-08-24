# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""``run_optimization`` gating of ``fail_on_reflection_error``.

The spec-driven EXECUTE EXPERIMENT handler opts in to making a persistently
failing reflection call fatal (retry then fail the run with the error).
``run_optimization`` must forward that flag ONLY to body mode — the sole mode
the spec handler runs, and the only ``run_*`` that accepts the kwarg — so
prompt/evolve handlers (fixed signatures) never receive an unexpected key, and
every non-opted-in caller behaves exactly as before.

Run:
    uv run --group test pytest tests/test_optimize_handler_reflection_forwarding.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import handlers.optimize_handler as optimize_handler
from handlers.optimize_handler import run_optimization


@pytest.fixture
def captured_kwargs(monkeypatch):
    """Replace resolve_mode with a handler that captures the forwarded kwargs."""
    seen: dict = {}

    def fake_handler(**kwargs):
        seen.clear()
        seen.update(kwargs)
        return {"status": "completed"}

    monkeypatch.setattr(optimize_handler, "resolve_mode", lambda _mode: fake_handler)
    return seen


def _call(mode: str, *, fail_on_reflection_error: bool):
    return run_optimization(
        MagicMock(),
        "db.s.fn(VARCHAR)",
        "db.s.train",
        "gt",
        ["q"],
        "exact_match",
        ["mistral-7b"],
        "claude-opus-4-7",
        optimize_mode=mode,
        fail_on_reflection_error=fail_on_reflection_error,
    )


def test_forwarded_to_body_when_opted_in(captured_kwargs):
    _call("body", fail_on_reflection_error=True)
    assert captured_kwargs["fail_on_reflection_error"] is True


def test_absent_for_body_by_default(captured_kwargs):
    # Default (standalone OPTIMIZE_AI_FUNCTION) forwards byte-identical to before:
    # the key is omitted so run_body_optimization uses its own False default.
    _call("body", fail_on_reflection_error=False)
    assert "fail_on_reflection_error" not in captured_kwargs


def test_not_forwarded_to_non_body_modes(captured_kwargs):
    # Even opted in, the flag is never forwarded to a non-body handler (whose
    # fixed signature would raise TypeError on the extra key).
    _call("evolve", fail_on_reflection_error=True)
    assert "fail_on_reflection_error" not in captured_kwargs
