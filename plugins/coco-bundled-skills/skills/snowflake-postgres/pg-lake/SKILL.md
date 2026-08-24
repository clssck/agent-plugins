---
name: snowflake-postgres-pg-lake
description: "pg_lake setup and usage on Snowflake Postgres instances: Postgres-resident Iceberg tables, POSTGRES_EXTERNAL_STORAGE integrations, COPY TO/FROM S3 from Postgres, moving data between Postgres and Snowflake. Triggers: 'pg_lake', 'postgres iceberg', 'pg iceberg', 'postgres to iceberg', 'iceberg from postgres', 'POSTGRES_EXTERNAL_STORAGE', 'postgres COPY to S3', 'postgres export to S3', 'move data postgres to snowflake'. Do NOT use for general Snowflake Iceberg (catalog integrations, external volumes, CLD) — those are handled by the top-level `iceberg` skill."
parent_skill: snowflake-postgres
---

# Snowflake Postgres - pg_lake

## When to Load

From `snowflake-postgres/SKILL.md` when intent is PG_LAKE.

**Note:** All `<SKILL_DIR>` placeholders below refer to the **snowflake-postgres/** directory (absolute path).

## Intent Detection

| Intent | Trigger | Workflow |
|--------|---------|----------|
| **SETUP** | "set up pg_lake", "storage integration", "enable pg_lake", "configure S3" | Full setup flow (Steps 1-5) |
| **USE** | "iceberg table", "COPY to S3", "export data", "parquet", "list iceberg tables", "pg_incremental", "incremental sync", "sync postgres to iceberg", "sync table to iceberg" | Load references, verify setup |
| **READ-FROM-SNOWFLAKE** | "read pg_lake in snowflake", "pg to snowflake iceberg", "catalog integration for pg_lake", "expose pg_lake to snowflake", "catalog linked database", "query postgres from snowflake" | See READ-FROM-SNOWFLAKE Workflow — requires managed-storage PG instance |

---

## SETUP Workflow

The setup flow crosses three systems (Snowflake SQL → AWS console → Postgres SQL) with two mandatory stopping points. The agent guides through each step and verifies before proceeding.

**Cloud platforms.** This workflow walks AWS/S3 in detail (Steps 2–3 cover IAM role ARN, trust policy, `update-aws` CLI). Azure is also supported for pg_lake, but the storage integration shape differs — Azure tenant + consent URL instead of an IAM role. If the PG instance is on Azure, fetch https://docs.snowflake.com/en/user-guide/data-load-azure-config (or run `cortex search docs "azure storage integration"`) for the current Azure setup and adapt Steps 2–3 accordingly. The high-level sequence (create integration → attach to instance → enable pg_lake) is the same across clouds.

**Why Snowflake IAM is involved:** The Postgres instance runs inside Snowflake's infrastructure and has no direct AWS credentials. To access a customer's S3 bucket, pg_lake uses Snowflake's storage integration — Snowflake assumes the customer's IAM role on behalf of the PG instance. The data flows directly from PG compute to S3, but the *authentication* goes through Snowflake's IAM trust chain. Public S3 buckets and URLs don't need any of this.

If the user asks why Snowflake is involved, explain this. If they don't have an S3 bucket and just want to try pg_lake, they can skip the storage integration entirely and use managed storage (`CREATE TABLE ... USING iceberg` without a location) or load from public URLs.

### Step 0: Determine Setup Path and Present Plan

Ask the user which path fits their situation:

| User has... | Path |
|-------------|------|
| S3 bucket + IAM role ready | Full setup (Steps 1-5) |
| No S3 bucket, just wants to try pg_lake | Enable pg_lake (Step 5) and query **public URLs** via foreign tables — no storage integration needed. Managed storage (`CREATE TABLE ... USING iceberg` without a location) requires the platform to have provisioned an internal bucket for the instance, which may not be available on all instances yet. If it fails with a 403, the user needs a customer S3 bucket. |
| S3 bucket but no IAM role | Help them create one. They need: an IAM role with S3 read/write permissions, trusted by Snowflake's service account, with **12-hour max session duration**. Provide the AWS CLI commands or console steps. |

**After determining the path, present the full plan and STOP. Do not run any commands or call any tools in this response.**

Example for the full setup path:

```
Here's the plan for setting up pg_lake on <INSTANCE_NAME>:

1. **Check prerequisites** — verify saved connection, Snowflake role, pg_lake availability
2. **Create storage integration** (Snowflake SQL, requires ACCOUNTADMIN) — links your S3 bucket to Snowflake via IAM role
3. **Configure AWS trust policy** — grants Snowflake permission to assume your IAM role so it can read/write your S3 bucket on behalf of Postgres (I'll auto-check if it's already done, and can run the CLI commands for you if available)
4. **Attach integration to instance** (Snowflake SQL) — connects the integration to your Postgres instance
5. **Enable pg_lake on Postgres** — install extensions, set S3 prefix, verify access

Steps 2 and 3 are the main stopping points — Step 2 creates cloud resources and Step 3 may need manual AWS work.

Ready to proceed? I can also answer any questions.
```

**⚠️ STOP HERE. Do not execute any commands. Do not proceed to Step 1. End your response after presenting the plan.** The user must reply before you continue. This is a hard stop — the setup creates cloud resources and modifies IAM, so the user needs a chance to review, ask questions, or adjust the plan.

**Once the user confirms, create todos to track progress** (adjust if steps are skipped):

```
1. Check prerequisites            [in_progress]
2. Create storage integration      [pending]
3. Configure AWS trust policy      [pending]
4. Attach integration to instance  [pending]
5. Enable pg_lake on Postgres      [pending]
```

Mark each `in_progress` before starting and `completed` when done. Add new todos if issues come up mid-workflow.

### Step 1: Prerequisites

**Check saved connection exists:**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py --list
```

**Check Snowflake role:**
The user must have ACCOUNTADMIN role for storage integration operations.

**Check pg_lake availability on the Postgres instance:**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --check-extensions --connection-name <PG_CONNECTION> --json
```

If pg_lake is not available, the instance may need an upgrade or pg_lake is not enabled for the account.

### Step 2: Create Storage Integration (Snowflake SQL)

**⚠️ MANDATORY STOPPING POINT** — Requires ACCOUNTADMIN role. IAM trust policy must be updated after this step.

Gather from user:
- **S3 bucket name** and path (must be in same AWS region as Snowflake account)
- **IAM role ARN** — user must have created an IAM role with S3 access

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  create \
  --name <INTEGRATION_NAME> \
  --role-arn <IAM_ROLE_ARN> \
  --locations s3://<BUCKET>/<PATH>/ \
  --snowflake-connection <SF_CONNECTION> \
  --json
```

If the result returns `already_exists: true`, the integration was created previously. Ask the user whether to use the existing one (skip to `describe`) or drop and recreate it. Don't fail — this is common in retry scenarios.

Then get the IAM values for the trust policy:

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  describe \
  --name <INTEGRATION_NAME> \
  --snowflake-connection <SF_CONNECTION>
```

The describe command writes sensitive values (IAM_USER_ARN, EXTERNAL_ID) to a secure temp file. Read the file path from the output, then read its contents to guide the user.

### Step 3: Check and Update AWS Trust Policy

**If check-aws or update-aws fails with expired or missing credentials**, the user may need to pick the right AWS profile. List available profiles:

```bash
aws configure list-profiles
```

If the right profile is obvious from the name (e.g., account ID in the profile name matches the role ARN), suggest it. Otherwise, use `ask_user_question` to let the user pick:

```
Which AWS profile has access to account <ACCOUNT_ID from role ARN>?
Options: [list each profile from aws configure list-profiles]
```

Pass the chosen profile with `--aws-profile <PROFILE>` on check-aws and update-aws.

**First, check if the trust policy is already configured:**

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  check-aws \
  --role-arn <IAM_ROLE_ARN> \
  --expected-principal <STORAGE_AWS_IAM_USER_ARN from Step 2> \
  --expected-external-id "<STORAGE_AWS_EXTERNAL_ID from Step 2>" \
  [--aws-profile <PROFILE>] \
  --json
```

This check tries boto3 first, then AWS CLI (falls back to CLI even if boto3 fails with expired creds). The result includes `cli_available: true/false` so you know whether CLI commands can be offered.

**Interpret the result:**

| `all_configured` | `cli_available` | Action |
|------------------|-----------------|--------|
| `true` | any | Skip to Step 4 — trust policy is already set up |
| `false` | `true` | Offer to run the AWS CLI commands for the user (see Path A below) |
| `false` | `false` | Show manual console instructions (see Path B below) |
| Check failed + `auth_error` | `true` | Credentials expired. List profiles (`aws configure list-profiles`), help user pick the right one, and retry with `--aws-profile`. If re-auth needed, suggest `aws sso login --profile <PROFILE>` |
| Check failed | `true` | Offer CLI commands — can't verify current state but can set it |
| Check failed | `false` | Show manual console instructions |

---

#### Path A: AWS CLI Available (`cli_available: true`)

**⚠️ MANDATORY STOPPING POINT** — This modifies the IAM role. Ask permission first.

Tell the user:

```
I can update your AWS trust policy and session duration automatically.
This will:
  - Update the trust policy on <role_name> to allow Snowflake to assume it
  - Set the maximum session duration to 12 hours

Sensitive values (IAM ARN, External ID) are read from a secure file — they won't appear in chat.

Want me to go ahead, or would you prefer to do it manually in the AWS Console?
```

If user approves, run `update-aws` (reads IAM values from the describe output file — nothing sensitive in the command):

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  update-aws \
  --role-arn <IAM_ROLE_ARN> \
  --sensitive-file <path from describe output in Step 2> \
  [--aws-profile <PROFILE>] \
  --json
```

After running, re-run `check-aws` to verify all checks pass. If `all_configured: true`, proceed to Step 4.

---

#### Path B: No CLI Available — Manual Console Instructions

**⚠️ MANDATORY STOPPING POINT** — User must complete this in AWS Console.

Present the following to the user:

**Part A: Update Trust Policy**

1. Open AWS Console → IAM → Roles
2. Search for and click on your IAM role: `<role_name>`
3. Click the **"Trust relationships"** tab
4. Click **"Edit trust policy"**
5. Replace or add the following statement:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "<STORAGE_AWS_IAM_USER_ARN>"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "<STORAGE_AWS_EXTERNAL_ID>"
        }
      }
    }
  ]
}
```

6. Click **"Update policy"**

> **If your role already has a trust policy**: Add the Snowflake statement to the existing `Statement` array — don't replace other trust relationships you need.

**Part B: Set Maximum Session Duration (CRITICAL)**

This is a *separate setting* from the trust policy — do not skip this step.

1. Still on your IAM role page, click the **"Edit"** button (top right of Summary section)
2. Scroll down to **"Maximum session duration"**
3. Select **12 hours** (the maximum)
4. Click **"Save changes"**

> **Why 12 hours?** pg_lake operations can run for extended periods. The default 1-hour limit causes silent credential expiration failures mid-operation.

---

**Common Mistakes (both paths):**

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Forgot to set 12-hour session duration | Operations fail silently after ~1 hour | Edit role → Set max session to 12 hours |
| Replaced entire trust policy | Broke other services using this role | Add statement to array, don't replace |
| Wrong role updated | Access denied errors | Verify role ARN matches the one in storage integration |
| External ID has extra quotes | External ID mismatch error | External ID value should NOT have extra quotes |

---

**Verification:** After the user completes Path A or Path B, re-run `check-aws` to confirm `all_configured: true`. If the check can't run, ask the user to confirm:

- [ ] Trust policy updated with correct IAM User ARN and External ID
- [ ] Maximum session duration set to 12 hours
- [ ] S3 bucket is in same AWS region as Snowflake account

Wait for confirmation before proceeding.

### Step 4: Attach Integration to Instance (Snowflake SQL)

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  attach \
  --instance <INSTANCE_NAME> \
  --integration <INTEGRATION_NAME> \
  --snowflake-connection <SF_CONNECTION> \
  --json
```

Verify the attachment:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  verify \
  --instance <INSTANCE_NAME> \
  --snowflake-connection <SF_CONNECTION> \
  --json
```

### Step 5: Enable pg_lake on Postgres

Ensure the instance is ready before connecting (auto-resumes if suspended):
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
  --ensure-ready --instance-name <INSTANCE_NAME> \
  --snowflake-connection <SF_CONNECTION>
```

Enable the extension:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --enable-extensions --connection-name <PG_CONNECTION> --json
```

#### If using customer-managed S3 (Steps 1-4 were completed):

Set the S3 location prefix (session-level — the platform handles persistence):
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --set-config s3://<BUCKET>/<PATH>/ \
  --connection-name <PG_CONNECTION> --json
```

The GUC (`pg_lake_iceberg.default_location_prefix`) is `PGC_SUSET` — can only be SET at session level by a superuser. In managed Snowflake Postgres, the platform persists it via `postgresql.conf` when the storage integration is attached. Check `persisted_by_platform` in the result — if `false`, the user may need to re-set after reconnection.

Verify S3 access through pg_lake. **Always pass `--prefix` explicitly** — each script invocation is a separate connection, so the session-level GUC from `--set-config` won't carry over:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --verify-s3 --prefix s3://<BUCKET>/<PATH>/ \
  --connection-name <PG_CONNECTION> --json
```

Optional — run end-to-end test with a test Iceberg table:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --test-table --prefix s3://<BUCKET>/<PATH>/ \
  --connection-name <PG_CONNECTION> --json
```

#### If using managed storage (skipped Steps 1-4):

No customer S3 configuration needed. Skip `--set-config`, `--verify-s3`, and `--test-table`.

Try creating an Iceberg table without a location to test managed storage:

```sql
psql "service=<PG_CONNECTION> connect_timeout=10" -c "
  CREATE TABLE _pg_lake_test (id int, val text) USING iceberg;
  INSERT INTO _pg_lake_test VALUES (1, 'managed storage works');
  SELECT * FROM _pg_lake_test;
  DROP TABLE _pg_lake_test;
"
```

**If this fails with a 403 / access denied on an internal S3 path**, managed storage is not provisioned for this instance. The platform needs to set up an internal bucket and credentials. The user's options are:
- Use a **customer-managed S3 bucket** instead (go back to Steps 1-4)
- Query **public URLs** via foreign tables (works without any storage)
- Load from public S3 datasets using `load_from` with an HTTPS URL

If it succeeds, the user can create Iceberg tables without specifying a location.

### Setup Complete

For **customer-managed S3**:
```
✅ pg_lake setup complete for <INSTANCE_NAME>

  Storage integration: <INTEGRATION_NAME>
  S3 location: s3://<BUCKET>/<PATH>/
  Extensions: pg_lake + sub-extensions installed
  S3 access: verified

  You can now:
  - CREATE TABLE ... USING iceberg (data goes to your S3 bucket)
  - COPY data TO/FROM S3
  - Query S3 files via foreign tables

  Say "help with iceberg tables" or "how to COPY to S3" for syntax guidance.
```

For **pg_lake without customer S3** (public URLs / managed storage):
```
✅ pg_lake enabled on <INSTANCE_NAME>

  Extensions: pg_lake + sub-extensions installed

  You can now:
  - Query public URLs via foreign tables (no credentials needed)
  - Load data from public datasets using load_from with HTTPS URLs
  - CREATE TABLE ... USING iceberg (if managed storage is provisioned for this instance)

  Say "help with iceberg tables" for syntax guidance.
```

---

## USE Workflow

When the user wants to work with pg_lake features (not setup):

### Step 1: Ensure instance is ready and verify pg_lake

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
  --ensure-ready --instance-name <INSTANCE_NAME> \
  --snowflake-connection <SF_CONNECTION>
```

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --check-extensions --check-config \
  --connection-name <PG_CONNECTION> --json
```

If not configured, offer to run the SETUP workflow.

### Step 2: Load appropriate reference

| User wants to... | Load reference |
|-------------------|---------------|
| Create/manage Iceberg tables, managed storage | `pg-lake/references/iceberg-tables.md` |
| Sync an operational PG table into an Iceberg mirror incrementally (pg_incremental pipelines) | `pg-lake/references/incremental-sync.md` |
| COPY data to/from S3, foreign tables, PG↔SF data movement (customer-S3) | `pg-lake/references/data-movement.md` |
| Read pg_lake Iceberg tables from Snowflake (managed storage, `CATALOG_SOURCE = SNOWFLAKE_POSTGRES`) | `pg-lake/references/snowflake-catalog-integration.md` — also see READ-FROM-SNOWFLAKE Workflow below |
| Snowflake → PG data flow (stage + COPY) | `pg-lake/references/data-movement.md` |
| Debug issues | `pg-lake/references/troubleshooting.md` |

### Step 3: Guide with verification

After the user runs operations, verify results:

```bash
# List Iceberg tables
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --list-iceberg --connection-name <PG_CONNECTION> --json
```

---

## READ-FROM-SNOWFLAKE Workflow

Query pg_lake Iceberg tables from Snowflake via `CATALOG_SOURCE = SNOWFLAKE_POSTGRES` (managed storage). All commands live in `pg_lake_catalog.py`. Detailed reference: `references/snowflake-catalog-integration.md`.

**Prerequisites:** PG instance uses **managed storage** (not customer-S3); PG instance is on the **same Snowflake account** as the SF connection (cross-account pairing fails with a terse error); account has `ENABLE_SNOWFLAKE_POSTGRES` + `ENABLE_POSTGRES_HIDDEN_EXTERNAL_VOLUME` enabled.

### Mode of operation: explanatory vs. live

If the user references identifiers that are obvious placeholders (`MY_PG_INSTANCE`, `<your_instance>`, `<pg_db>`, `MY_*`, angle-bracketed names, etc.), they are typically asking *how* this works — walk through Steps 0 → 5 as guidance, show the SQL/CLI shapes, and stop there. Don't escalate "instance not found" from the verify call into a troubleshooting loop; the placeholder is the signal.

When the user gives a concrete identifier they expect to exist, run the live workflow against it.

### Step 0: Confirm the PG instance is eligible

Before any `pg_lake_catalog.py` call, verify the instance is on a cloud + storage configuration that `CATALOG_SOURCE = SNOWFLAKE_POSTGRES` supports.

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  verify --instance <PG_INSTANCE> --snowflake-connection <SF_CONNECTION> --json
```

Returns `storage_integration`, `instance_info.host`, and related fields. Two checks decide whether to proceed:

**Customer-S3 storage integration attached?** → Fall back to the USE Workflow.  
If `storage_integration` is non-null (anything other than empty/null), stop and explain:

> This instance has `STORAGE_INTEGRATION = <name>` attached, so pg_lake is writing to your own S3 bucket. `CATALOG_SOURCE = SNOWFLAKE_POSTGRES` is the **managed-storage** path only — it can't read from customer-owned buckets. Use the existing external-stage flow in the USE Workflow instead (Parquet + `CREATE ICEBERG TABLE ... EXTERNAL_VOLUME`).

**Cloud platform supported?** → Defer to current Snowflake docs.  
The supported cloud + region matrix changes over time. Use the `instance_info.host` value as a hint, then check `cortex search docs "snowflake_postgres catalog integration"` (or current Snowflake docs) for the active support matrix. If you suspect the instance is on an unsupported cloud, mention it and let the user confirm before running `create-integration`. The server is the ultimate gate: when an unsupported configuration is attempted, the catalog-integration translators surface a friendly error and the workflow falls back to the external-stage path.

Only proceed to Step 1 if `storage_integration` is null/empty and the cloud is on the current support matrix.

### Step 1: Pre-flight (run both in parallel)

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  check-account-params --snowflake-connection <SF_CONNECTION> --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  list-pg-iceberg --connection-name <PG_CONNECTION> --json
```

`check-account-params` returns account flags, `current_role`, ranked `available_roles`, `instances_visible`, and `unverified_params`. If the instance list is empty, read `instance_visibility_note` — it distinguishes "no instances exist" from "your role can't see them". If `ok: false`, a required account param returned a definitive FALSE — the feature is disabled. Surface this to the user and suggest they work with their Snowflake account admin (ACCOUNTADMIN) to enable it; the admin can escalate to Snowflake support if the feature isn't available on the account. Do not proceed. If `ok: true` but `unverified_params` is non-empty, SHOW PARAMETERS couldn't confirm one or more flags (common on accounts where the feature is enabled but the param isn't surfaced through that interface). Proceed — the server is the source of truth and `create-integration` returns a clean `feature_not_enabled` error if the feature is actually off — but mention the unverified status to the user so they understand any downstream error context.

`list-pg-iceberg` returns `(catalog_name, namespace, table_name)` triples. If "extension not installed", run SETUP above first. Count the tables — this drives the branch in Step 2.5.

### Step 2: Role picker (only if current role lacks CREATE CATALOG INTEGRATION)

If `current_role` is not `ACCOUNTADMIN` and you're unsure whether it has `CREATE CATALOG INTEGRATION ON ACCOUNT`, present a picker from `available_roles` ranked by label (`Recommended` → `Likely works` → `Current role` → `May lack privileges`). Pass the selection as `--use-role <chosen>` to every mutating subcommand. Session-scoped only; no config files are modified. If the chosen role is wrong, the `insufficient_privileges_account` translator surfaces a specific `GRANT` SQL plus an `--use-role` retry hint.

**Role context is per-invocation, not session-sticky.** Every script call opens a fresh Snowflake session, so any non-default role context must be passed each time. If creation went through `--use-role <ROLE>`, the same flag is required on every later call against the same objects, including:

- read-only inspection: `describe-integration`, `cld-status`, `status` (the integration may not be visible to the user's default role even though `<ROLE>` created it)
- post-creation alters: `set-auto-refresh`, `set-refresh-interval`, `refresh`
- cleanup: `drop-integration`, plus the raw `DROP DATABASE <cld>` SQL for CLDs (typically via `snowflake_sql_execute`) — both inherit ownership from creation, so a default role with no `OWNERSHIP` grant will hit `not authorized`

### Step 2.5: Choose the path (per-table vs Catalog-Linked Database)

Given the `list-pg-iceberg` count from Step 1:

| Count | Default | Rationale |
|-------|---------|-----------|
| **1 table** | Per-table (`create-integration` + one `create-iceberg-table`) | Single-purpose exposure; no reason to propagate a whole DB |
| **2+ tables** | **CLD** (`create-integration` + `create-cld`) | One DDL covers every current and future pg_lake iceberg table — new tables typically surface within one `REFRESH_INTERVAL_SECONDS` cycle (default 30s) of PG-side creation |

Ask the user once before defaulting:

```
You have N pg_lake iceberg tables. Options:

[1] Catalog-Linked Database (recommended for >1 table)
    → Single CREATE DATABASE exposes all current and future tables.
    → `SHOW TABLES IN DATABASE <cld>` lists them as they appear.
    → Read-only by design (ALLOWED_WRITE_OPERATIONS = NONE).

[2] Per-table CREATE ICEBERG TABLE (pick specific tables)
    → One CREATE ICEBERG TABLE per PG table you want queryable.
    → Good for narrow, explicit exposure of just a few named tables.
```

Once the path is picked, follow Step 4A (per-table) or Step 4B (CLD).

### Step 3: Mandatory stopping point — present plan

**⚠️ STOP. Do not run `create-integration`. End your response after presenting the plan.**

```
I will set up a CATALOG_SOURCE = SNOWFLAKE_POSTGRES catalog integration:

  Integration:       <INTEGRATION_NAME>
  Postgres instance: <PG_INSTANCE>    Database: <PG_DATABASE>
  Snowflake role:    <CHOSEN_ROLE>
  Path:              <per-table | CLD>
  Tables exposed:    <N specific tables | all current + future>

⚠️ `CREATE CATALOG INTEGRATION` is a billable SF resource. Auto-refresh runs
at REFRESH_INTERVAL_SECONDS=30 by default — applied integration-wide, not
per-table. For larger table counts, raising the interval after creation
reduces Snowpipe refresh cost.

Proceed? (yes/no)
```

**Cost-warning check** (when the plan enables auto-refresh for many tables — either `--auto-refresh` on a per-table set, or the CLD path where every surfaced table refreshes on the integration's interval): call `build_auto_refresh_cost_warning(table_count)` from `pg_lake_catalog`. At or above the threshold it returns `warn=True` with a ready-to-paste recovery command. Embed that command in the plan so the user can act on it immediately after the integration exists:

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  set-refresh-interval --integration <INTEGRATION_NAME> --seconds 300 \
  --snowflake-connection <SF_CONNECTION> [--use-role <ROLE>] --json
```

`REFRESH_INTERVAL_SECONDS` is **integration-level**, not per-table — one value applies to every iceberg table under the integration (per-table and CLD paths alike). There is no way to set different intervals for different tables under a single integration; if the user needs per-table cadence, split into multiple integrations.

Threshold + suggested interval live in the script as `AUTO_REFRESH_COST_WARNING_THRESHOLD` and `AUTO_REFRESH_COST_SUGGESTED_INTERVAL` — tune via the constants, don't hardcode in prose.

**Never proceed without explicit approval.**

### Step 4A: Per-table path — create integration + each iceberg table

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  create-integration --name <INTEGRATION_NAME> \
  --postgres-instance <PG_INSTANCE> --database <PG_DATABASE> \
  --snowflake-connection <SF_CONNECTION> [--use-role <ROLE>] --json
```

If `already_exists: true`, the hint points at `describe-integration` or `drop-integration --confirm`. Don't silently reuse without user confirmation.

Then for each PG iceberg table the user picked:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  create-iceberg-table --name <SF_TABLE> --catalog <INTEGRATION_NAME> \
  --catalog-table-name <PG_TABLE> [--catalog-namespace <PG_SCHEMA>] \
  [--auto-refresh] --snowflake-connection <SF_CONNECTION> \
  [--use-role <ROLE>] --json
```

`CATALOG_NAMESPACE` defaults to `public`. `AUTO_REFRESH = TRUE` is opt-in.

### Step 4B: CLD path — create integration + linked database

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  create-integration --name <INTEGRATION_NAME> \
  --postgres-instance <PG_INSTANCE> --database <PG_DATABASE> \
  --snowflake-connection <SF_CONNECTION> [--use-role <ROLE>] --json

uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  create-cld --name <CLD_DATABASE_NAME> --catalog <INTEGRATION_NAME> \
  --snowflake-connection <SF_CONNECTION> [--use-role <ROLE>] --json
```

`create-cld` always emits `ALLOWED_WRITE_OPERATIONS = NONE` — SNOWFLAKE_POSTGRES CLDs are read-only by server-side mandate. There's no flag to override; the response payload surfaces a `propagation_note` so the agent knows to give the propagation window time before polling for tables.

**Auto-refresh on the CLD path:** there is no per-table toggle. Every table surfaced through the CLD refreshes on the integration's `REFRESH_INTERVAL_SECONDS` cadence (default 30s). To change cadence for all CLD-surfaced tables, run `set-refresh-interval` against the integration. `set-auto-refresh` is for per-table `CREATE ICEBERG TABLE` objects only (Step 4A path) — it does not apply to CLD-surfaced tables.

### Step 5: Verify

**Per-table path:**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  describe-integration --name <INTEGRATION_NAME> \
  --snowflake-connection <SF_CONNECTION> --json
```

Confirm `properties.ENABLED.value == "true"` and REST_CONFIG contains `POSTGRES_INSTANCE` + `CATALOG_NAME`. Then `SELECT count(*) FROM <SF_TABLE>;` from Snowflake.

**CLD path:**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  cld-status --name <CLD_DATABASE_NAME> \
  --snowflake-connection <SF_CONNECTION> --json
```

Confirm `healthy: true` (`execution_state == "RUNNING"`) and `iceberg_table_count > 0`. If the count is 0 on a fresh CLD, wait ~30s and retry — propagation typically completes within one `REFRESH_INTERVAL_SECONDS` cycle (default 30s). Use the `iceberg_tables[].name` list to pick a table and run `SELECT count(*) FROM <CLD_DATABASE_NAME>.<schema>.<name>;`.

### Cleanup (optional)

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  drop-integration --name <INTEGRATION_NAME> --confirm \
  --snowflake-connection <SF_CONNECTION> [--use-role <ROLE>] --json
```

Without `--confirm`, the command dry-runs. For a CLD, `DROP DATABASE <CLD_DATABASE_NAME>` on the Snowflake side first (no dedicated subcommand — use `snowflake_sql_execute` or drop via SnowSQL), then `drop-integration`. 11 failure modes are translated into friendly messages with specific recovery commands (`insufficient_privileges_account`, `feature_not_enabled`, `invalid_instance`, `missing_external_volume`, `refresh_interval_out_of_range`, `object_already_exists`, `object_not_found`, CLD-related). When a translation isn't available the raw Snowflake error surfaces — safe fallback.

---

## Tools

### Script: pg_lake_setup.py

General Postgres pg_lake operations (psycopg2 only).

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --check-extensions --connection-name <NAME> --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --enable-extensions --connection-name <NAME>
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --check-config --connection-name <NAME> --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --set-config s3://bucket/path --connection-name <NAME>
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --verify-s3 --prefix s3://<BUCKET>/<PATH>/ --connection-name <NAME> --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --test-table --connection-name <NAME> --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --list-iceberg --connection-name <NAME> --json
```

### Script: pg_lake_catalog.py

Catalog integration lifecycle for the `CATALOG_SOURCE = SNOWFLAKE_POSTGRES` (managed-storage) path. See READ-FROM-SNOWFLAKE Workflow above for the full flow.

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  check-account-params --snowflake-connection <CONN> --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  list-pg-iceberg --connection-name <PG_CONN> --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  create-integration --name <NAME> --postgres-instance <INST> \
  --database <PG_DB> --snowflake-connection <CONN> [--use-role <ROLE>] --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  describe-integration --name <NAME> --snowflake-connection <CONN> --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  create-iceberg-table --name <SF_TABLE> --catalog <INTEGRATION> \
  --catalog-table-name <PG_TABLE> [--catalog-namespace <SCHEMA>] \
  [--auto-refresh] --snowflake-connection <CONN> [--use-role <ROLE>] --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  drop-integration --name <NAME> --confirm \
  --snowflake-connection <CONN> [--use-role <ROLE>] --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  create-cld --name <CLD_DB> --catalog <INTEGRATION> \
  --snowflake-connection <CONN> [--use-role <ROLE>] --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  cld-status --name <CLD_DB> --snowflake-connection <CONN> --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  refresh --name <SF_TABLE> \
  --snowflake-connection <CONN> [--use-role <ROLE>] --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  set-auto-refresh --name <SF_TABLE> --enabled {true|false} \
  --snowflake-connection <CONN> [--use-role <ROLE>] --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  set-refresh-interval --integration <INTEGRATION> --seconds <30-86400> \
  --snowflake-connection <CONN> [--use-role <ROLE>] --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_catalog.py \
  status --name <SF_TABLE> --snowflake-connection <CONN> --json
```

**Library helper** (imported by the skill workflow, not a subcommand):
```python
from pg_lake_catalog import build_auto_refresh_cost_warning
warning = build_auto_refresh_cost_warning(table_count, interval_seconds=30)
# → {"warn": bool, "message": str, "recovery_command": str, ...}
```

### Script: pg_lake_storage.py

Snowflake storage integration operations (snowflake-connector only).

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  create --name <NAME> --role-arn <ARN> --locations s3://bucket/ \
  --snowflake-connection <CONN> --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  describe --name <NAME> --snowflake-connection <CONN>
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  check-aws --role-arn <ARN> \
  --expected-principal <IAM_USER_ARN> --expected-external-id "<EXT_ID>" \
  [--aws-profile <PROFILE>] --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  update-aws --role-arn <ARN> --sensitive-file <DESCRIBE_OUTPUT_FILE> \
  [--aws-profile <PROFILE>] --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  attach --instance <INST> --integration <NAME> --snowflake-connection <CONN>
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  verify --instance <INST> --snowflake-connection <CONN> --json
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  detach --instance <INST> --snowflake-connection <CONN>
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_storage.py \
  drop --name <NAME> --snowflake-connection <CONN>
```

**check-aws details:** Tries boto3 first, falls back to AWS CLI (including when boto3 fails with auth errors). Returns `all_configured: true` if trust policy and 12-hour session are set. Always returns `cli_available: true/false` — when true, use `update-aws` to configure automatically.

**update-aws details:** Reads sensitive IAM values from the describe output file (never exposes them in commands or chat). Updates trust policy and sets 12-hour session duration via AWS CLI. Requires `--sensitive-file` pointing to the describe output.

---

## Safety Rules

**Never execute destructive operations without explicit user request and approval:**
- **DROP TABLE** — permanently deletes data files from S3 (unrecoverable)
- **DROP COLUMN** — irreversible schema change
- **DELETE / TRUNCATE** — data loss
- **DROP STORAGE INTEGRATION** — breaks pg_lake access to S3
- **DETACH integration** — disconnects S3 from the instance

Read-only operations (SELECT, EXPLAIN, SHOW, DESCRIBE, LIST, COPY FROM, CREATE FOREIGN TABLE) are always safe.

If the user asks to "clean up" or "remove" something, confirm exactly what they want deleted before executing.

## Stopping Points

| Step | What happens | Why stop |
|------|-------------|----------|
| Create storage integration | Snowflake creates IAM trust relationship | Needs ACCOUNTADMIN, creates cloud resources |
| Update AWS trust policy | User modifies IAM role in AWS console | Manual AWS step — **skip if check-aws shows `all_configured: true`** |
| 12-hour session duration | User must verify IAM role setting | Most common missed step — causes silent failures |
| Create catalog integration (`CATALOG_SOURCE = SNOWFLAKE_POSTGRES`) | Snowflake creates a billable catalog integration + auto-refresh cadence | Needs role with `CREATE CATALOG INTEGRATION ON ACCOUNT`, creates SF-side resource, has ongoing cost |

---

## Output

- Setup: progress through each step with verification
- Use: syntax guidance from references + verification via scripts
