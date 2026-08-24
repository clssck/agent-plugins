# Guided Workflow: Create Policy in 2 Stages (UI Slash-Command Flow)

> ## You are now in the UI 2-stage flow. Different rules apply.
>
> This workflow is loaded only when the user's first message matches the slash command:
>
> ```
> /data-governance Create a new <policy type> policy for me
> ```
>
> issued by the data-governance UI component. The conversation MUST follow the 2-stage shape described below. **Do not** revert to the conversational create workflow, do not ask the user about target tables/columns up front, and do not auto-emit `ALTER TABLE` until Stage 2.
>
> The command already contains the policy type. Do **not** ask which policy type to create. Do **not** mention loading, routing, triggers, workflow files, or this file. The first visible response should only acknowledge the parsed type and ask for the fully qualified policy name.
>
> If you got here for any other reason (a normal conversational request like "I need to mask SSN on customers"), close this file and load the **conversational create workflow** instead.

## Hard rules for this workflow (read before doing anything else)

1. **First content question is the fully qualified policy name (`<database>.<schema>.<policy_name>`).** The UI component supplies this as the first follow-up; parse it into location and name, then run the uniqueness check before proceeding.
2. **Never ask about a target table or column in Stage 1.** Tables/columns are exclusively a Stage 2 concern.
3. **Stage 1 emits only `CREATE … POLICY`.** No `ALTER TABLE`, `ALTER VIEW`, `ALTER ICEBERG TABLE`, or tag attach.
4. **Stage 2 only runs if the user explicitly opts in** after the CREATE succeeds. Do not infer permission.
5. **Pre-write approval still applies** — show the SQL, wait for the user's "yes", then execute.
6. **Ask user-facing questions via the interactive question tool, not in prose.** See "Interactive Question Tool" below for the contract.
7. **Minimize suggested-prompts chips via prose discipline.** Keep prose to at most one short framing line per turn (or none); never emit a "next steps" / "you might also ask" / "here are some examples" list yourself. See "Interactive Question Tool → Disable suggested prompts" below for what's controllable from the workflow and what needs a separate agent-config / UI change.

---

## Why this workflow is different

| | Conversational create workflow | UI 2-stage flow (this file) |
|---|---|---|
| Target table/column asked | Up front (intake Q1: "What data are you protecting?") | **Never in Stage 1.** Asked only in Stage 2, after the policy already exists. |
| First question | What data, what protection, who has access | **What should we name the policy?** Ask for the fully qualified name (`<database>.<schema>.<policy_name>`), then run the uniqueness check. |
| Output of the create step | `CREATE POLICY` **and** `ALTER TABLE … SET POLICY` shown together | **Only `CREATE POLICY`.** No `ALTER TABLE` until Stage 2. |
| Stage 2 trigger | Implicit (single workflow) | **Explicit user opt-in:** "Would you like to apply this policy now?" |
| How questions are asked | Prose in the agent's reply | **Via the interactive question tool** the data-governance UI provides — structured prompt + options widget rendered inline. |

Stage 1 is strictly about *creating the policy object*. Stage 2 is strictly about *applying it to a column or table*. Do not mix them.

---

## Pre-Write Approval Rule (still applies)

Before any `CREATE`, `ALTER`, `DROP`, or `APPLY`:
1. Show the exact SQL.
2. Have the user's approval for *that specific* action.
3. Then execute.

**Approval already given in the user's current message counts — do not spend a turn re-asking for it.** If the user says "show me the SQL and then run it", "you're pre-approved to run it once shown", "show the ALTER and run it", or similar, then in the **same turn**: show the exact SQL *and* execute it. The gate is transparency (the SQL is shown) plus a specific authorization (which you already have) — not a mandatory extra round-trip. Re-asking here breaks the tight UI turn budget and can leave the policy created-but-unattached.

Still refuse to (a) skip showing the SQL ("just run it, don't show me"), or (b) remove/replace an existing protective control without an explicit go for that specific destructive step.

Read-only queries (`SHOW`, `DESCRIBE`, `GET_DDL`, `SELECT`) may be executed without confirmation.

---

## Interactive Question Tool

Whenever this workflow tells you to ask the user something — a name, a choice between options, a yes/no, a pre-write approval — invoke the **interactive question tool** the data-governance UI surface provides. The tool renders a structured ask-the-user widget inline in the chat. It supports three shapes:

- **Single-choice** — radio buttons. Use for `Yes / No`, *Definition / Attachment*, `Direct attach / Tag-based attach`, etc.
- **Multi-select** — checkboxes. Use for any *list-of-things* answer, especially role lists.
- **Short free-text** — a one-line typed answer. Use only when the answer is genuinely open-ended (a custom policy name, a custom expression, a fully-qualified table FQN that doesn't fit a quick discovery).

For each interactive question, pass:

- `prompt` — the literal question text shown to the user (e.g., *"What should we name the policy?"*, *"Apply this policy to a table now?"*).
- `shape` — `single-choice`, `multi-select`, or `free-text` (the three above).
- `options` — when `shape` is `single-choice` or `multi-select`, the discrete choices. For pre-write approvals, the standard single-choice set is `["Yes, run it", "Edit the SQL", "Cancel"]`. For multi-select questions, options are typically discovered (see the pattern below) and end with an *Other (free text)* escape.

Steps below render each question as a blockquote (`> …`) listing the prompt and, when applicable, the options. **Treat that blockquote as the spec of the tool call, not as prose to repeat back to the user.** Your prose reply for a question turn should be **at most one short framing line, or nothing at all** — the interactive tool's `prompt` + `options` carry the question content. Each turn must have exactly one framing line (or none); do **not** emit two near-duplicate "Got it — …" lines. Do **not** ask the same question twice (once in prose and once via the tool), and do **not** paste the options list into prose when the tool is rendering it. Do **not** append a "next steps" / "you might also ask" / "follow-up suggestions" / "here are some examples" list to your reply — that prose is exactly what suggestion-chip generators chew on (see "Disable suggested prompts" below).

### Pattern: enumerable lists (multi-select with discovery)

Several questions in this workflow ask the user to pick from a finite, discoverable set — most commonly **role lists** (who's allowed to see / who bypasses), but the same pattern fits any enumerable answer (tag names in a schema, columns in a table). For these, do not ask via free-text; ask via the interactive question tool's **multi-select** shape, with options populated from a one-shot read-only discovery query run in the same turn.

The shape is always:

1. **Discover** the candidate set silently before asking (read-only, no pre-write approval needed). Default queries:
   - **Role list** → `SHOW ROLES;` (use the `name` column).
   - **Tag list** → `SHOW TAGS IN SCHEMA <db>.<schema>;` (or the broader scope the user implied).
   - **Column list** → `DESCRIBE TABLE <fully-qualified-table>;` (use the `name` column).
2. **Ask** via the interactive tool, **multi-select**, with options = the discovered names (sorted; cap visible items at ~50 — longer lists should collapse to a typeahead in the widget) plus an **Other (free text)** escape so the user can type a name that isn't in the discovered list.
3. **Fallback**. If the discovery query returns zero rows, errors out (permission denied, schema not found, etc.), or is not applicable, skip step 1's options and ask the question via the interactive tool's **free-text** shape instead, prompting for a comma-separated list. Do not fail the conversation on a missing permission — surface the discovery error in one short prose line and proceed with free-text.

When a per-step blockquote below says *"Ask multi-select per the role-list pattern"*, the discovery + fallback shape above is implied — you don't need to repeat it inline. Use the prompt text given in the step.

**Fallback when the interactive tool itself isn't available.** If your current toolset does not include an interactive question / ask-user tool (e.g., a CLI session, an automated eval harness, or any non-UI surface), do **not** try to call a tool that isn't there. Ask the same question in prose immediately, in the same turn — keep the prompt text identical and list the options as a short bullet list under it (or as a comma-separated free-text instruction, when there are no options). Question turns must never end with no question to the user; the substance must always reach them, via the tool when present and in prose otherwise.

### Disable suggested prompts

The data-governance UI normally renders **suggested prompts** (clickable chips that fill the user's input box on click) below the agent's reply. **Minimize them for the entire duration of this workflow** — every turn, including pre-write approvals and the Stage-1 → Stage-2 handoff.

Two reasons:
1. The interactive question tool already presents the canonical answer set for every question. A parallel suggested-prompts row would be a *second* answer surface — different copy, different ordering, possibly different options — which leads to off-script answers that don't fit the workflow's branching.
2. The 2-stage flow has a strict turn shape (slash → fully qualified policy name → details → CREATE → apply? → target → ALTER, or the edit-flow analogue). Suggested prompts encourage the user to skip ahead or fork, which breaks the shape and confuses the per-turn discipline.

What you (the agent) can do — prose discipline:

- **Keep prose to at most one short framing line per turn** (or none — the interactive tool's prompt + options can stand on their own). Most suggestion-chip generators infer chips from the reply prose; less prose ⇒ fewer / weaker chips.
- **Never emit chip-style content yourself.** Do not append a "You might also ask…", "Try one of:", "Here are some examples:", "Next steps:", "Define the masking policy logic …" / open-ended exploration list to your reply. The interactive tool's `options` field is the only sanctioned answer-suggestion surface.
- **Don't restate the question in prose** when the interactive tool is rendering it — that doubles the surface area for the chip-generator and re-introduces the duplicate-reply pattern.

What this workflow can **not** do — surface-level mitigations (out of scope, but called out so reviewers know where to look if chips persist):

- The Snowflake Cortex Agents API as currently documented does not expose a per-reply `suppress_suggested_prompts` flag the agent can set from inside its response. If the data-governance UI generates these chips client-side from the assistant message, the only reliable suppression is at the UI / agent-config level — most plausibly via a directive in the data-governance UI agent's `instructions.response` (something like *"Do not propose follow-up questions or next-step suggestions; do not emit chip-style example lists"*), or a UI feature flag.
- If chips still appear with this skill loaded **and** prose is already minimal, the fix belongs in the data-governance UI agent definition or the UI rendering layer, not in this skill workflow. File that as a separate change against the agent config.

---

# STAGE 1 — Create the policy (no application)

## Step 1.1 — Confirm the policy type

The slash command tells you which policy type the user picked. **Combine the confirmation and the Step 1.2 fully qualified name question into a single reply** — do not emit two separate "Got it — …" lines. Use **at most one short prose line** as the lead-in (e.g. *"Aggregation policy it is."*) followed by the Step 1.2 question. Do not list every supported type back at them; do not ask the user to choose a type; do not append a "next steps" or "you might also ask" tail. Do not mention skill loading, workflow names, markdown files, triggers, slash-command patterns, or routing.

## Step 1.2 — Ask for the fully qualified policy name (FIRST question, always)

The UI 2-stage product contract supplies the policy name as the first follow-up. Ask for a fully qualified policy name so the answer carries both location and name in one turn.

Ask via the interactive question tool, free-text answer (no options):
> **prompt:** What should we name the policy? Provide the fully qualified name as `<database>.<schema>.<policy_name>`.

- Accept a fully qualified name such as `GOVERNANCE.POLICIES.MASK_PII_STRING`. Do not suggest a default.
- If the user provides only a bare name, ask once for the full `<database>.<schema>.<policy_name>`.
- If the user provides a malformed name, ask once for the corrected fully qualified name.
- If the UI follow-up contains template variables already expanded by the harness, treat the expanded value as authoritative.

Parse the response into `<database>`, `<schema>`, and `<policy_name>` and use those values for all remaining Stage 1 and Stage 2 SQL.

## Step 1.3 — Validate location and uniqueness

Verify the target schema exists and no policy with the same name already exists in the chosen location:
```sql
SHOW SCHEMAS LIKE '<schema>' IN DATABASE <database>;
SHOW MASKING POLICIES IN SCHEMA <database>.<schema>;
-- (or the appropriate SHOW <KIND> POLICIES variant for the chosen policy type)
```

- If the schema does not exist or the user lacks visibility, surface this in one short prose line and re-ask for a different fully qualified name. Do **not** offer to create the schema — that is outside this workflow's scope.
- If a policy with the same name already exists → surface it in one short prose line (*"A <kind> policy named `<name>` already exists in `<database>.<schema>`."*) and re-ask via the interactive tool: `prompt: "That name is already taken. Choose a different name?"`, `options: "Yes, pick a new name", "Cancel"`. On "Yes", re-ask the fully qualified name question (Step 1.2). Do **not** silently overwrite with `CREATE OR REPLACE`.
- If no conflict → proceed.

Once you have a valid `<database>.<schema>.<policy_name>`, confirm it back to the user in one short prose line, e.g. *"Got it: `MY_DB.GOVERNANCE.MASK_PII_STRING`. Now a few details..."*. Then proceed to the policy-specific questions (each asked via the interactive tool).

## Step 1.4 — Ask the policy-type-specific questions

Ask **only** the questions for the chosen type, **each via the interactive question tool**. Do not ask about target tables or columns. If the policy body needs to reference auxiliary tables (e.g., a mapping table for row access), that auxiliary table must already exist and the user must give you its fully-qualified name — but the *target* table this policy will protect is still a Stage 2 concern.

Skip any question the user has already answered in their initial message.

For the per-type questions below, the blockquote `prompt` / `options` lines are the spec of the tool call. When `options` is omitted, the question takes a free-text answer.

### Masking policy — Stage 1 questions

1. **Data type of the column.** The policy's argument and return type must match the target column type exactly.
   > **prompt:** What data type will the column be? (The policy's argument and return type must match the target column exactly.)
   > **options:** `STRING`, `NUMBER`, `DATE`, `TIMESTAMP`, `TIME`, `BOOLEAN`, `VARIANT`, *Other (free text)*

2. **Who is allowed to see the original (unmasked) value?** Recommend `IS_ROLE_IN_SESSION('<role>')` so secondary roles and inherited roles are respected. **Ask multi-select per the role-list pattern** (`SHOW ROLES` discovery + multi-select + free-text fallback — see the Interactive Question Tool section).
   > **prompt:** Which role(s) should see the original (unmasked) value? Pick one or more; the policy will use `IS_ROLE_IN_SESSION` so inherited and secondary roles are respected.
   > **options (multi-select):** *(populated from `SHOW ROLES`)*, *Other (free text — comma-separated role names not in the list)*

3. **What should everyone else see?** **Adapt the option list to the data type chosen in Q1** — present only the options that produce a value assignable to the policy's return type. Do not ask Q3 until Q1 is answered (or unambiguously implied by the user's earlier message); options that would yield a type-mismatched expression must be omitted from the choice set.

   > **prompt:** What should unauthorized roles see in this column?
   > **options:** (filtered by Q1's data type — see the table below)

   | Q1 data type | Options to present | Why others are dropped |
   |---|---|---|
   | `STRING` / `CHAR` / `VARCHAR` / `TEXT` | `NULL` (recommended), Fixed placeholder string (e.g. `'***MASKED***'`), Partial mask (last 4 of an SSN, domain-only of an email, prefix/suffix), Hash — `SHA2(val, 256)` (preserves uniqueness for joins), *Other (free text)* | — |
   | `NUMBER` / `INT` / `FLOAT` / `DECIMAL` | `NULL` (recommended), Fixed placeholder number (e.g. `0`, `-1`), Bucketed / rounded value (e.g. `ROUND(val, -3)` to nearest thousand, `FLOOR(val/1000)*1000`), *Other (free text)* | Raw `SHA2` returns a hex `STRING`; string placeholders like `'***MASKED***'` are not assignable to `NUMBER`. |
   | `DATE` / `TIMESTAMP_NTZ` / `TIMESTAMP_LTZ` / `TIMESTAMP_TZ` / `TIME` | `NULL` (recommended), Fixed placeholder (e.g. `DATE '1970-01-01'`, `TO_TIMESTAMP_NTZ('1970-01-01')`, `TIME '00:00:00'`), Truncated / coarsened value (e.g. `DATE_TRUNC('YEAR', val)`, `DATE_TRUNC('MONTH', val)`), *Other (free text)* | Raw `SHA2` returns `STRING`; string placeholders are not assignable to date/time types. |
   | `BOOLEAN` | `NULL` (recommended), Fixed `FALSE` (most secure default for permission-style flags), Fixed `TRUE`, *Other (free text)* | Partial mask and hash do not apply to a 2-valued type. |
   | `VARIANT` / `OBJECT` / `ARRAY` | `NULL` (recommended), Empty literal (`PARSE_JSON('{}')`, `OBJECT_CONSTRUCT()`, `ARRAY_CONSTRUCT()`), Redacted-keys variant (e.g. `OBJECT_DELETE(val, 'ssn', 'email')`), *Other (free text)* | Raw `SHA2` returns `STRING`; only valid for `VARIANT` if you cast back (rarely useful). |
   | `BINARY` | `NULL` (recommended), Fixed binary placeholder (e.g. `TO_BINARY('00')`), *Other (free text)* | Partial mask and hash break the column type. |

   The masked expression must be assignable to the policy's return type — a `NUMBER` masking policy cannot return `'***MASKED***'`, a `DATE` policy cannot return `SHA2(val, 256)`. If the user picks "Other" with a free-text answer that doesn't match the column type, point that out in prose and re-ask via the interactive tool with the type-correct option set.

4. *(Optional)* **Multi-argument policy?** Only ask if the user has hinted at conditional masking (e.g., a `visibility` flag).
   > **prompt:** Does the masking decision depend on another column (multi-argument policy)?
   > **options:** No (single-arg), Yes — *(if yes, follow up via the interactive tool with a free-text question for the extra arg names and types)*

### Row access policy — Stage 1 questions

1. **Row-filter argument** (the column name + type the policy receives — **not** the target column; that's Stage 2).
   > **prompt:** What is the row-filter argument? Give the column name and type used inside the policy body (e.g. `region STRING`, `tenant_id NUMBER`). This is the argument signature, **not** the target column — the target is a Stage 2 question.
   > *(free-text answer)*

2. **What logic decides row visibility?**
   > **prompt:** What logic should decide row visibility?
   > **options (single-choice):** Direct role check (one allowed value per role, via `IS_ROLE_IN_SESSION`), Lookup against an existing mapping table (you'll provide the fully-qualified table name and the role/value columns), User attribute via `SYSTEM$GET_TAG` (you'll provide the tag and the mapping table that joins it to allowed values)
   > *(if "Direct role check" is chosen, follow up multi-select per the role-list pattern asking which roles get which values; if mapping-table or user-attribute is chosen, follow up via the interactive tool with a free-text question for the fully-qualified table name and column mapping)*

3. **Bypass roles** (e.g., `ACCOUNTADMIN` always sees all rows). Skip if the user already named bypass roles in their initial message. **Ask multi-select per the role-list pattern.**
   > **prompt:** Which role(s), if any, should bypass the policy entirely (always see all rows)? Pick zero or more.
   > **options (multi-select):** *(populated from `SHOW ROLES`)*, *Other (free text — comma-separated role names not in the list)*
   > *(an empty selection means "no bypass")*

### Projection policy — Stage 1 questions

1. **Who is allowed to project the column** (i.e., have it appear in the outermost SELECT). For an unconditional clean-room block where no role may project the column, the answer is the empty selection — the policy body becomes a single `PROJECTION_CONSTRAINT(ALLOW => FALSE, ...)` with no allow branch. **Ask multi-select per the role-list pattern.**
   > **prompt:** Which role(s) should be allowed to project this column in the outermost SELECT? Pick zero or more; the policy will use `IS_ROLE_IN_SESSION` so inherited / secondary roles are respected. An empty selection means *no one* (unconditional clean-room block).
   > **options (multi-select):** *(populated from `SHOW ROLES`)*, *Other (free text — comma-separated role names not in the list)*

2. **When projection is denied, what should happen?**
   > **prompt:** When projection is denied, what should happen?
   > **options:** `FAIL` (default) — query errors out if the column appears in the outermost SELECT, `NULLIFY` — query succeeds; the column returns `NULL` in the outermost result

> ⚠️ `ENFORCEMENT => 'NULLIFY'` (single-quoted string, inside the deny-branch `PROJECTION_CONSTRAINT`). Unquoted `NULLIFY` is a Snowflake parse error; omitted `ENFORCEMENT` silently defaults to `FAIL`.

**Body templates by user choice:**

```sql
-- User picked: ENFORCEMENT => 'NULLIFY', role-conditional bypass for ROLE_A
CASE
  WHEN IS_ROLE_IN_SESSION('ROLE_A')
    THEN PROJECTION_CONSTRAINT(ALLOW => TRUE)
  ELSE
    PROJECTION_CONSTRAINT(ALLOW => FALSE, ENFORCEMENT => 'NULLIFY')
END

-- User picked: ENFORCEMENT => FAIL (default), role-conditional bypass
CASE
  WHEN IS_ROLE_IN_SESSION('ROLE_A')
    THEN PROJECTION_CONSTRAINT(ALLOW => TRUE)
  ELSE
    PROJECTION_CONSTRAINT(ALLOW => FALSE)   -- ENFORCEMENT defaults to FAIL
END

-- User picked: unconditional NULLIFY (clean room with no bypass)
PROJECTION_CONSTRAINT(ALLOW => FALSE, ENFORCEMENT => 'NULLIFY')
```

### Aggregation policy — Stage 1 questions

1. **Minimum group size.** The only valid parameter on `AGGREGATION_CONSTRAINT` is `MIN_GROUP_SIZE`. Do **not** invent parameters like `MIN_ROW_COUNT` or `MIN_ENTITY_COUNT`.
   > **prompt:** What minimum group size should the policy enforce? (`AGGREGATION_CONSTRAINT(MIN_GROUP_SIZE => N)`. The only valid parameter is `MIN_GROUP_SIZE` — do not invent others.)
   > **options:** `5`, `10`, `100`, *Other (free text — pick a positive integer)*

2. **Bypass roles** that get `NO_AGGREGATION_CONSTRAINT()`. **Ask multi-select per the role-list pattern.**
   > **prompt:** Which role(s), if any, should bypass the aggregation constraint (run unconstrained queries)? Pick zero or more.
   > **options (multi-select):** *(populated from `SHOW ROLES`)*, *Other (free text — comma-separated role names not in the list)*
   > *(an empty selection means "no bypass" — every role gets the constraint)*

3. *(Note — do not ask)* Whether the threshold counts rows or distinct entities is decided at **attach time** via the `ENTITY KEY (...)` clause — that is a Stage 2 question.

### Join policy — Stage 1 questions

1. **Default behavior — `JOIN_REQUIRED` value.**
   > **prompt:** What should the default `JOIN_REQUIRED` behavior be?
   > **options:** `TRUE` — every query must join the protected table to another table; no-join queries fail (typical for clean-room / partner data), `FALSE` — no restriction (rare as a standalone policy; usually only used as a bypass branch)

2. **Bypass roles** that get `JOIN_CONSTRAINT(JOIN_REQUIRED => FALSE)`. **Ask multi-select per the role-list pattern.**
   > **prompt:** Which role(s), if any, should bypass the join requirement (run unrestricted queries)? Pick zero or more.
   > **options (multi-select):** *(populated from `SHOW ROLES`)*, *Other (free text — comma-separated role names not in the list)*
   > *(an empty selection means "no bypass" — every role must join)*

### Tokenization policy — Stage 1 questions

1. **Data type of the column** (argument type and return type must match — same rule as masking).
   > **prompt:** What data type will the column be? (Argument and return types must match the target column exactly.)
   > **options:** `STRING`, `NUMBER`, `DATE`, `TIMESTAMP`, `TIME`, `BOOLEAN`, `VARIANT`, *Other (free text)*

2. **Tokenization expression** (the body of the policy). **Adapt the option list to the data type chosen in Q1** — same rule as the masking Q3 cheat-sheet: every option must produce a value assignable to the policy's return type. For a `STRING` policy all four shapes below are valid; for a `NUMBER` policy drop string-concat / literal-`'TOKENIZED'`-style options and prefer numeric transforms (e.g. `MOD(val * 2654435761, 1000000)`) or an external function with a `NUMBER` return; for `DATE` / `TIMESTAMP` use date arithmetic or an external function with a matching return; for `BOOLEAN` / `BINARY` essentially only an external function or a fixed literal of the right type makes sense. Do not ask Q2 until Q1 is answered.

   > **prompt:** What is the tokenization expression for the policy body?
   > **options:** (filtered by Q1's data type) Pure SQL transform of `val` (e.g. `'TOK_' || SHA2(val, 256)` for `STRING`; `MOD(val * 2654435761, 1000000)` for `NUMBER`; `DATEADD('day', HASH(val) % 365, DATE '1970-01-01')` for `DATE`/`TIMESTAMP`), External function call (e.g. `my_db.fpe.tokenize(val)` — must already exist; the function's return type must match Q1's data type), Fixed-literal mask of the right type (e.g. `'TOKENIZED'` for `STRING`, `0` for `NUMBER`, `DATE '1970-01-01'` for `DATE` — rarely useful but type-safe), *Other (free text — must return a value assignable to the policy's return type)*

3. **Bypass roles** that store raw values. Usually none — bypassing defeats the purpose. **Ask multi-select per the role-list pattern.**
   > **prompt:** Which role(s), if any, should bypass tokenization and store the raw value? Pick zero or more. (Usually none — bypassing defeats the purpose; only pick roles here if there's an explicit operational need.)
   > **options (multi-select):** *(populated from `SHOW ROLES`)*, *Other (free text — comma-separated role names not in the list)*
   > *(an empty selection means "no bypass" — every write is tokenized; if the user picks any roles, wrap the policy body in a `CASE` that returns `val` for those roles and the tokenized expression otherwise)*

4. *(Optional)* **Multi-argument policy?** Only ask if tokenization needs another column as a salt (e.g., `tokenize(val, salt)`). The `USING (...)` binding is Stage 2.
   > **prompt:** Does the tokenization need another column as a salt or auxiliary input (multi-argument policy)?
   > **options:** No (single-arg), Yes — *(if yes, follow up via the interactive tool with a free-text question for the extra arg names and types)*

5. *(Inform the user once, in prose)* Tokenization runs at **write time**. Once a row is inserted, the original value is gone (unless the tokenization is reversible by external key). A column cannot have both a masking and a tokenization policy.

## Step 1.5 — Generate the CREATE statement and confirm

Build the `CREATE OR REPLACE … POLICY` SQL for the chosen type. The policy body may reference existing helper objects (memoizable functions, mapping tables) — those must already exist. **Do not generate or mention any `ALTER TABLE`, `ALTER VIEW`, `ALTER ICEBERG TABLE`, or tag-attach SQL in this stage.**

Best-practice checklist for the generated SQL:
- Use `IS_ROLE_IN_SESSION('<role>')` for role checks (not `CURRENT_ROLE()`).
- For masking: use an explicit `ELSE NULL` or explicit masked literal so the fail-closed branch is visible.
- Match argument types exactly to the eventual column types — **and** make sure every branch of the policy body returns an expression assignable to the declared return type (e.g., a `NUMBER` policy can't return `'***MASKED***'`; a `DATE` policy can't return `SHA2(val, 256)`). The Q3 cheat-sheet above filters this for you; if the user typed "Other (free text)", re-validate the expression's type before emitting the `CREATE`.

Show the SQL in a single fenced block in your prose reply.

- **If the same user message that supplied the details also pre-approved running it** (e.g. "show me the SQL but you have approval to run it once shown", "…and then run it"): show the `CREATE` and **execute it in the same turn** — do not re-ask. Re-asking here is the most common way this flow runs out of turns before the policy is attached.
- **Otherwise**, ask for pre-write approval **via the interactive question tool**:
  > **prompt:** Run this `CREATE` statement now? (I will not apply the policy to any table in this step.)
  > **options:** Yes, run it, Edit the SQL, Cancel
  >
  > Wait for the user's choice. On `Yes, run it`, execute the single `CREATE` statement. On `Edit the SQL`, accept the user's revised SQL (free-text follow-up via the interactive tool) and re-confirm. On `Cancel`, stop.

If the create fails, surface the error to the user (in prose) and re-ask via the interactive tool whether to adjust and retry (`Yes, retry with edits` / `Cancel`). Do **not** silently retry.

## Step 1.6 — After CREATE succeeds, hand off to Stage 2 (ask explicitly)

Confirm success in one short prose line (e.g. *"Policy `<db>.<schema>.<policy_name>` created."*), then ask the Stage-2 routing question **via the interactive question tool**:

> **prompt:** Would you like to apply this policy to a table/column now?
> **options:** Yes, apply now, No, I'll do it later

- If **No, I'll do it later**: stop. Do not proactively apply, do not start a discovery query, do not list candidate tables.
- If **Yes, apply now**: continue to Stage 2.

---

# STAGE 2 — Apply the policy (only on explicit user request)

## Step 2.1 — Ask the attachment style, then the target

### Step 2.1a — Direct vs. tag-based (masking, tokenization only)

Tag-based attach is supported for **masking** and **tokenization** only. For **row access**, **projection**, **aggregation**, and **join**, go straight to Step 2.1b — do not mention tag-based as an option. If a user explicitly asks for tag-based attach on one of those four, say so plainly in prose (*"Tag-based attach for &lt;kind&gt; isn't supported — let's do direct attach instead."*) and continue with Step 2.1b.

> **Skip-the-question rule.** If the user's Stage-2 message already implies a style, do **not** re-ask:
> - Mentioned a specific column or table as the target (e.g., "apply to `<table>.<column>`", "attach to `<table>`") → **direct attach** → go to Step 2.1b. You already have the target.
> - Mentioned a tag, said "via tag", "tag-based", "use a tag", or referenced setting/creating a tag → **tag-based attach** → go to Step 2.1c.
> - Said only "yes" / "apply it" with no target or tag → ask the question below via the interactive tool.

Otherwise, ask via the interactive question tool:

> **prompt:** How should the policy be attached?
> **options:** Direct attach — bind to a specific column or table (best for one-off, explicit attachments), Tag-based attach — bind to a tag, then assign the tag to a database / schema / table / column (best when many objects share the same classification; the policy auto-applies wherever the tag is set)

For both masking and tokenization, the tag can be set at column, table, schema, or database level.

### Step 2.1b — Direct attach: ask for the target (using DB/Schema selectors)

Guide the user to the target using discovery-backed selectors — do **not** ask them to type a raw FQN.

**Step 2.1b-i — Select the database:**

Discover available databases silently (read-only):
```sql
SHOW DATABASES;
```

Ask via the interactive question tool, single-choice:
> **prompt:** Which database contains the target object?
> **options (single-choice):** *(populated from `SHOW DATABASES`, using the `name` column, sorted alphabetically)*, *Other (free text)*

**Step 2.1b-ii — Select the schema:**

After the user picks a database, discover schemas in it:
```sql
SHOW SCHEMAS IN DATABASE <selected_database>;
```

Ask via the interactive question tool, single-choice:
> **prompt:** Which schema?
> **options (single-choice):** *(populated from `SHOW SCHEMAS`, using the `name` column, sorted alphabetically; exclude `INFORMATION_SCHEMA`)*, *Other (free text)*

**Step 2.1b-iii — Select the table or view:**

After the user picks a schema, discover tables and views in it:
```sql
SHOW TABLES IN SCHEMA <database>.<schema>;
SHOW VIEWS IN SCHEMA <database>.<schema>;
```

Ask via the interactive question tool, single-choice (combine tables and views into one sorted list, indicating type):
> **prompt:** Which table or view should the policy apply to?
> **options (single-choice):** *(populated from discovery — e.g., `CUSTOMERS (TABLE)`, `CUSTOMER_VIEW (VIEW)`)*, *Other (free text — type an object name not in the list)*

**Step 2.1b-iv — Select the column (column-level policies only):**

For policy types that attach at the **column** level (masking, projection, tokenization), discover columns:
```sql
DESCRIBE TABLE <database>.<schema>.<table>;
```

Ask via the interactive question tool, single-choice:
> **prompt:** Which column should the policy be applied to?
> **options (single-choice):** *(populated from `DESCRIBE TABLE` — show column name and data type, e.g., `EMAIL (STRING)`, `SSN (STRING)`)*, *Other (free text)*

For policy types that attach at the **table** level (row access, aggregation, join), skip Step 2.1b-iv entirely.

For multi-argument masking or tokenization policies, follow up via the interactive tool with a multi-select question (using column discovery from the same `DESCRIBE TABLE` result) for which additional columns map to the extra arguments (these become the `USING (...)` clause).

### Step 2.1c — Tag-based attach: ask for the tag and where to set it

Tag-based attach has three pieces — ask each via the interactive question tool, in order. Don't merge them into a single prose paragraph.

1. **Tag fully-qualified name.**
   > **prompt:** Tag fully-qualified name (`<db>.<schema>.<tag_name>`). If the tag already exists, I'll reuse it; if not, I'll add a `CREATE TAG` statement to the SQL block.
   > *(free-text answer)*

2. **Tag string value to set on the target.**
   > **prompt:** What tag string value should be set on the target? A short classification label (e.g., `PII`, `HR_DATA`, `CONFIDENTIAL`); up to 256 chars. The value is stored on the target; the policy body only reads it if it calls `SYSTEM$GET_TAG_ON_CURRENT_COLUMN(...)` or `SYSTEM$GET_TAG(...)`.
   > *(free-text answer)*

3. **Where to set the tag.**
   > **prompt:** At what level should the tag be set? Pick the level that fits how broadly you want the policy to apply.
   > **options:** Column — `<db>.<schema>.<table>.<column>` (one specific column), Table — `<db>.<schema>.<table>` (all matching columns in the table), Schema — `<db>.<schema>` (all matching columns in tables/views in the schema, including new ones), Database — `<db>` (everything in the database — broadest)
   > *(after picking, follow up via the interactive tool with a free-text question for the fully-qualified target name at the chosen level)*

Validate the user's level pick (masking and tokenization both accept column / table / schema / database). In particular:
- **Schema/database level + a multi-arg masking or tokenization policy** → warn in prose that the `USING (...)` binding only works on direct attach; tag-based attach binds extra args by *column name match* (the table must have columns named like the policy's extra args, with matching data types). Then confirm via the interactive tool: `prompt: "Proceed anyway with tag-based attach at <level>?"`, `options: "Yes, proceed", "Switch to direct attach instead", "Cancel"`.
- Tag value is a free-form string. Don't validate its content; just preserve what the user typed (single-quoted in the SQL).

## Step 2.2 — Discover what's already there (read-only, no approval needed)

Run these to surface conflicts and existing references:

```sql
-- What policies already attach to this table (direct or via tag)?
SELECT
  REF_ENTITY_DOMAIN AS OBJECT_TYPE,
  REF_COLUMN_NAME AS COLUMN_NAME,
  POLICY_NAME,
  POLICY_KIND,
  TAG_DATABASE, TAG_SCHEMA, TAG_NAME   -- non-null if attached via tag
FROM TABLE(<db>.INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME => '<db>.<schema>.<table>',
  REF_ENTITY_DOMAIN => 'TABLE'
));

-- Confirm the new policy exists and inspect its signature
SELECT GET_DDL('POLICY', '<db>.<schema>.<policy_name>');
```

For **tag-based attach** also run these two queries:

```sql
-- Does the tag exist, and what policies are already on it?
SHOW TAGS LIKE '<tag_name>' IN SCHEMA <db>.<schema>;

SELECT POLICY_NAME, POLICY_KIND
FROM TABLE(<db>.INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME => '<db>.<schema>.<tag_name>',
  REF_ENTITY_DOMAIN => 'TAG'
));

-- What tags are already set on the target object?
SELECT TAG_NAME, TAG_VALUE, LEVEL
FROM TABLE(<db>.INFORMATION_SCHEMA.TAG_REFERENCES(
  '<db>.<schema>.<table>',  -- or the schema / database / table.column FQN
  'TABLE'                   -- match: TABLE / SCHEMA / DATABASE / COLUMN
));
```

Flag any conflict before generating the `ALTER`:

**Direct attach:**
- Column already has a masking policy → must `UNSET` first or pick another column.
- Aggregation policy: at most one row-level attach per table; multiple entity-level attaches allowed (one per distinct `ENTITY KEY`).
- Join policy: at most one per table.

**Tag-based attach (additional checks):**
- Tag already has a policy of the same kind **and same data type** → must `UNSET` it first, or use the `FORCE` keyword on `ALTER TAG SET ...` to replace atomically.
- Target already has a directly-attached policy of the same kind → direct attach takes precedence over the tag-based one (the tag-based attach will be a no-op until the direct one is removed). Surface this to the user.
- Target already has the tag set with a different value → `ALTER ... SET TAG` will overwrite the value silently. Confirm this is intended.

If discovery reveals a conflict, surface it to the user and ask how to proceed before generating any write SQL. Do not auto-resolve.

## Step 2.3 — Generate the ALTER statement and confirm

### Direct attach SQL

| Policy type | Attach SQL |
|-------------|-----------|
| Masking | `ALTER TABLE <table> MODIFY COLUMN <col> SET MASKING POLICY <db>.<schema>.<policy_name> [USING (<col1>, <col2>)];` |
| Row access | `ALTER TABLE <table> ADD ROW ACCESS POLICY <db>.<schema>.<policy_name> ON (<filter_col>);` |
| Projection | `ALTER TABLE <table> MODIFY COLUMN <col> SET PROJECTION POLICY <db>.<schema>.<policy_name>;` |
| Aggregation (row-level) | `ALTER TABLE <table> ADD AGGREGATION POLICY <db>.<schema>.<policy_name>;` |
| Aggregation (entity-level) | `ALTER TABLE <table> ADD AGGREGATION POLICY <db>.<schema>.<policy_name> ENTITY KEY (<entity_col>);` |
| Join | `ALTER TABLE <table> SET JOIN POLICY <db>.<schema>.<policy_name>;` (or `ALTER VIEW`) |
| Tokenization (standard) | `ALTER TABLE <table> MODIFY COLUMN <col> SET TOKENIZATION POLICY <db>.<schema>.<policy_name> [USING (<col1>, <col2>)];` |
| Tokenization (Iceberg) | `ALTER ICEBERG TABLE <table> MODIFY COLUMN <col> SET TOKENIZATION POLICY <db>.<schema>.<policy_name> [USING (...)];` |

For aggregation policies on a table with an entity column, ask one extra Stage-2 question **via the interactive question tool**:

> **prompt:** Should the minimum group size count rows or distinct entities?
> **options:** Rows — `ADD AGGREGATION POLICY <name>;`, Entities — `ADD AGGREGATION POLICY <name> ENTITY KEY (<column>);`
> *(if "Entities" is chosen, follow up via the interactive tool with a free-text question for the entity-key column name)*

### Tag-based attach SQL

Always emit the three statements together as a single SQL block (the user only approves once):

```sql
-- (a) Create the tag if discovery (Step 2.2) showed it does not exist.
--     Skip this line if the tag already exists.
CREATE TAG IF NOT EXISTS <db>.<schema>.<tag_name>;

-- (b) Bind the policy to the tag. Use FORCE only if Step 2.2 found a same-kind,
--     same-data-type policy already on the tag and the user confirmed replace.
ALTER TAG <db>.<schema>.<tag_name>
  SET <POLICY_KIND> POLICY <db>.<schema>.<policy_name>;

-- (c) Set the tag on the target at the chosen level. Use exactly one of:
ALTER TABLE    <db>.<schema>.<table> MODIFY COLUMN <col>
                                     SET TAG <db>.<schema>.<tag_name> = '<tag_value>';
ALTER TABLE    <db>.<schema>.<table> SET TAG <db>.<schema>.<tag_name> = '<tag_value>';
ALTER SCHEMA   <db>.<schema>         SET TAG <db>.<schema>.<tag_name> = '<tag_value>';
ALTER DATABASE <db>                  SET TAG <db>.<schema>.<tag_name> = '<tag_value>';
```

Substitute `<POLICY_KIND>` with `MASKING` or `TOKENIZATION`. The keyword in `ALTER TAG SET <POLICY_KIND> POLICY` is the policy kind, NOT the policy name. **Do not generate `ALTER TAG ... SET ROW ACCESS / PROJECTION / AGGREGATION / JOIN POLICY`** — those kinds are direct-attach only; redirect to Step 2.1b instead.

For Iceberg tables, use `ALTER ICEBERG TABLE` instead of `ALTER TABLE` in statement (c) when setting the tag at table or column level (e.g., `ALTER ICEBERG TABLE <t> SET TAG <tag> = '<v>'` and `ALTER ICEBERG TABLE <t> MODIFY COLUMN <c> SET TAG <tag> = '<v>'`). Schema-level and database-level `SET TAG` syntax does not change.

If discovery showed an existing same-kind/same-data-type policy on the tag, append `FORCE` to statement (b): `ALTER TAG <tag> SET <KIND> POLICY <new> FORCE`. This replaces the bound policy atomically (avoids the "unprotected for a moment between UNSET + SET" gap). Only use `FORCE` after the user explicitly confirms replace via the interactive tool: `prompt: "An existing <kind> policy is already bound to tag <tag_name> at the same data type. Replace it atomically (FORCE)?"`, `options: "Yes, replace with FORCE", "Cancel and choose a different tag"`.

Show the full SQL block in your prose reply.

- **If the user's current message already approved running it** (e.g. "yes, apply it now … show the ALTER and run it", "same approval — run it"): show the `ALTER` block and **execute it in the same turn** — do not re-ask. This is the Stage-2 turn; re-asking here typically leaves the policy created but never attached.
- **Otherwise**, ask for pre-write approval **via the interactive question tool**:
  > **prompt:** Run this `ALTER` block now? (For tag-based attach the three statements are approved together but executed in order; on any failure I will stop and report the error.)
  > **options:** Yes, run it, Edit the SQL, Cancel

Execute the statements **in order** on `Yes, run it` (or immediately, when the user pre-approved as above). On `Edit the SQL`, accept the user's revised SQL via a free-text follow-up on the interactive tool and re-confirm. On `Cancel`, stop. If statement (a) or (b) fails, stop and surface the error in prose — do not run (c) against an unbound tag, and **do not silently fall back to direct attach** (the user picked tag-based deliberately for inheritance; switching attach styles changes the semantics, not just the syntax). If the user explicitly asks to switch to direct attach after seeing the error (via free-text on the interactive tool), that's fine.

## Step 2.4 — Verify

After the ALTER succeeds:

```sql
-- Works for both direct and tag-based attach.
-- For tag-based, TAG_DATABASE/TAG_SCHEMA/TAG_NAME will be populated.
SELECT REF_ENTITY_DOMAIN AS OBJECT_TYPE, REF_COLUMN_NAME, POLICY_NAME, POLICY_KIND, TAG_DATABASE, TAG_SCHEMA, TAG_NAME
FROM TABLE(<db>.INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME => '<db>.<schema>.<table>',
  REF_ENTITY_DOMAIN => 'TABLE'
))
WHERE POLICY_NAME = '<policy_name>';
```

Confirm to the user with a one-line summary:
- Direct: *"Applied. `<policy_name>` is now active on `<table>.<column>`."*
- Tag-based: *"Applied. Tag `<tag_name>` now carries `<policy_name>` and is set on `<level>: <object>` with value `'<tag_value>'`. Coverage will extend to any matching column added later."*

After confirming, ask via the interactive question tool whether more targets are needed:

> **prompt:** Apply this policy to another target?
> **options:** Yes, attach to another target, No, we're done

If **Yes**, return to **Step 2.1** for the next target. Do not return to Stage 1 — the policy already exists. (For tag-based, applying the same policy to additional objects usually just means setting the same tag on more objects — i.e., extra `ALTER ... SET TAG` statements; you don't need to redo the `ALTER TAG SET <KIND> POLICY` step.) If **No**, stop.

---

## Stopping points

Every stopping point below is a question turn — the actual ask goes through the interactive question tool (see the "Interactive Question Tool" section above). Your prose for these turns should be brief framing only.

- ✋ After Step 1.2 (fully qualified name) + Step 1.3 (location and uniqueness validation): fully-qualified name is parsed and uniqueness confirmed.
- ✋ Before the `CREATE` statement (Step 1.5): pre-write approval (interactive tool, options `Yes, run it` / `Edit the SQL` / `Cancel`).
- ✋ Step 1.6: explicit yes/no (interactive tool, options `Yes, apply now` / `No, I'll do it later`) on whether to enter Stage 2. **Applies to all six policy types** — the Stage-1→Stage-2 handoff is universal; do not auto-advance even for types that skip the Step 2.1a question.
- ✋ Step 2.1a: **(masking and tokenization only.)** Explicit user choice (interactive tool, options `Direct attach` / `Tag-based attach`). For row access, projection, aggregation, and join, this stop does not apply — Step 2.1a is skipped and the workflow goes directly to Step 2.1b (direct attach) once the user has said yes at Step 1.6. Do not infer the attach style.
- ✋ Step 2.2: surface any policy conflicts in prose before writing (including tag-already-bound and target-tag-collision conflicts for tag-based). Use the interactive tool to confirm the resolution choice when there's more than one path forward.
- ✋ Before the `ALTER` statement(s) (Step 2.3): pre-write approval (interactive tool, options `Yes, run it` / `Edit the SQL` / `Cancel`). For tag-based, the three statements are approved together but executed in order; stop on any failure.

## What this workflow does NOT do

- It checks for name collisions in Step 1.3 (after the user provides the fully qualified name) and prompts the user to pick a different name if one already exists in the chosen location. It does **not** silently overwrite with `CREATE OR REPLACE`.
- It does not apply the split pattern proactively. If the user wants a memoizable unmask function, they will say so in their answers; otherwise the policy body is generated as-is.
- It does not proactively scan for similar tables or recommend a broader scale path beyond the attachment style the user picked. That is the conversational create workflow's job. (Tag-based attach itself **is** offered as a Stage-2 option here — see Step 2.1a — but only as a choice the user makes, not as an inferred recommendation.)
- It does not call into the policy audit workflow.

If the user pivots mid-flow to a non-UI request (e.g., "actually, audit my existing policies first"), exit this workflow and load the appropriate other file.
