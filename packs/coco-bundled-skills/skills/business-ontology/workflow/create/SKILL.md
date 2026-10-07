---
name: business-ontology-create
description: "Add individual Business Ontology items: create a domain, draft and approve a node, define a relationship between two nodes, or associate a node with a Snowflake object. Routed from the business-ontology skill."
parent_skill: business-ontology-workflow
---

# Create

## When to load

The user wants to add a single item to the Business Ontology. Routed from `../../SKILL.md`. For adding many items at once, route to `../import/SKILL.md`.

## Setup

Read once before calling any functions:
- `../../reference/API_CONTRACT_CRUD.md` — SYSTEM$ mutation signatures, payloads, and examples
- `../../reference/SUMMARY_FORMAT.md` — canonical render templates for item cards and diff cards

`<SKILL_DIR>` is a placeholder the agent resolves.

## Step 0 — Identify what to create

Determine the target type from the user's message:

| Type | Signals |
|---|---|
| **domain** | "add domain", "create a domain", "new category" |
| **node** | "create term", "add term", "add node", "define X", "add X to Purchasing" |
| **relationship** | "relationship between X and Y", "X is upstream of Y", "X triggers Y", "X is a synonym of Y" |
| **asset association** | "associate table X with term Y", "link column X to term Y", "term Y describes table X" |

If ambiguous, ask once:

```
What would you like to add?
  a) Domain
  b) Term
  c) Relationship between two nodes
  d) Association between a node and a Snowflake object
```

## Step 1 — Gather inputs

### Domain

Ask for:
- **Name** (required)
- **Description** (optional)

Then go to Step 2.

---

### Node

Ask for (in a single turn if possible):
- **Name** (required)
- **Domain** (required) — accept a domain name; `DRAFT_GLOSSARY_TERM` accepts `domainName` directly, so no pre-lookup is needed. If the user doesn't specify a domain or the concept is generic, use `"Core"` as the domain.
- **Kind** (optional, default `TERM`) — `TERM | METRIC | ENTITY`
- **Scope** (optional) — semantic scope identifier, e.g. `"Finance"` or `"Customer Success"`. Ask when the same concept name is used with different meanings across teams. Unique constraint is `(name, scope, domainId)`.
- **Description** (optional)
- **Tags** (optional, comma-separated)
- **Synonyms** (optional) — accept a mix of free-text aliases and existing node names
- **Formula** (METRIC kind only, optional) — SQL expression stored verbatim as the metric definition
- **Exclusions** (METRIC kind only, optional) — array of filter condition strings
- **Formula source** (METRIC kind only, optional) — provenance note (e.g. "from dbt model revenue_v2")

> **Formula detection:** When `itemKind == METRIC`, if the user's description contains SQL aggregation keywords (`SUM`, `COUNT`, `AVG`, `MAX`, `MIN`), arithmetic operators in context, or plain-English computation phrases (`minus`, `divided by`, `sum of`), proactively ask before Step 2:
> "This looks like it contains a formula — should I store `<expression>` in the `formula` field and keep only the plain description text?"
> If yes, split: put the formula in `formula`, shorten `description` to plain prose only. If no, keep description as-is.

If the user mentions an existing node as a synonym (e.g. "PO is a synonym for Purchase Order"), attempt a lookup via `CALL SYSTEM$GET_GLOSSARY_TERM('<name>')`. If the node is found, use `{"termId": "<uuid>"}`. If the lookup returns no result or errors, fall back to `{"text": "<name>"}` — the text form is always safe.

> **Scope disambiguation:** If the node name could refer to multiple scoped variants, call `SYSTEM$GET_GLOSSARY_TERM_SCOPES('<name>')` before proceeding. If `count > 1`, surface the variants and ask which scope the user means.

Then go to Step 2.

---

### Relationship

Ask for (in one turn):
- **Source node** (required) — name or UUID
- **Target node** (required) — name or UUID

