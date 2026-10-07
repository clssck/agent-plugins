# Feedback record

A **feedback record** is one builder-authored correction to an answer. It lives in `feedback.json`, beside `scope.yaml` in the context's stage.

This file is the contract CoCo works from; the builder never sees it. The builder writes prose, CoCo derives the record, shows it once, and records it on approval.

**Feedback is not refine.** `refine/` changes `scope.yaml` — which assets are in scope. Feedback corrects an *answer*. The boundary is enforced server-side, not by convention: a correction that changes what is in scope is rejected with

> `type "scope" cannot be recorded: bringing an unscoped asset into a context takes effect only at build time, so nothing would serve this correction`

So "exclude staging", "add a schema", "include this dashboard" belong in `refine/`.

**Never explain the mechanism to the builder.** Nothing consumes a stored record yet, and when something does it still will not be `scope.yaml` and still will not be anything the builder can act on. Tell them the correction is recorded and kept, and stop. Do not surface timing, paths or index state, and **do not promise the correction will change an answer** — nothing acts on one today, so a builder told otherwise asks their next question and gets the same wrong answer.

## The form

Twelve keys: three locate the context, four are required, five are optional. Everything else on the stored record — ids, provenance, lifecycle, timestamps — is server-owned and silently overwritten if sent.

| Key | Req | Notes |
|---|---|---|
| `database_name`, `schema_name` | yes | from `persist_state.py doctor` |
| `name` | yes | the domain. **There is no context-id parameter** — the server resolves the triple |
| `raw_feedback` | yes | the builder's words, verbatim. **Immutable after recording** |
| `type` | yes | one of six (below). **Immutable after recording** |
| `feedback_rule` | yes | the imperative instruction, single line. This field carries the fix, so the correct FQN belongs here |
| `indexed_text` | yes | the kind of question this should fire on, written as the question. The *only* text a question is matched against |
| `entity_keys` | — | 3-part FQNs the correction is about. Stored, **not used for matching**, not in the response — see below |
| `concepts` | — | business terms. Recorded; nothing reads them |
| `query_pattern` | — | **Rejected outright.** `draft` hard-errors on a non-empty value — fold its content into `indexed_text` instead |
| `triggering_query` | — | the question that produced the wrong answer. **Gates `absorbable`** |
| `expected_behavior` | — | what a right answer looks like. **Gates `absorbable`** |

Never send `deployment`: GS injects it and it is hidden from the help schema, so a client value has no place in the payload (`STORAGE.md`). Never send `session_id` either — provenance (`origin`, `trust`, `initiated_by`, `session_id`) is derived server-side from the request JWT, so a caller value is discarded. Nothing on this form identifies the reporter.

**The eval pair earns absorption.** `absorbable` is derived as `type != procedural AND triggering_query != "" AND expected_behavior != ""`. A correction missing either is still recorded, but can never be baked in by a later build, because without a question and the answer it should give, nothing gives that build a way to check the correction still holds. Capture both while the builder is still looking at the wrong answer — neither can be added afterwards: `update-feedback` has no parameter for either, and it rejects any change to `absorbable`.

## The six types

Do not tell the builder about `type` at all, and do not describe what anything downstream does with it — nothing reads it yet, and the one downstream consumer that will is not this skill's to describe.

| `type` | Picks it |
|---|---|
| `definition` | a term or metric means X |
| `relationship` | X is the same as / derives from / feeds Y |
| `association` | concept X lives in table Y |
| `retrieval_steer` | for questions like Q, use table T |
| `annotation` | a durable fact a build could bake in |
| `procedural` | a standing runtime policy with nothing to bake |

`annotation` vs `procedural` is the only subtle line: could a future build bake this in as a fact? → `annotation`. Is it a standing policy that must stay live? → `procedural` ("never expose PII columns").

These six are the whole set. **Do not infer the enum from a validation error** — the server's "not one of" message lists a seventh value, `scope`, which a separate rule then rejects, so a model self-correcting from the error text picks the one value that can never be recorded.

## Deriving the record

CoCo derives every field itself. No separate model call, no `CORTEX.COMPLETE` — per `DISCOVERY.md`, the orchestrator is already an LLM and calling one from it is redundant and fragile. Write the twelve keys as JSON, then hand it to `feedback_record.py draft`, which validates them and summarises what will be recorded.

| Field | How to derive it |
|---|---|
| `raw_feedback` | the builder's words, untouched. Never paraphrase, never tidy |
| `type` | classify per the six patterns above |
| `feedback_rule` | one imperative sentence, self-contained, single line. Name the **correct** FQN here |
| `indexed_text` | see below |
| `entity_keys` | whichever table the builder named as the problem. Optional — omit rather than infer |
| `concepts` | business terms the builder used |
| `triggering_query` | the failing question. Ask for it if the transcript does not have it — it gates absorption |
| `expected_behavior` | what a right answer looks like, one sentence. Also gates absorption |

### Naming tables

A correction usually names two tables — the one that was used and the one that should have been — and they go in different fields.

> Builder: *"pipeline questions keep hitting `SALES.STAGING.OPPS`, they should use `SALES.DATA.OPPORTUNITIES`"*

