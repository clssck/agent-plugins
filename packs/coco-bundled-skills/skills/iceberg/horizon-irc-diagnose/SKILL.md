---
name: horizon-irc-diagnose
description: "Diagnose and debug Horizon IRC — Snowflake's native Polaris-based Iceberg REST Catalog. This skill is specifically for Horizon IRC (Snowflake Polaris) only. Do NOT use for AWS Glue, Databricks Unity Catalog, or OpenCatalog. Triggers: test horizon IRC, debug horizon IRC, horizon IRC setup, diagnose horizon IRC, polaris setup, polaris catalog connectivity, PAT authentication horizon, horizon IRC not working, can't list namespaces horizon, table not visible horizon IRC, write access horizon IRC, write delegation, remote-signing, key-pair horizon IRC, JWT horizon, private key horizon."
---

# Horizon IRC Setup Tester

## When to Use

**This skill is for Horizon IRC (Snowflake Polaris) only.**

Do not ask the user which catalog type they are using — it is always Horizon IRC.
Do not route to any other catalog skill unless explicitly requested.

---

## Setup

**Load** the following reference (used across all sub-workflows):
- `references/api-reference.md`: Horizon IRC API endpoints, OAuth flow, URL format

---

## Workflow

```
Routing: One-shot or step-by-step?
       ↓
Collect: Account URL, Role, Database, Schema, Table, PAT
       ↓
  Summary confirmation
       ↓
  test/SKILL.md → Run 4-step diagnostic
       ↓
  ├─ step1 fail → connectivity-errors/SKILL.md
  ├─ step2 fail → authn-errors/SKILL.md
  ├─ step3 fail → authz-errors/SKILL.md
  ├─ step4 fail → table-access-errors/SKILL.md (→ storage-creds-errors if needed)
  └─ all pass  → Success summary + IRC base URL
```

---

## Out of Scope

- AWS Glue, Databricks Unity, OpenCatalog → Use their respective catalog integration skills
- Catalog-Linked Database (CLD) setup → Use `catalog-linked-database` skill
- External volumes → Use `iceberg-external-volume` skill

---

## Prerequisite Checks

### Input mode

**Ask**:
```
How would you like to provide your setup details?

A: One shot — I have everything ready, I'll provide it all at once
B: Step by step — walk me through each one
```

---

### One-Shot Mode (Option A)

**Ask**:
```
Please provide the following. Leave any field blank and I'll help you fill it in.

Account URL   (e.g. https://myorg-myaccount.snowflakecomputing.com):
Role          (e.g. MY_ROLE):
Database      (e.g. MY_DB):
Schema        (e.g. MY_SCHEMA):
Table         (e.g. MY_TABLE):
Auth secret   (paste PAT or JWT, or type 'create' to generate a PAT):
```

**For each blank field** → handle it using the corresponding step-by-step prereq below (Prereq 1–5) for that field only, then return to complete the summary.

