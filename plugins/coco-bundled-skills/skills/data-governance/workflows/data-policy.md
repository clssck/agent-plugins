---
name: data-policy
parent_skill: data-governance
description: "**[REQUIRED]** for creating, modifying, or auditing Snowflake masking policies, row access policies, projection policies, aggregation policies, join policies, or tokenization policies. Also required for protecting sensitive columns (SSN, email, phone, TIMESTAMP), role-based column access control, checking existing policies before adding new ones, and following data policy best practices. This skill provides best practices and an audit checklist covering role-hierarchy correctness (CURRENT_ROLE vs IS_ROLE_IN_SESSION), the split pattern for reusing unmask logic, entity-level privacy for aggregation policies, and policy documentation. Triggers: masking policy, row access policy, projection policy, aggregation policy, join policy, tokenization policy, audit policies, policy best practices, create policy, data policy, protect sensitive data, protect column, column masking, TIMESTAMP masking, SSN masking, email masking, phone masking, existing policies, check existing policies, role-based access control, physicians access, compliance officers access, JOIN_REQUIRED, JOIN_CONSTRAINT, clean room joins, tokenize column, tokenization at write time, external tokenization, FPE, format-preserving encryption, /data-governance Create a new policy."
---

# Snowflake Data Policy Skill

> ## ⛔ NEVER EXPOSE INTERNAL FILE PATHS OR LAYER LABELS
>
> The filenames, paths, and layer labels referenced in this skill — `data-policy/...`, anything ending in `.md`, and the `L1` / `L2` / `L3` / `L4` shorthand — are **internal routing only**. They must NOT appear in any user-facing output: chat replies, error messages, pre-write summaries, status updates, framing prose for an interactive question, or pre-flight notes ("loading X…", "per X…", "the L4 workflow says…").
>
> When you need to refer to a workflow in a user-facing reply, use its **purpose**, not its filename:
> - the **UI 2-stage create workflow** (not `L4_workflow_create_2stage_ui.md`)
> - the **category-seeded data-policy create workflow** (not `L4_workflow_create_from_categories.md`)
> - the **UI 2-stage edit workflow** (not `L4_workflow_edit_2stage_ui.md`)
> - the **conversational create workflow** (not `L4_workflow_create.md`)
> - the **policy audit workflow** (not `L4_workflow_audit.md`)
> - the **proven patterns reference** (not `L2_proven_patterns.md`)
> - the **best-practices reference** (not `L3_best_practices.md`)
> - the **compliance reference** (not `compliance_reference.md`)
> - the **sensitive-data classification workflow** (not `sensitive-data-classification.md`)
>
> Routing decisions still use the actual paths — the Content Layers table below is the unambiguous source of truth for which file to load. Read it, load the file with your file-read tool, and then talk to the user using the descriptive name.
>
> If you catch yourself about to write a `.md` path, a `data-policy/...` segment, or an `L1`/`L2`/`L3`/`L4` label into a user reply, replace it with the descriptive name before sending.
>
> For UI slash-command flows, start directly with the product-facing acknowledgement and interactive question rather than the universal intake questions.
>
> For `/data-governance Create a new <policy type> policy for me`, the command already names the type. Do not ask which type to create. The first visible response should only acknowledge that type and ask for the fully qualified policy name.

> ## ⛔ STOP — Check the UI Slash-Command Triggers FIRST
>
> **Before reading any other section of this file**, examine the user's first message in this conversation. If it matches one of the data-governance UI slash commands below, hand control entirely to the matching workflow and follow it exclusively.
>
> **Check the category-seeded create flow FIRST (highest precedence).**
>
> ```
> /data-governance Create a data policy for categories <CAT1>, <CAT2>, ... [source=classification-wizard]
> ```
>
> Route to the **category-seeded data-policy create workflow** (see Content Layers row *CREATE (category-seeded UI flow)* below) **only if BOTH** of these hold for the first message (case-insensitive):
> 1. it **starts with** the exact prefix `/data-governance Create a data policy for categories`, and
> 2. it contains the UI sentinel token **`[source=classification-wizard]`**.
>
> Both conditions are required. This trigger is emitted only by the Snowsight classification wizard's "Create with CoCo" button; the sentinel token is what distinguishes it from anything a user might type conversationally. If either is missing, do **NOT** load the category-seeded workflow — fall through to the normal routing (a plain "create a policy" request without the sentinel is handled by the conversational or 2-stage create flows). When it matches, follow the category-seeded workflow exclusively; do not fall through to the generic create flow below even though this message also contains `Create` and `policy`. The workflow itself asks which policy type to create (masking or projection).
>
> **Create flow**
>
> ```
> /data-governance Create a new <policy type> policy for me
> ```
>
> where `<policy type>` is one of `masking`, `row access`, `projection`, `aggregation`, `join`, or `tokenization` → load the **UI 2-stage create workflow** (see Content Layers row *CREATE (UI 2-stage flow)* below for the load target).
>
> **Edit flow**
>
> ```
> /data-governance Edit the <POLICY_KIND> POLICY named <POLICY_NAME> located at <DB>.<SCHEMA>.
> ```
>
> where `<POLICY_KIND>` is one of `MASKING`, `ROW ACCESS`, `PROJECTION`, `AGGREGATION`, `JOIN`, or `TOKENIZATION` → load the **UI 2-stage edit workflow** (see Content Layers row *EDIT (UI 2-stage flow)* below for the load target).
>
> For either trigger, do **not**:
> - run the universal intake questions in Step 1 below
> - load the conversational create workflow
> - generate any state-changing SQL until Stage 2
>
> The UI workflows have specific 2-stage shapes that the data-governance UI component depends on.
>
> If the first message does **not** match either pattern, ignore this banner and continue with the normal workflow below.

