# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Guard: failure feedback must never destroy the error it is reporting.

The four ``"Candidate (truncated)"`` sites in ``optimize_body.py`` all sit inside
``except`` handlers. They used to build the message with ``body[:500]`` /
``candidate[:500]``, which is fine for the usual SQL-string candidate and fatal
for a ``dict`` one -- slicing a dict raises ``KeyError``, and ``str()`` of that
KeyError is exactly ``slice(None, 500, None)``.

Because the raise happens *inside* the handler for an already-failed evaluation,
the bogus KeyError replaced the real error. Real cost: a server-side Snowpark
failure on the two complex-output datasets,

    252011: Python data type [dict] cannot be automatically mapped to Snowflake
            data type. Specify the snowflake data type explicitly.

was recorded in some cells as the literal string ``slice(None, 500, None)`` and
went undiagnosed. This module pins the truncation so that cannot recur.

Note this fixes the *masking*, not the underlying 252011 -- see
``dev/benchmark/paper/CAVEATS.md``.

Run:
    uv run --group dev pytest tests/test_optimize_body_feedback_truncation.py -q
"""

from __future__ import annotations

import json

import pytest

from snowflake_ai_optimize.gepa.optimize_body import truncate_for_feedback


def test_string_candidate_is_truncated_to_the_limit() -> None:
    """The ordinary case must keep behaving exactly as the old slice did."""
    body = "SELECT " + "x" * 1000
    assert truncate_for_feedback(body) == body[:500]
    assert len(truncate_for_feedback(body)) == 500


def test_short_string_is_returned_whole() -> None:
    """No padding, no alteration."""
    assert truncate_for_feedback("SELECT 1") == "SELECT 1"


def test_dict_candidate_does_not_raise() -> None:
    """The actual bug: a dict used to raise KeyError from inside an except block."""
    out = truncate_for_feedback({"body": "SELECT 1", "model": "claude-haiku-4-5"})
    assert isinstance(out, str)
    assert "SELECT 1" in out


def test_dict_candidate_never_yields_the_slice_repr() -> None:
    """Pin the exact signature that masked the real error.

    If this string ever comes back, the KeyError path is live again and any
    underlying failure is being silently overwritten.
    """
    for value in ({}, {"body": "SELECT 1"}, {0: "zero"}):
        assert "slice(None, 500, None)" not in truncate_for_feedback(value)


def test_empty_dict_is_the_sharpest_case() -> None:
    """``{}[:500]`` was the minimal reproducer; it must now be harmless."""
    assert truncate_for_feedback({}) == "{}"


def test_dict_is_truncated_too() -> None:
    """A large dict must still respect the limit -- feedback goes into a prompt."""
    out = truncate_for_feedback({"body": "y" * 5000})
    assert len(out) == 500


def test_object_with_no_json_form_is_stringified_not_raised() -> None:
    """``default=str`` absorbs unserializable *values*, so this must not raise.

    It comes back JSON-quoted rather than bare. Asserted explicitly because the
    first version of this test expected the bare repr and was wrong -- worth
    pinning the real shape so nobody "fixes" the helper to match an assumption.
    """

    class Circular:
        def __init__(self) -> None:
            self.me = self

        def __repr__(self) -> str:
            return "<Circular>"

    assert truncate_for_feedback(Circular()) == '"<Circular>"'


def test_unserializable_dict_key_falls_back_to_repr() -> None:
    """The case that genuinely reaches the except branch.

    ``default=`` applies to values, never to keys, so a non-scalar key makes
    ``json.dumps`` raise ``TypeError``. The helper must absorb it -- it is called
    from an except handler, where raising loses the real error.
    """
    out = truncate_for_feedback({(1, 2): "x"})
    assert isinstance(out, str)
    assert "slice(None, 500, None)" not in out
    assert "(1, 2)" in out, out


def test_none_and_scalars_are_handled() -> None:
    """These reach the path via odd candidate shapes; none may raise."""
    assert truncate_for_feedback(None) == "null"
    assert truncate_for_feedback(12345) == "12345"


def test_no_bare_slice_truncation_remains_in_the_module() -> None:
    """Source guard: the regression is a one-line revert nothing else would catch."""
    from pathlib import Path

    from snowflake_ai_optimize.gepa import optimize_body

    src = Path(optimize_body.__file__).read_text()
    assert "[:500]" not in src, (
        "a bare [:500] truncation is back in optimize_body.py; on a dict candidate "
        "it raises inside an except handler and overwrites the real error"
    )


def test_slicing_a_dict_really_does_produce_that_keyerror() -> None:
    """Document the mechanism, so the tests above are not cargo-culted.

    If a future Python changes this, the guards remain correct but the historical
    note in the docstrings would need rewording.
    """
    with pytest.raises(KeyError) as excinfo:
        {}[:500]  # type: ignore[index]
    assert str(excinfo.value) == "slice(None, 500, None)"


def test_dict_output_is_valid_json_when_it_fits() -> None:
    """Feedback goes to a reflection model, so it should be readable, not a repr."""
    out = truncate_for_feedback({"body": "SELECT 1"})
    assert json.loads(out) == {"body": "SELECT 1"}
