# Guided Workflow: Create Data Policy from Classification Categories (UI Slash-Command Flow)

> ## You are now in the category-seeded data-policy create flow. Different rules apply.
>
> This workflow is loaded only when the user's first message matches the slash command:
>
> ```
> /data-governance Create a data policy for categories <CAT1>, <CAT2>, ... [source=classification-wizard]
> ```
>
> issued by the Snowsight classification wizard's "Create with CoCo" button. The window is seeded
> with the detected classification categories. **Do not** ask "what data
> are you protecting?" — you already know the categories. The command is
> policy-type-agnostic: this workflow asks the user which data policy type to create. **Masking and
> projection are offered today** (aggregation, row access, and tokenization may be added later).
>
> **Trigger guard (verify before proceeding).** This workflow should only run when the first
> message (case-insensitive) **starts with** `/data-governance Create a data policy for
> categories` **and** contains the sentinel token **`[source=classification-wizard]`**. If the
> sentinel is absent, you were likely mis-routed — stop and hand control back to the normal
> `data-policy.md` routing (treat it as an ordinary "create a policy" request). Do not
> proceed on the prefix alone.
>
> **Hard-guarantee note.** Skills are prompt-routed, not access-controlled: this guard is a
> practical safeguard, not an enforced boundary. The real guarantee that this flow is reachable
> only from "Create with CoCo" is enforced at the UI/agent-config layer — the classification
> wizard is the only surface that emits this command (with the sentinel), into the scoped CoCo
> window it opens.
>
> If you got here for any other reason (a normal conversational request, or the generic
> `/data-governance Create a new <policy type> policy for me` slash command), close this file and
> load the appropriate other workflow.

## Hard rules for this workflow (read before doing anything else)

0. **Masking and projection only (for now).** This workflow creates a **masking** or a
   **projection** policy today. At Step 0.5 those are the two selectable options; if the user asks
   for aggregation, row access, or tokenization, tell them it is not available from this flow yet
   and offer masking or projection.
1. **Create the policy object only.** Do **NOT** bind the policy to the tag
   (`ALTER TAG ... SET MASKING/PROJECTION POLICY`), do **NOT** apply it to any column
   (`ALTER TABLE ... SET MASKING/PROJECTION POLICY`), and do **NOT** offer to apply it. The
   classification wizard performs the tag binding at its Finish step; that is outside this flow's
   scope.
2. **No Stage 2 / no apply-now prompt.** After the `CREATE` succeeds, confirm the fully-qualified
   name(s) and stop. Never ask "Would you like to apply this policy now?".
3. **Use live metadata only.** All reads use live paths (`SHOW`, `DESCRIBE`,
   `INFORMATION_SCHEMA.*`). Never read `SNOWFLAKE.ACCOUNT_USAGE.*` — a policy created here must be
   selectable by the wizard immediately, and `ACCOUNT_USAGE` lags up to ~2h.
4. **Masking: one policy per data type maps onto the tag's type slot.** A tag holds at most one
   masking policy per data type, so each generated **masking** policy targets exactly one data type
   so the wizard can bind it to that type's slot. **Projection** has no data-type dimension
   (`AS ()`), so a single projection policy covers all the selected categories' columns — this rule
   does not apply to projection.
5. **One policy per session by default.** If the selected categories span multiple data types,
   default to creating a single policy for one data type and advise the user to run "Create with
   CoCo" again for the other type(s). Create multiple policies in one session **only if the user
   explicitly asks**; if you do, return every fully-qualified name clearly.
6. **Pre-write approval still applies** — show the exact `CREATE` SQL, wait for the user's "yes",
   then execute. Read-only queries (`SHOW`, `DESCRIBE`, `SELECT`, `GET_DDL`) run without approval.
7. **Ask user-facing questions via the interactive question tool, not in prose.** Keep prose to at
   most one short framing line per turn. Never emit "next steps" / "you might also ask" lists.

---

## Interactive Question Tool

Whenever this workflow tells you to ask the user something, invoke the **interactive question
tool** the data-governance UI surface provides (single-choice, multi-select, or short free-text).
Treat each step's blockquote as the spec of the tool call, not as prose to repeat back. If the
interactive tool is not available (CLI, eval harness), ask the same question in prose in the same
turn, keeping the prompt text identical.

For role lists, discover candidates with a one-shot read-only `SHOW ROLES;` and present a
multi-select with an *Other (free text)* escape; fall back to free-text if discovery returns zero
rows or errors.

---