> **Scope disambiguation:** If either source or target node name could refer to multiple scoped variants, call `SYSTEM$GET_GLOSSARY_TERM_SCOPES('<name>')` before proceeding. If `count > 1`, surface the variants and ask which scope the user means.

**HARD RULE — always use FQN (`<domain>.<term>`) for relationship calls.** FQN is unambiguous even when the same term name exists in multiple domains. Use the exact domain name as it appears in the ontology (domain names can be long, e.g. `"Yum! - Finance - Sales and Transactions v2.Net Sales"`).

**Fallback — term ID:** Only needed when FQN fails because the term name itself contains a literal dot. Build a `name → termId` map using the query in `../../reference/API_CONTRACT_CRUD.md §termIdOrName resolution` (item 2).

If the same name appears in multiple domains → show the ambiguity and ask which domain's term is intended. Never silently pick one.

- **Type** (required) — choose from the standard vocabulary; load `../../reference/RELATIONSHIP_TYPES.md` for the full list with when-to-use guidance
- **Label** (optional for standard types; **mandatory** for `CUSTOM`) — short descriptive phrase

**Natural-language type inference** (echo back for user confirmation before proceeding):

| User says | Inferred type | Source → Target |
|---|---|---|
| "Y has a variant X / X is a variant of Y" | `HAS_VARIANT` | Y → X |
| "X is part of Y / Y has X as a component" | `HAS_PART` | Y → X |
| "X is computed from Y / Y derives X" | `DERIVES` | Y → X |
| "X measures Y" | `MEASURES` | X → Y |
| "X is identified by Y" | `IDENTIFIED_BY` | X → Y |
| "X classifies Y / Y is categorized by X" | `CLASSIFIES` | X → Y |
| "X applies to Y / X governs Y" | `APPLIES_TO` | X → Y |
| "X scopes Y / Y is only valid within X" | `SCOPES` | X → Y |
| "X is equivalent to / same as Y" | `EQUIVALENT_TO` | X (preferred) → Y |
| "X relates to Y" (no specific semantic) | `RELATED_TO` | X → Y |
| Doesn't fit any above | `CUSTOM` + **mandatory label** | user-specified |

When the inferred type is ambiguous between two standard types, ask the user to choose — do not silently fall back to `CUSTOM`.

**Synonym special case:** When the user says "X is a synonym of Y", ask first:
- "Does X have its own definition and owner, or is it just an alternate name/abbreviation?"
  - Own definition → use `EQUIVALENT_TO` edge
  - Just an alias → add `X` to `synonyms[]` attribute on the existing term via `SYSTEM$UPDATE_GLOSSARY_TERM` (no edge needed)

Then go to Step 2.

---

### Asset association

Ask for (in one turn):
- **Node** (required) — name or UUID

> **Scope disambiguation:** If the node name could refer to multiple scoped variants, call `SYSTEM$GET_GLOSSARY_TERM_SCOPES('<name>')` before proceeding. If `count > 1`, surface the variants and ask which scope the user means.

- **Asset type** (required) — `TABLE | VIEW | COLUMN | SEMANTIC_VIEW | DASHBOARD`
- **FQN or object name** (required) — fully qualified name (e.g. `ANALYTICS.PUBLIC.TRIP_PAYMENTS`) or object name + dimension for semantic views
- **Association role** (optional, default `DESCRIBES`) — `DESCRIBES | RELATED_SEMANTIC_VIEW | RELATED_DASHBOARD`

For semantic views, also ask for the **dimension name** (optional).

Then go to Step 2.

## Step 2 — Confirmation (stopping point)

⚠️ MANDATORY STOPPING POINT — Do NOT call any SYSTEM$ function until the user responds.

Render a compact summary of what will be created using the matching card from `../../reference/SUMMARY_FORMAT.md` (Concept card / Relationship card / Asset association card; for an edit to an existing ACTIVE item use the Edit diff card). Wait for an explicit confirmation before proceeding.

Include a choice for the user — **make active now** (default) or **save as draft** for later review. Append the choice line under the card:

- Domain: `go / cancel` (domains have no draft state)
- Concept / relationship / association: `go (make active) / draft (save for steward review) / cancel`

Domains are simpler — a name and description are enough:

```
Creating domain:
  Name: Purchasing
  Description: Procurement and vendor management terms

go / cancel
```

- **go** (default): draft and immediately approve — the item is live (ACTIVE)
- **draft**: persist to Snowflake as a draft suggestion (visible in the UI, survives session end, a steward can approve later)
- **cancel**: abort

**Clarifying "draft":** If the user says "draft", "save for now", or any other ambiguous phrase, confirm intent once before calling any API:

```
Save as draft — do you mean:
  (a) Persist to Snowflake as a draft suggestion (visible in UI, approve later)
  (b) Hold in session only — no save yet (I'll keep the details until you confirm)
```

- If (a) or the user already said "save as draft" / "draft for steward review" → call `SYSTEM$DRAFT_GLOSSARY_*` but not `SYSTEM$APPROVE_*`.
- If (b) or the user says "hold off" / "not ready" → no API call. Resume when the user confirms.

Do not proceed without a clear response. Domains do not have a draft state — they are always created directly.

## Step 3 — Execute and display result

### Domain

```sql
CALL SYSTEM$CREATE_GLOSSARY_DOMAIN('<name>', '<description>');
```

Display the returned `domainId` and `path`.

---

### Node

The node creation is two calls — DRAFT then APPROVE — presented as a single operation to the user (unless they chose "draft").

**1. Draft:**
```sql
CALL SYSTEM$DRAFT_GLOSSARY_TERM('{
  "name": "<name>",
  "domainName": "<domain>",
  "itemKind": "<kind>",
  "description": "<description>",
  "scope": "<scope>",
  "synonyms": [...],
  "formula": "<formula>",
  "exclusions": ["<filter1>"],
  "formulaSource": "<provenance>"
}');
-- Omit "scope" when not provided
-- Omit "formula", "exclusions", "formulaSource" when itemKind is not METRIC — the backend rejects them on non-METRIC terms
```

**2. Approve** (skip if user chose "draft"):
```sql
CALL SYSTEM$APPROVE_GLOSSARY_TERM('<termId from draft>');
```

If user chose **go**: display the returned `termId` and `status: ACTIVE`. Do not mention the intermediate draft state.

If user chose **draft**: display the returned `termId` and note it's saved as a draft for later approval:
```
Node "Purchase Order" saved as draft (termId: <uuid>).
Approve later via SYSTEM$APPROVE_GLOSSARY_TERM or in the Snowflake UI.
```

**Editing an existing ACTIVE node** (when the user wants to update rather than create):
```sql
CALL SYSTEM$UPDATE_GLOSSARY_TERM('<termId>', '{
  "<field>": "<value>"
}');
```

Valid patch fields (all optional):
- `description`
- `status` (`DRAFT | ACTIVE | DELETED`)
- `itemKind` (`TERM | METRIC | ENTITY`)
- `scope` (empty string `""` clears scope back to unscoped)
- `synonyms` (array — **replaces** the entire stored synonyms list; empty array `[]` clears all)
- `formula` (METRIC only — blank string clears it)
- `exclusions` (METRIC only — empty array `[]` clears)
- `formulaSource` (METRIC only)

Omit fields that are not changing. Display the updated node card after a successful call.

---

### Relationship

**Label validation before drafting:**
- If `label` is empty for a **standard type** → auto-fill the display label from `../../reference/RELATIONSHIP_TYPES.md` (e.g. `HAS_VARIANT` → `'has variant'`, `DERIVES` → `'derives'`). Do not pass NULL.
- If type is `CUSTOM` and `label` is empty → **stop and ask** the user for a label. Do not draft without one.

**1. Draft** (use FQN; fall back to termId only if term name contains a literal dot):
```sql
-- FQN format '<domain>.<term>' — label validation handled by the bullets above; never pass NULL for standard types
CALL SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP('<domain>.<sourceTerm>', '<domain>.<targetTerm>', '<type>', '<label>');
```

