# pg_lake Troubleshooting

Common errors and fixes encountered during pg_lake setup and usage.

## Storage Integration Errors

### Wrong integration type

**Error:** `Invalid storage integration type` or integration doesn't work with pg_lake

**Cause:** Used `EXTERNAL_STAGE` instead of `POSTGRES_EXTERNAL_STORAGE`

**Fix:** pg_lake requires `TYPE = POSTGRES_EXTERNAL_STORAGE`, not the standard Snowflake stage type:
```sql
CREATE STORAGE INTEGRATION my_int
  TYPE = POSTGRES_EXTERNAL_STORAGE  -- NOT EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  ...
```

### Needing BOTH integration types on the same bucket

**Error:** `not a storage integration of type EXTERNAL_STAGE` when trying to `CREATE STAGE` from a pg_lake integration (or the reverse when attaching to a PG instance).

**Cause:** The two integration types are not interchangeable and **cannot be mixed**:
- `POSTGRES_EXTERNAL_STORAGE` — attach to a PG instance so pg_lake writes Iceberg to S3.
- `EXTERNAL_STAGE` — back a Snowflake stage for `LIST`/`REMOVE`/file ops on the same bucket.

A workflow that both writes via pg_lake **and** manages files through a stage (e.g. reset/cleanup flows that `REMOVE` old data) needs **two separate integrations** pointing at the **same bucket and same IAM role** but with different `TYPE`:

```sql
CREATE STORAGE INTEGRATION pglake_s3
  TYPE = POSTGRES_EXTERNAL_STORAGE  STORAGE_PROVIDER = 'S3'
  STORAGE_AWS_ROLE_ARN = '<role>'   STORAGE_ALLOWED_LOCATIONS = ('s3://bucket/');

CREATE STORAGE INTEGRATION pglake_stage_s3
  TYPE = EXTERNAL_STAGE             STORAGE_PROVIDER = 'S3'
  STORAGE_AWS_ROLE_ARN = '<role>'   STORAGE_ALLOWED_LOCATIONS = ('s3://bucket/');
```

⚠️ Each integration gets its **own** `STORAGE_AWS_IAM_USER_ARN` + `STORAGE_AWS_EXTERNAL_ID`. **Both** pairs must be added to the IAM role's trust policy — run `pg_lake_storage.py describe` on each and update the trust policy with both.

### Insufficient role

**Error:** `Insufficient privileges to operate on integration`

**Cause:** Not using ACCOUNTADMIN role

**Fix:** Storage integration operations require ACCOUNTADMIN:
```sql
USE ROLE ACCOUNTADMIN;
CREATE STORAGE INTEGRATION ...
```

## AWS / IAM Errors

### 12-hour session duration (most common)

**Symptom:** Storage integration creates successfully but pg_lake operations fail silently or timeout after ~1 hour

**Cause:** IAM role Maximum session duration left at default (1 hour). pg_lake sessions run longer.

**Fix:** In AWS Console → IAM → Roles → your role → Edit → Maximum session duration → **12 hours** (43200 seconds)

### Trust policy not updated

**Error:** pg_lake cannot access S3 after integration is attached

**Cause:** IAM trust policy still has placeholder values or wasn't updated with Snowflake's IAM user ARN and external ID

**Fix:**
1. Run `pg_lake_storage.py describe --name <integration>` to get the IAM values (written to secure file)
2. Update the IAM role trust policy with the `STORAGE_AWS_IAM_USER_ARN` as Principal and `STORAGE_AWS_EXTERNAL_ID` as condition

### Trust entries go stale after drop + recreate

**Symptom:** S3 access silently fails (pg_lake can't write, stage can't `LIST`) after you dropped and recreated a storage integration — no config changed on the AWS side.

**Cause:** Every `CREATE STORAGE INTEGRATION` mints a **new** `STORAGE_AWS_IAM_USER_ARN` and/or `STORAGE_AWS_EXTERNAL_ID`. The old trust-policy entries on the IAM role are now stale, so the assume-role fails.

**Fix:** After **any** recreate, re-fetch and re-apply the trust policy:
1. `pg_lake_storage.py describe --name <integration>` to get the fresh IAM values
2. Replace the old Principal ARN + `sts:ExternalId` condition in the IAM role trust policy
3. If you maintain both integration types (above), do this for **both** — each recreate churns its own pair

### Region mismatch

**Error:** `The bucket you are attempting to access must be addressed using the specified endpoint`

**Cause:** S3 bucket is in a different AWS region than the Snowflake account

**Fix:** Create the S3 bucket in the same region as your Snowflake account. Check your account region:
```sql
SELECT CURRENT_REGION();
```

### STS endpoint not active

**Error:** IAM assume-role fails

**Cause:** STS endpoint not activated for the bucket's region

**Fix:** AWS Console → IAM → Account settings → STS endpoints → Activate the endpoint for your region

## PostgreSQL Connection Errors