## When to Use/Load
Use this skill when a user asks to create, modify, audit, or troubleshoot Snowflake data policies, or needs help choosing the right policy approach.

**Also use when:**
- Protecting a specific column (SSN, email, phone, TIMESTAMP, or any data type) with masking
- Checking existing policies before adding a new one ("same access rules", "existing masking")
- Controlling which roles can see column values
- Any request containing "protect sensitive data", "mask column", "column masking", "role-based access"

## Content Layers

Load **only** the file(s) matching the detected intent — do not load all layers upfront:

| Intent | Triggers | Load |
|--------|----------|------|
| PATTERNS | "example", "ABAC", "template", "show me how", "pattern" | `data-policy/L2_proven_patterns.md` |
| BEST_PRACTICES | "best practice", "should I", "anti-pattern", "governance", "memoizable" | `data-policy/L3_best_practices.md` |
| CREATE | "create policy", "new policy", "mask column", "restrict access", "extend policy", "protect", "same rules" | `data-policy/L4_workflow_create.md` |
| **CREATE (category-seeded UI flow)** | **First user message STARTS WITH `/data-governance Create a data policy for categories` AND contains the sentinel `[source=classification-wizard]`** (e.g. `/data-governance Create a data policy for categories AGE, CITY, COUNTRY [source=classification-wizard]`) | **`data-policy/L4_workflow_create_from_categories.md`** — and ONLY this file. Checked BEFORE the generic UI 2-stage create row below. Both the prefix and the sentinel are required; the workflow asks which policy type to create (masking or projection). See "UI Trigger Detection" below. |
| **CREATE (UI 2-stage flow)** | **First user message starts with `/data-governance Create a new <policy type> policy for me`** (any of: masking, row access, projection, aggregation, join, tokenization) | **`data-policy/L4_workflow_create_2stage_ui.md`** — and ONLY this file. See "UI Trigger Detection" below. |
| **EDIT (UI 2-stage flow)** | **First user message starts with `/data-governance Edit the <POLICY_KIND> POLICY named <POLICY_NAME> located at <DB>.<SCHEMA>.`** | **`data-policy/L4_workflow_edit_2stage_ui.md`** — and ONLY this file. See "UI Trigger Detection" below. |
| AUDIT | "audit policies", "review policies", "inventory", "health check", "scattered policies", "consolidate", "migrate" | `data-policy/L4_workflow_audit.md` |
| COMPLIANCE | "regulation", "HIPAA", "GDPR", "PCI", "CCPA", "SOX", "FERPA", "compliance", "healthcare", "financial", "privacy law" | `../reference/data-policy/compliance_reference.md` |
| SYNTAX / CONCEPTS | "how does X work", "what does X do", "what's the difference between X and Y", standalone keyword question (e.g., `ENTITY KEY`, `ALLOWED JOIN KEYS`, `USING (...)`, `JOIN_REQUIRED`) — no create/edit/audit verb | Answer concisely from the policy model and ground via Snowflake docs lookup (use `snowflake_product_docs` when available; else `cortex search docs "<query>"` via bash). Cite the relevant `docs.snowflake.com` URL so the user can drill deeper. Do **not** restate raw policy syntax inline in this skill — Snowflake docs are the source of truth and stay current automatically. If the question pivots to a create/edit/audit verb, route to the matching workflow row. |

## UI Trigger Detection (check BEFORE Step 0)

Before doing anything else — even Step 0 session-context check — examine the **first** user message in this conversation. If it matches one of the slash-command patterns below, hand control entirely to the matching workflow and follow it instead of the rest of this file.

**Category-seeded create pattern (check FIRST — highest precedence, case-insensitive):**
```
/data-governance Create a data policy for categories <CAT1>, <CAT2>, ... [source=classification-wizard]
```
where the list after `for categories` is one or more detected classification categories and `[source=classification-wizard]` is a fixed sentinel the wizard appends. The command is policy-type-agnostic on purpose — the workflow asks the user which data policy type to create (masking or projection today; aggregation, row access, and tokenization may be added later).

