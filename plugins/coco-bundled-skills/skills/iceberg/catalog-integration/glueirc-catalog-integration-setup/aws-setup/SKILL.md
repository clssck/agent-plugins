---
name: aws-glue-iceberg-setup
description: "AWS-side Glue Iceberg setup: auth, S3 discovery, Glue crawler, schema validation, Athena CTAS to Iceberg. Sub-skill of glueirc-catalog-integration-setup."
parent_skill: glueirc-catalog-integration-setup
---

# AWS-Side Glue Iceberg Setup

> **Sub-skill of `glueirc-catalog-integration-setup`** — covers AWS-side prerequisites (phases 1-5) for registering Iceberg tables in AWS Glue.
>
> This skill is complete on its own if you only need Glue/Iceberg infrastructure. If you also want Snowflake to query these tables through a Catalog-Linked Database (CLD), the skill will hand off to the parent skill at the end.

---

## Agent execution rules

> **CRITICAL — Follow these rules in every phase:**
>
> 1. **Always execute commands via bash.** Run every AWS CLI command shown in this skill using the bash tool. Never skip a command or replace it with a text explanation. The user needs to see actual command output.
> 2. **Continue through errors.** If an AWS command returns an error (e.g., `InvalidClientTokenId`, `AccessDenied`, service errors), log the error and **continue to the next command in the phase**. Do not stop the workflow. Run the full command sequence, then report all results at the end.
> 3. **Always include generated SQL in your messages.** When generating SQL (e.g., CTAS statements), include the full SQL text in your response message — do not only write it to a file. The user needs to see the SQL directly.
> 4. **Run all commands for the requested phase.** Each phase has a specific sequence of commands. Run every command in order, regardless of whether earlier commands succeeded or failed.
> 5. **Never switch to "explain-only" mode.** Even in test/sandbox environments, execute the actual commands. The execution attempt is the deliverable, not just the documentation.

---

## When to invoke

- User wants to set up AWS Glue as an Iceberg REST catalog for Snowflake
- User has parquet/CSV/JSON data in S3 and wants it queryable as Iceberg in Snowflake
- User needs help converting existing data to Iceberg format via Athena
- User mentions "Glue", "Iceberg", "catalog-linked database" + AWS setup

## Workflow routing — ask this first

**Before starting any phases, ask the user three questions:**

> **0. AWS profile and region** — collect these before running any commands:
> - "What AWS CLI profile should I use? (run `aws configure list-profiles` if unsure)"
> - "Which AWS region is your data in?"
>
> Capture `AWS_PROFILE` and `AWS_REGION` now. Every command in this skill uses `--profile <AWS_PROFILE> --region <AWS_REGION>`.
>
> **1. What format is your source data in?**
> - **(A) Already in Iceberg format in S3** (e.g., written by Spark, Flink, or Snowflake Iceberg tables) → complete Phases 1–3 only. Skip Phases 4–5.
> - **(B) Parquet, CSV, or JSON that needs converting** → complete all 5 phases including Athena CTAS conversion.
>
> **2. Do you want to connect this Glue catalog to Snowflake?**
> - **(Y) Yes** → after AWS setup is complete, this skill will hand off to the parent `glueirc-catalog-integration-setup` skill for Snowflake catalog integration, external volume, and CLD creation.
> - **(N) No** → this skill is the final step. AWS setup only.

Capture all three answers before proceeding. Only follow the phases that apply.

## What this skill does NOT cover

- Snowflake catalog integration, external volume, or CLD creation → hand off to **parent `glueirc-catalog-integration-setup` skill**
- Lake Formation fine-grained access control (column/row filters, tag-based policies) — this skill grants only the minimum LF permissions the Glue crawler needs to operate (database `DESCRIBE`/`CREATE_TABLE`/`ALTER` and optionally `DATA_LOCATION_ACCESS`); advanced LF governance is out of scope
- Writing/updating Iceberg tables from Snowflake (read-only flow)

---

## Polling pattern (reuse for crawler and Athena)

- Poll interval: **15 seconds**
- Max attempts: **40** (10 minutes)
- Crawler state transitions: `RUNNING` → `STOPPING` → `READY`
- Athena state transitions: `RUNNING` → `SUCCEEDED` or `FAILED`
- On `FAILED`: fetch error reason, present to user, diagnose before retrying

---

## Phase 1 — AWS Authentication

**Goal**: Verify the user has working AWS CLI access to the target account and identify the source S3 bucket.

> `AWS_PROFILE` and `AWS_REGION` are already captured from workflow routing. Use them in every command below.

### Steps

1. Verify credentials:
   ```bash
   aws sts get-caller-identity --profile <PROFILE>
   ```

2. Capture from the output:
   - `AWS_ACCOUNT_ID` — the 12-digit account number

3. List all S3 buckets the profile can access:
   ```bash
   aws s3 ls --profile <PROFILE>
   ```

   Show the output to the user. If there are ≤15 buckets, present as a numbered list:
   > "Here are your accessible S3 buckets — which one contains the data you want to register as Iceberg?"

   Capture the chosen bucket as `S3_BUCKET`.

4. Confirm access to the chosen bucket:
   ```bash
   aws s3 ls s3://<S3_BUCKET>/ --profile <PROFILE>
   ```

> **IMPORTANT**: Steps 1, 3, and 4 must ALL be executed via bash. Do not skip any of them even if an earlier step returned an error.

> **If AWS CLI is not installed**: Direct user to `brew install awscli` (macOS) or `pip install awscli`. If they need to configure a profile: `aws configure --profile <name>`.

### Error recovery