## STAGE 1 — Create the policy (no application)

### Step 0 — Parse and normalize the seed

Parse the slash command:
- **Categories** — the comma-separated list after `for categories` (and before the sentinel, if
  present).
- **Sentinel** — ignore the `[source=classification-wizard]` token when parsing; it is a routing
  marker, not part of the category list. (Its presence was already required to reach this
  workflow — see the Trigger guard above.)

Normalize each category to its **parent** semantic category using the alias table in the
**category masking-strategy catalog** (`../reference/data-policy/category-masking-templates.md`).
Keep the original name if it is not in the alias table. Echo the normalized categories back
in one short line, e.g. *"Protecting AGE, CITY, COUNTRY."*

If no categories were supplied, ask for them via the interactive tool (free-text, comma-separated).

### Step 0.5 — Ask which data policy type to create

The slash command is policy-type-agnostic, so confirm the type before going further. **Masking and
projection are the two types available from this flow today.**

> **prompt:** Which type of data policy do you want to create for these categories?
> **options (single-choice):**
> - Masking — transform the column value at read time so unauthorized roles see a masked value
> - Projection — control whether the column can appear in the outermost SELECT (visible vs blocked/nullified) by role

- Present **Masking** and **Projection** only. Do not offer aggregation, row access, or
  tokenization — they are not supported by this flow yet.
- If the user asks for one of those anyway, say plainly that this flow currently creates masking or
  projection policies only (the others are planned), and offer those two. Do not attempt to create
  an unsupported policy type here.
- **Fork on the choice:**
  - **Masking** → continue with Step 1 below (the masking path: Steps 1 → 6).
  - **Projection** → skip the masking-only Steps 1–3/5.5 and follow the **Projection path** section
    (Steps P1 → P6) instead. It reuses the shared guided selectors, approval, and hand-back.

> **Masking path (policy type = Masking).** Steps 1 → 6 below are the masking branch. If the user
> chose Projection at Step 0.5, ignore these and use the **Projection path** section instead.

### Step 1 — Group by expected type and advise

Look up each parent category in the catalog and group by **expected data type**. Surface the
grouping to the user in one short line. If the categories span more than one expected type
(e.g. `AGE` is typically NUMBER while `CITY`/`COUNTRY` are STRING), warn that a tag holds one
masking policy per data type, so they may want a separate policy per type, and note the actual
column types are confirmed by the wizard at bind time.

> Do **not** run `SELECT SYSTEM$GET_TAG_ON_CURRENT_COLUMN(...)` to inspect types — that function is
> valid only inside a policy body. If you want to see what a specific column already carries, use a
> live `INFORMATION_SCHEMA.TAG_REFERENCES` read; this is optional and not required for the flow.

### Step 2 — Ask the policy shape

> **prompt:** How should the masking policy treat the different categories?
> **options (single-choice):**
> - Category-aware — one policy per data type whose body applies each category's own strategy (e.g. CITY/COUNTRY full-redact, EMAIL partial, identifiers show-last-4), branching on the column's semantic category
> - Uniform — one policy per data type that applies a single generic redaction to every category the tag covers

- **Category-aware branching:** the policy body reads
  `SYSTEM$GET_TAG_ON_CURRENT_COLUMN('SNOWFLAKE.CORE.SEMANTIC_CATEGORY')` and branches with `WHEN`
  arms matching **parent** category names (add a known subcategory alias as an extra arm only when
  warranted). Each arm returns the catalog strategy for that category; the final `ELSE` is the
  fail-closed masked value. This relies on the wizard having auto-applied the `SEMANTIC_CATEGORY`
  system tag to columns — if auto-tagging is off, the body falls through to the default masked
  branch. State that dependency in one short line.
- **Uniform:** a single `CASE WHEN <authorized> THEN val ELSE <generic_masked_value> END` per data
  type.

If the categories span multiple data types, also confirm which data type this policy targets
(default to the type of the majority of categories; see Hard Rule 5 about one policy per session).

### Step 3 — Ask the authorized roles (sensible default)

Default to a fail-closed authorization: only a privileged governance role sees cleartext. Propose a
sensible default (e.g. `ACCOUNTADMIN`) and let the user adjust.

> **prompt:** Which role(s) should see the original (unmasked) value? Everyone else is masked. The policy uses `IS_ROLE_IN_SESSION` so inherited and secondary roles are respected.
> **options (multi-select):** *(populated from `SHOW ROLES`)*, *Other (free text)*
> *(default selection: ACCOUNTADMIN; an empty selection is not allowed — keep at least the default)*