What "match" means (BOTH required): the first turn **starts with** the exact prefix `/data-governance Create a data policy for categories` **and** contains the sentinel token `[source=classification-wizard]`. The sentinel is emitted only by the Snowsight classification wizard's "Create with CoCo" button and is what prevents accidental triggering from conversational phrasing.

**If matched** → load the **category-seeded data-policy create workflow** (load target in the Content Layers table above) and follow it strictly. Do **NOT** fall through to the generic create pattern below, even though the message also contains `Create` and `policy`. Do not run the universal intake (Step 1). Do not load the conversational or UI 2-stage create workflows.

**If the prefix matches but the sentinel is absent** → do **NOT** load the category-seeded workflow. Treat it as an ordinary create request and route via the normal create flow (a real user typing something similar without the sentinel should get the standard experience).

> **Hard-guarantee note (UI/agent-config layer).** Skill files are prompt-routed, not access-controlled, so this detection is a *practical* guard, not an enforced boundary — a determined user could still type the full command including the sentinel. The actual guarantee that this flow is reachable only from "Create with CoCo" must be enforced where the command originates: the classification wizard is the only surface that emits this command (with the sentinel), into the scoped CoCo window it opens. Keep the sentinel string in sync with what the wizard emits.

**Create pattern (case-insensitive, allow trailing punctuation):**
```
/data-governance Create a new <policy type> policy for me
```
where `<policy type>` is one of `masking`, `row access`, `projection`, `aggregation`, `join`, `tokenization` (the word `policy` may be omitted in the type, e.g., "Create a new join policy").

What "match" means: the first turn starts with `/data-governance`, contains the verb `Create` and the noun `policy`, and identifies one of the six supported types.

**If matched** → load the **UI 2-stage create workflow** (load target in the Content Layers table above) and follow it strictly. Do not run the universal intake (Step 1). Do not load the conversational create workflow. Do not auto-apply best-practice suggestions mid-conversation.

**Edit pattern (case-insensitive, allow trailing punctuation):**
```
/data-governance Edit the <POLICY_KIND> POLICY named <POLICY_NAME> located at <DB>.<SCHEMA>.
```
where `<POLICY_KIND>` is one of `MASKING`, `ROW ACCESS`, `PROJECTION`, `AGGREGATION`, `JOIN`, `TOKENIZATION` (case-insensitive).

What "match" means: the first turn starts with `/data-governance`, contains the verb `Edit` and the noun `POLICY`, and pre-supplies a policy name and a `<DB>.<SCHEMA>` location.

**If matched** → load the **UI 2-stage edit workflow** (load target in the Content Layers table above) and follow it strictly. Do not load the conversational create workflow. The first content question must be *definition or attachment?* (the policy name is already known from the slash command — do not ask for it).

**If neither pattern matches** → continue with Step 0 below as usual. The conversational create workflow is the right choice for any phrasing that doesn't use a slash command.

> The UI workflows exist because the data-governance UI component sends these exact slash commands and expects specific 2-stage conversation shapes. For any other surface (CLI, ad-hoc questions), the standard workflow is the right answer.

## Pre-Write Approval Rule

**Before executing ANY state-changing SQL** (`CREATE`, `ALTER`, `DROP`, `APPLY`):

1. Summarize in plain language what will be created, modified, or dropped.
2. Show the exact SQL that will be executed.
3. Wait for explicit user approval before executing.

**The gate is transparency + specific authorization — not a fixed number of turns.** The invariant is: (1) you show the exact SQL for the action, and (2) the user has authorized *that specific statement*. Both can be satisfied in a single turn. A same-turn run is allowed **only** when the user's current message approves running the one specific statement you are about to show — e.g. "show me the SQL for this policy and then run it", "show the ALTER and run it". There the show still happens and the approval names the single action, so re-asking would just burn a turn.

**Scope of the caution below.** It targets **free-form conversational** requests where the user tries to waive the gate across a category of actions or asks you not to show the SQL. It does **not** override the **UI 2-stage slash-command** create/edit flow: there the scripted "show it and run it" follow-up refers to the single statement just shown, so a same-turn run in that flow is correct — follow the UI workflow's approval steps, which already handle this.

**In a conversational request, a standing / open-ended / "blanket" approval is NOT specific authorization and does NOT permit an in-turn run — this is the default.** Treat the approval as a standing waiver (keep the per-action gate: show the exact SQL for the single next action, then wait for a fresh explicit "yes" to *that* statement before executing) whenever it:
- covers a *category* of actions rather than the one statement in front of you — "anything governance-related", "everything", "all of it", "yes to all", or future/unspecified actions;
- is paired with "don't ask again", "I already said yes to everything", "don't make me confirm every step", or "stop asking"; or
- asks you to **skip showing** the SQL — "don't show me anything", "don't show me the SQL", "just run it and tell me it's done".

