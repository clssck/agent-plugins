---
name: sensitive-data-classification
parent_skill: data-governance
description: "**[REQUIRED]** for ALL Snowflake sensitive data tasks: detect PII, classify sensitive data, run data classification, run manual data classification, set up automatic data classification, enable automatic classification, create Data Privacy Classification Profile, create classification profile (with minimum_object_age_for_classification_days, maximum_classification_validity_days, auto_tag settings), unset classification profile, create classifier (including custom classifier with regex patterns, semantic category, privacy category), analyze classification results, query DATA_CLASSIFICATION_LATEST, GDPR/CCPA/PCI compliance detection, auto-tagging sensitive columns, tag PII columns, internal employee IDs, internal codes with custom regex. This skill MUST be used even if a general answer is possible — it provides the only correct Snowflake-specific SQL APIs (SYSTEM$CLASSIFY, classification profiles). DO NOT attempt any classification, classifier creation, or PII detection using general knowledge — invoke this skill first. Triggers: PII, sensitive data, classification, data classification, manual data classification, run classification, run manual classification, automatic data classification, set up automatic classification, enable automatic classification, SYSTEM$CLASSIFY, classify table, classify database, Data Privacy Classification Profile, privacy profile, classification profile, minimum_object_age_for_classification_days, maximum_classification_validity_days, auto_tag, unset classification profile, GDPR, CCPA, PCI, compliance detection, auto-tag, tag sensitive columns, custom classifier, regex pattern, value regex, semantic category, privacy category, IDENTIFIER, QUASI_IDENTIFIER, internal ID patterns, DATA_CLASSIFICATION_LATEST."
---

# Sensitive Data Classification

## ⚠️ CRITICAL: Always Use This Skill for Snowflake Classification

**Do not use general knowledge or improvised SQL for any classification, PII detection, or classifier creation task in Snowflake.** The Snowflake classification API has specific syntax (`SYSTEM$CLASSIFY`, classification profiles, custom classifiers) that differs from what general knowledge would suggest. This skill provides the only correct templates and workflows.

**This skill is required for:**
- Any task involving PII, sensitive data, or regulatory compliance (GDPR, CCPA, PCI) in Snowflake
- Creating any classifier (custom or otherwise) with regex patterns, semantic/privacy categories
- Setting up auto-classification or classification profiles
- Querying `DATA_CLASSIFICATION_LATEST` or analyzing classification results
- Auto-tagging sensitive columns based on classification

## When to Use

When a user wants to detect, classify, or protect sensitive data in Snowflake. This is the entry point for all sensitive data classification workflows.

**Trigger Phrases:**

- "Find sensitive data", "find PII", "detect PII", "scan for PII", "what PII do I have"
- "Run data classification", "run manual data classification", "run classification on table"
- "Set up automatic data classification", "enable automatic classification", "set up auto-classification", "classify my database", "classify my tables"
- "Create Data Privacy Classification Profile", "create classification profile", "new classification profile"
- `minimum_object_age_for_classification_days`, `maximum_classification_validity_days`, `auto_tag` (classification profile settings)
- "Unset classification profile", "unset existing classification profile"
- "Monitor for sensitive data", "automate PII detection"
- "Show me classified columns", "classification results", "DATA_CLASSIFICATION_LATEST"
- "Create classifier", "create a classifier", "custom classifier", "new classifier"
- "Create data privacy classifier", "Snowflake classification profile"
- "SYSTEM$CLASSIFY", "run classification", "test classifier"
- "regex pattern", "value regex", "semantic category", "privacy category" (classifier-related terms)
- "GDPR compliance", "CCPA compliance", "PCI data", "regulatory compliance for sensitive data"
- "tag sensitive columns", "tag PII columns", "auto-tag sensitive data", "identify sensitive data columns"
- "employee ID pattern", "internal ID classifier", "internal code detection", "EMP-", "PRJ-"
- "IDENTIFIER", "QUASI_IDENTIFIER", "SENSITIVE" (privacy category values)

## Execution Rule