- `ExpiredToken` / `ExpiredTokenException` → "Your AWS session has expired. Run `aws sso login --profile <PROFILE>` or refresh your credentials."
- `InvalidClientTokenId` → "The AWS profile isn't configured correctly. Run `aws configure --profile <PROFILE>` to set it up."
- `AccessDenied` on S3 → "Your IAM user/role doesn't have S3 access to this bucket. Check your IAM policies."
- No buckets returned from `aws s3 ls` → "The profile has no S3 list permissions or no accessible buckets. Verify the profile with `aws sts get-caller-identity` and check the IAM policy."

### **STOP** — Confirm AWS credentials are working and `S3_BUCKET` is captured. If auth failed, help the user fix credentials before proceeding.

---

## Phase 2 — S3 Data Discovery

**Goal**: Find and inventory the source data files in S3.

### Steps

1. List bucket contents recursively:
   ```bash
   aws s3 ls s3://<BUCKET>/ --recursive --profile <PROFILE>
   ```

2. Identify file formats (parquet, CSV, JSON, ORC) and note their paths.

3. Build a source inventory table:

   | File | Format | Size | S3 Path |
   |------|--------|------|---------|
   | customer_reviews.parquet | parquet | 12.3 KB | s3://bucket/parquet/customer_reviews.parquet |

4. **CRITICAL — Directory structure check**:
   - Athena expects each table's data at a **directory prefix**, not a single file path
   - If files are flat (e.g., `s3://bucket/data.parquet`), they must be reorganized:
     ```bash
     # Copy into directory structure
     aws s3 cp s3://<BUCKET>/data.parquet \
       s3://<BUCKET>/tables/data/data.parquet \
       --profile <PROFILE>
     ```
   - Each table needs its own directory: `s3://bucket/tables/<table_name>/`

> See `references/KNOWN_GOTCHAS.md` → "File path vs directory path" for details on this issue.

### **STOP** — Present the S3 inventory to the user. Ask: "These are the files I found. Which ones should we convert to Iceberg? Any to skip?"

---

## Phase 3 — Glue Database & Crawler Setup

**Goal**: Create a Glue database and crawler to auto-discover table schemas.

> **REQUIRED command sequence**: You MUST run ALL of these commands via bash in order, regardless of errors:
> 1. `aws glue create-database` — create the database
> 2. `aws glue create-crawler` — create the crawler targeting S3
> 3. `aws glue start-crawler` — start the crawler
> 4. `aws glue get-tables` — verify discovered tables
>
> Even if `create-database` fails (e.g., AlreadyExistsException or service error), proceed to `create-crawler`. Even if `create-crawler` fails, proceed to `start-crawler`. Run every command.

### 3.1 Create or select the Glue database

Ask the user:
> "Do you have an existing Glue database to use, or should we create a new one?
> - **(A) Use existing** — provide the database name
> - **(B) Create new** — provide the desired name
>
> **Naming rules (new databases)**: lowercase only, letters/numbers/underscores, **no hyphens**.
> Example: `my_iceberg_db` ✓ &nbsp;|&nbsp; `my-iceberg-db` ✗"

**If (A) — use existing**: Capture `GLUE_DB_NAME` from the user and skip the `create-database` command. Proceed to step 3.2.

**If (B) — create new**: **Validate the name before running the command.**
- All lowercase? If not, convert and confirm with the user.
- Contains only letters, numbers, underscores? If a hyphen or other special character is present (e.g., `nm_iceberg-glue`), tell the user: *"Glue database names cannot contain hyphens — try `nm_iceberg_glue` instead."* Do not proceed until the name passes validation.

```bash
aws glue create-database \
  --database-input '{"Name":"<DB_NAME>"}' \
  --profile <PROFILE> \
  --region <REGION>
```

> **If `AlreadyExistsException`**: The database already exists. Ask the user whether to use it (option A) or pick a different name.

### 3.2 Create or select an IAM role for the crawler

The crawler needs an IAM role with:
- `AWSGlueServiceRole` managed policy (for Glue operations)
- S3 read access to the source bucket

Ask the user:
> "Do you have an existing IAM role for the Glue crawler, or should we create one?
> - **(A) Use existing** — provide the role name
> - **(B) Create new** — provide a name for the new role"

**If (A) — use existing**: Verify the role exists and check its policies:
```bash
aws iam get-role --role-name <CRAWLER_ROLE_NAME> --profile <PROFILE>
aws iam list-attached-role-policies --role-name <CRAWLER_ROLE_NAME> --profile <PROFILE>
```
Capture `CRAWLER_ROLE_NAME` and `CRAWLER_ROLE_ARN` from the `get-role` output. Proceed to step 3.2a.

**If (B) — create new**:
```bash
# Create the role with Glue trust policy
aws iam create-role \
  --role-name <CRAWLER_ROLE_NAME> \
  --assume-role-policy-document '{
    "Version":"2012-10-17",
    "Statement":[{
      "Effect":"Allow",
      "Principal":{"Service":"glue.amazonaws.com"},
      "Action":"sts:AssumeRole"
    }]
  }' \
  --profile <PROFILE>

# Attach Glue service policy
aws iam attach-role-policy \
  --role-name <CRAWLER_ROLE_NAME> \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole \
  --profile <PROFILE>

# Add inline S3 read policy
aws iam put-role-policy \
  --role-name <CRAWLER_ROLE_NAME> \
  --policy-name s3-read-access \
  --policy-document '{
    "Version":"2012-10-17",
    "Statement":[{
      "Effect":"Allow",
      "Action":["s3:GetObject","s3:ListBucket","s3:GetBucketLocation"],
      "Resource":["arn:aws:s3:::<BUCKET>","arn:aws:s3:::<BUCKET>/*"]
    }]
  }' \
  --profile <PROFILE>
```

