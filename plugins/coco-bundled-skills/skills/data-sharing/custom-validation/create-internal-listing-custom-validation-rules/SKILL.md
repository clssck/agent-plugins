---
name: create-internal-listing-custom-validation-rules
description: "Create and manage a DB table that stores custom listing validation rules for Internal Marketplace. Each rule has a name, title, config_type, and a props JSON blob (severity, status, rule_text, hints). Use when: setting up custom validation rules, adding listing validation rules, managing validation rule storage, creating the rules table, viewing rules, editing a rule, deleting a rule, disabling a rule, enabling a rule, shadow mode rule. Triggers: create validation rules table, add custom listing rule, setup listing validation, custom validation rules, show my rules, edit rule, disable rule, delete rule, set rule to shadow."
---

# Create Internal Listing Custom Validation Rules

Set up the database table that stores custom listing validation rules, and populate it with rules. Rules are later consumed by the `create-internal-listing-with-custom-validation` skill to validate listing manifests via Cortex AI before publish.

## When to Use

**USE THIS SKILL when:**
- Setting up the `LISTING_VALIDATION_RULES` table for the first time
- Adding new custom validation rules to an existing table
- Viewing the current rules in the table
- Editing a rule's text, severity, status, or hints
- Enabling, disabling, or setting a rule to shadow mode
- Deleting a rule

**Common triggers**: "create validation rules", "add listing rule", "show my validation rules", "edit rule X", "disable rule X", "set rule to shadow", "delete rule X"

## Rule Shape

Each rule stored in the table has the following structure:

| Field | Description |
|-------|-------------|
| `name` | Canonical rule identifier — used as `rule_id` in validation responses and telemetry |
| `title` | Human-readable display name shown in the UI |
| `config_type` | Always `listing_validation_rule` |
| `props` | VARIANT JSON blob containing the rule definition |
| `props.severity` | `ERROR` \| `WARNING` — `ERROR` blocks publish; `WARNING` surfaces but allows it |
| `props.status` | `enabled` \| `shadow` \| `disabled` — `shadow` runs silently for observation without blocking |
| `props.rule_text` | Natural language string — what Cortex AI reads and reasons against |
| `props.hints.fields_of_interest` | List of field paths (optional) — grounding hints that improve accuracy on structural checks |

**Example rule props:**
```json
{
  "severity": "ERROR",
  "status": "enabled",
  "rule_text": "If the publisher account name starts with 'TEST_', then every named
    account in organization_targets.access and organization_targets.discovery must also
    start with 'TEST_'. Using all_internal_accounts: true is also a violation, as it
    would expose the listing to production accounts. If the publisher account does not
    start with 'TEST_', this rule does not apply.",
  "hints": {
    "fields_of_interest": [
      "organization_targets.access",
      "organization_targets.discovery"
    ]
  }
}
```

## Workflow

```
Start → Fetch Available Fields → Ask: table location → Ask: intent
                                                              ↓
          ├─ Create/Add rules → Step 1: Setup Table → [Per-rule loop] Step 2: Gather Rule → Step 3: Insert Rule → ask "add another?"
          │                            ↓                       ↓                                       ↓
          │                     ⚠️ STOP if missing      ⚠️ STOP for approval                   → Step 4: Verify (when done)
          │                     required privileges
          └─ Manage existing rules → Manage Rules (view / edit / delete)
```

**Ask for table location first** — always ask this before determining intent. Use the ask_question tool:
```
Where is your validation rules table?

  [Enter] INTERNAL_MARKETPLACE.VALIDATION_RULES.LISTING_VALIDATION_RULES (default)

Or enter a full path: DATABASE.SCHEMA.TABLE_NAME
```

If the user presses Enter, use `INTERNAL_MARKETPLACE.VALIDATION_RULES.LISTING_VALIDATION_RULES`. If they type a path, accept it as-is (3-part `DB.SCHEMA.TABLE`) — do not append or modify the name. Carry this forward as the table location for all steps.

**Then determine intent** — ask what the user wants to do:
```
What would you like to do?

  • Add rules — create the table if needed and add new validation rules
  • Manage existing rules — view, edit, enable/disable, shadow, or delete rules
```