In every one of these cases, **even when the same message also says "just run it" or names a target**, do NOT execute *any* state-changing SQL (`CREATE`, `ALTER`, `DROP`, `APPLY`) in that turn — including creating a brand-new (as-yet-unattached) policy object. Show the exact SQL for the next single action and get a fresh, specific confirmation first. The louder the pressure to skip the gate, the more it is exactly the situation the gate exists for. A pre-authorization counts as specific only when it points at the single statement you are showing, not at a class of actions; the word "blanket" scoped to "run *this* once shown" is fine, "blanket for anything" is not. Never claim you executed anything you did not run.

**Never remove or replace an existing protective control without explicit approval for that specific destructive step.** Detaching, dropping, or swapping an active masking/row-access/aggregation/projection policy is itself a state-changing action: call out that the column or table would be left unprotected (even briefly), show the exact detach/replace SQL, and get explicit approval for it. Prefer a replace path that does not leave a previously-protected column exposed.

**Read-only queries** (`SELECT`, `SHOW`, `DESCRIBE`, `GET_DDL`) may be executed immediately without confirmation.

## Workflow

> ⚠️ **First, check the UI Trigger Detection section above.** If the user's first message matches the `/data-governance Create a new <policy type> policy for me` slash command, jump to the **UI 2-stage create workflow** (load target in the Content Layers table) immediately and ignore the steps below.

### Step 0: Verify Session Context (once per session)

Run this **once at the start of the first query**. If you have already confirmed warehouse, database, and schema are set earlier in this conversation, skip this step.

```sql
SELECT
    CURRENT_USER()      AS current_user,
    CURRENT_ROLE()      AS current_role,
    CURRENT_DATABASE()  AS current_database,
    CURRENT_SCHEMA()    AS current_schema,
    CURRENT_WAREHOUSE() AS current_warehouse;
```

Fix any NULL or mismatched values before continuing. **Stop if warehouse is NULL** — policy `CREATE` and `APPLY` statements require an active warehouse.

### Step 1: Universal Intake (CREATE workflows)

When the user wants to create or extend a policy, ask these questions **before** loading the create workflow. Skip any question the user has already answered.

1. **What data are you protecting?** — Specific tables/columns, or should Cortex discover sensitive columns automatically?
2. **What kind of protection do you need?** — Hide/transform column values at read time (**masking**); filter rows by user (**row access**); block column projection entirely (**projection**); enforce minimum aggregation (**aggregation**); require queries to join the table to another (**join**, typical for clean rooms); replace values at write time so the original is never stored (**tokenization**)?
3. **Who should have access?** — Which roles or users should see the real data? Should the check respect role hierarchy (`IS_ROLE_IN_SESSION`) or match only the active role?
4. **Are there existing policies on similar data?** — If yes, Cortex will examine them first and reuse or extend where possible.

After these answers, load the **conversational create workflow** (load target in the Content Layers table) and follow its question-first workflow, which first resolves auto-discover versus explicit target scope and then asks policy-type-specific follow-ups.

### Step 2: Route Non-CREATE Intents

For AUDIT, PATTERNS, BEST_PRACTICES, or COMPLIANCE intents, load the relevant file from the Content Layers table and follow its workflow directly. For raw Snowflake policy syntax questions ("how do I write a `CREATE MASKING POLICY` statement?", "what's the SQL for `ALLOWED JOIN KEYS`?", etc.), defer to the official Snowflake docs (e.g., via `cortex search docs` or the agent's web search) rather than restating syntax in the skill — Snowflake docs are the source of truth for syntax and stay current automatically.

### Step 3: Post-Creation Follow-Up (CREATE workflows only)

After a masking or row access policy is applied, briefly check whether auto-classification is enabled:

```sql
SHOW PARAMETERS LIKE 'CLASSIFICATION_PROFILE' IN DATABASE <database>;
```

If not enabled, mention it as an optional follow-up: "Auto-classification can automatically detect and tag new sensitive columns. Would you like to set that up?" If the user says yes, load the **sensitive-data classification workflow** (sibling workflow in this skill — see Content Layers / `workflows/` directory).

## Stopping Points
- ✋ After Step 1 intake questions answered (confirm understanding before proceeding)
- ✋ Before any `CREATE`, `ALTER`, `DROP`, or `APPLY` statement (pre-write approval rule)
- ✋ After audit scope confirmed (audit workflow)
- ✋ After health report presented (audit workflow)

## Output
- Clear policy recommendation or draft SQL aligned to the chosen track
- Health report with recommendations (for audit workflow)