> **IAM propagation delay**: After creating the role, wait ~10 seconds before starting the crawler. IAM roles take time to propagate. Starting immediately may fail with "role not found."

### 3.2b Minimum operator permissions

The IAM identity running this skill (your user or assumed role) needs these permissions. If you hit `AccessDenied` on any command above, share this policy with your AWS admin:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GlueSetup",
      "Effect": "Allow",
      "Action": [
        "glue:CreateDatabase", "glue:GetDatabase", "glue:GetDatabases",
        "glue:CreateCrawler", "glue:StartCrawler", "glue:GetCrawler",
        "glue:DeleteCrawler",
        "glue:GetTable", "glue:GetTables", "glue:UpdateTable"
      ],
      "Resource": "*"
    },
    {
      "Sid": "IAMRoleCreation",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole", "iam:AttachRolePolicy", "iam:PutRolePolicy",
        "iam:GetRole", "iam:ListAttachedRolePolicies",
        "iam:PassRole"
      ],
      "Resource": "arn:aws:iam::<ACCOUNT_ID>:role/<CRAWLER_ROLE_NAME>"
    },
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:ListAllMyBuckets", "s3:GetBucketLocation",
        "s3:ListBucket", "s3:GetObject",
        "s3:PutObject", "s3:DeleteObject", "s3:CreateBucket"
      ],
      "Resource": [
        "arn:aws:s3:::<BUCKET>",
        "arn:aws:s3:::<BUCKET>/*",
        "arn:aws:s3:::<RESULTS_BUCKET>",
        "arn:aws:s3:::<RESULTS_BUCKET>/*"
      ]
    },
    {
      "Sid": "AthenaExecution",
      "Effect": "Allow",
      "Action": [
        "athena:StartQueryExecution", "athena:GetQueryExecution",
        "athena:GetWorkGroup", "athena:ListWorkGroups"
      ],
      "Resource": "*"
    },
    {
      "Sid": "LakeFormation",
      "Effect": "Allow",
      "Action": [
        "lakeformation:GetDataLakeSettings",
        "lakeformation:GrantPermissions",
        "lakeformation:ListResources"
      ],
      "Resource": "*"
    }
  ]
}
```

> If you used an existing role (option A above), omit the `IAMRoleCreation` block. If Lake Formation is not enabled in your account, omit the `LakeFormation` block.

### 3.2a Grant Lake Formation permissions (if LF is enabled)

Many AWS accounts have Lake Formation enabled. When LF is active, IAM policies alone are not enough — the crawler role also needs explicit LF grants on the Glue database. Without this, the crawler fails with `Insufficient Lake Formation permission(s): Required Describe on <DB_NAME>`.

First, check whether your account uses Lake Formation as the metadata security layer:

```bash
aws lakeformation get-data-lake-settings \
  --profile <PROFILE> --region <REGION> \
  --query 'DataLakeSettings.CreateDatabaseDefaultPermissions'
```

If the output does **not** contain `IAM_ALLOWED_PRINCIPALS`, Lake Formation is actively managing permissions (restrictive mode). Skip ahead if `IAM_ALLOWED_PRINCIPALS` with `"Permissions": ["ALL"]` is present — that means LF is in IAM compatibility mode and IAM policies are sufficient; you likely do **not** need explicit LF grants.

Grant the crawler role the minimum required permissions on the Glue database:

```bash
# Grant Describe + CreateTable on the database to the crawler role
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier="arn:aws:iam::<ACCOUNT_ID>:role/<CRAWLER_ROLE_NAME>" \
  --permissions "DESCRIBE" "CREATE_TABLE" "ALTER" \
  --resource '{"Database":{"Name":"<DB_NAME>"}}' \
  --profile <PROFILE> --region <REGION>
```

If the S3 path is registered as a Lake Formation data location, also grant data location access:

```bash
# Grant DATA_LOCATION_ACCESS on the S3 path
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier="arn:aws:iam::<ACCOUNT_ID>:role/<CRAWLER_ROLE_NAME>" \
  --permissions "DATA_LOCATION_ACCESS" \
  --resource '{"DataLocation":{"ResourceArn":"arn:aws:s3:::<BUCKET>"}}' \
  --profile <PROFILE> --region <REGION>
```

> **Not sure if your S3 path is an LF data location?** Run:
> ```bash
> aws lakeformation list-resources --profile <PROFILE> --region <REGION>
> ```
> If `<BUCKET>` appears in the output, the data location grant is required.

> **WARNING — Avoid `--use-service-linked-role` when registering S3 paths**: If your S3 bucket is NOT already registered as an LF data location and you need to register it, prefer `--role-arn <specific-iam-role>` over `--use-service-linked-role`. The service-linked role (`AWSServiceRoleForLakeFormationDataAccess`) intercepts ALL S3 access to the bucket once created, and deregistering it requires deleting the IAM service-linked role entirely:
> ```bash
> # Only run this if you need to fully deregister the S3 path from LF
> aws iam delete-service-linked-role \
>   --role-name AWSServiceRoleForLakeFormationDataAccess \
>   --profile <PROFILE>
> ```
> If you don't need LF data governance on this bucket, the safest approach is to NOT register it with LF at all — just grant the LF database/table permissions in step 3.2a without registering the S3 location.

> **If you get `AccessDeniedException` running the LF grant commands**: You need `lakeformation:GrantPermissions` permission on your caller identity (typically requires the `AWSLakeFormationDataAdmin` managed policy). Contact your AWS admin if you lack this permission.

#### SSO console vs CLI identity mismatch

> **WARNING**: Your CLI identity and AWS Console identity are often different principals. If you run `aws glue create-database` as an IAM user (e.g., `sf-afe-skumar`) but browse the Glue console via SSO (e.g., `AWSReservedSSO_Contributor_...`), LF grants given to the CLI user will not apply to the console role. The database will appear missing or inaccessible in the console even though it was created successfully.

Check which identity you're using in each context:

```bash
# CLI identity
aws sts get-caller-identity --profile <PROFILE> --region <REGION>

