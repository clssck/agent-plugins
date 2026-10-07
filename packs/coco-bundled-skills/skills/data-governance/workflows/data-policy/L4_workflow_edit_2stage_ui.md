# Guided Workflow: Edit Policy in 2 Stages (UI Slash-Command Flow)

> ## You are now in the UI 2-stage edit flow. Different rules apply.
>
> This workflow is loaded only when the user's first message matches the slash command:
>
> ```
> /data-governance Edit the <POLICY_KIND> POLICY named <POLICY_NAME> located at <DB>.<SCHEMA>.
> ```
>
> issued by the data-governance UI component. The conversation MUST follow the 2-stage shape described below. **Do not** revert to the standard workflows, do not propose a wholesale rewrite of the policy without first showing the user what is currently there, and do not generate any `ALTER` / `CREATE OR REPLACE` SQL until Stage 2.
>
> Do **not** mention loading, routing, triggers, workflow files, this file, fallback rules, or whether an interactive question tool is available. If the UI tool is unavailable, ask the same product-facing question in prose without explaining tool availability.
>
> If you got here for any other reason (a normal conversational request like "I need to update the masking on customers"), close this file and load the **conversational create workflow** (which also covers extension and modification).

## Hard rules for this workflow (read before doing anything else)

1. **The policy NAME and LOCATION (db.schema) come pre-supplied in the slash command.** Do not ask for them again.
2. **First content question is `definition` vs `attachment`.** That is the *only* thing to ask before any read or write.
3. **Stage 2 begins with a read-only inspection** (`GET_DDL` for definition, `INFORMATION_SCHEMA.POLICY_REFERENCES` for attachment). Show the user what is currently there before proposing changes.
4. **No write SQL** (`ALTER POLICY`, `CREATE OR REPLACE`, `ALTER TABLE`, `DROP`) **until the user has seen the current state and described the change.**
5. **Pre-write approval still applies** — show the SQL, wait for the user's "yes", then execute.
6. **Ask user-facing questions via the interactive question tool, not in prose.** See "Interactive Question Tool" below for the contract.
7. **Minimize suggested-prompts chips via prose discipline.** Keep prose to at most one short framing line per turn (or none); never emit a "next steps" / "you might also ask" / "here are some examples" list yourself. See "Interactive Question Tool → Disable suggested prompts" below for what's controllable from the workflow and what needs a separate agent-config / UI change.
8. **Product-facing first response.** The first visible response should acknowledge the named policy and ask `Definition` vs `Attachment` rather than opening with the universal intake questions.

---

## Why this workflow is different

| | UI 2-stage create flow | Edit flow (this file) |
|---|---|---|
| Policy already exists | No — about to create one | Yes — pre-supplied by name in the slash command |
| First content question | "What should we name the policy?" | "Definition or attachment?" |
| Stage 1 output | `CREATE … POLICY` | (no SQL — just the routing question) |
| Stage 2 begins with | Asking the target table/column | A **read-only** `GET_DDL` or `POLICY_REFERENCES` query |
| Stage 2 write | `ALTER TABLE … SET POLICY` (attach) | `ALTER POLICY` (preferred — no re-application needed) **or** `ALTER TABLE`/`ALTER TAG` (attachment path) |
| How questions are asked | Via the interactive question tool the data-governance UI provides (same convention) | Via the interactive question tool the data-governance UI provides — structured prompt + options widget rendered inline. |

Stage 1 is strictly about *identifying intent*. Stage 2 is strictly about *inspecting then changing the named policy*. Do not skip the inspection step.

---

## Pre-Write Approval Rule (still applies)

Before any `CREATE OR REPLACE`, `ALTER`, `DROP`, or `APPLY`:
1. Show the exact SQL.
2. Have the user's approval for *that specific* action.
3. Then execute.

**Approval already given in the user's current message counts — do not spend a turn re-asking.** If the user says "show me the SQL and then run it", "you're pre-approved once shown", or similar, show the statement *and* execute it in the **same** turn. The gate is transparency + a specific authorization, not a mandatory extra round-trip. Still refuse to skip the show step, or to remove/replace an existing protective control without an explicit go for that specific step.

Read-only queries (`SHOW`, `DESCRIBE`, `GET_DDL`, `SELECT`, `INFORMATION_SCHEMA.POLICY_REFERENCES`) may be executed without confirmation.

---

## Interactive Question Tool

