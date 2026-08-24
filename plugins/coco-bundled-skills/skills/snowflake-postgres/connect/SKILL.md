---
name: snowflake-postgres-connect
description: "Network policy setup and connectivity checks. Triggers: 'my IP', 'network policy', 'can't connect', 'add IP', 'import connection'."
parent_skill: snowflake-postgres
---

# Snowflake Postgres - Connect

> **Windows users:** see [references/windows.md](../references/windows.md) — install prereqs, credential file paths (`%APPDATA%\postgresql\` instead of `~/`), and command-flow notes differ on native Windows. WSL behaves as Linux.

## When to Load

From `snowflake-postgres/SKILL.md` when intent is CONNECT.

**Note:** All `<SKILL_DIR>` placeholders must be absolute paths.

## Workflow

### Verify Saved Connection (Before Any Operations)

Before running any workflow that requires a saved connection, read existing saved connections:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py --list
```
If the target instance isn't present, use the import flow below.

### Import Connection

For instances created outside Cortex Code (UI, CLI, etc.).

#### Step 1: List Existing Instances

```sql
SHOW POSTGRES INSTANCES;
```

List saved connections (no secrets) and compare against instance names:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py --list
```
`<SKILL_DIR>` must be an absolute path.

If any instances are not saved, ask:
```
I see these instances not in your connections file: [list].
Would you like to add one? If yes, I can pre-fill host/port/user, and you can add the password locally.
```

#### Step 2: Get Instance Details

```sql
DESCRIBE POSTGRES INSTANCE <instance_name>;
```

⚠️ **DESCRIBE may contain sensitive metadata in `access_roles`** - do NOT display raw SQL results. Extract only: `host`.

#### Step 2b: Fetch CA Certificate

After DESCRIBE, fetch the CA certificate for server identity verification:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
  --fetch-cert \
  --instance-name <instance_name> \
  --connection-name <instance_name> \
  [--snowflake-connection <name>]
```

This saves the cert to `~/.snowflake/postgres/certs/<instance_name>.pem` and upgrades the service entry to `sslmode=verify-ca` if the entry exists. If the entry doesn't exist yet (first import), the cert is still saved and will be referenced in Step 3.

#### Step 3: Add Connection Locally (No Secrets in Chat)

**Never** ask the user to paste a password into chat. Connections use standard PostgreSQL files.

Provide what we know:
- `host` from DESCRIBE
- `port` 5432
- `database` `postgres`
- `user` `snowflake_admin`
- `sslmode` `verify-ca` (with cert from Step 2b)
- `sslrootcert` path from Step 2b output

Tell user to add to `~/.pg_service.conf`:
```ini
[<instance_name>]
host=<host>
port=5432
dbname=postgres
user=snowflake_admin
sslmode=verify-ca
sslrootcert=/Users/<user>/.snowflake/postgres/certs/<instance_name>.pem
```

If cert fetch failed in Step 2b, fall back to `sslmode=require` (omit `sslrootcert`).

**⚠️ For password management, always use file-based methods** - never show passwords or `.pgpass` format.

If the user needs new credentials, use `pg_connect.py --reset` (it handles SQL internally and updates ~/.pgpass):
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
  --reset \
  --instance-name <instance_name> \
  --host <host_from_describe> \
  [--role <snowflake_admin|application>] \
  [--snowflake-connection <name>]
```
Use `--host` to create the connection if it doesn't exist. `<SKILL_DIR>` must be an absolute path. **Never execute RESET ACCESS via SQL tool** - passwords would appear in chat.

#### Step 4: Confirm

After the user has updated their connection (manually or via script):
```
✅ Connection **[instance_name]** ready
   Host: [host]
   Service file: ~/.pg_service.conf
   Password: ~/.pgpass
   Connect with: psql "service=[instance_name] connect_timeout=10"
```

### Non-Snowflake Postgres (Neon, Supabase, RDS, Aurora, Azure, Cloud SQL, Crunchy Bridge, self-hosted, etc.)

When the user's Postgres is not on Snowflake, the core advice is simple: **use standard PostgreSQL tooling**. The connection files (`~/.pg_service.conf` and `~/.pgpass`) are plain Postgres, not Snowflake-specific, so anything that speaks Postgres (psql, pgAdmin, DBeaver, `pg_doctor.py`) works against them once saved.

**Crunchy Bridge note:** Snowflake Postgres was built on Crunchy's technology, but **Crunchy Bridge** (the standalone managed service) is still a separate product. Users coming from or still using Crunchy Bridge treat it exactly like any other external Postgres — standard tools only, no Snowflake-specific commands.

#### What does NOT apply to non-Snowflake Postgres

Do not run any of these — they will error and mislead the user:

- Snowflake SQL against the Postgres instance: `SHOW POSTGRES INSTANCES`, `DESCRIBE POSTGRES INSTANCE`, `ALTER POSTGRES INSTANCE …`, `EXECUTE POSTGRES QUERY`
- Script subcommands: `pg_connect.py --create`, `--reset`, `--fetch-cert`, `--ensure-ready`, `--upgrade-ssl`
- Snowflake network policies (`POSTGRES_INGRESS` rules); the provider has its own IP allowlist mechanism
- `pg_lake` / Iceberg setup (`pg_lake_setup.py`, `pg_lake_storage.py`)

#### What works unchanged

- `psql "service=<name> connect_timeout=10" -c "<SQL>"` for running any query
- `pg_connect.py --list` to see what's saved
- `pg_doctor.py --connection-name <name>` for health diagnostics (uses only standard `pg_catalog` / `pg_statio` views)
- Any standard `psql` meta-command the user asks for (`\d`, `\dt`, `\l`, etc.)

Known caveat for `pg_doctor.py` on non-Snowflake Postgres: the `outliers` check requires the `pg_stat_statements` extension to be loaded. Many hosted Postgres providers (Neon, Supabase free tier, RDS without a custom parameter group) do not enable it by default — that check will show a warning like `pg_stat_statements not enabled` while all other checks run normally. Tell the user how to enable it if they want slow-query insights (it's a server-level setting on most providers).

#### Saving a non-Snowflake connection

**Never accept a password pasted in chat.** Walk the user through adding it themselves — the files are standard Postgres:

1. **Ask for non-sensitive details only:** host, port (usually 5432), database name, user, and the required SSL mode.
2. **Tell them to add an entry to `~/.pg_service.conf`:**
   ```ini
   [<short_name>]
   host=<host>
   port=5432
   dbname=<database>
   user=<user>
   sslmode=require
   ```
3. **Tell them to add the password to `~/.pgpass`** (format `host:port:database:user:password`, one line, file must be `chmod 600`). PostgreSQL refuses to read `.pgpass` unless permissions are correct.
4. **Verify** with either:
   - `psql "service=<short_name> connect_timeout=10" -c "SELECT 1;"`, or
   - `pg_connect.py --test --connection-name <short_name>` (tests the saved connection without asking for the string again).
   If that succeeds, everything else listed under "What works unchanged" above will just work.

Common SSL defaults by provider (use these as a starting point, but let the user override if they know otherwise):

| Provider hint (host pattern) | Typical `sslmode` |
|---|---|
| Neon (`*.neon.tech`) | `require` |
| Supabase (`*.supabase.co`, `*.pooler.supabase.com`) | `require` |
| AWS RDS / Aurora (`*.rds.amazonaws.com`) | `require` (or `verify-full` if CA bundle is set up) |
| Azure Database for Postgres (`*.postgres.database.azure.com`) | `require` |
| Google Cloud SQL | `require` or `verify-ca` |
| Crunchy Bridge (`*.postgresbridge.com` / `*.crunchybridge.com`) | `require` |
| Self-hosted / unknown | Ask the user; default to `require` |

If `psql` errors with an SSL mismatch, try `sslmode=require` first; only move to `verify-ca` / `verify-full` if the provider's CA bundle is already on disk.

#### If the user wants Snowflake-only features on their non-Snowflake Postgres

Tell them directly that these features are Snowflake Postgres-specific (not something this skill can set up on external providers) and suggest the equivalent concept on their provider (e.g., "For Neon, IP allowlisting is in the Neon dashboard under project settings"). Do not attempt to run Snowflake SQL against the instance.

### Get User's IP

```bash
curl -s ifconfig.me
```

Always append `/32` for CIDR notation for a single IP when using in network rules.

Optional: If the user already has a network policy name and wants to verify access first:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/network_policy_check.py \
  --policy-name <POLICY_NAME> \
  --ip <IP>
```
`<SKILL_DIR>` must be an absolute path.

### Setup Network Policy

**⚠️ MANDATORY STOPPING POINT**

⚠️ **Postgres requires `POSTGRES_INGRESS` mode** - standard policies won't work!

#### Step 1: Get Approval
⚠️ **If the user is planning to use an IP/subnet that will be open to the internet or a very large range, eg 0.0.0.0/0, ::/0 stop and warn them about the risks**

Present to user:
```
⚠️ Please verify with your Security team before making any networking changes. 
Creating any network policies can have security implications.

I will create a network policy to allow your IP ([IP]/32) to connect.

This involves:
1. Creating a network rule (POSTGRES_INGRESS mode)
2. Creating a network policy
3. Attaching it to the instance

Proceed? (yes/no)
```

#### Step 2: Execute ALL Three SQL Statements

After approval, **execute all three SQL statements in sequence:**

```sql
-- Execute Step 1: Create network rule
CREATE NETWORK RULE POSTGRES_INGRESS_RULE_<INSTANCE>
  TYPE = IPV4
  VALUE_LIST = ('<IP>/32')
  MODE = POSTGRES_INGRESS;
```

```sql
-- Execute Step 2: Create network policy
CREATE NETWORK POLICY POSTGRES_INGRESS_POLICY_<INSTANCE>
  ALLOWED_NETWORK_RULE_LIST = ('POSTGRES_INGRESS_RULE_<INSTANCE>');
```

```sql
-- Execute Step 3: Attach to instance
ALTER POSTGRES INSTANCE <INSTANCE>
  SET NETWORK_POLICY = 'POSTGRES_INGRESS_POLICY_<INSTANCE>';
```

Do NOT stop after step 1 - complete all three steps.

### First-Connection Troubleshooting (Local `psql` → Snowflake Postgres)

When a user says "I can't connect" or local `psql` never worked, classify the failure before suggesting fixes. Always use fail-fast commands:

```bash
psql "service=<instance_name> connect_timeout=10" -c "SELECT 1;"
```

Three common classes:

| Symptom | Likely cause | Next step |
|---------|--------------|-----------|
| Timeout / hang / no route | Missing or wrong network policy / IP not allowlisted | Verify `POSTGRES_INGRESS` policy is attached, then confirm current IP is included |
| SSL / certificate verification error | Wrong `sslmode`, missing CA cert, stale cert path | Run `pg_connect.py --fetch-cert`, prefer `sslmode=verify-ca`, or fall back to `sslmode=require` if cert fetch is unavailable |
| Connection refused / instance unavailable / admin shutdown | Instance is suspended or not ready | Check instance state in Snowflake, resume/wait, then retry |

#### 1. Network-policy failures

Typical signals:
- `timeout expired`
- hangs until `connect_timeout=10`
- connection works from one network but not another

Check:
- whether a network policy is attached to the instance
- whether the current public IP is in the policy's allowed rules

If missing, route to **Setup Network Policy** above. If present but wrong, update the rule list for the user's current IP.

#### 2. SSL / CA failures

Typical signals:
- certificate verify failures
- hostname / CA chain complaints
- connection succeeds only with insecure SSL settings

Preferred fix order:

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
  --fetch-cert \
  --instance-name <instance_name> \
  --connection-name <instance_name> \
  [--snowflake-connection <name>]
```

Then ensure the service entry uses:

```ini
sslmode=verify-ca
sslrootcert=/Users/<user>/.snowflake/postgres/certs/<instance_name>.pem
```

If cert fetch cannot run yet, use `sslmode=require` as a temporary fallback and tell the user the stronger fix is to fetch/install the CA cert.

#### 3. Suspended / not-ready instances

Typical signals:
- connection refused immediately
- instance was recently created or resumed
- Snowflake-side commands show the instance is suspended / resuming

Check instance state in Snowflake and resume if needed. Re-test only after the instance reports ready.

```sql
SHOW POSTGRES INSTANCES LIKE '<instance_name>';
DESCRIBE POSTGRES INSTANCE <instance_name>;
```

#### What to say back

Give a concrete diagnosis and one next action:

```text
This looks like a network-policy issue, not a password problem.
Your next step is to attach or update a `POSTGRES_INGRESS` policy for your current IP, then retry:

  psql "service=<instance_name> connect_timeout=10" -c "SELECT 1;"
```

Avoid vague advice like "check your connection settings" when the error clearly matches one of the three classes above.

## Output

- IP address shown
- Network policy SQL executed/confirmed