# Console identity — check the top-right corner of the AWS Console, or:
# IAM → Roles → search for your SSO role name
```

If they differ, either:

**Option A — Grant LF permissions to the SSO role explicitly:**
```bash
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier="arn:aws:iam::<ACCOUNT_ID>:role/aws-reserved/sso.amazonaws.com/<SSO_ROLE_NAME>" \
  --permissions "DESCRIBE" "CREATE_TABLE" "ALTER" "DROP" \
  --resource '{"Database":{"Name":"<DB_NAME>"}}' \
  --profile <PROFILE> --region <REGION>
```

**Option B — Set `IAM_ALLOWED_PRINCIPALS` as the LF default** (broader, removes per-principal enforcement for new objects):
```bash
aws lakeformation put-data-lake-settings \
  --data-lake-settings '{
    "CreateDatabaseDefaultPermissions":[{"Principal":{"DataLakePrincipalIdentifier":"IAM_ALLOWED_PRINCIPALS"},"Permissions":["ALL"]}],
    "CreateTableDefaultPermissions":[{"Principal":{"DataLakePrincipalIdentifier":"IAM_ALLOWED_PRINCIPALS"},"Permissions":["ALL"]}]
  }' \
  --profile <PROFILE> --region <REGION>
```

> Option B affects all future objects created in the account — confirm with your AWS admin before using it. Option A is the safer, targeted fix.

> If you use Option B, you must **recreate the Glue database** — LF default permissions only apply at creation time, not retroactively.

### 3.3 Create and run the crawler

```bash
aws glue create-crawler \
  --name <CRAWLER_NAME> \
  --role "arn:aws:iam::<ACCOUNT_ID>:role/<CRAWLER_ROLE_NAME>" \
  --database-name <DB_NAME> \
  --targets '{"S3Targets":[{"Path":"s3://<BUCKET>/<PREFIX>/"}]}' \
  --schema-change-policy '{"UpdateBehavior":"UPDATE_IN_DATABASE","DeleteBehavior":"LOG"}' \
  --recrawl-policy '{"RecrawlBehavior":"CRAWL_EVERYTHING"}' \
  --profile <PROFILE> \
  --region <REGION>
```

> **GOTCHA**: The `--role` parameter requires the **full ARN**, not just the role name. Using just the name silently fails or errors.

> **Crawler target path**: After Phase 2 reorganization, use the **parent directory** that contains all table subdirectories (e.g., `s3://bucket/tables/`), not individual table paths. The crawler will create one table per subdirectory.

Start the crawler (after ~10s IAM propagation delay):
```bash
sleep 10
aws glue start-crawler --name <CRAWLER_NAME> \
  --profile <PROFILE> --region <REGION>
```

Poll until complete (see Polling pattern above):
```bash
aws glue get-crawler --name <CRAWLER_NAME> \
  --profile <PROFILE> --region <REGION> \
  --query 'Crawler.State'
```

### Error recovery

- `EntityNotFoundException` → Database or crawler name is wrong. Check spelling.
- `InvalidInputException` on role → Role ARN is malformed or doesn't exist. Verify with `aws iam get-role`.
- Crawler stuck in `RUNNING` after 10 minutes → Check the AWS Glue console for errors. Common cause: S3 permissions on the crawler role.
- `AlreadyExistsException` → Database or crawler already exists. This is OK — use the existing one or delete and recreate.
- `Insufficient Lake Formation permission(s): Required Describe on <DB_NAME>` → Lake Formation is enabled. The crawler role is missing LF grants. Follow step **3.2a** above to grant `DESCRIBE`, `CREATE_TABLE`, `ALTER` on the database, and `DATA_LOCATION_ACCESS` on the S3 bucket if registered as an LF data location.

### 3.4 Verify Iceberg table registration

The standard S3 Glue crawler **does not understand Iceberg format natively**. When crawling Iceberg data, it may create spurious entries for metadata files (`.metadata.json`, `.avro` manifest files, `metadata/` subdirectory) and name the real data table after a file rather than the Iceberg table name.

After the crawler finishes, check whether discovered tables are correctly registered as Iceberg:

```bash
aws glue get-tables --database-name <DB_NAME> \
  --profile <PROFILE> --region <REGION> \
  --query 'TableList[].{Name:Name,Type:Parameters.table_type,Location:StorageDescriptor.Location}'
```

**If `table_type` is missing or tables have unexpected names** (e.g., `metadata`, `data`, `snap_*`):
1. Delete the spurious entries: `aws glue delete-table --database-name <DB_NAME> --name <SPURIOUS_TABLE>`
2. Register the correct Iceberg table manually (see below)

**If user chose option A (already Iceberg format)**: skip the crawler entirely and register directly.

#### Manual Iceberg table registration

> **CRITICAL**: You must include a full `StorageDescriptor` in the registration. Registering with only `Parameters` (table_type + metadata_location) causes Glue to return a malformed `LoadTableResponse` — Snowflake will fail with `Cannot find schema with current-schema-id=0 from schemas`.