Whenever this workflow tells you to ask the user something — the routing question, what to change, a pre-write approval — invoke the **interactive question tool** the data-governance UI surface provides. The tool renders a structured ask-the-user widget inline in the chat. It supports three shapes:

- **Single-choice** — radio buttons. Use for `Definition / Attachment`, `Yes, run it / Edit the SQL / Cancel`, etc.
- **Multi-select** — checkboxes. Use for any *list-of-things* answer (role lists, multiple targets to remove, etc.).
- **Short free-text** — a one-line typed answer. Use only when the answer is genuinely open-ended (a description of the change in the user's own words, a custom replacement body, a target FQN that doesn't fit a quick discovery).

For each interactive question, pass:

- `prompt` — the literal question text shown to the user (e.g., *"Definition or attachment?"*, *"Run this `ALTER` now?"*).
- `shape` — `single-choice`, `multi-select`, or `free-text`.
- `options` — when `shape` is `single-choice` or `multi-select`, the discrete choices. For pre-write approvals, the standard single-choice set is `["Yes, run it", "Edit the SQL", "Cancel"]`. For multi-select questions, options are typically discovered (see the pattern below) and end with an *Other (free text)* escape.

Steps below render each question as a blockquote (`> …`) listing the prompt and, when applicable, the options. **Treat that blockquote as the spec of the tool call, not as prose to repeat back to the user.** Your prose reply for a question turn should be **at most one short framing line, or nothing at all** — the interactive tool's `prompt` + `options` carry the question content. Each turn must have exactly one framing line (or none); do **not** emit two near-duplicate acknowledgement lines. Do **not** ask the same question twice (once in prose and once via the tool), and do **not** append a "next steps" / "you might also ask" / "follow-up suggestions" / "here are some examples" list to your reply — that prose is exactly what suggestion-chip generators chew on (see "Disable suggested prompts" below).

### Pattern: enumerable lists (multi-select with discovery)

