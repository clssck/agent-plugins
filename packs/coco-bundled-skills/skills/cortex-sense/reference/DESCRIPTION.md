# Context description

Single contract for generating, confirming, and persisting a Cortex Sense context's **description**. Used by `setup/SKILL.md` §10 and `refine/SKILL.md` §6.

## Why this exists

The description is consumed by the `cortex_sense` tool. When an agentic client has several contexts available, the description is the **only** signal it uses to decide which context(s) to pass as tool input for a given user query. A vague description means the wrong context gets selected, or a relevant one gets skipped.

So the description is written for a **routing decision made by another agent**, not as a human-facing summary. It answers exactly one question: *would a query about X be better answered with this context loaded?*

## Source of truth

The description lives **only** in the context object's `COMMENT`. It is deliberately not duplicated in `scope.yaml` — one writable home, no reconciliation problem.

The manifest stores a single marker, `description_synced_version`, which records the `version_id` of the manifest the description was last confirmed against. See "Drift tracking" below.

## When this runs

**Before the save** — not after it. The description is generated and confirmed while the builder is still in the interactive stretch, before `put-stage-file` runs. This means `description_synced_version` can be written as part of the same single `put-stage-file` call that saves the rest of the manifest — no second write, no snapshot/`version_id` divergence.

**Both `setup` §10 and `refine` §6 always regenerate and re-confirm on every save.** The marker records which version was last confirmed; it is not used to gate whether the description step runs. Re-confirming on every save is always cheaper than silently misrouting queries on a stale description.

## Generation rules

Generate from the in-memory manifest — the `sources[].rules` (which schemas/patterns are in and out), `concepts`, and the use case name. Do not run new discovery queries just to write the description. **Orchestrator reasoning step — never `CORTEX.COMPLETE`.**

**Shape:** 1–3 sentences, plain prose, no markdown, no leading label. Aim for 150–400 characters.

**Must include:**

1. **Subject matter in domain vocabulary** — what the data is *about*, using words a user would actually type. Prefer the vocabulary already harvested into `concepts` and table/column comments over the schema names themselves. "Game stats, player performance, team analytics" routes better than "the NBA.DATA schema".
2. **The main coverage areas** — the two or three things a query could reasonably ask about. This is what makes the routing decision possible.

**Include when they meaningfully change routing:**

3. **Notable exclusions** — only when a reader would otherwise wrongly assume coverage. An excluded subject area ("excludes Quora-related content") is worth a clause; routine hygiene exclusions (`_SUMMARIZE_*` temp tables, personal sandbox schemas, staging) are **not** — they add length without changing any routing decision.
4. **Grain or time bounds** — when the context is restricted in a way that would make it the wrong answer for some queries (e.g. "daily snapshots only", "FY24 onward").

**Avoid:**

- Internal pipeline vocabulary — `snowscope`, `horizon_star`, `catalog_objects`, `access_history`, `L1`/`L2`, `QBE`, `version_id`, `target_lag`.
- Bare schema/pattern lists as the primary content. A description that is only `NBA.DATA.*, NBA.STATS.*` gives an agent nothing to match a natural-language query against. Name the subject matter; schema names are at most supporting detail.
- Build mechanics — warehouse, role, table counts, refresh cadence. None of it affects context selection.
- Filler openers — "This context contains…", "A collection of data about…". Lead with the substance.
- Hedging ("various", "assorted", "and more") — it defeats the routing purpose.

**Distinctness:** the description should be distinguishable from the account's other context descriptions, so an agent choosing between them has something to go on. Two contexts over adjacent data should differ in their description, not just their name.

> **Known limitation — distinctness cannot be verified.** There is no read-back path for existing descriptions (see "No read-back" below), so distinctness is a **best-effort authoring guideline**, not a check. Do not claim to the builder that a description was verified as distinct. When two contexts are known from `list-contexts` to cover related subject matter, lean on the *differentiating* detail (grain, time bound, sub-domain, exclusion) to separate them.

### Worked example

Given a manifest scoping `NBA.DATA.*` with `*QUORA*`, `NBA.DATA._SUMMARIZE_*`, and several personal schemas excluded:

> Context for NBA basketball data covering game stats, player performance, and team analytics from the NBA.DATA schema. Excludes Quora-related content and internal sandbox schemas.

Why it routes well: names three matchable subject areas, and flags the one exclusion (Quora) a reader might otherwise assume is covered. The `_SUMMARIZE_*` and personal-schema exclusions are correctly collapsed into "internal sandbox schemas" rather than enumerated.

## Confirm block

Render this **verbatim** (substituting `<domain>` and the generated text) and then wait. This is a real gate — do not persist a description the builder has not seen.

```
Here's the description for <domain>:

  <generated description>

This is what agents read to decide whether to use this context for a
question, so it's worth getting right.

  press enter to accept  ·  or type your own
```

Handling the reply:

| Reply | Action |
|---|---|
| Empty / `ok` / `yes` / `accept` / equivalent | Use the generated description as-is. Set `description_synced_version` in the in-memory manifest before saving (see "Drift tracking"). |
| Free-form prose | Use the builder's text **verbatim** — do not rewrite, expand, or "improve" it. It is their description. Set `description_synced_version`. |
| A request to adjust ("make it shorter", "mention the playoff tables") | Regenerate with that constraint, re-render the confirm block, wait again. |
| `skip` / "leave it" / "no description" | Skip the `ALTER`. Do **not** set `description_synced_version` — the marker stays absent or unchanged so the next save re-offers. Say nothing further about it. |

Do not use `AskUserQuestion` here — it is a free-text gate, consistent with the rest of the builder flow.

## Applying it

Build the SQL in Python and write it to a temp file — this keeps the shell out of the path entirely, so bash never interpolates `<description>`:

```python
# Runs in CoCo bash sandbox (Linux) — safe on any host OS
import tempfile, os

if "$$" in description:
    # ask builder once for a rewrite — this has not been observed in practice
    raise ValueError("description contains $$")

sql = f'ALTER CORTEX SENSE <DB>.<SCHEMA>."<domain>" SET COMMENT=$${description}$$;'
fd, sql_path = tempfile.mkstemp(suffix=".sql")
with os.fdopen(fd, "w") as f:
    f.write(sql)
```

```bash
# Runs in CoCo bash sandbox (Linux) — safe on any host OS
uv run --project <SKILL_DIR>/.. snow sql --format json -f "$sql_path"
```

`<DB>` and `<SCHEMA>` are the values used for `create-context` (doctor `database` / `schema`; default `TEMP` / `CORTEX_SENSE`). `<domain>` is the use case name.

**Identifier quoting:** the domain **must** be double-quoted in the SQL. Context names are created lowercase; an unquoted identifier resolves to the uppercased name and fails. `validate_state()` constrains `business_domain` to `[A-Za-z0-9_-]+`, so the name itself can never contain a quote.

**Literal quoting:** use **dollar quoting** (`$$…$$`), not single quotes. Builder-authored descriptions routinely contain apostrophes ("a team's roster"); inside a `'…'` literal each one needs doubling. Dollar quoting passes the text verbatim. Using a temp `.sql` file (as above) means bash never sees the description string — `$$` terminates only the SQL literal, which is a Python-level check, not a shell concern.

> `$$` in builder-supplied text would terminate the dollar-quoted literal early. The `if "$$" in description` guard enforces this before the SQL is constructed — ask once for a rewrite if it triggers.

**Response handling:**

- **`Statement executed successfully`** → done. `description_synced_version` was already written into the manifest before `put-stage-file` ran.
- **`error.message` matches "does not exist" / "not found" (case-insensitive)** → `create-context` has not propagated. Skip silently and continue — do not retry (a second attempt within the same window will fail identically). The manifest is already saved; the description will apply on the next save.
- **`error.message` matches "insufficient privileges" / "access denied" / "unauthorized" (case-insensitive)** → the active role lacks `MODIFY` or `OWNERSHIP` on the context object. Surface **once** as an advisory line: *"Note: couldn't set the routing description — grant `MODIFY` on `<DB>.<SCHEMA>.<domain>` to `<ROLE>` if you'd like this set."* Then continue.
- **Any other error** → **non-blocking**. Log internally, do not surface to the builder, and continue.

> **Non-blocking by design.** The description is metadata that improves routing; it is not part of the scope the build consumes. A failure here must never prevent the confirm block from rendering or the build from being queued. The one exception is a privilege error — surfaced once as an advisory, never a blocker.

## Drift tracking

The manifest stores:

```yaml
description_synced_version: v-20260729-162000-abc123
```

This is the `version_id` of the manifest the description was last confirmed against.

**How the marker is written:** set `description_synced_version` in the in-memory manifest (before `put-stage-file`) to the `version_id` being minted for this save. It then rides in the single `put-stage-file` call with the rest of the manifest — no second write, no divergence between `scope.yaml` and `scope_<version_id>.yaml`. Do **not** write the marker when the builder skips.

| State | Meaning |
|---|---|
| **Absent** | No description has ever been confirmed — always generate and offer one. |
| **Present** | A description was confirmed at some prior save. Still regenerate and re-offer on the current save (the scope may have changed). |

The "present and equal to the current `version_id`" case cannot arise in the save path — `put-stage-file` always mints a new `version_id`. The marker's purpose is only to record *that* a description was confirmed; both flows re-offer unconditionally.

## No read-back

There is no way to read an existing description back:

- `get-context` does not return the comment.
- `SHOW CORTEX SENSE` / `SHOW CORTEX SENSES` / `DESCRIBE CORTEX SENSE` are not valid syntax.

Consequences, which the flows must respect:

1. **Drift can be detected but not diffed.** In a later session the marker tells you a description was previously confirmed, but the current text cannot be displayed. Always generate a fresh description to offer; never imply you are showing the builder their existing one.
2. **Distinctness cannot be checked.** See the caveat under "Generation rules".
3. **Within a single session**, the description just generated *is* known — it is fine to reference it in that same session.

This contract is forward-compatible: if a read-back path lands, the confirm block can additionally show the old text for comparison.