```bash
aws glue create-table \
  --database-name <DB_NAME> \
  --table-input '{
    "Name": "<TABLE_NAME>",
    "Parameters": {
      "table_type": "ICEBERG",
      "metadata_location": "s3://<BUCKET>/<PATH>/metadata/<VERSION>.metadata.json"
    },
    "StorageDescriptor": {
      "Columns": [
        {"Name": "<col1>", "Type": "<type1>"},
        {"Name": "<col2>", "Type": "<type2>"}
      ],
      "Location": "s3://<BUCKET>/<PATH>/",
      "InputFormat": "org.apache.iceberg.mr.mapred.MapredIcebergInputFormat",
      "OutputFormat": "org.apache.iceberg.mr.mapred.MapredIcebergOutputFormat",
      "SerdeInfo": {
        "SerializationLibrary": "org.apache.iceberg.mr.hive.HiveIcebergSerDe"
      }
    }
  }' \
  --profile <PROFILE> --region <REGION>
```

> **Finding the metadata_location**: Look in `s3://<BUCKET>/<PATH>/metadata/` for a file matching `*-<uuid>.metadata.json`. Use the most recent one (highest version number or most recent timestamp):
> ```bash
> aws s3 ls s3://<BUCKET>/<PATH>/metadata/ --profile <PROFILE> | grep '.metadata.json' | sort | tail -5
> ```

> **Columns**: Use the column names and types from your Iceberg schema. For the initial registration, the types should match the Iceberg schema exactly. The crawler would normally infer these, but since we're registering manually, retrieve them from the metadata JSON:
> ```bash
> aws s3 cp s3://<BUCKET>/<PATH>/metadata/<VERSION>.metadata.json - --profile <PROFILE> | python3 -c "import json,sys; m=json.load(sys.stdin); [print(f['name'], f['type']) for f in m['schemas'][m['current-schema-id']]['fields']]"
> ```

---

## Phase 4 — Schema Discovery & Validation

**Goal**: Verify Glue tables were created correctly and fix type mismatches.

> **Load `references/ATHENA_TYPE_MAPPING.md` now** — it contains common gotchas and links to official type mapping docs.

### 4.1 List discovered tables

```bash
aws glue get-tables --database-name <DB_NAME> \
  --profile <PROFILE> --region <REGION> \
  --query 'TableList[].{Name:Name,Cols:StorageDescriptor.Columns[].{N:Name,T:Type},Location:StorageDescriptor.Location}'
```

### 4.2 Validate each table's schema

For each table, compare the Glue-inferred types against actual parquet column types.

