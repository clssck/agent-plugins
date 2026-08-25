---
name: cortex-sense-feedback
description: "[Work In Progress] Record one correction against a built Cortex Sense domain: what goes wrong, which questions it comes up on, and what should happen instead. CoCo derives the record from what the builder said, shows one confirm card in their own words, and records it only on explicit approval. Use when: the builder explicitly asks to record feedback, or reports a wrong answer and wants it corrected. Triggers: @cortex-sense feedback <domain>, record feedback, give feedback on <domain>, log a correction, @cortex-sense resume <domain> + feedback."
parent_skill: cortex-sense
---

# Feedback

> **[Work In Progress]** This sub-skill is under active development. Recording a correction works end to end and is durable, but nothing consumes a stored correction yet, and there is no way to list or edit one from here. Tell the builder it is a work in progress the first time they reach this path, and do not describe capabilities it does not have. Registered as item 12 in `../reference/NOT_YET_IMPLEMENTED.md`, which is what to delete against when this path is finished.

## When to load

The builder used the **feedback verb** and is reporting an answer that was wrong.

Corrections that change *which assets are in scope* — "exclude staging", "add a schema", "include this dashboard" — are not feedback. They belong in `../refine/SKILL.md`, and the server rejects them outright. §1 asks once when a report is ambiguous between the two. An un-verbed correction ("DAU is wrong", "the agent picked the wrong table") also stays with `refine` — don't claim this path for it.

Never tell the builder how or when a correction takes effect, and never promise that it will. Nothing acts on a stored correction yet, so say it is recorded and kept, and stop there.

## Setup

Read once, before drafting:

- `../reference/FEEDBACK_RECORD.md` — the form, the six types, how to derive each field, the `indexed_text` rules, the error map
- `../reference/INSTRUCTIONS.md` — shares the definition/relationship/association vocabulary; `retrieval_steer` and `annotation` are feedback-only, classified per `FEEDBACK_RECORD.md`'s own table
- `../reference/STORAGE.md` — `get-context`, and how builder SQL is run

`<WORKSPACE_DIR>` and `<SKILL_DIR>` are placeholders the agent resolves.

## 0. Pre-flight (doctor + context check)

Issue both calls immediately, in the same turn — do not wait for one to finish before starting the other.

```bash
uv run --project <SKILL_DIR>/.. python <SKILL_DIR>/../scripts/persist_state.py doctor
```

plus `get-context` for the domain per `../reference/STORAGE.md`.

- **`snow_cli == "missing"`** → render the install line and stop.
- **`get-context` NotFound** → there is no context to correct yet. Say so and route to `../setup/SKILL.md`.
- **Any other `get-context` error** → log internally and continue.

The builder never sees `snow` tracebacks, validator detail lines, raw tool traces, or step commentary. If something fails with no recovery, render one plain sentence and stop.

## 1. Get the wrong-answer report

If the report came with the verb, go straight to §2. Otherwise render this and wait:

```
──────────────────────────────────────────────────────────────────
  Feedback for <domain>                        [work in progress]
──────────────────────────────────────────────────────────────────
  Tell me what went wrong, in your own words — the question you
  asked, what came back, and what it should have been.

  I'll show you the correction before anything is saved.

  This is still being built: your correction is saved and kept,
  and you can't list or edit corrections from here yet.
──────────────────────────────────────────────────────────────────
```

**When the report is really about scope, ask once.** "Exclude staging", "add a schema", "this table shouldn't be here" are about *what is in scope*, and the server rejects them outright, so guessing wrong costs a round trip and a confusing error. Where it could be either, ask and route on the answer:

```
  Is the answer wrong, or should that data not be in scope at all?
```

Wrong answer stays here. Not-in-scope goes to `../refine/SKILL.md`. Ask only when it is genuinely ambiguous — a plain wrong-answer report needs no question.

## 2. Draft the feedback

Three things carry the correction. Get them from the builder's own words, asking only for what the transcript does not give:

- **What goes wrong** — the situation, including what happens today.
- **Which questions it comes up on** — the kind of question, not one example.
- **What should happen instead.**

The situation and the questions fuse fully into one field. What should happen instead is used twice: verbatim as `feedback_rule`, and again, generically and without its FQN, folded into that same field. The card shows the fusion, never the answers separately.