**2. Approve** (skip if user chose "draft"):

For a single interactive item, ask once before approving — the account-wide draft queue may contain items from other sessions:

```
Approve this relationship? The draft queue may contain other items from previous sessions.
  yes        → approve this relationship only (individual call)
  yes + all  → approve everything in the queue (use only if you know the queue is clean)
  no         → leave as draft for steward review
```

- **"yes"** (default):
  ```sql
  -- Use same FQN (or termId) as the draft call
  CALL SYSTEM$APPROVE_GLOSSARY_RELATIONSHIP('<domain>.<sourceTerm>', '<domain>.<targetTerm>', '<type>');
  ```
- **"yes + all"** (explicit user choice only):
  ```sql
  CALL SYSTEM$APPROVE_ALL_GLOSSARY_RELATIONSHIPS();
  ```

Display the returned state. If user chose "draft", note it's saved for later approval.

---

### Asset association

> **CREATE vs DRAFT:** `CREATE_GLOSSARY_ASSOCIATION` is permitted here because this skill handles a **single** interactive item at a time. For bulk operations (>1 association), always redirect to `../import/SKILL.md` — bulk imports must use `DRAFT_GLOSSARY_ASSET` to allow review before approval.

**go (make active now):**
```sql
-- Single-step direct creation — no intermediate draft (single item only)
-- Use FQN format for term: '<domain>.<term_name>'; fall back to termId if term name contains a dot
CALL SYSTEM$CREATE_GLOSSARY_ASSOCIATION(
  '<domain>.<termName>',
  '{"refType": "<objectType>", "fqn": "<objectFQN>"}',
  '<associationRole>'
);
```
Display the returned `associationId` and `state: APPROVED`.

**save as draft:**
```sql
-- Use FQN format for term: '<domain>.<term_name>'; fall back to termId if term name contains a dot
CALL SYSTEM$DRAFT_GLOSSARY_ASSET('<domain>.<termName>', '{"refType": "<objectType>", "fqn": "<objectFQN>"}', '<associationRole>');
```
Display the returned draft state; note it requires steward approval.

To approve a draft association later:
```sql
-- Same term identifier (FQN or termId) and assetRefJson as the draft call; no role parameter
CALL SYSTEM$APPROVE_GLOSSARY_ASSET('<domain>.<termName>', '{"refType": "<objectType>", "fqn": "<objectFQN>"}');
```

Verify the association via `SYSTEM$GET_GLOSSARY_TERM_ASSETS('<domain>.<termName>', '')` — do not rely on the `representedAs` field in `SYSTEM$GET_GLOSSARY_TERM`.

---

### Feature gate error

If any SYSTEM$ call returns a feature-gate error, surface once:

> *(Business Ontology is not yet enabled in this account — contact your account admin to enable it (`FEATURE_BUSINESS_GLOSSARY`).)*

Then stop.

## Step 4 — Offer related actions

After **domain** creation:
```
Domain "Purchasing" created.  Want to add nodes to it?
```

After **node** creation:
```
Node "Purchase Order" created.  Want to add relationships or associate it with a Snowflake object?
```

After **relationship** or **association**:
```
Done.  Want to add another?
```

## What this skill never does

- Ask the user to provide a `domainId` UUID — always accept domain names and resolve internally
- Expose DRAFT termIds or internal storage details to the user (unless they explicitly chose "draft")
- Run DRAFT and APPROVE calls in separate turns without user intent
- Create more than one item per invocation (for bulk, route to `../import/SKILL.md`)
- Use `CREATE_GLOSSARY_ASSOCIATION` for more than one association — if the user asks to link multiple objects in a single message, redirect to import
- Approve relationships without first checking the draft queue for foreign-session items
- Pass bare term names (instead of FQN or termId) to relationship, association, or delete calls when duplicates may exist across domains