> See `references/ATHENA_TYPE_MAPPING.md` for common gotchas and debugging steps.
> For the full authoritative mapping, refer to the [Athena Data Types docs](https://docs.aws.amazon.com/athena/latest/ug/data-types.html) and [Snowflake Iceberg Data Types docs](https://docs.snowflake.com/en/user-guide/tables-iceberg-data-types).

### 4.3 Verify row counts

For each table, check the crawler's table location:
```bash
aws glue get-table --database-name <DB_NAME> --name <TABLE> \
  --profile <PROFILE> --region <REGION> \
  --query 'Table.StorageDescriptor.Location'
```

If the location points to a **file** (ends in `.parquet`) instead of a **directory prefix** (ends in `/`), Athena will return 0 rows. Fix by reorganizing files per Phase 2 step 4.

### 4.4 Fix duplicate partition columns (Snowflake-exported Parquet)

> **CRITICAL — Snowflake COPY INTO gotcha**: When Snowflake exports Hive-partitioned Parquet files using `COPY INTO ... PARTITION BY`, it writes the partition column **inside** each Parquet file AND creates the Hive-style directory structure (e.g., `C_MKTSEGMENT=AUTOMOBILE/`). Standard Hive convention expects the partition column to exist ONLY in the directory path, not in the data files.
>
> When the Glue crawler discovers such data, it registers the partition column **twice** — once from the Parquet schema (in `StorageDescriptor.Columns`) and once from the directory structure (in `PartitionKeys`). Athena sees this as duplicate columns and refuses to query the table.

**Detection**: For each partitioned table, check if the partition key also appears in the regular columns:

```bash
aws glue get-table --database-name <DB_NAME> --name <TABLE> \
  --profile <PROFILE> --region <REGION> \
  --query '{Columns:Table.StorageDescriptor.Columns[].Name,PartitionKeys:Table.PartitionKeys[].Name}'
```

If any column name appears in both `Columns` and `PartitionKeys`, it must be removed from `StorageDescriptor.Columns`.

**Fix**: Use `aws glue update-table` to remove the duplicate column from `StorageDescriptor.Columns`. Retrieve the current table definition, remove the duplicate column from the Columns array, and update:

```bash
# Get current table definition
aws glue get-table --database-name <DB_NAME> --name <TABLE> \
  --profile <PROFILE> --region <REGION> > /tmp/table_def.json
```

Edit `/tmp/table_def.json`:
1. Extract the `"Table"` object and rename the key to `"TableInput"`
2. Remove the duplicate partition column from `StorageDescriptor.Columns`
3. Remove metadata fields: `DatabaseName`, `CreateTime`, `UpdateTime`, `CreatedBy`, `IsRegisteredWithLakeFormation`, `CatalogId`, `VersionId`

```bash
# Update the table
aws glue update-table \
  --database-name <DB_NAME> \
  --table-input file:///tmp/table_def.json \
  --profile <PROFILE> --region <REGION>
```

**Verify after fix**: Run a simple query via Athena to confirm the table is queryable without duplicate column errors:

```bash
aws athena start-query-execution \
  --query-string "SELECT * FROM <DB_NAME>.<TABLE> LIMIT 5" \
  --query-execution-context '{"Database":"<DB_NAME>"}' \
  --result-configuration '{"OutputLocation":"s3://<RESULTS_BUCKET>/"}' \
  --profile <PROFILE> --region <REGION>
```

### **STOP** — Present discovered tables and their schemas to the user. Ask: "Here are the tables and column types the crawler found. Do these look correct, or should we fix any types before converting to Iceberg?"

---

## Phase 5 — Parquet-to-Iceberg Conversion via Athena

**Goal**: Convert Glue external tables to Iceberg format using Athena CTAS.

> **Two approaches for parquet-to-Iceberg conversion:**
> - **Athena CTAS** (this skill's default) — SQL-only, no Spark setup required. Works for parquet, CSV, and JSON. Requires Athena engine v3 workgroup.
> - **Glue Spark job (`add_files`)** (parquet only) — more reliable for large parquet datasets. Avoids Athena workgroup setup entirely. Requires a short PySpark ETL script.
>
> This skill defaults to the Athena CTAS path. If you hit repeated Athena workgroup issues or prefer not to set up Athena, say so and the agent will generate the Glue Spark job script instead.

> **REQUIRED**: For each table, generate a complete CTAS statement and include the full SQL in your response message. Do not only write SQL to a file — the user must see each CTAS statement directly in the conversation. Cover ALL tables specified by the user (typically: customer_reviews, order_history, product_catalog, shipping_logs).
>
> Also explain the key Iceberg table properties (`table_type`, `format`, `write_compression`, `location`, `is_external`) in your response message.

### 5.0 Verify Athena engine version

Iceberg CTAS requires **Athena engine version 3** (Trino-based). Verify the workgroup uses engine v3:
```bash
aws athena get-work-group --work-group primary \
  --profile <PROFILE> --region <REGION> \
  --query 'WorkGroup.Configuration.EngineVersion'
```

If the result shows `Athena engine version 2` or earlier, the user must update their workgroup or create a new one with engine v3.

### 5.1 Set up Athena output location

First check if the workgroup already has a configured output location:

```bash
aws athena get-work-group --work-group primary \
  --profile <PROFILE> --region <REGION> \
  --query 'WorkGroup.Configuration.ResultConfiguration.OutputLocation'
```

- **If the output is a non-null S3 path** (e.g., `"s3://existing-results-bucket/"`): capture that as `ATHENA_RESULTS_BUCKET` and skip bucket creation — the workgroup is already configured.
- **If the output is `null` or empty**: create a new results bucket:

```bash
aws s3 mb s3://<ACCOUNT_ID>-<REGION>-athena-results \
  --profile <PROFILE> --region <REGION>
```

### 5.2 IAM permissions for Athena CTAS

Athena CTAS **writes** Iceberg data files to S3. The IAM identity running Athena needs S3 write access to the Iceberg output location. If using the default Athena workgroup, your user/role needs:

```json
{
  "Effect": "Allow",
  "Action": ["s3:PutObject", "s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation", "s3:DeleteObject"],
  "Resource": ["arn:aws:s3:::<BUCKET>/iceberg/*", "arn:aws:s3:::<BUCKET>"]
}
```

> This is separate from the crawler role. The crawler only reads source data; Athena writes the Iceberg output.

### 5.3 Run CTAS for each table

Use Athena's `StartQueryExecution` API to convert each table. Athena creates **Iceberg v2** tables by default:

```bash
aws athena start-query-execution \
  --query-string "
    CREATE TABLE <DB_NAME>.<TABLE>_iceberg
    WITH (
      table_type = 'ICEBERG',
      location = 's3://<BUCKET>/iceberg/<TABLE>/',
      is_external = false,
      format = 'PARQUET',
      write_compression = 'ZSTD'
    ) AS SELECT * FROM <DB_NAME>.<TABLE>
  " \
  --query-execution-context '{"Database":"<DB_NAME>"}' \
  --result-configuration '{"OutputLocation":"s3://<RESULTS_BUCKET>/"}' \
  --profile <PROFILE> --region <REGION>
```

> **Table properties** (from [AWS docs](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg-creating-tables.html)):
> - `format` — defaults to `PARQUET`. Explicit is better for cross-engine clarity.
> - `write_compression` — defaults to `ZSTD` in recent Athena. Snowflake reads ZSTD and SNAPPY.
> - `vacuum_min_snapshots_to_keep` — set explicitly if you plan to run VACUUM later.

For partitioned tables, add the `partitioning` property (Iceberg hidden partitioning transforms):
```sql
CREATE TABLE db.orders_iceberg
WITH (
  table_type = 'ICEBERG',
  location = 's3://bucket/iceberg/orders/',
  is_external = false,
  partitioning = ARRAY['month(order_date)']
)
AS SELECT * FROM db.orders
```

> **Partition transforms** supported: `year()`, `month()`, `day()`, `hour()`, `bucket(N, col)`, `truncate(N, col)`.
> For small datasets (<1M rows), skip partitioning — the overhead isn't worth it.

Then poll for completion (see Polling pattern above):
```bash
aws athena get-query-execution \
  --query-execution-id <ID> \
  --profile <PROFILE> --region <REGION> \
  --query 'QueryExecution.Status.State'
```

On FAILED, get the error:
```bash
aws athena get-query-execution \
  --query-execution-id <ID> \
  --profile <PROFILE> --region <REGION> \
  --query 'QueryExecution.Status.StateChangeReason'
```

### 5.4 Handle type mismatch errors

If CTAS fails with `HIVE_BAD_DATA` or similar:

1. Drop the failed Iceberg table (if partially created)
2. Create a new external table with corrected column types
3. Re-run CTAS with explicit column casting

Example with column-level fixes:
```sql
CREATE TABLE db.table_iceberg
WITH (
  table_type = 'ICEBERG',
  location = 's3://bucket/iceberg/table/',
  is_external = false
) AS
SELECT
  CAST(id AS BIGINT) AS id,
  name,
  CAST(price AS DOUBLE) AS price
FROM db.table_source
```

### 5.5 Athena SQL dialect notes

- **Athena Trino engine uses double quotes** for identifiers: `"column name"` (NOT backticks)
- Backticks work in Hive DDL (`CREATE EXTERNAL TABLE`) but NOT in Trino DML (`SELECT`, `CTAS`)
- If a column name has spaces, use: `SELECT "order id" FROM ...`

### 5.6 Verify converted tables

After all CTAS queries complete, verify row counts:
```sql
SELECT COUNT(*) FROM <DB_NAME>.<TABLE>_iceberg;
```

Run this for each table to confirm data was fully converted.

> **One-time conversion note**: This CTAS created a point-in-time snapshot of your source data. New data written to the original source location will **not** automatically appear in the Iceberg tables. If your source data is actively updated (e.g., daily parquet drops or streaming writes), you'll need a strategy:
> - Re-run CTAS periodically and replace the Iceberg table, or
> - Use a Glue ETL job to append new data to the Iceberg table incrementally, or
> - Use streaming ingest to maintain the Iceberg table going forward.
>
> For a one-time migration or POC this is fine. Flag this to the user if they're building production pipelines.

### 5.7 Table maintenance (for ongoing use)

Athena supports OPTIMIZE and VACUUM for Iceberg tables:

```sql
-- Compact small files (run periodically for tables with frequent writes)
OPTIMIZE db.table_iceberg REWRITE DATA USING BIN_PACK;

-- Expire old snapshots and delete orphaned files
VACUUM db.table_iceberg;
```

> **Limits**: OPTIMIZE can only process 100 partitions per query — use a WHERE clause on partition columns to stay under the limit. VACUUM can delete up to 20,000 objects per execution.

For CTAS one-time conversions, maintenance is not urgent — but document it for the user if they plan to write to these tables later.

### 5.8 Clean up source tables (optional)

> **STOP** — Ask the user before proceeding. Dropping source tables is destructive.

> **WARNING**: Dropping an Athena-managed Iceberg table (`is_external = false`) **deletes the underlying S3 data**. Only drop if you're sure the Iceberg table is the one you want to keep.

Once Iceberg tables are verified, you can drop the original external tables:
```sql
DROP TABLE <DB_NAME>.<TABLE>;
-- Optionally rename Iceberg table
ALTER TABLE <DB_NAME>.<TABLE>_iceberg RENAME TO <DB_NAME>.<TABLE>;
```

### 5.9 Delete the Glue crawler

The crawler was created for one-time schema discovery and is no longer needed. Delete it to avoid accidental re-crawls and unnecessary cost.

```bash
aws glue delete-crawler \
  --name <CRAWLER_NAME> \
  --profile <PROFILE> --region <REGION>
```

> Skip this step if you plan to re-crawl the same bucket in the future (e.g., for schema evolution as new files are added). Otherwise, delete it — you can always recreate one with `aws glue create-crawler`.

---

## Cost awareness

- **Athena CTAS**: Charged per bytes scanned from the source table. For large datasets, this can be significant. Warn the user before converting tables >100GB.
- **Glue Crawler**: Charged per DPU-hour. A single crawl of a small bucket is typically <$1, but large buckets with many files can cost more.
- **S3 storage**: Iceberg conversion creates new data files. The source parquet AND Iceberg files coexist until you clean up the source.

---

## Handoff to Snowflake

> **STOP — Ask the user before proceeding.**
> "Your AWS setup is complete. Your Iceberg tables are registered in Glue database `<DB_NAME>`. Do you want to connect this to Snowflake now (catalog integration + CLD setup)?"
>
> - If **No**: AWS setup is done. Summarize what was built and exit.
> - If **Yes**: continue below.

### Create the Snowflake IAM role

The Snowflake catalog integration and external volume use a **separate IAM role** from the Glue crawler role — Snowflake needs Glue read access and S3 access via this role. Create it now while AWS CLI is ready.

**Ask**: "Do you have an existing IAM role for Snowflake to assume (separate from the crawler role), or should we create one? Provide the role name."

**If creating new**:

```bash
# Create the role — Snowflake will assume it; use your account as placeholder for now
aws iam create-role \
  --role-name snowflake-glue-access \
  --assume-role-policy-document '{
    "Version":"2012-10-17",
    "Statement":[{
      "Effect":"Allow",
      "Principal":{"AWS":"arn:aws:iam::<AWS_ACCOUNT_ID>:root"},
      "Action":"sts:AssumeRole",
      "Condition":{"StringEquals":{"sts:ExternalId":"placeholder"}}
    }]
  }' \
  --profile <PROFILE>

# Attach Glue read policy
aws iam put-role-policy \
  --role-name snowflake-glue-access \
  --policy-name glue-iceberg-read \
  --policy-document '{
    "Version":"2012-10-17",
    "Statement":[
      {
        "Effect":"Allow",
        "Action":[
          "glue:GetCatalog","glue:GetDatabase","glue:GetDatabases",
          "glue:GetTable","glue:GetTables"
        ],
        "Resource":"*"
      },
      {
        "Effect":"Allow",
        "Action":["s3:GetObject","s3:ListBucket","s3:GetBucketLocation",
                  "s3:PutObject","s3:DeleteObject"],
        "Resource":[
          "arn:aws:s3:::<S3_BUCKET>",
          "arn:aws:s3:::<S3_BUCKET>/*"
        ]
      }
    ]
  }' \
  --profile <PROFILE>
```

> **Note**: The trust policy uses a placeholder external ID. The parent skill's Create Workflow (Step 2) will replace it with the real Snowflake IAM user ARN and `STORAGE_AWS_EXTERNAL_ID` / `GLUE_AWS_EXTERNAL_ID` after the integrations are created. See `create/SKILL.md` Step 2.5.
>
> **S3 write permissions** (`PutObject`, `DeleteObject`) are required even for read-only Iceberg use cases — Snowflake's external volume validation writes and deletes a probe file during setup.

Capture `IAM_ROLE_ARN` from the `create-role` output (or from `aws iam get-role --role-name snowflake-glue-access`).

---

Once the user confirms they want Snowflake integration, return to the **parent `glueirc-catalog-integration-setup` skill** (Create Workflow) with these collected variables:

| Variable needed by parent skill | Source |
|------------------------------------|--------|
| `AWS_ACCOUNT_ID` | Phase 1 |
| `AWS_REGION` | Phase 1 |
| `S3_BUCKET` | Phase 2 |
| `ICEBERG_OUTPUT_PREFIX` (e.g., `iceberg/`) | Phase 5 |
| `GLUE_DB_NAME` | Phase 3 |
| `IAM_ROLE_ARN` for Snowflake | Handoff step above |
| `TABLE_NAMES[]` — list of converted Iceberg tables | Phase 5 |

Tell the user:
> AWS side is ready. Your Iceberg tables are registered in Glue database `<DB_NAME>`.
> Next step: set up the Snowflake catalog integration, external volume, and CLD.
> Returning to the Glue catalog integration setup workflow.

Then continue with the parent skill's **Create Workflow → Step 2** (catalog integration creation).

> **Snowflake type mapping note**: Athena `TIMESTAMP` (without timezone) maps to Iceberg `timestamp`, which Snowflake reads as `TIMESTAMP_NTZ(6)` (microsecond precision, no timezone). If your data has timezone-aware timestamps, use `TIMESTAMP WITH TIME ZONE` in Athena — Snowflake maps Iceberg `timestamptz` to `TIMESTAMP_LTZ(6)`. See `references/ATHENA_TYPE_MAPPING.md` for the full Iceberg→Snowflake mapping.

---

## Stopping points summary

| After Phase | Gate | What to confirm |
|-------------|------|-----------------|
| Phase 1 | **STOP** | AWS credentials working, account ID and region captured |
| Phase 2 | **STOP** | Which files to convert, directory structure OK |
| Phase 4 | **STOP** | Table schemas correct, types validated |
| Phase 5.8 | **STOP** | Before dropping source tables (destructive) |

---

## Variables to collect

| Variable | Example | Phase |
|----------|---------|-------|
| `AWS_PROFILE` | `Contributor-849350360261` | 0 (routing) |
| `AWS_REGION` | `us-west-2` | 0 (routing) |
| `AWS_ACCOUNT_ID` | `849350360261` | 1 |
| `S3_BUCKET` | `avalanche-dataset` | 1 |
| `S3_DATA_PREFIX` | `parquet/` | 2 |
| `GLUE_DB_NAME` | `avalanche_db` | 3 |
| `CRAWLER_ROLE_NAME` | `glue-crawler-role` | 3 |
| `CRAWLER_ROLE_ARN` | `arn:aws:iam::849350360261:role/glue-crawler-role` | 3 |
| `CRAWLER_NAME` | `avalanche-crawler` | 3 |
| `TABLE_NAMES[]` | `[customer_reviews, order_history, ...]` | 4 |
| `ICEBERG_OUTPUT_PREFIX` | `iceberg/` | 5 |
| `ATHENA_RESULTS_BUCKET` | `849350360261-us-west-2-athena-results` | 5 |

---

## Error handling summary

| Error | Phase | Cause | Fix |
|-------|-------|-------|-----|
| `ExpiredToken` | 1 | AWS session expired | `aws sso login --profile <PROFILE>` |
| `AccessDenied` on S3 | 1 | Missing S3 permissions | Check IAM policies |
| `AlreadyExistsException` | 3 | DB/crawler exists | Use existing or delete first |
| Crawler stuck `RUNNING` | 3 | S3 permission or network issue | Check Glue console |
| `Insufficient Lake Formation permission(s)` | 3 | LF enabled; crawler role missing LF grants | Follow step 3.2a — grant `DESCRIBE`, `CREATE_TABLE`, `ALTER` on DB; grant `DATA_LOCATION_ACCESS` on S3 bucket if registered |
| `HIVE_BAD_DATA` | 5 | Type mismatch in CTAS | Fix types per `ATHENA_TYPE_MAPPING.md` |
| `TABLE_NOT_FOUND` | 5 | Glue table name mismatch | Verify with `get-tables` |
| `SYNTAX_ERROR: backquoted identifiers` | 5 | Backticks in Trino DML | Use double quotes |
| `AccessDenied` on `iam:CreateRole` | 3 | Caller lacks IAM role creation permissions | Use existing role (step 3.2 option A) or ask AWS admin to create the role |
| `InvalidRequestException` on Athena workgroup | 5 | Athena engine version mismatch or misconfigured workgroup | Verify engine v3 (step 5.0) or switch to Glue Spark approach |