```json
{
  "type": "retrieval_steer",
  "entity_keys": ["SALES.STAGING.OPPS"],
  "feedback_rule": "For pipeline questions use SALES.DATA.OPPORTUNITIES, not SALES.STAGING.OPPS.",
  "indexed_text": "User is asking about sales pipeline — how much was generated, open pipeline, coverage, or trends. Answered from opportunities data (open opportunities by stage and close date), not the staging table. Pipeline questions should be answered from the curated, deduplicated table instead."
}
```

- `feedback_rule` names the **right** table, because it is the field that carries the fix.
- `entity_keys` records whichever table the builder named as the problem — usually the one the wrong answer used, since the correct one is already in `feedback_rule`. **Optional:** omit it when no table was named, and do not infer one.
- `indexed_text` names neither FQN, including in its closing sentence — the same fix `feedback_rule` states with a name and an instruction, restated here without either.

**What `entity_keys` does today: nothing.** It is shape-validated, canonicalized and stored, and nothing reads it. Record it as the durable note of which table the report was about, not because it changes behaviour — and never ask the builder to reason about it.

Each key must have **exactly three** parts. Fewer, and the server rejects it. More, and the server accepts it and stores the tail as the object segment (`A.B.C.D` gives object `C.D`), so `feedback_record.py draft` rejects that before it is sent.

### `indexed_text`

The only text a question is matched against — `feedback_rule`, `raw_feedback`, `type` and the targets contribute nothing to finding a record. Nothing performs that matching yet, so what follows is how to write the field, not a description of a running pipeline.

- **Write the situation and the intent as the question, not the fix.** The server's parameter doc asks for "a paraphrase of the kind of question this correction should fire on, written as the question rather than the fix". A question describes a problem ("how's pipeline?"), never its resolution ("use OPPORTUNITIES"), so these two parts cannot resemble the question that should reach it if they read as an instruction.
- **The outcome is the one deliberate exception, and only at category level.** A short, non-FQN, non-imperative sentence describing what should happen — not instructing it. A record matched on intent alone is never surfaced by its fix, so the fix gets a foothold too, at the cost of some resemblance to a question.
- **No fully-qualified names anywhere in the field, including the outcome.** FQNs and the imperative phrasing both stay in `feedback_rule` alone.
- **Three parts, one voice:** what the user is trying to ask, what the underlying data is, and — generically — what should happen instead. One paragraph, not three stitched sentences; each part alone dilutes the others.
- **One paragraph of prose.** Newlines collapse on the way in, so a bulleted answer becomes a run-on line.
- **Under 2 KB.** Longer dilutes it, and nothing server-side enforces the cap.

Good — the first two parts read like a question someone would actually ask, and the outcome states the fix at category level as its own sentence, naming no FQN:

> "User is asking about sales pipeline — how much was generated, open pipeline, coverage, or trends. Answered from opportunities data (open opportunities by stage and close date), not the staging table. Pipeline questions should be answered from the curated, deduplicated table instead."

Not this. A keyword blob with FQNs in it is the documented wrong answer:

> ~~"pipeline; open pipeline; SALES.DATA.OPPORTUNITIES; SALES.STAGING.OPPS"~~

## Recording

The write in step 2 only runs after the builder has approved the card `feedback/SKILL.md` §3 renders — never before.

```bash
# 1. validate + summarise (pure; no network, no writes)
uv run --project <SKILL_DIR>/.. python <SKILL_DIR>/../scripts/feedback_record.py \
    draft --from-file <WORKSPACE_DIR>/cs_fb.json
```

`draft` is the only subcommand: this script never emits or runs SQL, because storage SQL is not wrapped in Python anywhere in this skill. Step 2 assembles and runs the statement per `STORAGE.md` "Recording feedback" — that file carries the SQL, including the sandbox annotation for the `snow sql` call; do not duplicate either here. The statement is `SELECT SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER($$…$$) AS result`. Dollar quoting is required — the payload routinely carries apostrophes and `\n`, and a single-quoted literal needs `''` doubling that is not valid JSON — and the function requires a **constant** argument, so `snow sql` cannot bind a parameter.

`draft` rejects `$$` anywhere in the free-form fields, because `$$` inside a dollar-quoted literal terminates it. If a builder's wording contains it, ask them to rephrase; there is no escape sequence inside dollar quoting.

### Response

```json
{"feedback_id": "fb:…", "lifecycle_state": "active", "envelope_version": 1,
 "indexed_text": "…", "indexed": false}
```

Five keys, all internal. **None is shown to the builder.** `feedback_id` present is the only proof the write landed; `envelope_version` is the version that committed, and `indexed_text` is the stored form of what was composed.

`indexed` is **always `false`** — the server hardcodes it, because nothing projects a record into a search index yet, so it carries no information today. Read it rather than assuming a value, but do not build copy around it and do not tell the builder anything about searchability.

Numbers come back as floats: `envelope_version` reads `1.0`, not `1`. Normalize before comparing or displaying one.

### Reading it back

Use `STORAGE.md`'s "Loading — one call" `get-stage-file` pattern, substituting `path: feedback.json`. Do not duplicate the fence here.

