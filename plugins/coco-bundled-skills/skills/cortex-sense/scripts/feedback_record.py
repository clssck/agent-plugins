"""feedback_record.py — validate one Cortex Sense feedback record and summarise it.

Storage is handled by SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER — the skill calls
that SQL function directly. This module does NOT write to Snowflake.

Subcommands
-----------
draft     Validate the record and print a summary of what will be recorded. Pure:
          no network, no filesystem writes.

Why a summary at all: the caller composes the record by reasoning, so something has
to catch a plausible-looking record that can never work — a two-part entity key, an
indexed_text written as the fix, a field the server requires and did not get.

This deliberately does **not** claim to reproduce the server's normalization. It
applies the same intent so the summary is worth reading, but a local mirror of
another system's rewriting drifts the moment that system changes, and a drifted
mirror is worse than none: it would be believed. Treat the summary as a check on the
record, not as a preview of the stored bytes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# The six recordable types, in the server's declaration order. `scope` is a
# seventh known value the server rejects, so it is handled separately: a caller
# that reads the enum out of an error message would otherwise retry with it.
_TYPES = (
    "definition",
    "relationship",
    "association",
    "retrieval_steer",
    "annotation",
    "procedural",
)
_TYPE_SCOPE = "scope"

_LOCATORS = ("database_name", "schema_name", "name")
_REQUIRED = ("raw_feedback", "type", "feedback_rule", "indexed_text")

# Fields that carry builder prose. Every one is a $$-termination risk and every one
# has a byte cap the server does not enforce.
_FREE_TEXT = (
    "raw_feedback",
    "feedback_rule",
    "indexed_text",
    "query_pattern",
    "triggering_query",
    "expected_behavior",
)

# Documented in FEEDBACK_RECORD.md ("Limits, and who enforces them"), enforced
# nowhere server-side. Overrunning them degrades retrieval quality silently rather
# than failing, so they are enforced here. query_pattern has no entry: it is
# rejected outright below regardless of length, so a byte cap on it would be dead.
_CAPS = {
    "raw_feedback": 8 * 1024,
    "feedback_rule": 4 * 1024,
    "indexed_text": 2 * 1024,
    "triggering_query": 2 * 1024,
    "expected_behavior": 2 * 1024,
}
_MAX_ENTITY_KEYS = 64

_KNOWN_KEYS = frozenset(
    _LOCATORS
    + _REQUIRED
    + ("entity_keys", "concepts", "query_pattern", "triggering_query", "expected_behavior")
)

# Whitespace-run collapsing is applied to the fields the server collapses, so the
# summary reads close to the stored form without claiming to equal it. The rest are
# trimmed only, which is why raw_feedback keeps the builder's line breaks.
_COLLAPSED = ("feedback_rule", "indexed_text", "query_pattern")
_TRIMMED = ("raw_feedback", "triggering_query", "expected_behavior")

# A three-part dotted name anywhere in prose. indexed_text must not contain one: it
# has to read like the question a builder would ask, and a question does not contain
# an identifier.
_FQN_IN_PROSE = re.compile(r"\b[A-Za-z_][\w$]*\.[A-Za-z_][\w$]*\.[A-Za-z_][\w$]*\b")
_BULLET = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+", re.MULTILINE)

class FeedbackError(RuntimeError):
    """Input the caller must fix before a record can be built."""


# --------------------------------------------------------------------------- #
# normalization
# --------------------------------------------------------------------------- #


def _collapse(s: str) -> str:
    return " ".join(s.split())


def _split_quote_aware(s: str) -> tuple[list[str], bool]:
    """Split on '.' outside double quotes. Returns (parts, unbalanced).

    Unlike the server, which caps the split at three pieces and lets a fourth
    segment fold into the object name, this returns every part so a four-part name
    is rejected by name instead of silently storing `C.D` as the object.
    """
    parts: list[str] = []
    buf: list[str] = []
    in_quote = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == '"':
            if in_quote and i + 1 < len(s) and s[i + 1] == '"':
                buf.append('""')
                i += 2
                continue
            in_quote = not in_quote
            buf.append(c)
            i += 1
            continue
        if c == "." and not in_quote:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    parts.append("".join(buf))
    return parts, in_quote


def _looks_case_sensitive(ident: str) -> bool:
    """True when an unquoted identifier has capitals somewhere other than the front.

    Unquoted names fold to upper, so `sales` and `Sales` are just casual typing and
    fold harmlessly. `MixedCase` or `myTable` is the ambiguous one: it may be a
    genuinely case-sensitive object, in which case folding it silently produces a
    different object that validates fine and then never matches.
    """
    return any(c.islower() for c in ident) and any(c.isupper() for c in ident[1:])


def _resolve_segment(seg: str) -> tuple[str, bool]:
    """Resolve one identifier segment. Returns (resolved, looked_case_sensitive).

    Applies the server's identifier resolution rules: a double-quoted segment is
    case-sensitive, so it sheds its quotes and keeps its case with interior ""
    unescaped; anything else is case-insensitive and folds to upper. The server keeps
    its own copy of these rules rather than sharing one, so treat this as the same
    intent, not a guaranteed-identical implementation.

    The result is deliberately not a fixed point for quoted input — resolving
    `"MixedCase"` yields a bare `MixedCase`, which a second pass would uppercase —
    so this runs exactly once, over the JSON the caller composed. A summary must
    never be fed back in.
    """
    seg = seg.strip()
    if len(seg) >= 2 and seg.startswith('"') and seg.endswith('"'):
        return seg[1:-1].replace('""', '"'), False
    return seg.upper(), _looks_case_sensitive(seg)


def _canonical_entity_key(key: str) -> tuple[str, bool, list[str]]:
    """Returns (canonical, ok, segments_that_looked_case_sensitive).

    An input that does not yield exactly three segments is returned trimmed and
    left for validation to reject by name, rather than padded into something that
    reads as canonical.

    Emptiness is judged **after** resolution, not before, because a segment can be
    non-empty as written and resolve to nothing: `""` is a two-character token that
    unquotes to the empty string. Checking only the written form would accept
    `sales.data.""` and emit `SALES.DATA.`, which the server then rejects — turning a
    local error into a round trip and a server-worded failure.
    """
    raw = key.strip()
    parts, unbalanced = _split_quote_aware(raw)
    if unbalanced or len(parts) != 3:
        return raw, False, []
    resolved = []
    suspicious = []
    for p in parts:
        r, s = _resolve_segment(p)
        resolved.append(r)
        if s:
            suspicious.append(p.strip())
    if any(not r for r in resolved):
        return raw, False, []
    return ".".join(resolved), True, suspicious


def _normalize_set(values: list, per_entry) -> tuple[list[str], int, int]:
    """Apply per_entry, drop blanks, dedupe preserving first-occurrence order.

    Returns (kept, dropped_blank, dropped_duplicate). A blank or non-string entry
    is caller noise, not a duplicate — kept separate so the confirm card never
    tells the builder "duplicates were merged" when the actual cause was a stray
    empty entry. The server dedupes silently; the duplicate count is reported so
    the card can show a target count that matches reality.
    """
    seen: set[str] = set()
    out: list[str] = []
    dropped_blank = 0
    dropped_duplicate = 0
    for v in values:
        if not isinstance(v, str):
            dropped_blank += 1
            continue
        e = per_entry(v)
        if not e:
            dropped_blank += 1
            continue
        if e in seen:
            dropped_duplicate += 1
            continue
        seen.add(e)
        out.append(e)
    return out, dropped_blank, dropped_duplicate


def normalize(rec: dict) -> tuple[dict, dict]:
    """Return (normalized record, notes). Never raises; validation reports problems."""
    out: dict = {}
    notes: dict = {"warnings": [], "dropped_duplicates": 0, "bad_entity_keys": []}

    if isinstance(rec, dict):
        unknown = sorted(set(rec) - _KNOWN_KEYS)
        if unknown:
            # Silently dropping an unrecognized key is indistinguishable from a typo
            # that quietly loses data — "expected_behaviour" (British spelling) would
            # otherwise draft clean while doing nothing.
            notes["warnings"].append(
                f"unrecognized field(s), ignored: {', '.join(unknown)}"
            )

    for k in _LOCATORS:
        v = rec.get(k)
        out[k] = v.strip() if isinstance(v, str) else v

    v = rec.get("type")
    out["type"] = v.strip().lower() if isinstance(v, str) else v

    for k in _COLLAPSED:
        v = rec.get(k)
        if isinstance(v, str):
            out[k] = _collapse(v)
        elif v is not None:
            out[k] = v
    for k in _TRIMMED:
        v = rec.get(k)
        if isinstance(v, str):
            out[k] = v.strip()
        elif v is not None:
            out[k] = v

    keys = rec.get("entity_keys") or []
    if isinstance(keys, list):
        def _ek(s: str) -> str:
            if not s.strip():
                return ""  # a blank entry is caller noise, not a malformed key
            canon, ok, suspicious = _canonical_entity_key(s)
            if not ok:
                notes["bad_entity_keys"].append(s.strip())
            for seg in suspicious:
                notes["warnings"].append(
                    f'{seg!r} in {s.strip()!r} is stored uppercased. If that object '
                    f'really is case-sensitive, write it as "{seg}" — an unquoted '
                    "name folds to upper and would never match"
                )
            return canon
        kept, blank, dup = _normalize_set(keys, _ek)
        out["entity_keys"] = kept
        notes["dropped_duplicates"] += dup
        if blank:
            notes["warnings"].append(
                f"{blank} entry/entries in entity_keys were dropped (blank or not a "
                "string) — check the input if that wasn't expected"
            )
    elif keys:
        out["entity_keys"] = keys

    concepts = rec.get("concepts") or []
    if isinstance(concepts, list):
        # Collapsed, not just trimmed, like the server: a term pasted out of a doc
        # often carries a tab or a non-breaking space, and trimming alone keeps it as
        # a second concept that reads identically to the first.
        kept, blank, dup = _normalize_set(concepts, _collapse)
        out["concepts"] = kept
        notes["dropped_duplicates"] += dup
        if blank:
            notes["warnings"].append(
                f"{blank} entry/entries in concepts were dropped (blank or not a "
                "string) — check the input if that wasn't expected"
            )
    elif concepts:
        out["concepts"] = concepts

    # absorbable mirrors the server's own derivation (FEEDBACK_RECORD.md "The eval
    # pair earns absorption"): type != procedural AND triggering_query AND
    # expected_behavior. The value itself is server-owned and never sent — this is
    # purely so draft can warn about the one shape that can never be repaired after
    # the write, per this module's own stated purpose of catching a plausible-looking
    # record that can never work.
    notes["absorbable"] = (
        out.get("type") != "procedural"
        and bool(out.get("triggering_query"))
        and bool(out.get("expected_behavior"))
    )
    if out.get("type") != "procedural" and not notes["absorbable"]:
        notes["warnings"].append(
            "triggering_query and expected_behavior are both missing or empty, so "
            "this record can never be absorbed into a build. Neither can be added "
            "later — capture them now if the builder is still looking at the wrong answer"
        )

    return out, notes


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #


def validate(rec: dict, notes: dict) -> list[str]:
    """Every rule the normalized record breaks, all of them, in one list.

    All at once rather than first-failure: the caller is composing a form, and one
    failure per round trip costs a round trip per mistake.
    """
    errs: list[str] = []

    for k in _LOCATORS:
        v = rec.get(k)
        if not isinstance(v, str) or not v:
            errs.append(f"{k} is required")

    for k in _REQUIRED:
        v = rec.get(k)
        if not isinstance(v, str) or not v:
            if k == "feedback_rule":
                errs.append(
                    "feedback_rule is required: a record with nothing to inject "
                    "cannot change an answer, but would still report success"
                )
            elif k == "indexed_text":
                errs.append(
                    "indexed_text is required: it is the only text a question is "
                    "matched against, so a record without one can never be found"
                )
            else:
                errs.append(f"{k} is required")

    # query_pattern is documented as "omit — fold it into indexed_text instead"
    # (nothing reads it, like concepts, but unlike concepts this skill never derives
    # it at all). Unlike session_id/deployment, which the allow-list in normalize()
    # makes structurally impossible to send, query_pattern would otherwise pass
    # through untouched if a future edit ever populated it. Reject it loudly here
    # instead of letting that drift ship silently.
    if rec.get("query_pattern"):
        errs.append(
            "query_pattern is deliberately unused by this skill — fold its content "
            "into indexed_text instead (see FEEDBACK_RECORD.md)"
        )

    t = rec.get("type")
    if isinstance(t, str) and t:
        if t == _TYPE_SCOPE:
            errs.append(
                'type "scope" cannot be recorded: bringing an unscoped asset into a '
                "context takes effect only at build time, so nothing would serve it. "
                "Route this to refine/ instead"
            )
        elif t not in _TYPES:
            errs.append(f"type {t!r} is not one of: {', '.join(_TYPES)}")

    # The payload is sent inside a dollar-quoted SQL literal, and `$$` inside one
    # terminates it. Dollar quoting has no escape sequence, so there is nothing to
    # escape to: the only options are reject or produce broken SQL. Free text is
    # verbatim builder prose, so this is reachable — "the query returned $$0 instead
    # of revenue". No byte cap and no server-side check catches it.
    for k in _FREE_TEXT:
        v = rec.get(k)
        if isinstance(v, str) and "$$" in v:
            errs.append(
                f"{k} contains '$$', which would terminate the dollar-quoted SQL "
                "literal early. There is no escape for it — ask the builder to rephrase"
            )

    for k, cap in _CAPS.items():
        v = rec.get(k)
        if isinstance(v, str) and len(v.encode("utf-8")) > cap:
            errs.append(
                f"{k} is {len(v.encode('utf-8'))} bytes, over the {cap}-byte cap"
            )

    it = rec.get("indexed_text")
    if isinstance(it, str) and it:
        m = _FQN_IN_PROSE.search(it)
        if m:
            errs.append(
                f"indexed_text contains the qualified name {m.group(0)!r}. It is the "
                "embedded text, and an identifier pulls the match away from how "
                "people phrase questions — put names in entity_keys and feedback_rule"
            )

    raw_it = rec.get("_raw_indexed_text")
    if isinstance(raw_it, str):
        if "\n\n" in raw_it.strip():
            errs.append(
                "indexed_text must be one paragraph — it is stored as a single line, "
                "so separate paragraphs run together"
            )
        elif _BULLET.search(raw_it):
            errs.append(
                "indexed_text must be flowing prose, not a list — list markers are "
                "flattened into one line on the way in"
            )

    for bad in notes.get("bad_entity_keys", []):
        errs.append(
            f"entity_key {bad!r} is not a three-part DATABASE.SCHEMA.OBJECT name; "
            "a key in any other shape matches nothing"
        )

    # A non-list entity_keys/concepts value bypasses normalize()'s list-shaped
    # canonicalization/dedup/cap path entirely (normalize() forwards it verbatim so
    # it lands here, rather than dropping it, precisely so this can catch it) and
    # would otherwise sail through to build_params untouched — a very reachable
    # mistake, since the caller is an LLM composing JSON by hand and "a string
    # instead of a one-element list" is one of the most likely shapes to slip.
    for k in ("entity_keys", "concepts"):
        v = rec.get(k)
        if v is not None and not isinstance(v, list):
            errs.append(f"{k} must be a list of strings, got {type(v).__name__}")

    for k in ("entity_keys", "concepts"):
        v = rec.get(k)
        if isinstance(v, list):
            for entry in v:
                if isinstance(entry, str) and "$$" in entry:
                    errs.append(
                        f"{k} entry {entry!r} contains '$$', which would terminate "
                        "the dollar-quoted SQL literal early. There is no escape "
                        "for it — ask the builder to rephrase"
                    )

    keys = rec.get("entity_keys")
    if isinstance(keys, list) and len(keys) > _MAX_ENTITY_KEYS:
        errs.append(f"entity_keys has {len(keys)} entries, over the {_MAX_ENTITY_KEYS} cap")

    return errs


def prepare(raw: dict) -> tuple[dict, dict]:
    """Normalize then validate. Raises FeedbackError with every problem joined."""
    if not isinstance(raw, dict):
        raise FeedbackError("record must be a JSON object")
    rec, notes = normalize(raw)
    # Paragraph shape has to be judged before collapsing, which normalize() has
    # already done, so the pre-collapse text rides along under a private key.
    probe = dict(rec)
    if isinstance(raw.get("indexed_text"), str):
        probe["_raw_indexed_text"] = raw["indexed_text"]
    errs = validate(probe, notes)
    if errs:
        raise FeedbackError("\n".join(errs))
    return rec, notes


# --------------------------------------------------------------------------- #
# payload shaping + preview
# --------------------------------------------------------------------------- #


def build_params(rec: dict) -> dict:
    """The `parameters` object. Omits empty optionals; never sends `deployment`."""
    params = {k: rec[k] for k in _LOCATORS}
    for k in _REQUIRED:
        params[k] = rec[k]
    for k in ("entity_keys", "concepts"):
        if rec.get(k):
            params[k] = rec[k]
    # session_id is deliberately absent: the server derives provenance (origin,
    # trust, initiated_by, session_id) from the request JWT, so a caller-supplied
    # value is discarded. Sending it would imply a control we do not have.
    # query_pattern is deliberately absent too: validate() already rejects a
    # non-empty one, but it stays out of this list as well so the guarantee
    # holds structurally, not only because that check keeps existing.
    for k in ("triggering_query", "expected_behavior"):
        if rec.get(k):
            params[k] = rec[k]
    # Backstop, not the primary guard: validate()'s per-field checks give a specific
    # error naming the exact field, but they enumerate _FREE_TEXT plus entity_keys/
    # concepts by hand. This checks the whole assembled payload at once so a future
    # field added here without a matching validate() entry, or a caller who invokes
    # build_params directly without going through prepare() first, cannot ship a
    # "$$" that terminates the dollar-quoted SQL literal early.
    if "$$" in json.dumps(params):
        raise FeedbackError(
            "the assembled record contains '$$' somewhere in its payload, which "
            "would terminate the dollar-quoted SQL literal early — refusing to "
            "build a payload that is not safe to send"
        )
    return params


def summary(rec: dict, notes: dict) -> dict:
    """What the confirm card reads, plus the payload the record call needs.

    `card` is the builder's own framing — what they said, the situation, and what
    should happen instead. `record` is the payload. They are separate keys because the
    card must not grow field-by-field with the record: a builder checks whether we
    understood them, not whether twelve keys are populated. `said` is their verbatim
    words, so they can see what we read as well as what we made of it.
    """
    return {
        "ok": True,
        "domain": rec["name"],
        "card": {
            "said": rec["raw_feedback"],
            "situation": rec["indexed_text"],
            "instead": rec["feedback_rule"],
            "asked": rec.get("triggering_query", ""),
            "expected": rec.get("expected_behavior", ""),
        },
        "record": build_params(rec),
        "warnings": notes["warnings"],
        "dropped_duplicates": notes["dropped_duplicates"],
        "absorbable": notes["absorbable"],
    }



# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _load(from_file: str | None) -> dict:
    try:
        text = Path(from_file).read_text() if from_file else sys.stdin.read()
    except OSError as e:
        raise SystemExit(f"cannot read input: {e}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise SystemExit(f"cannot read input: invalid JSON: {e}")


def _dispatch(args: argparse.Namespace) -> int:
    raw = _load(getattr(args, "from_file", None))
    rec, notes = prepare(raw)
    print(json.dumps(summary(rec, notes), indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="feedback_record.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    # draft is the card's data source: pure, so it can run as often as the builder
    # edits without touching the filesystem.
    draft = sub.add_parser("draft")
    draft.add_argument("--from-file")

    args = p.parse_args()
    try:
        return _dispatch(args)
    except FeedbackError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