### Step 4 — Ask where to store the policy and its name (guided selectors)

Use the same guided sequence as the standard UI create flow — database, then schema, then bare
name — so the experience is consistent.

**Step 4a — database:**
```sql
SHOW DATABASES;
```
> **prompt:** Which database should the policy be stored in?
> **options (single-choice):** *(from `SHOW DATABASES`, `name` column, sorted)*, *Other (free text)*

**Step 4b — schema:**
```sql
SHOW SCHEMAS IN DATABASE <selected_database>;
```
> **prompt:** Which schema in `<selected_database>`?
> **options (single-choice):** *(from `SHOW SCHEMAS`, `name` column, sorted; exclude `INFORMATION_SCHEMA`)*, *Other (free text)*

**Step 4c — name:**
> **prompt:** What should we name the policy?
> *(free-text answer — the bare policy name only, e.g. `MASK_ADDRESS_STRING`)*

**Uniqueness check** (live):
```sql
SHOW MASKING POLICIES IN SCHEMA <database>.<schema>;
```
If a masking policy with the same name already exists in that location, surface it in one short
line and re-ask for a different name. Do **not** silently overwrite with `CREATE OR REPLACE`.

### Step 5 — Generate the CREATE statement

Build one `CREATE MASKING POLICY` per targeted data type. Requirements:
- Argument and return type match the target data type; every branch returns an expression
  assignable to the return type (use the catalog's type-appropriate expressions).
- Use `IS_ROLE_IN_SESSION('<role>')` for the authorized check (never `CURRENT_ROLE()`).
- Explicit `ELSE` fail-closed branch.
- `COMMENT` recording purpose, the categories covered, and a provenance note that the policy was
  created via the classification wizard.

**Category-aware example (STRING):**
```sql
CREATE MASKING POLICY <db>.<schema>.<name> AS (val STRING) RETURNS STRING ->
  CASE
    WHEN IS_ROLE_IN_SESSION('ACCOUNTADMIN') THEN val
    WHEN SYSTEM$GET_TAG_ON_CURRENT_COLUMN('SNOWFLAKE.CORE.SEMANTIC_CATEGORY') IN ('CITY', 'COUNTRY', 'STREET_ADDRESS')
      THEN '***MASKED***'
    ELSE '***MASKED***'
  END
COMMENT = 'Category-aware masking for CITY, COUNTRY. Created via classification wizard. Owner: <team>.';
```

> Only add `WHEN` arms for categories actually in scope, and only list those categories in the
> `COMMENT`. Use each category's catalog strategy — e.g. a partial-mask arm
> (`CONCAT(LEFT(val,2), '***@', SPLIT_PART(val,'@',2))`) for `EMAIL`, or a show-last-4 arm for
> identifiers — **only when that category is part of the seeded set**. Do not emit arms for
> categories the user did not bring.

**Uniform example (STRING):**
```sql
CREATE MASKING POLICY <db>.<schema>.<name> AS (val STRING) RETURNS STRING ->
  CASE
    WHEN IS_ROLE_IN_SESSION('ACCOUNTADMIN') THEN val
    ELSE '***MASKED***'
  END
COMMENT = 'Uniform masking for CITY, COUNTRY. Created via classification wizard. Owner: <team>.';
```

### Step 5.5 — Preview the effect (read-only, before approval)

Before asking for approval, show the user **what the policy will do to sample data**. Build the
preview from the built-in sample values in the catalog's *Representative sample values* section and
run it as **one read-only `SELECT`** (`UNION ALL` across the in-scope categories). Do **not** run
`SYSTEM$GET_TAG_ON_CURRENT_COLUMN(...)` in the preview — evaluate each category's masked
**expression** on its sample value directly (see the catalog's "How to build the preview query").

Present a compact before/after table, including the authorized-role case (value returned
unchanged):

```
Category   Viewer            Sample value      Result
CITY       authorized role   New York          New York
CITY       everyone else     New York          ***MASKED***
COUNTRY    everyone else     Canada            ***MASKED***
EMAIL      everyone else     alice@corp.com    al***@corp.com
```

Add one short caveat line: the preview evaluates each category's masked expression on a sample; it
does not execute the full policy (the role check and the `SEMANTIC_CATEGORY` branch are not run
here), so it illustrates per-category output, not live policy evaluation.

**For a hand-edited body (the user chose "Edit the SQL"), preview best-effort:** evaluate whatever
masked branches are pure expressions of `val` on the samples, and clearly flag any branch that
can't be evaluated statically — e.g. one that references other columns, a mapping-table subquery,
`IS_ROLE_IN_SESSION`, or an external/non-deterministic function ("this branch can't be previewed
without attaching the policy"). Never attach the policy just to preview it.

### Step 5.6 — Show the SQL and get pre-write approval

Show the `CREATE` SQL in a single fenced block (after the preview), then ask for pre-write approval
via the interactive tool:

> **prompt:** Run this `CREATE` statement now? (I will not attach the policy to the tag or any column — the classification wizard does that when you finish it.)
> **options:** Yes, run it, Edit the SQL, Cancel

On `Yes, run it`, execute the `CREATE`. On `Edit the SQL`, accept the revised SQL, **re-run the
preview (Step 5.5, best-effort) on the edited body**, then re-confirm. On `Cancel`, stop. If the
create fails, surface the error and re-ask whether to adjust and retry.

### Step 6 — Verify and hand back

After the create succeeds, verify with:
```sql
SELECT GET_DDL('POLICY', '<db>.<schema>.<name>');
```

Then give a **clear, unmistakable success message with an explicit next action**. Make three things
obvious: (1) the policy was created, (2) its fully-qualified name, and (3) that the user should go
**back to the classification setup screen** to attach it to their tag. Use a format like:

> ✅ **Masking policy created:** `<db>.<schema>.<name>` (STRING).
>
> **Next step —** return to the **classification setup screen** and select this policy for your
> tag. The wizard attaches it when you finish; nothing is attached from here.

If the user asked for multiple policies (one per data type), lead with the same success line and
then list **every** fully-qualified name so they can select each in the wizard.

**Stop here.** Do not attach, do not apply, do not prompt to apply — the only call to action is
"go back to the classification screen and attach it there."

---

## Projection path (policy type = Projection)

Entered only when the user chose **Projection** at Step 0.5. A projection policy controls whether a
column may appear in the outermost `SELECT` — it is a **role-based allow/deny** decision, not a
value transform. So there is **no data-type grouping and no per-category masked expression**: a
single projection policy (`AS () RETURNS PROJECTION_CONSTRAINT`) covers all the selected categories'
columns regardless of type. Skip Steps 1–3 and 5.5; follow P1 → P6 here.

### Step P1 — Who may project (see) these columns?

**Ask multi-select per the role-list pattern** (`SHOW ROLES`). Default to `ACCOUNTADMIN`. An empty
selection means *no one* may project the columns (unconditional clean-room block). Uses
`IS_ROLE_IN_SESSION` so inherited/secondary roles are respected.

> **prompt:** Which role(s) should be allowed to project (include in the outermost SELECT) these columns? Everyone else is blocked. Pick zero or more; an empty selection means no one may project them.
> **options (multi-select):** *(populated from `SHOW ROLES`)*, *Other (free text)*

### Step P2 — Enforcement when projection is denied

> **prompt:** When a blocked role selects the column, what should happen?
> **options (single-choice):** `FAIL` (default) — the query errors if the column is in the outermost SELECT, `NULLIFY` — the query succeeds and the column returns `NULL`

> ⚠️ `ENFORCEMENT => 'NULLIFY'` must be a **single-quoted** string inside the deny-branch
> `PROJECTION_CONSTRAINT`. Unquoted `NULLIFY` is a parse error; omitting `ENFORCEMENT` defaults to
> `FAIL`.

### Step P3 — Where to store the policy and its name

Use the **same guided selectors as Step 4** — database (`SHOW DATABASES`) → schema
(`SHOW SCHEMAS IN DATABASE`) → bare policy name. Uniqueness check (live) uses:
```sql
SHOW PROJECTION POLICIES IN SCHEMA <database>.<schema>;
```
If the name already exists, surface it and re-ask. Do not silently `CREATE OR REPLACE`.

### Step P4 — Generate the CREATE statement

Signature is `AS () RETURNS PROJECTION_CONSTRAINT` (no `val` argument). Include `ENFORCEMENT =>
'NULLIFY'` only when the user chose NULLIFY; omit it for the `FAIL` default. Use
`IS_ROLE_IN_SESSION` (never `CURRENT_ROLE`).

**Role-conditional (one or more allowed roles):**
```sql
CREATE PROJECTION POLICY <db>.<schema>.<name> AS () RETURNS PROJECTION_CONSTRAINT ->
  CASE
    WHEN IS_ROLE_IN_SESSION('ACCOUNTADMIN')
      THEN PROJECTION_CONSTRAINT(ALLOW => TRUE)
    ELSE PROJECTION_CONSTRAINT(ALLOW => FALSE, ENFORCEMENT => 'NULLIFY')
  END
COMMENT = 'Projection policy for CITY, COUNTRY. Created via classification wizard. Owner: <team>.';
```

**Unconditional block (empty role selection — no one may project):**
```sql
CREATE PROJECTION POLICY <db>.<schema>.<name> AS () RETURNS PROJECTION_CONSTRAINT ->
  PROJECTION_CONSTRAINT(ALLOW => FALSE, ENFORCEMENT => 'NULLIFY')
COMMENT = 'Projection policy (unconditional block) for CITY, COUNTRY. Created via classification wizard. Owner: <team>.';
```

(For `FAIL`, drop the `, ENFORCEMENT => 'NULLIFY'` — the deny branch becomes
`PROJECTION_CONSTRAINT(ALLOW => FALSE)`.)

### Step P5 — Preview the effect (conceptual, no SQL)

Projection has **no value transform**, so do **not** run a `SELECT` and do **not** attach the policy
to preview it. Before approval, show a conceptual outcome table:

| Viewer | Outcome |
|---|---|
| authorized role(s) | column appears normally in query results |
| everyone else | `FAIL`: the query errors if the column is in the outermost SELECT — `NULLIFY`: the column returns `NULL` |

Add one short line: this describes projection behavior; nothing is executed or attached.

### Step P6 — Show the SQL, approve, create, and hand back

Show the `CREATE` SQL in a single fenced block, then pre-write approval via the interactive tool
(same as Step 5.6):

> **prompt:** Run this `CREATE` statement now? (I will not attach the policy to the tag or any column — the classification wizard does that when you finish it.)
> **options:** Yes, run it, Edit the SQL, Cancel

On `Yes, run it`, execute the single `CREATE`; on `Edit the SQL`, accept the revision, re-show the
conceptual preview (P5) if the deny/allow behavior changed, and re-confirm; on `Cancel`, stop.
Verify with `SELECT GET_DDL('POLICY', '<db>.<schema>.<name>');`, then give the same clear
success + go-back hand-back as Step 6, worded for a projection policy:

> ✅ **Projection policy created:** `<db>.<schema>.<name>`.
>
> **Next step —** return to the **classification setup screen** and select this policy for your
> tag. The wizard attaches it when you finish; nothing is attached from here.

**Stop here.** Do not attach, apply, or prompt to apply.

---

## What this flow does NOT do

- It does **not** bind the policy to the tag (`ALTER TAG ... SET MASKING/PROJECTION POLICY`).
- It does **not** apply the policy to any column (`ALTER TABLE ... SET MASKING/PROJECTION POLICY`).
- It does **not** ask "apply this policy now?" — the classification wizard owns tag binding at its
  Finish step.
- It does **not** read `ACCOUNT_USAGE` — all reads are live.
- It does **not** run `SYSTEM$GET_TAG_ON_CURRENT_COLUMN(...)` in a standalone `SELECT`, and does
  **not** attach the policy to preview it — the masking effect preview is computed from masked
  expressions on sample values, and the projection preview is a conceptual outcome table (no SQL).
- It does **not** scan for similar tables or recommend a broader scale path.

If the user pivots mid-flow to a different request (e.g. "actually audit my existing policies"),
exit this workflow and load the appropriate other workflow.

## Stopping points

**Masking path:**
- ✋ Step 2: user picks the policy shape (interactive tool).
- ✋ Step 3: authorized roles confirmed.
- ✋ Step 4: location + unique name assembled.
- ✋ Step 5.5: effect preview shown (read-only) before approval is requested.
- ✋ Before the `CREATE` (Step 5.6): pre-write approval (`Yes, run it` / `Edit the SQL` / `Cancel`).
- ✋ Step 6: policy created and FQN(s) confirmed — then stop (no apply stage).

**Projection path:**
- ✋ Step P1: allowed roles confirmed.
- ✋ Step P2: enforcement (`FAIL` / `NULLIFY`) confirmed.
- ✋ Step P3: location + unique name assembled.
- ✋ Step P5: conceptual outcome preview shown before approval is requested.
- ✋ Before the `CREATE` (Step P6): pre-write approval (`Yes, run it` / `Edit the SQL` / `Cancel`).
- ✋ Step P6: policy created and FQN confirmed — then stop (no apply stage).
