---
name: semantic-view-agentic-optimization
description: "Run, resume, or inspect automated AI-driven optimization on a Cortex Analyst semantic view via the SYSTEM$CORTEX_ANALYST_*_AGENTIC_OPTIMIZATION procedures. Use whenever the user wants to comprehensively optimize / improve / augment / enhance / auto-tune a semantic view; start an optimization job; check, poll, or fetch results of an in-progress or finished run; resume a previously kicked-off optimization without remembering its ID; cancel a running optimization; or list past optimization runs. Trigger phrases include 'run agentic optimization', 'optimize my semantic view (automated)', 'AI-improve my model', 'are the optimization results in', 'did my optimization finish', 'I kicked off an optimization on <view> earlier', 'check optimization status', 'cancel optimization', 'show optimization history', 'past optimization runs'. Prefer this skill over one-shot suggestion mining (vqr_suggestions, filters_and_metrics_suggestions) whenever the user implies a comprehensive optimization job rather than a single-purpose suggestion request."
parent_skill: semantic-view
---

# Agentic Optimization

Agentic optimization is an asynchronous, server-side AI process that comprehensively analyzes a semantic view and proposes improvements (new VQRs, better descriptions, structural changes). The work runs inside Snowflake — this skill orchestrates it through four `SYSTEM$CORTEX_ANALYST_*_AGENTIC_OPTIMIZATION` procedures and only applies approved changes back to the model.

For one-off VQR suggestions use `vqr_suggestions/SKILL.md`. For metric/filter/fact suggestions use `filters_and_metrics_suggestions/SKILL.md`. For YAML-only checks use `validate/SKILL.md`. When the user wants to apply one specific advanced modeling intent — comparing to the same period last year/month (YoY/MoM/SPLY); building a rolling / YTD / lag-N metric; an SCD2 or ASOF temporal join; a snapshot fact that must not sum across time; an accumulating funnel; multi-path metrics through a chosen FK; cross-entity derived metrics; a `PRIVATE` fact; a computed-FK join; AI metadata steering Cortex Analyst; or diagnosing a fan trap / "multi-path relationship not supported" / inflated numbers — use `../patterns/SKILL.md` instead. Choose *this* skill when the user asks for a *job-style* optimization — something they kick off, walk away from, and come back to later.

**Important prerequisite:** agentic optimization mines existing verified queries to discover patterns. A view with zero VQRs has nothing for the optimizer to learn from. If the user wants to optimize a view that has no VQRs, route them through `vqr_suggestions/SKILL.md` first; this skill enforces that check in Phase 3.0 before spending any warehouse time.

## How this skill operates

Two principles drive every decision below; understanding them removes the need for a long rulebook:

- **The procedure is the source of truth.** All four operations live in Snowflake, so every action goes through `snowflake_sql_execute`. There is no local state to manage and no file to edit until results come back. Calling these procedures from `bash` or any non-Snowflake tool will not work.
- **Results are proposals, not edits.** A `COMPLETED` optimization returns *suggestions* — applying them mutates the user's model. Apply nothing without explicit user approval, even if every suggestion looks good. Auto-apply has no upside (the user can re-approve in seconds) and a real downside (silent regressions). When the user does approve, route through the existing edit/VQR/upload skills so the changes go through the normal review path.

## Prerequisites