### Connection timeout to PG instance

**Symptom:** `psql` or `psycopg2` hangs then times out connecting to the Postgres host

**Causes:**
- No network policy attached to instance (required for external access)
- IP not in the network policy's allowed list
- VPN or corporate firewall blocking port 5432

**Fix:**
1. Create a network policy with `POSTGRES_INGRESS` mode:
```sql
CREATE NETWORK RULE my_rule TYPE = IPV4 VALUE_LIST = ('<your-ip>/32') MODE = POSTGRES_INGRESS;
CREATE NETWORK POLICY my_policy ALLOWED_NETWORK_RULE_LIST = ('my_rule');
ALTER POSTGRES INSTANCE <name> SET NETWORK_POLICY = 'my_policy';
```
2. Check your IP: `curl -s ifconfig.me`
3. Verify with `pg_lake_setup.py --check-extensions --connection-name <name>` — if it hangs, the IP isn't allowed

### Authentication failure after password reset

**Symptom:** `psql: FATAL: password authentication failed`

**Cause:** pgpass file has stale password

**Fix:** Reset credentials via script (updates pgpass automatically):
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
  --reset --instance-name <NAME> --snowflake-connection <CONN>
```

## pg_lake Extension Errors

### Extension not available

**Error:** `extension "pg_lake" is not available`

**Cause:** pg_lake not enabled on the instance or instance needs upgrade

**Fix:** Check with `pg_lake_setup.py --check-extensions`. If not available, the instance may need a version upgrade or pg_lake needs to be enabled for the account.

### Permission denied on CREATE EXTENSION

**Error:** `permission denied to create extension "pg_lake"`

**Cause:** Not using the correct Postgres role

**Fix:** Connect as `snowflake_admin` (the default admin role for Snowflake Postgres instances):
```
psql "service=<name>" -c "CREATE EXTENSION IF NOT EXISTS pg_lake CASCADE"
```

### pg_lake_iceberg.default_location_prefix not persisting

**Symptom:** `pg_lake_iceberg.default_location_prefix` resets to empty on reconnect

**Cause:** Used session-level `SET` instead of a persistent method

**Fix:** Use persistent mode (tries ALTER SYSTEM SET):
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --set-config s3://bucket/path --connection-name <name>
```

Check `persist_method` in the JSON output:
- `system` — persisted via ALTER SYSTEM, survives reconnections
- `session` — not persisted. The GUC is `PGC_SUSET` so ALTER DATABASE/ROLE SET won't work. In managed Snowflake Postgres, the platform typically sets this via `postgresql.conf` when the storage integration is attached. If ALTER SYSTEM is also blocked, session-level SET after each connect is the only option.

**Note:** The full GUC name is `pg_lake_iceberg.default_location_prefix` (not `default_location_prefix`). It's registered by the `pg_lake_iceberg` shared library.

## Iceberg Table Errors

### Cannot create Iceberg table

**Error:** `could not access storage` or `permission denied for schema`

**Cause:** Storage integration not attached, or default_location_prefix not set

**Fix:** Verify setup:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_lake_setup.py \
  --check-config --verify-s3 --connection-name <name> --json
```

### lake_file.list() returns error

**Error:** `could not list files at s3://...`

**Cause:** S3 permissions issue — IAM role doesn't have the right S3 policy, or trust policy is wrong

**Fix:** Verify the IAM policy includes: `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`, `s3:GetBucketLocation`, `s3:DeleteObject`

### `invalid identifier` on a mirrored/Iceberg column

**Error:** `invalid identifier '"started_at"'` (or similar) when querying a pg_lake Iceberg table from Snowflake

**Cause:** pg_lake writes Parquet/Iceberg with **lowercase** column names; Snowflake stores and resolves them **uppercase**. Quoted lowercase identifiers (`"started_at"`) don't match.

**Fix:** Use **unquoted** column and table names — Snowflake uppercases them automatically to match:
```sql
SELECT started_at FROM my_cld.public.readings;   -- resolves to STARTED_AT ✓
SELECT "started_at" FROM ...                      -- invalid identifier ✗
```

### Stale metadata after reset/recreate (old OIDs)

**Symptom:** After truncating/recreating pg_lake tables, discovery (per-table or CLD) surfaces stale or missing data, or points at metadata that no longer matches the current tables.

**Cause:** pg_lake keys Iceberg metadata paths by table **OID**. Recreating tables assigns new OIDs (e.g. `18626` → `18674`); the old metadata files from previous OIDs linger in S3 and can be re-discovered.

**Fix:** Wipe the stale S3 prefix as part of any reset flow before rediscovery, e.g.:
```sql
REMOVE @PGLAKE_STAGE/frompg/;   -- requires the EXTERNAL_STAGE integration (see "Needing BOTH integration types")
```
For a CLD, drop + recreate the linked database after wiping S3 to avoid stale catalog state (auto-refresh alone may retain it).
