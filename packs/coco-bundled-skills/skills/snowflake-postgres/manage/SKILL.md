---
name: snowflake-postgres-manage
description: "Manage Snowflake Postgres instances: list, describe, create, suspend, resume."
parent_skill: snowflake-postgres
---

# Snowflake Postgres - Manage

> **Windows users:** see [references/windows.md](../references/windows.md) — install prereqs, credential file paths (`%APPDATA%\postgresql\` instead of `~/`), and command-flow notes differ on native Windows. WSL behaves as Linux.

## When to Load

From `snowflake-postgres/SKILL.md` when intent is MANAGE.

**Note:** All `<SKILL_DIR>` placeholders must be absolute paths.

## Workflow

### List Instances

```sql
SHOW POSTGRES INSTANCES;
```

Present results showing name, state, compute_family, storage_size_gb.

If the user wants to import connections, compare instance names to saved connection names and offer to add missing ones:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py --list
```

### Describe Instance

```sql
DESCRIBE POSTGRES INSTANCE <instance_name>;
```

⚠️ **CRITICAL:** DESCRIBE response contains credentials in `access_roles`.
- DO NOT display raw SQL results
- Show only: name, state, host, port, database, compute_family, storage_size_gb

### Create Instance

**⚠️ MANDATORY STOPPING POINT** - Creates billable resources.

#### Step 1: Pre-flight check (feature + name collision)

Run once before gathering requirements — catches two common failure modes early:

```sql
SHOW POSTGRES INSTANCES;
```

- **Errors** (e.g., "unsupported feature", "syntax error near POSTGRES") → Snowflake Postgres may not be enabled on this account/region. Tell the user to verify the feature is available in their region and ask their account admin to confirm enablement before proceeding. Do not proceed to CREATE.
- **Succeeds** → feature is available. Check the result for an existing instance with the requested name; if it exists, suggest a different name before proceeding.

#### Step 2: Gather Requirements

**Load** `references/instance-options.md` for valid options.

**Ask** user with ready-to-go defaults:
```
I'll create a Postgres instance with these defaults:

  Name:     pg_[timestamp]
  Size:     Default general-purpose family (see `references/instance-options.md`)
  Storage:  10 GB
  HA:       Off

Type yes to proceed, or tell me what to change.
Type "options" to see all available configurations.
```

**If user says "options":** Use `ask_user_question` to show what they can change:
```
What would you like to configure?

1. Instance size (see `references/instance-options.md`)
2. Storage (currently: 10 GB)
3. High availability (currently: Off)
4. Postgres version (currently: latest)
5. Network policy (currently: none)
6. Authentication (currently: POSTGRES)
7. Storage integration (currently: none)
8. Postgres settings (currently: none)
9. Comment (currently: none)
```

If the user asks for sizes or limits, load `references/instance-options.md`.

**If user gives partial info:** Merge with defaults and confirm.

#### Step 3: Validate Parameters

Validate against `references/instance-options.md`:
- Compute family exists and matches type (Standard/Burstable/HighMem)
- Storage within limits (Burstable max 100GB)
- HA not available for Burstable instances
- Network policy exists if specified

#### Step 4: Check active role (privilege check)

`CREATE POSTGRES INSTANCE` requires `CREATE POSTGRES INSTANCE ON ACCOUNT` — typically held by `ACCOUNTADMIN` or a custom role with an explicit grant. Check what the user can use before attempting the billable operation.

Run:
```sql
SELECT CURRENT_ROLE();
```

**If result is `ACCOUNTADMIN`** → proceed to Step 5 with no role override.

**Otherwise** → run:
```sql
SELECT CURRENT_AVAILABLE_ROLES();
```
This returns a JSON array of roles the user can activate. Parse the list and present a picker via `ask_user_question`, ranking candidates so the user sees likely-to-work options first:

- `ACCOUNTADMIN` if present → labelled **Recommended**
- Any role matching `*ADMIN*` (e.g. `SYSADMIN`, `SECURITYADMIN`) → labelled **Likely works**
- All other roles → labelled **May not have CREATE POSTGRES INSTANCE**
- Final option: "Try anyway with current role (`<current>`)" — useful when the user has a custom grant

```
Your current role is <current_role>. CREATE POSTGRES INSTANCE
typically requires ACCOUNTADMIN or a role with an explicit grant.

Which role should I use for this CREATE?
[picker with ranked options from CURRENT_AVAILABLE_ROLES()]
```

Remember the selected role (`<chosen_role>`) — it will be passed via `--use-role` in Step 6. This override is session-scoped to the script invocation only; it does not modify `~/.snowflake/connections.toml` or `~/.snowflake/config.toml`.

#### Step 5: Get Approval

Present full configuration to user:
```
I will create a Postgres instance:

| Setting | Value |
|---------|-------|
| Name | [name] |
| Compute | [compute_family] ([cores] cores, [memory]) |
| Storage | [size] GB |
| Postgres | [version] |
| High Availability | [Yes/No] |
| Authentication | [POSTGRES or POSTGRES_OR_SNOWFLAKE] |
| Network Policy | [policy_name or "None - configure after"] |
| Storage Integration | [integration_name or omit if none] |
| Comment | [comment or omit if none] |
| Snowflake Role | [chosen_role] |

⚠️ This creates a billable resource and requires a role with
   CREATE POSTGRES INSTANCE privilege (typically ACCOUNTADMIN).
Proceed? (yes/no)
```

**NEVER proceed without explicit approval.**

#### Step 6: Execute

**⚠️ MANDATORY: Use `pg_connect.py --create`** - this is the ONLY way to create instances that does not show passwords. Do NOT use `snowflake_sql_execute` or any SQL tool. The script:
1. Executes CREATE SQL internally (using `--use-role` if provided)
2. Fetches CA certificate via DESCRIBE (for `sslmode=verify-ca`)
3. Saves connection to `~/.pg_service.conf` with cert verification
4. Saves password to `~/.pgpass` automatically
5. Probes port 5432 to report reachability
6. Never exposes passwords or certificate content in chat

**Do NOT ask the user if they want to save the connection - the script saves automatically.**

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
  --create \
  --instance-name <name> \
  --compute-pool <compute_family> \
  --storage <size> \
  [--enable-ha] \
  [--postgres-version <version>] \
  [--network-policy <policy_name>] \
  [--auth-authority <POSTGRES|POSTGRES_OR_SNOWFLAKE>] \
  [--storage-integration <integration_name>] \
  [--postgres-settings '<json>'] \
  [--comment '<text>'] \
  [--use-role <chosen_role>] \
  [--snowflake-connection <name>]
```

**Parameters:**
- `--compute-pool` - valid `COMPUTE_FAMILY` from `references/instance-options.md`
- `--storage` - Size in GB (10-65535)
- `--enable-ha` - Enable high availability
- `--postgres-version` - Postgres version (e.g., 18)
- `--network-policy` - Network policy name (must exist)
- `--auth-authority` - `POSTGRES` (default) or `POSTGRES_OR_SNOWFLAKE` (enables Snowflake token auth)
- `--storage-integration` - Storage integration name for pg_lake (type `POSTGRES_EXTERNAL_STORAGE`)
- `--postgres-settings` - JSON server settings (e.g., `'{"postgres:work_mem": "128MB"}'` — use `:` not `=`)
- `--comment` - Free-form text comment
- `--use-role` - Snowflake session role override from Step 4 (e.g., `ACCOUNTADMIN`). Only active for this invocation — no config files are modified.
- `--snowflake-connection` - Snowflake CLI connection name (optional)

**Extended parameters:** If the user requests parameters not supported by the script (e.g., `MAINTENANCE_WINDOW_START`, `TAG`, `FORK`), consult `references/instance-options.md` for current syntax and use raw SQL via SQL tool (but warn user credentials will be visible).

**If the script errors with "Insufficient privileges":** retry once with `--use-role ACCOUNTADMIN`. If still failing, ask the user's account admin to run `GRANT CREATE POSTGRES INSTANCE ON ACCOUNT TO ROLE <role>;`.

**If the script errors with `team_iam_role_arn_not_found` or similar `INTERNAL_ERROR`:** this is a server-side provisioning failure. Retry once; if it persists, the Postgres feature may not be enabled for the account/region. Tell the user to verify regional availability and contact their admin.

#### Step 7: After Success — Act on the Probe Result

**⚠️ Do NOT run `--reset` after CREATE.** The `--create` script already saved the password. RESET is only for rotating passwords later.

The script's output includes a probe status line. **Your next action depends on it** — do NOT stop and wait for the user to ask:

| Probe status | Meaning | Required next step |
|--------------|---------|---------------------|
| `✅ Port 5432 reachable` | Instance is live and the network path is open (either a `--network-policy` was provided at CREATE, or the user's IP is already allowed) | Confirm with user, offer a test query via `psql "service=<name> connect_timeout=10" -c "SELECT version();"` |
| `⚠️ Port 5432 not reachable (timed out)` | No network policy allowing this IP | **Immediately** offer to set up a network policy (route to `connect/SKILL.md` → Setup Network Policy). `psql` will hang until one is configured. |
| `⏳ Port 5432 refused` | Instance still provisioning | Run `pg_connect.py --ensure-ready --instance-name <name>` to wait for READY, then re-probe or retry psql. In parallel, offer network policy setup. |
| `⏳ Host DNS not propagated` | Just-created hostname not yet resolvable | Wait 30–60s, then run `--ensure-ready` before psql. |

Relay the script's output to the user, then **actively drive the next step** — do not leave them with a reachability warning and no follow-up.

Sample user-facing message (when the probe reported `timed out` — no network policy yet):
> ✅ Created **[name]** ([compute], [storage]GB)
> ✅ Connection saved to `~/.pg_service.conf`
> ✅ Password saved to `~/.pgpass`
> ✅ CA certificate saved, `sslmode=verify-ca`
>
> The instance isn't reachable on port 5432 yet — no network policy is allowing your IP. `psql` will hang until one is set up. Want me to configure a network policy for your IP now?

If the cert line showed a warning instead, the connection still works with `sslmode=require`. The cert can be fetched later with `pg_connect.py --fetch-cert --instance-name [name]`.

### Suspend Instance

**⚠️ MANDATORY STOPPING POINT** - Get approval first, then execute.

**Step 1:** Present to user what will happen:
```
I will suspend [instance_name]. This will:
- Stop compute billing (storage billing continues)
- Drop all active connections

Proceed? (yes/no)
```

**Step 2:** After user approves, execute:
```sql
ALTER POSTGRES INSTANCE <instance_name> SUSPEND;
```

### Resume Instance

```sql
ALTER POSTGRES INSTANCE <instance_name> RESUME;
```

Note: May take 3-5 minutes. Connection string remains the same.

### Reset Credentials (Rotate Password)

**⚠️ MANDATORY STOPPING POINT**

Before attempting reset, verify the instance exists and you have access. See the connect skill for workflows.

Explain impact:
```
I will reset credentials for [instance_name] and role [role_name]. This will:
- Generate a new password for the role (only `snowflake_admin` or `application`)
- Invalidate the old password (existing connections may drop)

Proceed? (yes/no)
```

**⚠️ After approval, use `pg_connect.py --reset` (NOT `snowflake_sql_execute`)** - the script handles the SQL internally and updates ~/.pgpass. Executing RESET via SQL tool would expose the new password in chat.

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py \
  --reset \
  --instance-name <instance_name> \
  [--role <role_name>] \
  [--host <host>] \
  [--use-role <snowflake_role>] \
  [--snowflake-connection <name>]
```

- Supported Postgres roles (`--role`): `snowflake_admin` (default) and `application`.
- `--host` - Creates service entry if missing (use host from DESCRIBE)
- `--use-role` - Snowflake session role override if the default role lacks privilege to ALTER the instance. Session-scoped only.
- `--snowflake-connection` - Snowflake CLI connection name (optional)

## Output

- List/Describe results (safe fields only)
- Confirmation of create/suspend/resume
- Import guidance for local connections file update

For LIST results:
- Let the SQL result table speak for itself, but you may mention they need to use ctrl+t to expand the table
- Add only a brief summary: count + any notable states (e.g., "8 instances, 2 suspended") and offer to show other details
- Don't create a second markdown table
