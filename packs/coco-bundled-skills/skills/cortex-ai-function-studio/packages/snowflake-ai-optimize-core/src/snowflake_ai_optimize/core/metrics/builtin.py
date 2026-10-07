# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Built-in metric scoring functions."""

import re

from snowflake.snowpark import Session

_BRACKET_PATTERN = re.compile(r"\[[^\]]*\]")


def exact_match_core(
    expected: str, predicted: str, session: Session | None = None
) -> tuple[float, str]:
    """Exact string comparison (case-insensitive, whitespace-trimmed)."""
    expected = str(expected).strip().lower()
    predicted = str(predicted).strip().lower()
    score = float(expected == predicted)
    if score == 1.0:
        feedback = "Correct! Prediction matches expected value."
    else:
        feedback = f"Incorrect. Expected '{expected}' but got '{predicted}'."
    return score, feedback


def fuzzy_match_core(
    expected: str,
    predicted: str,
    session: Session | None = None,
    *,
    threshold: float = 0.85,
) -> tuple[float, str]:
    """Token-based similarity using SequenceMatcher.

    Args:
        expected: Expected (ground-truth) value.
        predicted: Predicted value to compare against ``expected``.
        session: Optional Snowpark session (unused; accepted for metric-signature
            parity).
        threshold: Minimum similarity score to consider a match (default 0.85)

    """
    from difflib import SequenceMatcher

    expected = str(expected).strip().lower()
    predicted = str(predicted).strip().lower()
    similarity = SequenceMatcher(None, expected, predicted).ratio()
    score = float(similarity >= threshold)
    if score == 1.0:
        feedback = f"Correct! Similarity {similarity:.0%} >= threshold {threshold:.0%}."
    else:
        feedback = (
            f"Incorrect. Similarity {similarity:.0%} < threshold {threshold:.0%}."
        )
    return score, feedback


def contains_match_core(
    expected: str, predicted: str, session: Session | None = None
) -> tuple[float, str]:
    """Check if expected value is contained within the prediction."""
    expected = str(expected).strip().lower()
    predicted = str(predicted).strip().lower()
    score = float(expected in predicted)
    if score == 1.0:
        feedback = "Correct! Prediction contains expected value."
    else:
        feedback = f"Incorrect. Prediction does not contain '{expected}'."
    return score, feedback


def map_normalized_to_original_index(
    original: str, normalized: str, norm_index: int
) -> int:
    """Map an index from normalized string back to original string position."""
    orig_idx = 0
    norm_idx = 0

    while norm_idx < norm_index and orig_idx < len(original):
        match = _BRACKET_PATTERN.match(original[orig_idx:])
        if match:
            orig_idx += len(match.group())
            norm_idx += 2  # "[]" in normalized
        else:
            orig_idx += 1
            norm_idx += 1

    return min(orig_idx, len(original))


def redaction_match_core(
    expected: str, predicted: str, session: Session | None = None
) -> tuple[float, str]:
    """Check if two strings match except for content inside brackets [...].

    Compares text outside of bracketed placeholders, allowing different
    redacted values (e.g., [USERNAME], [TIME]) to vary between strings.
    """
    expected = str(expected).strip()
    predicted = str(predicted).strip()

    bracket_pattern = _BRACKET_PATTERN

    expected_normalized = bracket_pattern.sub("[]", expected)
    predicted_normalized = bracket_pattern.sub("[]", predicted)

    score = float(expected_normalized == predicted_normalized)
    if score == 1.0:
        feedback = "Correct! Text matches with redaction placeholders."
    else:
        min_len = min(len(expected_normalized), len(predicted_normalized))
        diff_start = None
        for i in range(min_len):
            if expected_normalized[i] != predicted_normalized[i]:
                diff_start = i
                break
        if diff_start is None and len(expected_normalized) != len(predicted_normalized):
            diff_start = min_len

        if diff_start is not None:
            # Check for preamble (extra text at the beginning)
            if diff_start == 0 and len(predicted_normalized) > len(expected_normalized):
                # Check if expected appears near the end of predicted (preamble case)
                check_len = min(50, len(expected_normalized))
                if check_len > 0 and predicted_normalized.endswith(
                    expected_normalized[-check_len:]
                ):
                    preamble_len = len(predicted_normalized) - len(expected_normalized)
                    preamble = predicted[: min(preamble_len + 20, len(predicted))]
                    feedback = (
                        f"Added preamble: Response has extra text at the beginning that must be removed. "
                        f"Do not include introductory phrases. "
                        f"Unwanted prefix: '{preamble[:100]}{'...' if len(preamble) > 100 else ''}'"
                    )
                    return score, feedback

            # Check for postamble (extra text at the end)
            if diff_start == len(expected_normalized) and len(
                predicted_normalized
            ) > len(expected_normalized):
                orig_postamble_start = len(expected)
                postamble = predicted[max(0, orig_postamble_start - 20) :]
                feedback = (
                    f"Added postamble: Response has extra text at the end that must be removed. "
                    f"Do not include concluding phrases. "
                    f"Unwanted suffix: '{'...' if orig_postamble_start > 20 else ''}{postamble[-100:]}'"
                )
                return score, feedback

            exp_has_bracket = expected_normalized[diff_start : diff_start + 2] == "[]"
            pred_has_bracket = predicted_normalized[diff_start : diff_start + 2] == "[]"

            # Map diff_start from normalized index to original string index
            orig_diff_start = map_normalized_to_original_index(
                expected, expected_normalized, diff_start
            )

            # Use the mapped index for context extraction
            ctx_start = max(0, orig_diff_start - 20)
            ctx_end = min(len(expected), orig_diff_start + 40)
            exp_snippet = expected[ctx_start:ctx_end]

            # Also map for predicted string
            orig_diff_start_pred = map_normalized_to_original_index(
                predicted, predicted_normalized, diff_start
            )
            pred_ctx_end = min(len(predicted), orig_diff_start_pred + 40)
            pred_snippet = predicted[ctx_start:pred_ctx_end]

            prefix = "..." if ctx_start > 0 else ""
            suffix_exp = "..." if ctx_end < len(expected) else ""
            suffix_pred = "..." if pred_ctx_end < len(predicted) else ""

            if exp_has_bracket and not pred_has_bracket:
                feedback = (
                    f"Missed redaction: predicted has literal text where redaction expected. "
                    f"Expected: '{prefix}{exp_snippet}{suffix_exp}' "
                    f"Predicted: '{prefix}{pred_snippet}{suffix_pred}'"
                )
            elif pred_has_bracket and not exp_has_bracket:
                feedback = (
                    f"Over-redacted: predicted redacted something that should be literal. "
                    f"Expected: '{prefix}{exp_snippet}{suffix_exp}' "
                    f"Predicted: '{prefix}{pred_snippet}{suffix_pred}'"
                )
            else:
                feedback = (
                    f"Text modified outside redactions at position {diff_start}. "
                    f"Expected text: '{prefix}{exp_snippet}{suffix_exp}' "
                    f"but got: '{prefix}{pred_snippet}{suffix_pred}'. "
                    f"Preserve original text exactly, only replace PII with redaction placeholders."
                )
        else:
            feedback = "Incorrect. Text outside brackets does not match."
    return score, feedback