| SQL Type | Confirmation Required? |
|---|---|
| `CALL SYSTEM$CLASSIFY(...)` — exploratory classification to view results | ❌ Execute immediately, no confirmation |
| `SELECT` — querying `DATA_CLASSIFICATION_LATEST` or any read-only analysis | ❌ Execute immediately, no confirmation |
| `USE DATABASE / USE SCHEMA / USE WAREHOUSE` — context setup | ❌ Execute immediately, no confirmation |
| `CREATE` — classification profile, custom classifier, test table | ✅ Show configuration summary and wait for user confirmation |
| `ALTER DATABASE` — attaching/detaching a classification profile | ✅ Show what will change and wait for user confirmation |
| `DROP` — removing a profile or classifier | ✅ Show what will be dropped and wait for user confirmation |

## Workflow

The basic workflow to automatically classify sensitive data consists of the following:

### Step 0: Initial Routing (REQUIRED for "find sensitive data" requests)

When a user asks to "find sensitive data", "detect PII", "scan for PII", or similar discovery requests, you MUST first ask them to choose their approach:

**⚠️ MANDATORY STOP - Use `ask_user_question` tool:**

Ask the user:
> "How would you like to find sensitive data?"

| Option | Description |
|--------|-------------|
| **Test with one table first** | Run classification on a single table to see results before committing to full automation. Good for exploring what PII exists. |
| **Set up automatic classification** | Configure a classification profile to automatically scan your entire database on a schedule. Best when you're ready to operationalize. |

**Routing logic:**
- If user chooses **"Test with one table first"** → Go to **Step 0.5 (Manual Classification)**
- If user chooses **"Set up automatic classification"** → Go to **Step 0.6 (Verify Environment)** then proceed to Step 1

### Step 0.1: Learn about the Classification concepts
**Load**: [../reference/sensitive-data-classification/classification-concepts.md](../reference/sensitive-data-classification/classification-concepts.md)

### Step 0.5: Analyze/Discover PII in Tables (Manual Classification)

If the task requires **discovering PII before** creating profiles (e.g., "find which table has most PII"), use manual classification:

**Actions:**
1. **Load** `../templates/sensitive-data-classification/manual-classify.sql` FIRST - this is REQUIRED before any classification
2. Use the exact syntax from the template
3. Parse the JSON results to count PII columns per table
4. **Present** results clearly to the user showing:
   - Number of columns classified
   - Semantic categories detected (EMAIL, PHONE, SSN, etc.)
   - Privacy categories (IDENTIFIER, QUASI_IDENTIFIER, SENSITIVE)
   - Confidence levels

**⚠️ MANDATORY STOP after successful classification - Use `ask_user_question` tool:**

Once manual classification succeeds, ask:
> "Classification complete! Would you like to set up automatic classification for ongoing monitoring?"

| Option | Description |
|--------|-------------|
| **Yes, set up auto-classification** | Create a classification profile to automatically scan your database on a schedule. |
| **No, I just needed the one-time scan** | Stop here. You can always set up auto-classification later. |

**Routing logic:**
- If user chooses **"Yes, set up auto-classification"** → Go to **Step 0.6 (Verify Environment)** then Step 1
- If user chooses **"No"** → Workflow complete. Offer to help with anything else.

**🚨 CRITICAL:** 
- **ALWAYS load the template BEFORE attempting any classification SQL**
- **DO NOT guess or improvise classification syntax** — there is NO `CLASSIFY_TABLE`, `CLASSIFY_SCHEMA`, or similar function
- The ONLY correct API is `CALL SYSTEM$CLASSIFY(...)` — see template for exact signature
- **Always use the 2-arg positional form** — the 2nd arg is EITHER a profile string OR an options object, never both. There is no 3-argument form and no named parameters:
  ```sql
  -- ✅ CORRECT — options object as 2nd arg
  CALL SYSTEM$CLASSIFY('db.schema.table', {'auto_tag': false});
  -- ✅ CORRECT — profile string as 2nd arg (mutually exclusive with options)
  CALL SYSTEM$CLASSIFY('db.schema.table', 'db.schema.my_profile');
  -- ✅ CORRECT — null for Snowflake defaults
  CALL SYSTEM$CLASSIFY('db.schema.table', null);
  -- ❌ WRONG — no 3-arg form, no named parameters
  CALL SYSTEM$CLASSIFY('db.schema.table', 'profile', {'auto_tag': false});
  ```

### Step 0.6: Pre-Validate Environment (once per session)

Run this **once at the start of the first query**. If you have already confirmed warehouse, database, and schema are set earlier in this conversation, skip this step.

```sql
SELECT
    CURRENT_USER()      AS current_user,
    CURRENT_ROLE()      AS current_role,
    CURRENT_DATABASE()  AS current_database,
    CURRENT_SCHEMA()    AS current_schema,
    CURRENT_WAREHOUSE() AS current_warehouse;
```