Then derive the record from those, per `../reference/FEEDBACK_RECORD.md` "Deriving the record":

| From | Field |
|---|---|
| `persist_state.py doctor` (§0) | `database_name`, `schema_name` |
| the domain already named to reach this path | `name` |
| all three, the third at category level with no FQN — see below | `indexed_text` |
| what should happen instead, imperative, naming the correct FQN | `feedback_rule` |
| the builder's words, untouched | `raw_feedback` |
| the classification | `type` |
| the failing question, and what a right answer looks like | `triggering_query`, `expected_behavior` |
| any table the wrong answer used | `entity_keys`, optional |

`feedback_rule` needs the **correct** FQN, but the builder does not always name it. If they did, use it. If they didn't, ask which table it should be — same principle as `entity_keys` ("omit rather than infer"), applied here because guessing an FQN and being wrong is worse than a missing one.

`indexed_text` draws on all three answers, because it is matched on **intent** (the questions), **relevance** (the situation), and, generically, the shape of the **fix**. Per `../reference/FEEDBACK_RECORD.md` "`indexed_text`" the fix is the one deliberate exception to writing the field as a question — a record matched on intent alone is never surfaced by its own fix. Write all three as one flowing paragraph, intent first — three stitched sentences dilute each other, and a question alone will not match a report about the data or the fix it needs. No part names a qualified name, including the outcome part — the FQN and the imperative phrasing both stay in `feedback_rule` alone.

> questions about pipeline coverage, open pipeline, quarterly trends
> + answers coming from the staging table with its duplicate renewals
> + the fix, generically: pipeline questions should be answered from the curated, deduplicated table instead
> = "User is asking about sales pipeline — how much was generated, open pipeline, coverage, or trends. Answered from opportunities data, not the staging table. Pipeline questions should be answered from the curated, deduplicated table instead."

Do this yourself — there is no separate model call and no `CORTEX.COMPLETE`. Write the JSON to `<WORKSPACE_DIR>/cs_fb.json`, then:

```bash
uv run --project <SKILL_DIR>/.. python <SKILL_DIR>/../scripts/feedback_record.py \
    draft --from-file <WORKSPACE_DIR>/cs_fb.json
```

Exit 0 prints a summary. Its `card` is what §3 renders; its `record` is the payload §4 sends. Render the card from `card`, not from the JSON you composed.

Exit 1 prints every problem at once. Fix exactly the fields named and re-run. **Exception: never edit `raw_feedback` to make it pass.** It must stay the builder's words, untouched — if a `$$` or the byte cap rejects it, ask them to rephrase; there is no fix CoCo can make on their behalf. If the second attempt also fails, show the builder what you could not resolve rather than guessing a third time.

Two things are easy to get wrong:

- **`indexed_text` is the only field a question is matched against.** The outcome part restates the fix at category level, never as an instruction.
- **`triggering_query` and `expected_behavior` cannot be added later.** Together they decide whether a future build can absorb the correction, and there is no parameter to set them afterwards. Capture them while the builder is still looking at the wrong answer.

## 3. Confirm

⚠️ **STOP.** Nothing is written until the builder explicitly approves. Rendering the card is not approval.

```
─── sales_ops · feedback ──────────────────── [work in progress] ─

  What you said
    "pipeline questions keep hitting SALES.STAGING.OPPS, which
     still has the duplicate renewal rows we filtered out — should
     be SALES.DATA.OPPORTUNITIES"

  When this applies
    User is asking about sales pipeline — how much was generated,
    open pipeline, coverage, or trends. Answered from opportunities
    data, not the staging table. Pipeline questions should be
    answered from the curated, deduplicated table instead.

  Instead
    For pipeline questions use SALES.DATA.OPPORTUNITIES, not
    SALES.STAGING.OPPS.

  You asked
    "how is our pipeline doing this quarter"

  Expected
    an answer from the curated opportunities table

──────────────────────────────────────────────────────────────────
  looks right · edit when · edit instead · cancel
```

`What you said` is their words verbatim; the rows under it are what we made of them. Both matter, because only the builder can tell whether the second follows from the first, and a paraphrase that drifted is exactly what a confirm step exists to catch.