**If Auth secret = 'create'** → follow [Prereq 5 Authentication](#prereq-5-authentication) below.

**If Account URL is blank** → auto-detect:
```sql
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME();
```
Construct URL as `https://<result>.snowflakecomputing.com`

**Once all 6 values are collected** → skip to [Prerequisites Confirmed](#prerequisites-confirmed).

---

### Step-by-Step Mode (Option B)

Walk through each prerequisite one at a time, in order.

### Prereq 1: Account URL

**Ask**:
```
Do you know your Snowflake account URL?
(e.g. https://myorg-myaccount.snowflakecomputing.com)

A: Yes — I have my account URL (e.g. https://myorg-myaccount.snowflakecomputing.com)
B: I know my org-account identifier (e.g. myorg-myaccount)
C: I'm not sure
```

**If A** → Record the URL as provided. Derive the account identifier from it by stripping the protocol and `.snowflakecomputing.com` suffix.

**If B** → Record the identifier and construct the URL as: `https://<org>-<account>.snowflakecomputing.com`

**If C** → Auto-detect by running:
```sql
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME();
```
Construct the URL as: `https://<result>.snowflakecomputing.com`

**⚠️ STOP**: Confirm both account identifier (`<org>-<account>`) and account URL before proceeding.

---

### Prereq 2: Role

**Ask**:
```
Which Snowflake role would you like to use for catalog access?

A: I have a role in mind
B: Show me available roles
```

**If B** → Run:
```sql
SHOW ROLES;
SHOW GRANTS TO USER <current_user>;
```

**Once role is provided** → Record it. Role validation (catalog privileges) will be surfaced naturally in Step 3 of the diagnostic.

**⚠️ STOP**: Confirm role name before proceeding.

---

### Prereq 3: Database

**Ask**:
```
Do you already have a Snowflake database to use as your Iceberg catalog?

A: Yes — I have a database ready
B: No — I need to create one
```

**If A** → Ask for the database name and record it.

**If B** → Walk through database creation using the active Snowflake connection:

**Step 3.1** — Ask for a name:
```
What would you like to name your database? (e.g. MY_DB)
```

**Step 3.2** — Storage:

Tell the user how storage will work and offer the opt-out — do not pose it as a required question:

```
I'll create <db_name> with Snowflake-managed storage — Snowflake stores the Iceberg files, so there's no external volume to set up. If you prefer to keep the files in your own cloud storage, just say so and I'll switch to setting up an external volume instead.
```

**If the user opts for their own cloud storage**, get the external volume to use:
```
What's the name of your external volume for Iceberg storage? (e.g. MY_EXTERNAL_VOLUME)
Not sure? Run: SHOW EXTERNAL VOLUMES;
```

- **If a volume exists** → record its name and use it as `<external_volume_name>` in the Step 3.3 own-storage template below.
- **If no external volume exists** → delegate:
```
⚠️ STOP: Please set up an external volume first using the `iceberg-external-volume` skill,
then return here.
```

**Step 3.3** — Create the database:

**Snowflake-managed storage (default):**
```sql
CREATE DATABASE <db_name>;
```

**If the user opted for their own cloud storage:**
```sql
CREATE DATABASE <db_name>
  EXTERNAL_VOLUME = '<external_volume_name>';
```

Verify it was created:
```sql
SHOW DATABASES LIKE '<db_name>';
```

**⚠️ STOP**: Confirm database exists before proceeding.

---

### Prereq 4: Schema & Table

**Ask**:
```
Do you already have a schema and Iceberg table in that database?

A: Yes — I have both ready
B: I have a schema but no table
C: I need to create both
```

**If A** → Ask for schema name and table name, record both.

**If B** → Ask for schema name and record it. Then create a table:

**Step 4.B.1** — Ask for a table name:
```
What would you like to name your Iceberg table? (e.g. MY_TABLE)
```

**Step 4.B.2** — Create it:

Pick the template that matches the database from Step 3.3.

**Snowflake-managed storage:**
```sql
CREATE ICEBERG TABLE IF NOT EXISTS <db>.<schema>.<table> (
    id         INT,
    name       STRING,
    created_at TIMESTAMP
)
CATALOG = 'SNOWFLAKE'
EXTERNAL_VOLUME = 'SNOWFLAKE_MANAGED';
```

**If the user opted for their own cloud storage (Step 3.2):** omit the `EXTERNAL_VOLUME` clause so the table inherits the database's external volume.
```sql
CREATE ICEBERG TABLE IF NOT EXISTS <db>.<schema>.<table> (
    id         INT,
    name       STRING,
    created_at TIMESTAMP
)
CATALOG = 'SNOWFLAKE';
```

Verify:
```sql
SHOW ICEBERG TABLES IN SCHEMA <db>.<schema>;
```

**If C** → Create schema first, then table:

**Step 4.C.1** — Ask for names:
```
What would you like to name your schema? (e.g. MY_SCHEMA)
What would you like to name your Iceberg table? (e.g. MY_TABLE)
```

**Step 4.C.2** — Create schema:
```sql
CREATE SCHEMA <db>.<schema>;
```

**Step 4.C.3** — Create table:

Pick the template that matches the database from Step 3.3.

**Snowflake-managed storage:**
```sql
CREATE ICEBERG TABLE IF NOT EXISTS <db>.<schema>.<table> (
    id         INT,
    name       STRING,
    created_at TIMESTAMP
)
CATALOG = 'SNOWFLAKE'
EXTERNAL_VOLUME = 'SNOWFLAKE_MANAGED';
```

**If the user opted for their own cloud storage (Step 3.2):** omit the `EXTERNAL_VOLUME` clause so the table inherits the database's external volume.
```sql
CREATE ICEBERG TABLE IF NOT EXISTS <db>.<schema>.<table> (
    id         INT,
    name       STRING,
    created_at TIMESTAMP
)
CATALOG = 'SNOWFLAKE';
```

Verify:
```sql
SHOW ICEBERG TABLES IN SCHEMA <db>.<schema>;
```

**⚠️ STOP**: Confirm schema and table exist before proceeding.

---

### Prereq 5: Authentication

**Ask**:
```
How are you authenticating to Horizon IRC?

A: Personal Access Token (PAT) — I have one ready
B: Personal Access Token (PAT) — create one for me
C: Key-pair authentication — I have a JWT ready
D: Key-pair authentication — I need help generating a JWT
```

**If A** → Record that PAT is ready.

**If B** → Create one via SQL:
```sql
ALTER USER <current_user> ADD PROGRAMMATIC ACCESS TOKEN HORIZON_PAT_<YYYYMMDD_HHMMSS>;
```
**Immediately after the SQL executes, output the full token value in a code block in your response** — do not rely on the user reading it from the result table (it may be truncated):
```
<full_token_value_from_result>
```
Tell the user: "Copy the token above — it will not be shown again."

**If C** → Record the JWT. It will be used as `client_secret` in Step 2. Note: `snowsql`-generated JWTs are valid for up to 1 hour (Snowflake caps key-pair JWT lifetime at 1 hour regardless of the `exp` claim). Regenerate if held longer.

**If D** → Generate a JWT using SnowSQL:
1. Follow the instructions in [Generating a JWT (Key-Pair Auth)](references/api-reference.md#generating-a-jwt-key-pair-auth) and run the `snowsql --generate-jwt` command.
2. Copy the JWT printed to stdout.
3. Paste it here (valid for up to 1 hour; regenerate if held longer).

**⚠️ STOP**: Confirm auth secret (PAT or JWT) is ready before proceeding.

---

### Prerequisites Confirmed

**Present summary**:
```
Prerequisites Verified:
═══════════════════════════════════════════════════════════
✓ Account Identifier: <org>-<account>
✓ Account URL:        <account_url>
✓ Role:    <role_name>
✓ Database: <db_name>
✓ Schema:  <schema_name>
✓ Table:   <table_name>
✓ Auth secret: Ready (PAT or JWT)
═══════════════════════════════════════════════════════════
```

**⚠️ STOP**: "Does everything look correct? Ready to run the diagnostic?"

→ **Load** `test/SKILL.md`

---

## Output

On success: confirmation that the Horizon IRC endpoint is reachable, authentication works (PAT or JWT), namespaces are listable, and table metadata loads — along with the IRC base URL for use by external engines (Spark, Trino, Flink, etc.).

---

## Stopping Points

- ✋ Input mode selection: one-shot or step-by-step
- ✋ Prereq 1: Account identifier and URL confirmed
- ✋ Prereq 2: Role confirmed
- ✋ Prereq 3: Database exists and name confirmed
- ✋ Prereq 4: Schema and table exist and names confirmed
- ✋ Prereq 5: PAT or JWT ready
- ✋ Prerequisites summary: Approval before running test

**Resume rule:** Upon user approval ("yes", "looks good", "proceed"), continue to next step without re-asking.

---

## Documentation

- [Horizon IRC Overview](https://docs.snowflake.com/en/user-guide/tables-iceberg-query-using-external-query-engine-snowflake-horizon)
- [Horizon IRC Write Access](https://docs.snowflake.com/en/LIMITEDACCESS/iceberg/tables-iceberg-write-using-external-write-engine-snowflake-horizon)
- [Personal Access Tokens](https://docs.snowflake.com/en/user-guide/key-pair-auth#personal-access-tokens)
- [Iceberg REST Catalog API](https://iceberg.apache.org/spec/#rest-catalog-api)