This returns the whole envelope, so find the record by its `feedback_id` and read `version` for the envelope version. A `NOT_FOUND` here has two causes that are not the same: no `feedback.json` yet (nothing recorded, not an error), or no context at all. Disambiguate with `get-context` first — reporting "nothing recorded" for a domain that does not exist sends the builder to the wrong place instead of to `setup/`.

The server also exposes `list-feedback`, which returns a per-record summary instead of the raw file. This skill does not use it: recording needs one read, for the error recovery below, and `get-stage-file` is the read this family already uses everywhere else.

## Errors

A rejection arrives as a **failed SQL statement**, not as an error field inside the envelope: `snow sql` exits non-zero with the message in stderr, prefixed by a status code. Verified against a live stack — `type: "scope"` returns

```
399525 (XX000): INVALID_ARGUMENT: type "scope" cannot be recorded: bringing an
unscoped asset into a context takes effect only at build time, so nothing would
serve this correction
```

So read the failure text, not `response_structured`. A clean statement with a `feedback_id` in the response is the only proof a write landed.

| Code | What is true | What to say |
|---|---|---|
| `InvalidArgument` | nothing written | surface **every** line — the server joins all failures into one message deliberately, so a builder fixes them in one pass |
| `NotFound` | the domain has no context | nothing to attach feedback to; route to `setup/` |
| `Unauthenticated` | no auth in the session | the session can't reach Cortex Context |
| `ResourceExhausted` | nothing written | this context's feedback file is full. **Do not** repeat the error's "remove older records" advice — records cannot be removed |
| `DataLoss` | nothing written; the file is damaged and deliberately untouched | it needs a human. Do not retry |
| `FailedPrecondition` | all five write attempts were contended, none confirmed | read the file back first (see "Reading it back" above), then report what is actually there |
| `Unknown` | at least one write went out, outcome genuinely unknown | read the file back first (see "Reading it back" above). **Never retry blind** — a retry creates a second record |
| `Internal` | server-side | report plainly; safe to retry once. Note an existing context can answer `create-context` with a bare `INTERNAL` and an empty description rather than "already exists" — check with `get-context` first |
| a `snow sql` failure with no status code | **unknown**, not "not saved" | treat as `Unknown` |

**On any error, read the file back before saying anything.** One call turns every ambiguous outcome into a definite answer, and only a clean response proves a write landed.

## Limits, and who enforces them

There are **no per-field byte caps server-side** — one record can consume the whole 1 MB envelope and still validate. `draft` imposes the caps below because nothing else does, and overrunning them degrades quality silently rather than failing.

| | Cap | Enforced by |
|---|---|---|
| `raw_feedback` | 8 KB | `draft` only |
| `feedback_rule` | 4 KB | `draft` only |
| `indexed_text` | 2 KB | `draft` only |
| `triggering_query`, `expected_behavior` | 2 KB each | `draft` only |
| `entity_keys` | 64 entries | `draft` only |
| three parts per entity key | exactly 3 | server rejects **fewer**; `draft` rejects **more**, which the server would accept and store with the tail as the object segment |
| whole file, per context | 1 MB | server (`ResourceExhausted`) |

The 1 MB limit is a **dead end**, not a threshold to manage. Its error advises superseding or removing older records, but no action removes a record and the store rejects any write that reduces the record count. Do not repeat that advice.

## Normalization

The server rewrites input on the way in, so a surprise in a stored record should be recognisable rather than mysterious. `draft` applies the same intent locally to keep its summary useful, but it does not promise byte equality and is not a mirror of the server.

- `feedback_rule`, `indexed_text`, `query_pattern`: internal whitespace runs collapse to one space. So does each `concepts` entry — a term pasted out of a doc often carries a tab or a non-breaking space, and trimming alone keeps it as a second concept that looks identical to the first and compares unequal to it.
- `concepts`, unlike `entity_keys`, are never case-folded — dedup is exact after whitespace-collapse, so `"Pipeline"` and `"pipeline"` are stored as two distinct concepts. Write a term the same way every time.
- `raw_feedback` and the rest: trimmed only, so line breaks survive.
- `entity_keys`: each segment resolves the way Snowflake resolves an identifier, through a copy of the catalog side's resolver kept in step by a test rather than shared, because this package cannot import that one. Unquoted folds to upper; **quoted keeps its case and sheds its quotes**, so `SALES.DATA."MixedCase"` is stored as `SALES.DATA.MixedCase`. Quote a genuinely case-sensitive name when composing it — left unquoted, `SALES.DATA.MixedCase` becomes `SALES.DATA.MIXEDCASE`, a different object, which validates fine and is then wrong permanently with nothing to signal it.
- `entity_keys` and `concepts`: deduped **silently**. `draft` reports what it dropped so the card can show a target count that matches reality.

**Resolution runs once, over the JSON you composed — never feed a summary back in.** A resolved name is not a fixed point: re-resolving `SALES.DATA.MixedCase` folds it to `SALES.DATA.MIXEDCASE`, a different object. When a builder asks for a change, patch your own JSON and re-draft from that.