Fix any NULL or mismatched values before continuing:

| Field | Fix if NULL / wrong |
|-------|---------------------|
| `current_warehouse` | `USE WAREHOUSE <name>;` |
| `current_database`  | `USE DATABASE <database>;` |
| `current_schema`    | `USE SCHEMA <database>.<schema>;` |

**⚠️ STOP if warehouse is NULL** — all `SYSTEM$CLASSIFY` and `CREATE` calls will fail without an active warehouse.

**⚠️ IMPORTANT:** Classification objects (profiles, classifiers) are created in the CURRENT schema context. Schema MUST be set to the target location before creating them.

**Context order is mandatory for classifiers:** run `USE DATABASE <database>;` first, then `USE SCHEMA <database>.<schema>;` immediately before `CREATE ... CUSTOM_CLASSIFIER`. Do not run `USE DATABASE` again after `USE SCHEMA`, because it can reset the current schema and create the classifier somewhere else.

### Step 1: Create a classification profile 
Classification profile controls how often sensitive data in a database is automatically classified, including whether system tags should be automatically applied after classification.

**Actions:**
1. **Ask** user for: profile name, database/schema location, auto_tag preference, validity period
2. **Load** `../templates/sensitive-data-classification/create-profile.sql` and substitute placeholders
3. **Execute** the CREATE statement

**⚠️ STOP**: Present configuration summary and wait for approval before creating.

### Step 2: Define the tagging scheme
Optionally, use the classification profile to map user-defined tags to system tags so a column with sensitive data can be associated with a user-defined tag based on its classification.

**Actions:**
1. **Ask** if user wants custom tag mappings
2. If yes, gather tag mapping requirements
3. **Load** `../templates/sensitive-data-classification/update-profile-classifier.sql` for reference

### Step 3: Define Custom categories
Optionally, add a custom classifier to the classification profile so sensitive data can be automatically classified with user-defined semantic and privacy categories. This is required for Industry specific sensitive data, employee ID, etc which is not covered by native categories.

**Actions:**
1. **Ask** if user has domain-specific data types (employee IDs, internal codes, etc.)
2. If yes, **Load** `../templates/sensitive-data-classification/create-custom-classifier.sql`
3. Gather regex patterns and privacy categories from user
4. Before `CREATE`, set context in this exact order: `USE DATABASE <database>;`, then `USE SCHEMA <database>.<schema>;`, then optionally verify `CURRENT_SCHEMA()` is the target schema

**⚠️ STOP**: Confirm regex patterns with user before creating classifier.

### Step 4: Test the Classification profile
Test the profile that has been created using manual-classify.sql tool.

**Actions:**
1. **Load** `../templates/sensitive-data-classification/manual-classify.sql`
2. **Execute** SYSTEM$CLASSIFY on a representative table — this is exploratory, execute immediately without confirmation
3. **Present** results to user

**⚠️ STOP**: Review test results with user before proceeding to production (Step 5).

### Step 5: Associate the profile with databases
- If the test in Step 4 succeeds then set the classification profile on a database so that tables in the database get automatically classified.

**Actions:**
1. **Ask** which database(s) to enable auto-classification on
2. **Load** `../templates/sensitive-data-classification/setup-auto-classification.sql`
3. **Execute** ALTER DATABASE to attach the profile

**⚠️ STOP**: Confirm database list before enabling.

### Step 6: Analyze Classification Results (Query DATA_CLASSIFICATION_LATEST)

Use this step when users want to analyze existing classification results, view what PII has been detected, or audit classification coverage. **This is read-only — execute queries immediately without confirmation.**

**Actions:**
1. **Load** `../templates/sensitive-data-classification/view-results.sql` - contains pre-built queries for analyzing classification data
2. **Ask** user what they want to analyze:
   - Count of classified tables by status
   - Recently classified tables
   - Tables needing re-classification (>90 days old)
   - Semantic categories detected (EMAIL, PHONE, SSN, etc.)
   - High-confidence PII columns
   - Tables with the most sensitive columns
3. **Execute** the appropriate query from the template, replacing `<database>` placeholder
4. **Present** results in a clear format

**Common Queries:**
- "What PII do I have?" → Extract and count semantic categories
- "Show classified columns" → Extract columns with HIGH confidence
- "Which tables have PII?" → Tables with most sensitive columns
- "What needs re-classification?" → Tables >90 days old