Route based on their answer: Add rules → Step 1. Manage existing rules → [Manage Existing Rules](#manage-existing-rules).

---

### Fetch Available Fields

**Goal:** Build a complete list of valid manifest field paths and their allowed values — used when generating `hints.fields_of_interest` and when advising users on valid field values as they describe rules.

**Run at the very start of every session — before any other steps, regardless of intent.**

Fetch this URL to understand all manifest fields and the valid values each field can take:

`https://docs.snowflake.com/en/user-guide/collaboration/listings/organizational/org-listing-manifest-reference#organization-listing-fields`

Additionally, run:

```sql
SHOW AVAILABLE INTERNAL MARKETPLACE CONFIGS;
```

From the results, collect the names of all rows where `props` = `custom_attribute_type`. These are the custom attribute field names that can appear in a listing manifest under `custom_attributes[*].name`.

Also include these publisher metadata fields as valid hint targets: `provider_account_name`, `current_user`, `current_role`.

Keep all field paths and their valid values in context — use them when generating `hints.fields_of_interest` and when advising users on valid values as they describe rules.

---

### Step 1: Setup Validation Rules Table

**Goal:** Ensure the storage table exists at the location already confirmed. The table location (`<database>.<schema>.LISTING_VALIDATION_RULES`) was resolved before intent was determined — do not ask for it again.

**Actions:**

1. **Check what already exists** to determine which privileges are needed:
```sql
-- Check if the database exists
SELECT COUNT(*) AS db_exists
FROM SNOWFLAKE.INFORMATION_SCHEMA.DATABASES
WHERE DATABASE_NAME = UPPER('<database>');

-- If database exists, check if the schema exists
SELECT COUNT(*) AS schema_exists
FROM <database>.INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME = UPPER('<schema>');

-- If schema exists, check if the table exists
SELECT COUNT(*) AS table_exists
FROM <database>.INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = UPPER('<schema>')
  AND TABLE_NAME = 'LISTING_VALIDATION_RULES';
```

If the table already exists, skip sub-steps 2 and 3 and proceed directly to creating the rules (Step 2).

3. **Check the current role has the required privilege** for the object that needs to be created. Only check for the one privilege that applies — do not check all three:

| What needs to be created | Run this check |
|--------------------------|----------------|
| Database does not exist | `SHOW GRANTS ON ACCOUNT` → filter for `CREATE DATABASE` |
| Database exists, schema does not | `SHOW GRANTS ON DATABASE <database>` → filter for `CREATE SCHEMA` |
| Both exist, table does not | `SHOW GRANTS ON SCHEMA <database>.<schema>` → filter for `CREATE TABLE` |

Example for database creation:
```sql
SHOW GRANTS ON ACCOUNT;
-- Look for a row where privilege = 'CREATE DATABASE' AND grantee_name = CURRENT_ROLE()
```

If the required privilege is missing:
```
⛔ Role <current_role> is missing the <PRIVILEGE> privilege needed to create <object>.

To grant it:
  GRANT CREATE DATABASE ON ACCOUNT TO ROLE <current_role>;
  -- or
  GRANT CREATE SCHEMA ON DATABASE <database> TO ROLE <current_role>;
  -- or
  GRANT CREATE TABLE ON SCHEMA <database>.<schema> TO ROLE <current_role>;

Ask your account admin to run the appropriate GRANT, then retry.
```

**⚠️ STOP**: Do NOT proceed if the required privilege is missing.

4. **Confirm what will be created** before running any DDL. Present only the objects that do not yet exist:

```
⚠️ The following objects do not exist and will be created:
  • DATABASE: <database>        ← only if db_exists = 0
  • SCHEMA:   <database>.<schema>  ← only if schema_exists = 0

Reply YES to proceed, or provide a different location.
```

**⚠️ STOP**: Wait for explicit confirmation before continuing. Do not proceed on ambiguous responses.

5. **Create database and schema if needed:**
```sql
CREATE DATABASE IF NOT EXISTS <database>;
CREATE SCHEMA IF NOT EXISTS <database>.<schema>;
```

6. **Create the rules table:**
```sql
CREATE TABLE IF NOT EXISTS <database>.<schema>.LISTING_VALIDATION_RULES (
    name        VARCHAR(255)     NOT NULL,
    title       VARCHAR(500)     NOT NULL,
    config_type VARCHAR(100)     NOT NULL DEFAULT 'listing_validation_rule',
    props       VARIANT          NOT NULL,
    created_by  VARCHAR(255)     DEFAULT CURRENT_USER(),
    created_at  TIMESTAMP_NTZ    DEFAULT CURRENT_TIMESTAMP(),
    updated_at  TIMESTAMP_NTZ    DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT uq_rule_name UNIQUE (name)
);
```

**Output:** Table ready for storing validation rules at `<database>.<schema>.LISTING_VALIDATION_RULES`.

---

### Step 2: Gather One Rule from User

**Goal:** Collect the rule text for a single rule, auto-generate all other fields, and confirm with the user before inserting. Repeat for additional rules.

**Ask user** (as plain text output — do not use the ask_question tool):
```
Describe the rule you want to enforce (in plain language):
```

**Auto-generate the remaining fields** from the rule text:

| Field | How to derive |
|-------|---------------|
| `name` | Extract the core concept as a short `snake_case` identifier (e.g. `test_account_isolation`) |
| `title` | Title-case version of `name` (e.g. `TEST Account Isolation`) |
| `severity` | Default `ERROR`; use `WARNING` if the rule text uses softer language ("should", "recommend", "prefer") |
| `status` | Default `enabled` |
| `hints.fields_of_interest` | Match the rule text against the combined field list fetched at startup (standard manifest fields + `custom_attributes.<name>` entries from `SHOW AVAILABLE INTERNAL MARKETPLACE CONFIGS`). Include only fields that are semantically relevant to what the rule is checking. Omit `hints` entirely if no fields clearly apply. |

**Present the generated rule for review:**
```
Here's the rule I generated:

  name:      "test_account_isolation"
  title:     "TEST Account Isolation"
  severity:  ERROR (blocks publish on FAIL)
  status:    enabled (actively enforced)
  rule_text: "If the publisher account name starts with 'TEST_', then every named
              account in organization_targets.access and organization_targets.discovery
              must also start with 'TEST_'. Using all_internal_accounts: true is also
              a violation. If the publisher does not start with 'TEST_', rule does not apply."
  hints:     organization_targets.access, organization_targets.discovery

Confirm? (yes / edit / cancel)
```

**If user says edit** — ask which field(s) to change and apply them. Re-show the updated rule and ask for confirmation again. Repeat until confirmed or cancelled.

**⚠️ STOP**: Do not insert until the user confirms this rule.

---

### Step 3: Insert Rule

**Goal:** Insert the confirmed rule if it does not already exist (by `name`), then offer to add another.

**Actions:**

1. **Check if the rule name already exists:**
```sql
SELECT COUNT(*) AS already_exists
FROM <database>.<schema>.LISTING_VALIDATION_RULES
WHERE name = '<name>';
```

If it already exists:
```
⚠️  A rule named '<name>' already exists and will be skipped.
```
Skip the INSERT and go to step 3.

2. **Insert the rule:**

```sql
INSERT INTO <database>.<schema>.LISTING_VALIDATION_RULES
    (name, title, config_type, props)
SELECT '<name>', '<title>', 'listing_validation_rule', PARSE_JSON('<props_json>');
```

> **Note:** Escape any single quotes in `props_json` by doubling them: `'` → `''`.

Where `props_json` is (with hints):
```json
{"severity": "<ERROR|WARNING>", "status": "<enabled|shadow|disabled>", "rule_text": "<rule_text>", "hints": {"fields_of_interest": ["<field_1>", "<field_2>"]}}
```
or (without hints):
```json
{"severity": "<ERROR|WARNING>", "status": "<enabled|shadow|disabled>", "rule_text": "<rule_text>"}
```

3. **Ask whether to add another rule:**
```
✅ Rule '<name>' saved.

Add another rule? (yes / no)
```

- **yes** → return to Step 2 for the next rule
- **no** → proceed to Step 4

> To update an existing rule, use the management SQL in [Edit a Rule](#edit-a-rule).

---

### Step 4: Verify and Report

**Goal:** Confirm rules were saved and show a summary.

**Actions:**

1. **Query stored rules:**
```sql
SELECT
    name,
    title,
    config_type,
    props:severity::VARCHAR    AS severity,
    props:status::VARCHAR      AS status,
    props:rule_text::VARCHAR   AS rule_text,
    props:hints:fields_of_interest::VARCHAR AS hints,
    created_by,
    created_at
FROM <database>.<schema>.LISTING_VALIDATION_RULES
ORDER BY created_at DESC;
```

2. **Present success summary:**
```
✅ Validation rules created successfully!

Table: <database>.<schema>.LISTING_VALIDATION_RULES

| # | name | title | severity | status |
|---|------|-------|----------|--------|
| 1 | test_account_isolation | TEST Account Isolation | ERROR | enabled |
| ... | ... | ... | ... | ... |

To use these rules for listing validation:
→ Use the create-internal-listing-with-custom-validation skill
```

---

## Manage Existing Rules

Use this section when the user wants to view, edit, enable/disable, shadow, or delete rules. The table location (`<database>.<schema>.LISTING_VALIDATION_RULES`) was already resolved — use it for all queries below.

---

### View Rules

```sql
SELECT
    name,
    title,
    props:severity::VARCHAR    AS severity,
    props:status::VARCHAR      AS status,
    props:rule_text::VARCHAR   AS rule_text,
    props:hints:fields_of_interest::VARCHAR AS hints,
    created_by,
    created_at,
    updated_at
FROM <database>.<schema>.LISTING_VALIDATION_RULES
ORDER BY created_at DESC;
```

Display as a table. If no rows, inform the user the table is empty.

---

### Edit a Rule

**Ask the user** which rule to edit and what to change (rule_text, title, severity, status, or hints).

Confirm the proposed change with the user before executing:
```
Updating rule '<name>':
  <field>: <old_value> → <new_value>

Confirm? (yes / no)
```

**⚠️ STOP**: Get confirmation before running any UPDATE.

```sql
-- Update rule_text
UPDATE <database>.<schema>.LISTING_VALIDATION_RULES
SET props = OBJECT_INSERT(props, 'rule_text', '<new_rule_text>', TRUE),
    updated_at = CURRENT_TIMESTAMP()
WHERE name = '<rule_name>';

-- Update severity
UPDATE <database>.<schema>.LISTING_VALIDATION_RULES
SET props = OBJECT_INSERT(props, 'severity', '<ERROR|WARNING>', TRUE),
    updated_at = CURRENT_TIMESTAMP()
WHERE name = '<rule_name>';

-- Update title
UPDATE <database>.<schema>.LISTING_VALIDATION_RULES
SET title = '<new_title>',
    updated_at = CURRENT_TIMESTAMP()
WHERE name = '<rule_name>';

-- Update hints
UPDATE <database>.<schema>.LISTING_VALIDATION_RULES
SET props = OBJECT_INSERT(props, 'hints', PARSE_JSON('{"fields_of_interest": ["<field_1>", "<field_2>"]}'), TRUE),
    updated_at = CURRENT_TIMESTAMP()
WHERE name = '<rule_name>';
```

---

### Change Rule Status

Use `OBJECT_INSERT` to update the `status` field within the `props` VARIANT:

```sql
-- Enable a rule
UPDATE <database>.<schema>.LISTING_VALIDATION_RULES
SET props = OBJECT_INSERT(props, 'status', 'enabled', TRUE),
    updated_at = CURRENT_TIMESTAMP()
WHERE name = '<rule_name>';

-- Disable a rule (skipped entirely during validation)
UPDATE <database>.<schema>.LISTING_VALIDATION_RULES
SET props = OBJECT_INSERT(props, 'status', 'disabled', TRUE),
    updated_at = CURRENT_TIMESTAMP()
WHERE name = '<rule_name>';

-- Set to shadow mode (runs silently — never blocks)
UPDATE <database>.<schema>.LISTING_VALIDATION_RULES
SET props = OBJECT_INSERT(props, 'status', 'shadow', TRUE),
    updated_at = CURRENT_TIMESTAMP()
WHERE name = '<rule_name>';
```

**⚠️ STOP**: Confirm with user before executing any status change.

---

### Delete a Rule

Confirm with the user before deleting:
```
⚠️  This will permanently delete rule '<name>' ("<title>").
Are you sure? (yes / no)
```

**⚠️ STOP**: Do NOT delete without explicit confirmation.

```sql
DELETE FROM <database>.<schema>.LISTING_VALIDATION_RULES
WHERE name = '<rule_name>';
```

After deleting, run the View Rules query and show the updated table.

---

## Stopping Points

- ✋ **Table location**: Ask for table location before any other interaction — wait for response before asking intent
- ✋ **Intent**: Ask what the user wants to do — wait for response before proceeding
- ✋ **Step 1**: If current role is missing the required privilege (`CREATE DATABASE`, `CREATE SCHEMA`, or `CREATE TABLE`) — do NOT proceed
- ✋ **Step 2**: After presenting the auto-generated rule — confirm (or edit) before inserting
- ✋ **Edit a Rule**: Confirm proposed changes before executing UPDATE
- ✋ **Change Rule Status**: Confirm before executing status UPDATE
- ✋ **Delete a Rule**: Confirm before executing DELETE

**Resume rule:** Upon user approval, proceed directly to next step.

## Output

- **Table**: `<database>.<schema>.LISTING_VALIDATION_RULES` created/verified
- **Rules**: Inserted rules with name, title, config_type, and props (severity, status, rule_text, hints)
- **Summary**: Table of all stored rules with their configuration

## Rule Status Reference

| Status | Behavior |
|--------|----------|
| `enabled` | Rule is active — FAIL verdict is honored (ERROR blocks, WARNING warns) |
| `shadow` | Rule runs silently — results are reported but never block publish |
| `disabled` | Rule is skipped entirely during validation |

## Related Skills

- `create-internal-listing-with-custom-validation`: Validate a listing manifest against these rules via Cortex AI and create the listing
