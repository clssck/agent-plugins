# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""AI_COMPLETE call-site rewriting.

Injects show_details, return_error_details, and file prompt workarounds into DDL.
"""

import re

from snowflake_ai_optimize.core.sql_utils import FunctionArg
from snowflake_ai_optimize.core.stage import apply_file_prompt_prefix_workaround

# SQL types whose Python values (lists/dicts) must be normalized to JSON
# strings before ``create_dataframe`` (to avoid mixed-type schema inference)
# and PARSE_JSON-wrapped when projected back so the body sees the correct
# VARIANT / ARRAY / OBJECT type.
SEMI_STRUCTURED_TYPES = {"ARRAY", "VARIANT", "OBJECT"}

# Synthetic placeholder used by :func:`_inject_show_details` and
# :func:`_inject_return_error_details` to probe for the presence of a
# top-level kwarg via :func:`_replace_ai_complete_named_arg`
# (the string-aware walker).  A sentinel guarantees the probe value
# differs from any plausible existing kwarg value (TRUE / FALSE /
# variable / expression) so a "did the result change?" comparison
# unambiguously distinguishes "kwarg present" from "kwarg absent" — a
# direct probe with the real replacement (TRUE) would false-negative
# when the existing value is already TRUE.  The hex suffix is just for
# uniqueness; it has no semantic meaning.
_INJECTOR_PROBE_SENTINEL = "__cortex_inject_probe_e8a4c2d6f1b9__"

_PROMPT_WITH_TO_FILE_FIRST_ARG_RE = re.compile(
    r"(?P<prefix>PROMPT\(\s*')"
    r"(?P<template>(?:''|[^'])*)"
    r"(?P<suffix>'\s*,\s*TO_FILE\(\s*'(?:(?:'')|[^'])+'\s*,\s*[^)]+\))",
    re.IGNORECASE | re.DOTALL,
)


def find_ai_complete_call(ddl: str) -> tuple[str, int, int] | None:
    r"""Find AI_COMPLETE(...) using recursive descent style parsing.

    Returns (inner_content, start_of_match, end_of_match) or None.
    Handles nested calls like ARRAY_CONSTRUCT(OBJECT_CONSTRUCT(...))
    and SQL string literals containing parens.

    The leading ``\b`` anchors the match to a word boundary so a
    function whose name happens to *end* in ``AI_COMPLETE`` (e.g.
    ``MY_AI_COMPLETE(``) is NOT matched starting from the inner
    substring — that would silently rewrite the wrong call site.
    """
    m = re.search(r"\bAI_COMPLETE\s*\(", ddl, re.IGNORECASE)
    if not m:
        return None

    start = m.end()  # position after opening (

    def _skip_string(pos: int) -> int:
        """Advance past a SQL single-quoted string, handling '' escapes."""
        pos += 1  # skip opening '
        while pos < len(ddl):
            if ddl[pos] != "'":
                pos += 1
            elif pos + 1 < len(ddl) and ddl[pos + 1] == "'":
                pos += 2  # skip escaped ''
            else:
                return pos + 1  # skip closing '
        return pos

    def _skip_parens(pos: int) -> int:
        """Advance past a balanced (...) group, recursing for nested parens/strings."""
        pos += 1  # skip opening (
        while pos < len(ddl):
            ch = ddl[pos]
            if ch == "'":
                pos = _skip_string(pos)
            elif ch == "(":
                pos = _skip_parens(pos)
            elif ch == ")":
                return pos + 1  # skip closing )
            else:
                pos += 1
        return pos  # unterminated

    i = start
    while i < len(ddl):
        ch = ddl[i]
        if ch == "'":
            i = _skip_string(i)
        elif ch == "(":
            i = _skip_parens(i)
        elif ch == ")":
            inner = ddl[start:i]
            return inner, m.start(), i + 1
        else:
            i += 1

    return None


def replace_ai_complete_named_arg(
    ai_complete_inner: str, arg_name: str, replacement_expr: str
) -> str:
    """Replace the first top-level `arg_name=>` value inside an AI_COMPLETE arg list."""
    arg_pattern = re.compile(rf"\b{re.escape(arg_name)}\s*=>\s*", re.IGNORECASE)
    paren_depth = 0
    pos = 0
    while pos < len(ai_complete_inner):
        if ai_complete_inner[pos] == "'":
            pos = _find_sql_string_end(ai_complete_inner, pos)
            continue

        if ai_complete_inner[pos] == "(":
            paren_depth += 1
            pos += 1
            continue
        if ai_complete_inner[pos] == ")":
            if paren_depth > 0:
                paren_depth -= 1
            pos += 1
            continue

        if paren_depth > 0:
            pos += 1
            continue

        match = arg_pattern.match(ai_complete_inner, pos)
        if not match:
            pos += 1
            continue

        value_start = match.end()
        while (
            value_start < len(ai_complete_inner)
            and ai_complete_inner[value_start].isspace()
        ):
            value_start += 1
        if value_start >= len(ai_complete_inner):
            return ai_complete_inner

        value_end = _find_ai_complete_arg_value_end(
            ai_complete_inner,
            value_start,
        )
        return (
            ai_complete_inner[:value_start]
            + replacement_expr
            + ai_complete_inner[value_end:]
        )

    return ai_complete_inner


def inject_show_details(expr_or_ddl: str) -> tuple[str, tuple[int, int]] | None:
    """Inject ``show_details=>TRUE`` into the first AI_COMPLETE(...) call.

    Used by BOTH body-mode (``snow_gepa_optimize_anything._build_inline_eval_sql``)
    and prompt-mode (``TempAIFunction.__init__``, which builds
    ``self.inline_expr``) so the inline SQL can capture per-row token usage via
    AI_COMPLETE's ``usage`` block.

    Three cases:

    1. ``show_details=>(true|false)`` already named — force it to ``TRUE`` via
       :func:`_replace_ai_complete_named_arg`.
    2. AI_COMPLETE call has 5+ POSITIONAL args (5th positional is
       ``show_details`` per Snowflake's signature) — replace the value at
       position 5 with ``TRUE`` in place.  Appending the named kwarg in
       this shape would yield Snowflake's "specified more than once" error,
       so an in-place edit is the only way to keep token capture working.
    3. Otherwise — append ``, show_details=>TRUE`` to the inner arg list.

    Returns ``(rewritten, (start, end))`` where ``(start, end)`` is the
    AI_COMPLETE expression span in the ORIGINAL ``expr_or_ddl`` so body-mode
    callers can substitute that span with a ``__details:choices[0]:messages``
    column reference.  Returns ``None`` only when no AI_COMPLETE call is
    present (every other shape is rewritable).
    """
    found = find_ai_complete_call(expr_or_ddl)
    if found is None:
        return None
    inner, match_start, match_end = found

    # Case 1: show_details already specified as a top-level named kwarg.
    # Force TRUE.
    #
    # We use the string-aware walker
    # :func:`_replace_ai_complete_named_arg` as the source
    # of truth for kwarg presence — a regex pre-check would not be
    # string-aware (a prompt content literal like ``'set show_details=>TRUE'``
    # would falsely match) and a "did the result change?" check would
    # false-negative when the existing value already equals the
    # replacement (TRUE → TRUE is a byte-identical replacement that looks
    # like a no-op).  Probe with a unique sentinel: if the walker
    # substituted, the kwarg is genuinely present and we then do the real
    # TRUE replacement.  Otherwise fall through to Case 2 / Case 3.
    probed = replace_ai_complete_named_arg(
        inner, "show_details", _INJECTOR_PROBE_SENTINEL
    )
    if probed != inner:
        case1_inner = replace_ai_complete_named_arg(inner, "show_details", "TRUE")
        rewritten = (
            expr_or_ddl[:match_start]
            + f"AI_COMPLETE({case1_inner})"
            + expr_or_ddl[match_end:]
        )
        return rewritten, (match_start, match_end)
    # Else: no top-level show_details kwarg; fall through.

    # Case 2: 5+ leading POSITIONAL args.  The 5th (and final) positional
    # slot is ``show_details`` per Snowflake's public AI_COMPLETE syntax
    # (model, messages/prompt, model_parameters, response_format, show_details
    # — see https://docs.snowflake.com/en/sql-reference/functions/ai_complete-single-string).
    # We rewrite that slot's value to ``TRUE`` in place — appending a named
    # ``show_details=>TRUE`` kwarg here would raise "specified more than
    # once" since the slot is positionally occupied.  All-named calls
    # return ``[]`` from :func:`_positional_arg_spans` regardless of how
    # many top-level commas they contain, so a 5-named-arg call (model,
    # messages, model_parameters, response_format, return_error_details)
    # is correctly classified as safe to extend via Case 3.
    spans = _positional_arg_spans(inner)
    if len(spans) >= 5:
        s5, e5 = spans[4]
        new_inner = inner[:s5] + "TRUE" + inner[e5:]
        rewritten = (
            expr_or_ddl[:match_start]
            + f"AI_COMPLETE({new_inner})"
            + expr_or_ddl[match_end:]
        )
        return rewritten, (match_start, match_end)

    # Case 3: append `, show_details=>TRUE` to the inner arg list.
    new_inner = inner.rstrip() + ", show_details=>TRUE"
    rewritten = (
        expr_or_ddl[:match_start]
        + f"AI_COMPLETE({new_inner})"
        + expr_or_ddl[match_end:]
    )
    return rewritten, (match_start, match_end)


def inject_return_error_details(
    expr_or_ddl: str,
) -> tuple[str, tuple[int, int]] | None:
    """Force ``return_error_details=>TRUE`` on the first AI_COMPLETE(...) call.

    Per Snowflake's ``AI_COMPLETE`` contract
    (https://docs.snowflake.com/en/sql-reference/functions/ai_complete),
    ``return_error_details=>TRUE`` switches the per-row return shape from a
    bare value (``NULL`` on error) to ``OBJECT(value, error)`` where the
    error string carries the model failure reason (context-length exceeded,
    content filter, JSON-mode validation failure, etc.).

    Used by BOTH:

    * prompt-mode (:meth:`TempAIFunction._rewrite_ai_complete_for_error_details`),
      where ``call_rows`` projects ``__RES:value`` / ``__RES:error`` and
      surfaces ``"INFERENCE_ERROR: <msg>"`` for failed rows.
    * body-mode (:func:`snow_gepa_optimize_anything._build_inline_eval_sql`),
      where the CTE projects ``__DETAILS:value:choices[...]`` and the outer
      SELECT wraps the body in ``CASE WHEN __DETAILS:error IS NOT NULL THEN
      'INFERENCE_ERROR: ' || ... ELSE <body> END`` so per-row inference
      errors flow into the GEPA reflection LM as actionable signal instead
      of being silently dropped to NULL by the body's accessors.

    Two cases (mirrors :func:`_inject_show_details` Case 1 / Case 3):

    1. ``return_error_details=>(true|false)`` already named — force the
       value to ``TRUE`` via :func:`_replace_ai_complete_named_arg`
       so a user-supplied ``FALSE`` does not silently disable per-row
       error capture during evaluation.
    2. Otherwise — append ``, return_error_details=>TRUE`` to the inner arg
       list.

    Returns ``(rewritten, (start, end))`` where ``(start, end)`` is the
    AI_COMPLETE expression span in the ORIGINAL ``expr_or_ddl``, or
    ``None`` when no AI_COMPLETE call is present.

    Per the public ``AI_COMPLETE`` syntax
    (https://docs.snowflake.com/en/sql-reference/functions/ai_complete-single-string),
    ``return_error_details`` is a named-only kwarg ("the final parameter" in
    every syntax variation), so a positional form is not valid user-authored
    SQL.  The append branch below is therefore always safe — it never
    collides with a positional slot.
    """
    found = find_ai_complete_call(expr_or_ddl)
    if found is None:
        return None
    inner, match_start, match_end = found

    # Case 1: return_error_details already specified as a top-level named
    # kwarg.  Force TRUE.  See :func:`_inject_show_details` Case 1 for the
    # rationale on the sentinel-probe approach (regex isn't string-aware
    # and a "did the result change?" check would false-negative when the
    # existing value is already TRUE — byte-identical replacement looks
    # like a no-op).
    probed = replace_ai_complete_named_arg(
        inner, "return_error_details", _INJECTOR_PROBE_SENTINEL
    )
    if probed != inner:
        new_inner = replace_ai_complete_named_arg(inner, "return_error_details", "TRUE")
    else:
        # No top-level kwarg present — append.
        new_inner = inner.rstrip() + ", return_error_details=>TRUE"

    rewritten = (
        expr_or_ddl[:match_start]
        + f"AI_COMPLETE({new_inner})"
        + expr_or_ddl[match_end:]
    )
    return rewritten, (match_start, match_end)


def ai_complete_returns_structured(expr_or_ddl: str) -> bool:
    """Detect whether an AI_COMPLETE call returns a structured object.

    Snowflake's ``AI_COMPLETE`` returns:

    * VARCHAR (text) when ``response_format`` is absent or NULL
    * OBJECT  (structured JSON) when ``response_format`` is set to a
      non-NULL schema

    The body-mode inline-eval substitutes the AI_COMPLETE span with a
    ``COALESCE(... :messages, ... :message:content, ... :raw_message)``
    expression, all of which return VARIANT.  Bodies that operated on a
    VARCHAR result (e.g. ``LENGTH(AI_COMPLETE(...))`` or a custom UDF
    expecting a STRING arg) would silently regress: VARIANT auto-coerces
    in most contexts but not all (PARSE_JSON, ::ARRAY, strict UDF args).

    The body-mode CTE uses this flag to decide whether to wrap the
    COALESCE in ``::STRING``: ``True`` means leave as VARIANT (mirrors the
    OBJECT return), ``False`` means cast to STRING (mirrors the VARCHAR
    return).  Either way the substituted expression has the SAME runtime
    type as the original AI_COMPLETE call so the body's surrounding
    operators behave identically.

    Heuristic: returns ``True`` iff ``response_format`` is supplied with a
    non-NULL value, either as a named arg (``response_format=>...``) or
    positionally (slot 4 per Snowflake's signature).  Anything else —
    absent, named-NULL, or positional-NULL — is treated as text mode.
    """
    found = find_ai_complete_call(expr_or_ddl)
    if found is None:
        return False
    inner, _, _ = found

    # Named form: response_format=>VALUE.  Capture characters up to the
    # next top-level comma or close-paren — using ``\S+`` here was greedy
    # and crossed argument boundaries when the SQL was formatted compactly
    # (``response_format=>NULL,foo=>bar`` would capture
    # ``NULL,foo=>bar`` and incorrectly classify text mode as structured
    # because ``rstrip(",")`` only trims a TRAILING comma).  ``[^,)]*``
    # stops at the first comma or ``)``, which is the right boundary for
    # a single arg value.  Function-call values like
    # ``OBJECT_CONSTRUCT('a','b')`` also stop at their first internal
    # comma but the captured prefix is still non-NULL, so the True/False
    # decision is correct even though the captured text is partial.
    m = re.search(r"\bresponse_format\s*=>\s*([^,)]*)", inner, re.IGNORECASE)
    if m is not None:
        value = m.group(1).strip()
        return value.upper() != "NULL"

    # Positional form: slot 4 is response_format
    # (model, messages, model_parameters, response_format, ...).
    spans = _positional_arg_spans(inner)
    if len(spans) >= 4:
        s, e = spans[3]
        value = inner[s:e].strip()
        return value.upper() != "NULL"

    return False


def apply_file_prompt_prefix_workaround_to_ddl(ddl: str) -> str:
    """Apply the temporary AI_COMPLETE file-prefix workaround to DDL."""

    def _rewrite_prompt(match: re.Match[str]) -> str:
        template = match.group("template")
        new_template = apply_file_prompt_prefix_workaround(
            template,
            first_prompt_arg_is_file=True,
        )
        if new_template == template:
            return match.group(0)
        return f"{match.group('prefix')}{new_template}{match.group('suffix')}"

    return _PROMPT_WITH_TO_FILE_FIRST_ARG_RE.sub(_rewrite_prompt, ddl)


def semi_structured_param_names(args: "list[FunctionArg]") -> set[str]:
    """Return upper-cased names of parameters declared as semi-structured types.

    A parameter is semi-structured when its declared SQL type is ``ARRAY``,
    ``VARIANT``, or ``OBJECT`` (see :data:`SEMI_STRUCTURED_TYPES`).  These
    parameters need ``PARSE_JSON()`` wrapping when called via
    ``create_dataframe`` because their Python values (lists, dicts) must be
    normalized to JSON strings to avoid mixed-type schema inference issues.

    Replaces the former regex-over-DDL parameter scan — callers now pass
    ``FunctionDefinition.args`` (from ``describe_function``) instead of a
    DDL string.
    """
    return {a.name.upper() for a in args if a.type.upper() in SEMI_STRUCTURED_TYPES}


def _find_sql_string_end(sql: str, start: int) -> int:
    """Return the first index after the closing quote of a SQL single-quoted string."""
    pos = start + 1
    while pos < len(sql):
        if sql[pos] != "'":
            pos += 1
            continue

        if pos + 1 < len(sql) and sql[pos + 1] == "'":
            pos += 2
            continue
        return pos + 1
    return pos


def _find_ai_complete_arg_value_end(sql: str, start: int) -> int:
    """Find the end of an SQL expression in argument position (comma- or top-level-).

    This parser is simple but handles common nested forms like function calls
    (e.g. IFNULL(MODEL_NAME, 'x')) and quoted strings.
    """
    if start >= len(sql):
        return start

    if sql[start] == "'":
        return _find_sql_string_end(sql, start)

    paren_depth = 0
    pos = start
    while pos < len(sql):
        ch = sql[pos]
        if ch == "'":
            pos = _find_sql_string_end(sql, pos)
            continue
        if ch == "(":
            paren_depth += 1
            pos += 1
            continue
        if ch == ")":
            if paren_depth > 0:
                paren_depth -= 1
                pos += 1
                continue
            return pos
        if ch == "," and paren_depth == 0:
            return pos
        pos += 1
    return pos


def _positional_arg_spans(inner: str) -> list[tuple[int, int]]:
    """Return ``(start, end)`` byte spans for each top-level positional arg.

    Walks *inner* once, tracking string-literal state and nesting depth across
    parentheses, braces, and brackets. Each returned span covers the meaningful
    content of a comma-separated arg with leading and trailing whitespace
    stripped, up to (but not including) the first top-level ``name=>value``
    syntax — Snowflake function calls require positional args to precede named
    args, so any args after the first ``=>`` are named and not included.

    Nesting depth is tracked across ``()``, ``{}``, and ``[]`` so a comma inside
    an object literal (``{'temperature':0.2,'max_tokens':100}``) or an array
    literal (a messages array ``[{...},{...}]``) is NOT mistaken for a top-level
    argument separator — otherwise a ``model_parameters`` / ``response_format``
    object would be split into bogus positional slots (mis-classifying the call
    and corrupting in-place ``show_details`` rewrites).

    Used by :func:`_inject_show_details` to locate the 5th positional slot
    (``show_details`` per Snowflake's signature) for in-place rewriting
    when the AI_COMPLETE call has 5+ positional args.  Replacing the
    existing value with ``TRUE`` preserves the call's wire-format while
    enabling per-row token capture.

    All-named calls return ``[]`` regardless of how many top-level commas
    they contain.
    """
    spans: list[tuple[int, int]] = []
    # Combined nesting depth across (), {}, and []. SQL literals are balanced,
    # so a single counter correctly returns to 0 at each top-level position.
    depth = 0
    pos = 0
    arg_raw_start = 0  # byte index just after the previous top-level comma
    saw_content = False

    def _trim(start: int, end: int) -> tuple[int, int]:
        while start < end and inner[start].isspace():
            start += 1
        while end > start and inner[end - 1].isspace():
            end -= 1
        return start, end

    while pos < len(inner):
        ch = inner[pos]
        if ch == "'":
            # Skip a single-quoted SQL string with `''` escape.
            saw_content = True
            pos += 1
            while pos < len(inner):
                if inner[pos] != "'":
                    pos += 1
                elif pos + 1 < len(inner) and inner[pos + 1] == "'":
                    pos += 2
                else:
                    pos += 1
                    break
            continue
        if ch in "({[":
            depth += 1
            saw_content = True
            pos += 1
            continue
        if ch in ")}]":
            if depth > 0:
                depth -= 1
            pos += 1
            continue
        if depth > 0:
            pos += 1
            continue
        # Top-level processing.
        if ch == ",":
            if saw_content:
                spans.append(_trim(arg_raw_start, pos))
            arg_raw_start = pos + 1
            saw_content = False
            pos += 1
            continue
        if ch == "=" and pos + 1 < len(inner) and inner[pos + 1] == ">":
            # First top-level `=>` → the arg currently being parsed is
            # named.  Stop collecting positional spans here.
            return spans
        if not ch.isspace():
            saw_content = True
        pos += 1
    if saw_content:
        spans.append(_trim(arg_raw_start, len(inner)))
    return spans