When a question asks the user to pick from a finite, discoverable set — most commonly **role lists** (who's allowed / who bypasses), but also tag names, target FQNs, columns on a table — do not ask via free-text; ask via the interactive tool's **multi-select** shape with options populated from a one-shot read-only discovery query run in the same turn.

The shape is always:

1. **Discover** the candidate set silently before asking (read-only, no pre-write approval needed). Default queries:
   - **Role list** → `SHOW ROLES;` (use the `name` column).
   - **Current attachments of this policy** → already done in Step 2A.1 — reuse those rows as the options when asking what to remove.
   - **Tag list in a schema** → `SHOW TAGS IN SCHEMA <db>.<schema>;`.
   - **Column list of a table** → `DESCRIBE TABLE <fully-qualified-table>;` (use the `name` column).
2. **Ask** via the interactive tool, **multi-select**, with options = the discovered names (sorted; cap visible items at ~50, longer lists collapse to a typeahead) plus an **Other (free text)** escape.
3. **Fallback**. If the discovery query returns zero rows, errors out, or is not applicable, ask via the interactive tool's **free-text** shape instead. Surface the discovery error in one short prose line and proceed.

When a per-step blockquote below says *"Ask multi-select per the role-list pattern"* (or the analogous attachment-list / column-list phrasing), the discovery + fallback shape above is implied.

**Fallback when the interactive tool itself isn't available.** If your current toolset does not include an interactive question / ask-user tool (e.g., a CLI session, an automated eval harness, or any non-UI surface), do **not** try to call a tool that isn't there. Ask the same question in prose immediately, in the same turn — keep the prompt text identical and list the options as a short bullet list under it (or as a comma-separated free-text instruction, when there are no options). Question turns must never end with no question to the user; the substance must always reach them, via the tool when present and in prose otherwise.

### Disable suggested prompts

The data-governance UI normally renders **suggested prompts** (clickable chips that fill the user's input box on click) below the agent's reply. **Minimize them for the entire duration of this workflow** — every turn, including the routing question, the read-back of current state, the pre-write approval, and the verify reply.

Two reasons:
1. The interactive question tool already presents the canonical answer set for every question. A parallel suggested-prompts row would be a *second* answer surface — different copy, different ordering, possibly different options — which leads to off-script answers that don't fit the definition / attachment branching.
2. The edit flow has a strict turn shape (slash → routing question → read-back + describe-change → ALTER → verify). Suggested prompts encourage the user to skip ahead or fork into the wrong path (e.g., bouncing between definition and attachment mid-flow), which breaks the read-before-write rhythm.

What you (the agent) can do — prose discipline:

- **Keep prose to at most one short framing line per turn** (or none — the interactive tool's prompt + options can stand on their own). Most suggestion-chip generators infer chips from the reply prose; less prose ⇒ fewer / weaker chips.
- **Never emit chip-style content yourself.** Do not append a "You might also ask…", "Try one of:", "Here are some examples:", "Next steps:", "Define the policy logic …" open-ended exploration list to your reply. The interactive tool's `options` field is the only sanctioned answer-suggestion surface.
- **Don't restate the question in prose** when the interactive tool is rendering it — that doubles the surface area for the chip-generator and re-introduces the duplicate-reply pattern.

What this workflow can **not** do — surface-level mitigations (out of scope, but called out so reviewers know where to look if chips persist):

- The Snowflake Cortex Agents API as currently documented does not expose a per-reply `suppress_suggested_prompts` flag the agent can set from inside its response. If the data-governance UI generates these chips client-side from the assistant message, the only reliable suppression is at the UI / agent-config level — most plausibly via a directive in the data-governance UI agent's `instructions.response` (something like *"Do not propose follow-up questions or next-step suggestions; do not emit chip-style example lists"*), or a UI feature flag.
- If chips still appear with this skill loaded **and** prose is already minimal, the fix belongs in the data-governance UI agent definition or the UI rendering layer, not in this skill workflow.

---

# STAGE 1 — Identify the edit intent

## Step 1.1 — Acknowledge the policy

The slash command tells you the policy kind, name, and location. Acknowledge it briefly in your first reply, e.g. *"Got it — let's edit the masking policy `MY_DB.GOVERNANCE.MASK_PII_STRING`."* Do not ask for the name or location — you already have them. Do not mention matching an edit command, loading a workflow, routing, fallback rules, or interactive-tool availability.

If the slash command is missing the policy KIND, NAME, or LOCATION, say so plainly and ask the user to re-issue the command with the missing piece. Do not guess.

## Step 1.2 — Ask: definition or attachment? (FIRST question, always)

> **This is the very first content question, regardless of policy kind.** Ask via the interactive question tool, single-choice.

> **prompt:** What part of the policy do you want to edit?
> **options:** Definition — the body / signature / who is allowed, Attachment — the objects and tags this policy is assigned to

If the interactive tool is not available, ask exactly the same question and options in prose. Do not explain that this is a fallback and do not mention tools.

- Accept what the user picks. The two valid answers map to *definition* and *attachment*. If the user types free text instead of clicking, common synonyms: *body*, *logic*, *rules* → definition; *tables*, *tags*, *columns*, *targets*, *where it applies* → attachment.
- If the user mixes both ("change who can see it AND attach to one more column"), pick the **definition** path first (Stage 2D), finish that, then re-ask via the interactive tool whether to do the attachment edit as a follow-up (`prompt: "Now do the attachment edit too?"`, `options: "Yes, do the attachment edit", "No, we're done"`).
- If the user's answer is ambiguous or doesn't match either branch, re-ask once via the interactive tool.

Once you have a clear answer, proceed to Step 2D (definition) or Step 2A (attachment). Do **not** run any SQL in Stage 1.

---

# STAGE 2D — Edit the policy definition

## Step 2D.1 — Read the current definition (no approval needed)

Run `GET_DDL` to fetch the current definition. This is read-only, so no pre-write approval is required.

```sql
SELECT GET_DDL('POLICY', '<db>.<schema>.<policy_name>');
```

Show the returned DDL to the user in a fenced code block in your prose reply, then ask what should change **via the interactive question tool**. Skip this question if the user already said exactly what they want changed in their answer to Step 1.2.

> **prompt:** Here's the current definition. What should change? Describe the change you want — e.g., add a role to the bypass list, change the masked value, switch from `CURRENT_ROLE` to `IS_ROLE_IN_SESSION`, fix the data type, etc.
> *(free-text answer — the user describes the change in their own words)*

If `GET_DDL` returns nothing (policy not found), say so in prose and stop. Do not propose creating a new policy as a fallback — the user explicitly asked to edit a named policy, not create one.

## Step 2D.2 — Generate the change

Build the modified policy SQL. **Always prefer `ALTER … POLICY`** — it updates the policy in place without dropping and recreating the object, so existing grants, attachments, and tag bindings are preserved and the policy does **not** need to be re-applied to any table or column.

```sql
-- Preferred: ALTER POLICY (preserves grants, attachments, and tag bindings;
-- no re-application needed). Use the appropriate ALTER for the policy kind:
ALTER MASKING POLICY <db>.<schema>.<policy_name> SET BODY ->
  <new body expression>;

ALTER ROW ACCESS POLICY <db>.<schema>.<policy_name> SET BODY ->
  <new body expression>;

ALTER PROJECTION POLICY <db>.<schema>.<policy_name> SET BODY ->
  <new body expression>;

ALTER AGGREGATION POLICY <db>.<schema>.<policy_name> SET BODY ->
  <new body expression>;

-- Fallback ONLY when the signature (argument list or return type) must change.
-- CREATE OR REPLACE drops and recreates the policy object — attachments survive
-- only if the new signature exactly matches the old one; otherwise the policy
-- must be re-applied to every target manually.
CREATE OR REPLACE <POLICY_KIND> POLICY <db>.<schema>.<policy_name>
  AS (...) RETURNS ... -> <new body>;
```

**When to use which:**

| Change requested | Use |
|---|---|
| Body logic only (add/remove a role, change masked value, switch role-check style) | `ALTER … POLICY … SET BODY` |
| Comment change | `ALTER … POLICY … SET COMMENT = '…'` (or `UNSET COMMENT`) |
| Signature change (add/remove an argument, change the return type) | `CREATE OR REPLACE` (warn the user that re-application may be needed if the signature differs) |

If you must use `CREATE OR REPLACE` because the signature is changing, **warn the user explicitly** via the interactive tool before showing the SQL:

> **prompt:** This change modifies the policy's signature. Using `CREATE OR REPLACE` means the policy may need to be re-applied to its targets if the new signature doesn't match. Proceed?
> **options:** Yes, proceed with CREATE OR REPLACE, Cancel — I'll adjust to keep the same signature

Best-practice checklist:
- Preserve everything the user did NOT ask to change (signature, comment, role list, etc.).
- For masking / tokenization: keep an explicit `ELSE NULL` (or other fail-closed branch).
- Use `IS_ROLE_IN_SESSION('<role>')` for role checks (not `CURRENT_ROLE()`).

Show the SQL in a single fenced block in your prose reply, then ask for pre-write approval **via the interactive question tool**:

> **prompt:** Run this `ALTER POLICY` now?
> **options:** Yes, run it, Edit the SQL, Cancel

Execute on `Yes, run it`. On `Edit the SQL`, accept the user's revised SQL via a free-text follow-up on the interactive tool and re-confirm. On `Cancel`, stop. If the change fails, surface the error in prose and re-ask via the interactive tool whether to adjust and retry (`Yes, retry with edits` / `Cancel`).

## Step 2D.3 — Verify

After the change executes:

```sql
SELECT GET_DDL('POLICY', '<db>.<schema>.<policy_name>');
```

Confirm in one short line that the requested change is now present in the body. If the policy is attached to anything, mention that the new definition is now in effect for those targets (no re-attach needed for `ALTER ... SET BODY`; the same is true for `CREATE OR REPLACE` as long as the signature didn't change).

---

# STAGE 2A — Edit the policy attachment

## Step 2A.1 — Read the current attachments (no approval needed)

Run `INFORMATION_SCHEMA.POLICY_REFERENCES` to enumerate where the policy is currently attached. This is read-only.

```sql
SELECT
  REF_DATABASE_NAME, REF_SCHEMA_NAME, REF_ENTITY_NAME,
  REF_ENTITY_DOMAIN AS OBJECT_TYPE,
  REF_COLUMN_NAME,
  TAG_DATABASE, TAG_SCHEMA, TAG_NAME       -- non-null when attached via tag
FROM TABLE(<db>.INFORMATION_SCHEMA.POLICY_REFERENCES(
  POLICY_NAME => '<db>.<schema>.<policy_name>'
));
```

Show the returned attachments to the user in a compact form in your prose reply — one line per row including the **object type**: e.g., `CUSTOMERS (TABLE).EMAIL` for direct column attach, `CUSTOMER_VIEW (VIEW)` for table-level, `tag PII_TAG` for tag-based. Then ask what should be added or removed **via the interactive question tool**. Skip this question if the user already specified in Step 1.2.

> **prompt:** Here are the current attachments. What change do you want to make?
> **options:** Add an attachment (direct or tag-based), Remove an attachment, Both — first remove, then add, *Other (free text — describe in your own words)*
> *(after a choice is made, follow up via the interactive tool with a free-text question for the specifics — which target/tag to add or remove, at which level)*

If the policy is currently attached to nothing and the user picks **Remove an attachment**, say so in prose and stop. If the user picks **Add an attachment**, proceed normally.

## Step 2A.2 — Generate the change

Build the SQL based on the requested operation:

| Operation | SQL |
|---|---|
| Add direct attach (masking / projection / tokenization) | `ALTER TABLE <table> MODIFY COLUMN <col> SET <KIND> POLICY <db>.<schema>.<policy_name>;` |
| Add direct attach (row access / aggregation / join) | `ALTER TABLE <table> ADD <KIND> POLICY <db>.<schema>.<policy_name>;` |
| Remove direct attach | `ALTER TABLE <table> [MODIFY COLUMN <col>] UNSET <KIND> POLICY;` |
| Add tag-based binding (masking / tokenization only) | `ALTER TAG <db>.<schema>.<tag_name> SET <KIND> POLICY <db>.<schema>.<policy_name>;` |
| Remove tag-based binding | `ALTER TAG <db>.<schema>.<tag_name> UNSET <KIND> POLICY;` |
| Add tag to an object | `ALTER TABLE <table> [MODIFY COLUMN <col>] SET TAG <db>.<schema>.<tag_name> = '<v>';` |
| Remove tag from an object | `ALTER TABLE <table> [MODIFY COLUMN <col>] UNSET TAG <db>.<schema>.<tag_name>;` |

If the user asks to add the policy via tag-based attach for **row access**, **projection**, **aggregation**, or **join**, say plainly in prose (*"Tag-based attach for &lt;kind&gt; isn't supported — let's do direct attach instead."*) and continue with the direct-attach SQL.

If discovery in Step 2A.1 already showed the same attachment present (e.g., user wants to add an attach that exists), point that out in prose and stop — don't issue a no-op `ALTER`.

If discovery in Step 2A.1 showed an existing **tag-based** attachment for this policy (`TAG_NAME` non-null) and the user is asking to add a **direct** attach to the same column or table, surface the precedence interaction in prose, then ask the resolution choice **via the interactive question tool** before generating any `ALTER`:

> **prompt:** This column/table is already covered by `<policy_name>` via tag `<tag_name>`. Adding a direct attach will take precedence — the tag-based attach will become a no-op on this target until the direct one is removed. How do you want to proceed?
> **options:** Proceed with the direct attach (tag-based becomes a no-op on this target), Remove the tag-based binding instead, Cancel

(This mirrors the symmetric warning in the create flow Step 2.2.) Wait for the user's choice before issuing any write SQL.

Show the SQL in a single fenced block in your prose reply, then ask for pre-write approval **via the interactive question tool**:

> **prompt:** Run this `ALTER` now?
> **options:** Yes, run it, Edit the SQL, Cancel

Execute on `Yes, run it`. On `Edit the SQL`, accept the user's revised SQL via a free-text follow-up on the interactive tool and re-confirm. On `Cancel`, stop. If the change fails, surface the error in prose and re-ask via the interactive tool whether to adjust and retry.

## Step 2A.3 — Verify

After the change executes, re-run `POLICY_REFERENCES` (same query as Step 2A.1) and confirm the attachment list now reflects the requested add/remove. One short line of confirmation is enough.

---

## Stopping points

Every stopping point below is a question turn — the actual ask goes through the interactive question tool (see the "Interactive Question Tool" section above). Your prose for these turns should be brief framing only.

- ✋ After Step 1.2: user must pick *Definition* or *Attachment* (interactive tool, single-choice) before any read.
- ✋ After Step 2D.1 / Step 2A.1: user sees the current state in prose and describes the change via the interactive tool (free-text for definition; choice + free-text follow-up for attachment) before any write SQL is generated.
- ✋ Before each `ALTER POLICY` / `CREATE OR REPLACE` / `ALTER TABLE` (Step 2D.2 / Step 2A.2): pre-write approval (interactive tool, options `Yes, run it` / `Edit the SQL` / `Cancel`).

## Output

- Read-only display of the current state (DDL or attachments).
- One concrete SQL block per write operation (preferring `ALTER POLICY` over `CREATE OR REPLACE` to avoid re-application), with the user's explicit approval before it runs.
- One-line verification after the write.