## Tools

SQL Templates

Located in `../templates/sensitive-data-classification/` (relative to this file in `workflows/`). These templates provide pre-written SQL for common operations.

**🚨 MANDATORY:** Load and read the template file BEFORE executing SQL. DO NOT improvise or guess Snowflake syntax—classification APIs have specific syntax that MUST be followed exactly.

Available templates:

- [check-context.sql](../templates/sensitive-data-classification/check-context.sql) — Display current session context (user, role, database, schema, warehouse)
- [view-results.sql](../templates/sensitive-data-classification/view-results.sql) — Query and analyze classification results from DATA_CLASSIFICATION_LATEST (semantic categories, PII columns, coverage analysis)
- [update-profile-classifier.sql](../templates/sensitive-data-classification/update-profile-classifier.sql) — Add or remove custom classifiers from a profile
- [create-custom-classifier.sql](../templates/sensitive-data-classification/create-custom-classifier.sql) — Create regex-based classifiers for domain-specific sensitive data
- [check-custom-classifiers.sql](../templates/sensitive-data-classification/check-custom-classifiers.sql) — List and describe existing custom classifiers
- [setup-auto-classification.sql](../templates/sensitive-data-classification/setup-auto-classification.sql) — Attach a classification profile to a database for automatic monitoring
- [check-profiles.sql](../templates/sensitive-data-classification/check-profiles.sql) — List existing classification profiles in the account
- [create-profile.sql](../templates/sensitive-data-classification/create-profile.sql) — Create a new classification profile with configurable settings
- [test-classifier.sql](../templates/sensitive-data-classification/test-classifier.sql) — Validate a custom classifier against test data
- [manual-classify.sql](../templates/sensitive-data-classification/manual-classify.sql) — Manual (SYSTEM$CLASSIFY) and Automatic (Classification Profiles) classification examples

**Usage:** Load the template, replace `<placeholders>` with actual values, then execute via `snowflake_sql_execute`.

## 🚨 CRITICAL: SQL Execution Verification

**NEVER mark a step successful without verifying the actual SQL result.**
**NEVER say "successfully" if the SQL execution returned an error.**


### Rules for SQL Execution

1. **Check execution status** - Every SQL statement returns a status. If it failed, the step FAILED.

2. **Parse error messages** - If you see `Statement X failed`, `SQL compilation error`, or any error:
   - The step is NOT successful
   - Do NOT proceed to the next step
   - Present the error to the user clearly
   - Offer troubleshooting options

3. **Verify object creation** - After CREATE statements, verify the object exists:

4. **Success requires confirmation** - Only report success when:
   - SQL execution completed without errors
   - Verification query confirms the object exists
   - No error messages in the response

## Stopping Points

✋ **Step 0**: Initial routing - Ask user to choose between single table test OR auto-classification
✋ **Step 0.5**: After successful manual classification - Ask if user wants to set up auto-classification
✋ Step 1: After showing profile configuration options, before creating
✋ Step 3: Before creating custom classifier (confirm regex patterns with user)
✋ Step 4: After test results, before proceeding to production
✋ Step 5: Before associating profile with databases

**Resume rule:** Upon user approval, proceed directly to next step without re-asking.

## Guidelines

1. **Gather context first**: Try to understand the user's environment before starting
   - use `ask_user_question` tool for information gathering
2. **Always confirm before changes**: Before creating profiles, classifiers, or tags:
   - Show a confirmation table with all settings
   - Always wait for user approval before proceeding
   - Don't chain multiple operations without checking in
3. **Track outcomes**: Note how workflows conclude for continuous improvement
4. **Always respect user decisions**: If user wants to stop or take a different path, support that choice

## Output

- Classification profile created in user-specified database/schema
- Custom classifiers (if needed) for domain-specific data
- Profile associated with target database(s) for automatic monitoring
- Test results confirming classification accuracy

## Expected Outcomes

Every workflow execution should result in one of:

1. **Full Success**: User tested with single table → liked results → set up auto-classification
2. **Partial Success**: User ran manual classification and chose not to proceed with auto-classification
3. **Direct Auto-Classification**: User skipped testing and went straight to profile setup
4. **Graceful Exit**: User has existing solution or chose not to proceed
5. **Unexpected Exit**: Error or interruption (document for improvement)