- An existing semantic view (`DATABASE.SCHEMA.VIEW_NAME`) **or** a stage-based semantic model file (`@DATABASE.SCHEMA.STAGE/model.yaml`)
- A warehouse for the optimization job (`CREATE` only — `GET`/`LIST`/`CANCEL` don't need one)
- Role privileges to call the `SYSTEM$CORTEX_ANALYST_*` procedures on the target model

## Procedure reference

All four procedures take a single JSON-string argument. The `semantic_model` field selects the target — use **either** `semantic_view` **or** `semantic_model_file`, never both.

| Procedure | Purpose | Required JSON keys | Returns |
|-----------|---------|--------------------|---------|
| `SYSTEM$CORTEX_ANALYST_CREATE_AGENTIC_OPTIMIZATION` | Start a new optimization job | `semantic_model` (required), `experimental` (optional) — the warehouse is taken from the **session**, not this JSON | `optimization_name` (the handle for everything else) |
| `SYSTEM$CORTEX_ANALYST_GET_AGENTIC_OPTIMIZATION` | Poll status / fetch results | `<optimization_name>` (positional string arg) | `{request_id, status, state}` (`state` is itself a JSON string) |
| `SYSTEM$CORTEX_ANALYST_LIST_AGENTIC_OPTIMIZATIONS` | List runs for a model | `semantic_model`, `experimental` | `{optimizations: [{optimization_name, status}, ...]}` |
| `SYSTEM$CORTEX_ANALYST_CANCEL_AGENTIC_OPTIMIZATION` | Cancel an in-progress run | `<optimization_name>` (positional string arg) | Prefixed status string `AGENTIC_OPTIMIZATION_STATUS_<STATE>` (e.g. `_CANCELLING`, `_CANCELED`) |

`GET` returns one of four statuses, each driving the next action:

| Status | Meaning | Next action |
|--------|---------|-------------|
| `IN_PROGRESS` | Still running | Wait ~30s, poll again |
| `COMPLETED` | Finished | Parse `state` for results |
| `FAILED` | Errored | Surface `state` to user; do not retry blindly |
| `CANCELED` | User cancelled (server uses single-`L` spelling) | No further action |

## Workflow

### Phase 1: Identify the semantic model

Collect from the user (in this order):

| Field | Required | Notes |
|-------|----------|-------|
| **Semantic model reference** | Yes | `DATABASE.SCHEMA.VIEW_NAME`, **or** stage path `@DATABASE.SCHEMA.STAGE/model.yaml` |
| **Warehouse** | For `CREATE` only | Skip if user already specified; otherwise `SELECT CURRENT_WAREHOUSE()` and confirm |

If the user provided only a partial name, list candidates first so they can disambiguate:

```sql
SHOW SEMANTIC VIEWS LIKE '%<NAME>%' IN ACCOUNT;
```

✋ **Stop here** if the model reference is ambiguous — the rest of the workflow is keyed on this name and a wrong target wastes a job (which can range from ~20 seconds for a small well-tuned model to many minutes for a large one with dozens of VQRs).

### Phase 2: Choose the operation

Skip this prompt if the user's original message clearly stated one (e.g. "cancel my optimization" → Phase 5; "are the results in for my optimization on `DATABASE.SCHEMA.VIEW_NAME`" → Phase 2.5 Resume). Otherwise:

```
What would you like to do?

1. Run a new agentic optimization
2. Check status / fetch results of an existing optimization on this view
3. List all past optimizations for this model
4. Cancel a running optimization
```

If the user is **returning to check on a previously kicked-off run** (e.g. "I started one yesterday — any results?", "did my optimization finish?"), they almost never remember the `optimization_name`. Don't ask for it — go to Phase 2.5 (Resume) and discover it from the model's history.

### Phase 2.5: Resume an existing optimization (returning user)

When the user wants status or results but hasn't supplied an `optimization_name`, look it up from history rather than putting the burden on them.

#### 2.5.1 List runs for the model

```sql
SELECT PARSE_JSON(SYSTEM$CORTEX_ANALYST_LIST_AGENTIC_OPTIMIZATIONS($${
    "semantic_model": { "semantic_view": "DATABASE.SCHEMA.VIEW_NAME" },
    "experimental": "{}"
}$$)) AS result;
```

Parse `result:optimizations` — an array of `{optimization_name, status}` (often with a creation timestamp; sort newest-first when present).

#### 2.5.2 Pick the right run

Apply this priority order automatically. The reasoning: an in-progress run is what they're almost always asking about, and a recent completed run is the next most likely target. Anything else needs a real choice from the user.

1. **Exactly one `IN_PROGRESS`** → use it; jump to Phase 4 polling
2. **Multiple `IN_PROGRESS`** → present them (with timestamps if available) and ask which to check; ✋ stop here — guessing here can lead to "checking status" of the wrong job
3. **No `IN_PROGRESS`, one or more `COMPLETED`** → use the most recent `COMPLETED`; jump to Phase 6 (Review Results) via a single `GET`
4. **Only `FAILED` / `CANCELED`** → report that and ask whether to start a new run (Phase 3) or inspect a past run

Always **report what you picked** before fetching, so the user can correct you cheaply:

```
Found 3 past optimizations for DATABASE.SCHEMA.VIEW_NAME:
- opt_abc123  IN_PROGRESS  (started 2h ago)   ← checking this
- opt_xyz789  COMPLETED    (yesterday)
- opt_def456  FAILED       (3 days ago)
```

#### 2.5.3 Fetch the chosen run

```sql
SELECT PARSE_JSON(SYSTEM$CORTEX_ANALYST_GET_AGENTIC_OPTIMIZATION('<optimization_name>')) AS result;
```

Then route by status:

| Status | Action |
|--------|--------|
| `IN_PROGRESS` | Continue with Phase 4 (poll) |
| `COMPLETED` | Skip to Phase 6 (Review Results) |
| `FAILED` | Surface `state` to user; offer Phase 3 (new run) |
| `CANCELED` | Inform user; offer Phase 3 (new run) |

### Phase 3: Run a new optimization

#### 3.0 Sanity-check: does the model have VQRs to optimize?

Agentic optimization is fundamentally a VQR-mining process — it learns from the patterns in the model's verified queries (frequent metrics, common filters, recurring joins) and proposes generalizations. A view with **zero VQRs** gives the optimizer nothing to learn from: the job will spin up the warehouse, run, and return no useful suggestions, or fail outright. Catching this up front saves real warehouse time and a confused user wondering why nothing came back.

Read the model and check whether `verified_queries:` has at least one entry. The cheapest check via SQL — `REGEXP_INSTR` (not `REGEXP_LIKE`, which requires whole-string matches; and not the `(?ms)` inline flag form, which Snowflake's regex engine does not support):

```sql
SELECT REGEXP_INSTR(
    SYSTEM$READ_YAML_FROM_SEMANTIC_VIEW('DATABASE.SCHEMA.VIEW_NAME'),
    'verified_queries:\\s*\\n\\s+-'
) > 0 AS has_vqrs;
```

For a stage-based model file you can read the YAML directly (`@stage/path.yaml`) — or, if the user already loaded it via `cortex agent-studio sv-read`, scan the resulting YAML for a non-empty `verified_queries:` list. Either approach is fine — what matters is detecting the zero-VQR case before spending warehouse time.

If `has_vqrs` is false, ✋ stop and offer two paths:

1. **Bootstrap VQRs first, then come back** — route to `vqr_suggestions/SKILL.md` (mines Cortex Analyst usage or query history). Or use `filters_and_metrics_suggestions/SKILL.md` if the user wants to enrich the model with metrics/filters before suggesting VQRs.
2. **Proceed anyway** if the user has a strong reason — agentic optimization can sometimes still surface structural suggestions from the model shape alone, but tell them up front that results may be sparse.

Tone matters here: "this view has no VQRs, so the optimizer has nothing to learn from — let me suggest some VQRs first via `vqr_suggestions`, that takes about a minute" lands much better than "no VQRs, can't proceed".

#### 3.1 Check for in-progress runs first

These jobs aren't free — they spin up a warehouse and burn LLM/SQL calls. Runtime ranges from ~20 seconds for a small well-tuned model up to many minutes for a large one with dozens of VQRs, and a duplicate run rarely produces meaningfully different suggestions. List existing optimizations before starting:

```sql
SELECT PARSE_JSON(SYSTEM$CORTEX_ANALYST_LIST_AGENTIC_OPTIMIZATIONS($${
    "semantic_model": { "semantic_view": "DATABASE.SCHEMA.VIEW_NAME" },
    "experimental": "{}"
}$$)) AS result;
```

For a stage-based model file, swap the `semantic_model` value:

```json
{ "semantic_model_file": "@DATABASE.SCHEMA.STAGE/model.yaml" }
```

If any entry has `status = IN_PROGRESS`, ✋ stop and ask the user whether to:

1. Wait on the existing run (jump to Phase 4 with that `optimization_name`)
2. Cancel it (Phase 5) and then start a new one
3. Abort

#### 3.2 Create the optimization

`CREATE` returns the optimization name as a **bare string** (e.g. `DATABASE.SCHEMA.OPT_<uuid>`), not a JSON object — do not wrap it in `PARSE_JSON` or the client will error out *after* the server has already kicked off the job, leaving an orphan run.

The procedure picks the warehouse up from the SQL session, not from the JSON arg (`warehouse` is **not** a valid key on this procedure — the proto schema only defines `semantic_model`, `optimization_type`, and `experimental`). Set the session warehouse before calling:

```sql
USE WAREHOUSE WAREHOUSE_NAME;

SELECT SYSTEM$CORTEX_ANALYST_CREATE_AGENTIC_OPTIMIZATION($${
    "semantic_model": { "semantic_view": "DATABASE.SCHEMA.VIEW_NAME" }
}$$) AS optimization_name;
```

Surface the returned `optimization_name` to the user immediately. The job survives session boundaries — but only if the user can identify it later. Showing the ID up front is much cheaper than recovering it via Phase 2.5 next session.

```
Agentic optimization started

Optimization ID: <optimization_name>
Target:          DATABASE.SCHEMA.VIEW_NAME
Warehouse:       WAREHOUSE_NAME

Typical runtime ranges from ~20 seconds (small/well-tuned models) to several minutes (large models or many VQRs). I'll poll for status.
```

#### 3.3 Continue to Phase 4 (poll for completion)

### Phase 4: Poll for completion

If you don't have an `optimization_name` (e.g. user is returning to a prior run), jump back to Phase 2.5 to discover it via `LIST` rather than asking them — they likely don't have it.

```sql
SELECT PARSE_JSON(SYSTEM$CORTEX_ANALYST_GET_AGENTIC_OPTIMIZATION('<optimization_name>')) AS result;
```

The result is `{request_id, status, state}`. The `state` field is itself a JSON string — call `PARSE_JSON(result:state)` (or `TRY_PARSE_JSON`) to read it.

**Polling cadence and rationale:**

- Wait ~30 seconds between polls. Tighter polling burns tokens and adds load without changing outcome — these jobs run for minutes.
- After 3–5 polls without completion, ✋ stop and ask whether to keep waiting or cancel. The user may have other things to do, and silently looping for ten minutes feels worse than asking.
- Stop polling immediately on `COMPLETED`, `FAILED`, or `CANCELED`.

**On `FAILED`:** surface the `state` JSON to the user — it contains the failure reason. Don't auto-retry; the cause is usually deterministic (privileges, model issues, warehouse problems) and a blind retry just burns time.

**On `COMPLETED`:** continue to Phase 6 (Review Results).

### Phase 5: Cancel an in-progress optimization

```sql
SELECT SYSTEM$CORTEX_ANALYST_CANCEL_AGENTIC_OPTIMIZATION('<optimization_name>') AS result;
```

The procedure is idempotent — the returned value is a string of the form `AGENTIC_OPTIMIZATION_STATUS_<STATE>` reflecting the run's current status:

| Returned value | Interpretation |
|---|---|
| `AGENTIC_OPTIMIZATION_STATUS_CANCELLING` | Still spinning down — re-poll `GET` if the user wants the final state |
| `AGENTIC_OPTIMIZATION_STATUS_CANCELED` | Successfully cancelled (note: server returns the American spelling with one `L`) |
| `AGENTIC_OPTIMIZATION_STATUS_FAILED` / `_COMPLETED` / `_IN_PROGRESS` | Run was already terminal (or didn't exist as in-progress) — cancel is a no-op; report the existing status to the user |

Two formatting gotchas worth knowing:

- A "cancel" call can return without actually cancelling anything. Always read the response and report it accurately rather than assuming the run is now cancelled.
- `LIST` and `GET` return **unprefixed** statuses (`IN_PROGRESS`, `COMPLETED`, `FAILED`, `CANCELED`); only `CANCEL` returns the full `AGENTIC_OPTIMIZATION_STATUS_*` prefix. When comparing values across calls, strip the prefix or do a case-insensitive substring check rather than relying on exact string equality.

### Phase 6: Review results

When `GET` returns `status = COMPLETED`, parse the `state` JSON and present grouped suggestions. Field names may shift between API versions, so read the keys you find rather than insisting on a fixed schema. Expected categories:

- **Verified queries to add** — name, question, SQL, justification
- **Description / synonym improvements** — table/column path + proposed text
- **Structural suggestions** — new metrics, named filters, computed facts, relationships

Present them grouped, with a recommendation marker so the user knows where to focus first:

```
Agentic Optimization Results — DATABASE.SCHEMA.VIEW_NAME (<optimization_name>)

── Verified Queries (N) ─────────────────────────
1. ⭐ <vqr_name>
   Q: <question>
   SQL: <one-line summary>
   Why: <justification>

── Description Improvements (N) ─────────────────
2. [<table>.<column>] <new description excerpt>

── Structural Changes (N) ───────────────────────
3. [<table>] add metric <name> = <expr>
```

⭐ marks the broadly-useful or high-frequency picks; briefly note why others are lower priority. If `state` includes a `warnings` field, display it.

✋ Stop here and wait for the user to choose what to apply. Even if every suggestion looks correct, applying without explicit consent erases the user's ability to push back — and they will sometimes push back, because they know things about their data that the optimizer doesn't.

### Phase 7: Apply approved changes

Route accepted suggestions through the existing skills so they get the same review and validation as any other edit:

- **VQR additions** → `vqr_management/SKILL.md` (`sv-edit` operation `add_vqr`)
- **Metrics / filters / facts / relationships / descriptions** → `edit/SKILL.md` (`sv-edit` with the matching operation)

If the optimization payload includes `changes` triples (`operation` / `path` / `value`), pass them directly to `sv-edit` — they're already in the right shape and rewriting them by hand only introduces typos.

After edits land, validate via `validate/SKILL.md` (YAML check by default; bulk VQR validation only if the user asks). If the model came from a deployed semantic view and the user wants the changes live, deploy via `upload/SKILL.md` (`sv-deploy`).

### Phase 8 (optional): View optimization history

For "show me past optimization runs":

```sql
SELECT PARSE_JSON(SYSTEM$CORTEX_ANALYST_LIST_AGENTIC_OPTIMIZATIONS($${
    "semantic_model": { "semantic_view": "DATABASE.SCHEMA.VIEW_NAME" },
    "experimental": "{}"
}$$)) AS result;
```

For any `COMPLETED` entry the user wants to revisit, fetch it with `GET_AGENTIC_OPTIMIZATION('<optimization_name>')` (Phase 4) and present per Phase 6. They can re-apply old suggestions through Phase 7 — older runs sometimes contain ideas that became relevant only after later changes.

## Stopping points

- ✋ Phase 1: model reference ambiguous
- ✋ Phase 2.5: multiple `IN_PROGRESS` runs for the same model — ask which to resume
- ✋ Phase 3.0: model has zero VQRs — offer to bootstrap via `vqr_suggestions/` before optimizing
- ✋ Phase 3.1: an `IN_PROGRESS` run already exists
- ✋ Phase 4: 3–5 polls without completion — ask whether to keep waiting or cancel
- ✋ Phase 6: before applying any suggestion to the model

## Error handling

| Error | Likely cause | Fix |
|-------|--------------|-----|
| `Semantic view not found` | Wrong `DATABASE.SCHEMA.VIEW_NAME` or insufficient grants | `SHOW SEMANTIC VIEWS IN <db>.<schema>` and verify `CURRENT_ROLE()` |
| `Insufficient privileges` | Role lacks usage on procedures or model | Grant on the schema; confirm role |
| `GS_EXCEPTION` / `SQL execution internal error` from `GET` | Unknown `optimization_name` (the procedure throws rather than returning a clean 404) | Run `LIST` to discover valid names; never feed user-typed ids straight to `GET` without verifying they exist first |
| `Optimization not found` | Stale `optimization_name` from another account/role | Run `LIST` to discover valid names |
| `Warehouse not specified` (CREATE) | No active session warehouse | Run `USE WAREHOUSE <name>` before calling — the procedure has no `warehouse` JSON key, it reads the session warehouse |
| `state` is unparseable JSON | Older API version or unexpected payload | Surface raw `state` string to user; don't guess at fields |
| `FAILED` status | Server-side error captured in `state` | Show `state` reason; don't auto-retry |

## Success criteria

- ✅ Operation chosen unambiguously (run / status / list / cancel)
- ✅ For `run`: `optimization_name` reported to the user immediately after `CREATE`
- ✅ For `status`: poll loop terminated on `COMPLETED`, `FAILED`, or `CANCELED` — never busy-loops
- ✅ Suggestions presented grouped, ranked, with recommendations marked
- ✅ No edits applied without explicit user approval per suggestion (or per group)
- ✅ Validation run after applying changes; deployment only when the user asks