Every row is a field that actually gets stored — `When this applies` is the `indexed_text` paragraph, all three parts fused, and `Instead` is `feedback_rule`. The card deliberately does not show the three elicited answers separately: the record keeps only the fusion, so showing them as well would present something that is not stored beside something that is, and let them drift apart across an edit.

`When this applies` and `Instead` say the same fix twice on purpose — one generic and unnamed, one specific and imperative — because they are two different stored fields, not two views of one. Do not shorten either to remove the overlap.

It is still not a view of the record — a builder is checking whether we understood them, not whether twelve fields are populated.

What to render:

- Keep the `[work in progress]` marker in the header. It is the builder's only signal that this path is still being built, and it costs them nothing to see.
- Render from the summary's `card`, never from the JSON you composed: `said` → `What you said` (never re-wrap or tidy it), `situation` → `When this applies`, `instead` → `Instead`, `asked` → `You asked`, `expected` → `Expected`.
- **Omit `You asked` or `Expected`** when that one is empty. They are worth showing because they cannot be added later and together they decide whether a future build can absorb the correction — this card is the last chance to get them right.
- Append any `warnings` from the summary as indented lines under the row they concern.

What never to render:

- `type`, `entity_keys`, `concepts`, ids, lifecycle, provenance, or anything about indexing. All of it is either server-owned or mechanical, and showing it invites a builder to manage something they do not control.

Responses: `looks right` / `ok` / `yes` / `go` → §4. `edit when <text>` replaces `indexed_text` outright — the builder's own words stand as all three parts, and none is re-derived from it. `edit instead <text>` patches `feedback_rule`, and also re-derives the outcome part inside `indexed_text`: leaving the old one would describe a fix that is no longer the one being recorded. Patch your JSON, re-run `draft`, re-render. `cancel` → discard and confirm nothing was saved. Anything else → treat it as a correction to what the builder said, re-derive all three parts, and re-render.

When the builder rewrites `When this applies` directly, take it as written; when a correction instead changes what they said, keep all three parts: an edit that drops the questions, the situation, or the outcome part matches on that much less. If their rewrite itself fails `draft` (an FQN slipped in, or it reads as a list), the same rule as `raw_feedback` applies: ask them to adjust it, don't silently tidy their words to make it pass.

Free-form text is always accepted as a direct edit, even when it matches no keyword.

## 4. Record the feedback

Build the payload from the summary's `record` and run it per `../reference/STORAGE.md` "Recording feedback". Do not restate the SQL here.

The response is internal. `feedback_id` present means the write committed, and that is the only proof — a clean exit code alone is not.

## 5. Tell the builder what happened

One line, in their words:

```
  Recorded for <domain>: pipeline questions should use the curated
  opportunities table. It's saved and kept.
```

Say nothing about indexing, timing, or which mechanism applies it, and do not say it will be used from here on. `indexed` is always `false` today and carries no information, and nothing reads a stored correction — a builder promised an effect asks their next question, gets the same wrong answer, and stops trusting the rest.

On **any** error, read `feedback.json` back before saying anything — one call turns an ambiguous outcome into a definite one. Then follow the error map in `../reference/FEEDBACK_RECORD.md`.

Never retry a failed record blind: every attempt mints a new id, so a retry after an ambiguous failure creates a second correction rather than repairing the first.

## What this skill never does

- Drop the `[work in progress]` marker, or describe capabilities this path does not have — listing, editing, or retracting a correction.
- Save before an explicit affirmative.
- Render the card from your own JSON instead of the summary's `card`.
- Patch the summary and re-draft from that. Patch your own JSON: a resolved identifier is not a fixed point, so a second pass folds `SALES.DATA.MixedCase` into `SALES.DATA.MIXEDCASE`, a different object that validates and is then wrong permanently.
- Put a qualified name in `indexed_text`, or the fix instead of the situation.
- Show the builder `type`, `entity_keys`, ids, lifecycle, provenance, or index state.
- Tell the builder when or how the correction takes effect, or promise that it will.
- Repeat the "remove older records" advice from a full-file error — no action removes a record.
- Issue two `record-feedback` calls for one domain at the same time.
- Offer to edit, retract, or list existing corrections. This sub-skill records only.
