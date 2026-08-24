---
name: openflow-core-session-cli
description: CLI/terminal session initialization for Openflow (nipyapi cache, profiles, version). Load on the CLI surface when work requires the NiFi API (Gen1 connectors, canvas, custom flows). Not used on the Snowsight (SQL-only) surface — see core-session-sql.md.
---

# Openflow Session Management (CLI / terminal surface)

This reference handles nipyapi-based session initialization for the **CLI/Desktop surface**. Load it when the resolved work requires the NiFi API — Gen1 connectors, canvas operations, or custom flow authoring — i.e. the "CLI + Gen1/canvas" cell of the capability x intent matrix (see `SKILL.md` Surface Detection).

**Do not load this on the Snowsight (SQL-only) surface, nor for CLI + Gen2 SQL work** — those use `references/core-session-sql.md` (connection + SOM probe, no nipyapi). Follow the workflow below only once nipyapi is genuinely needed.

**Session vs bootstrap:** this reference is the CLI **session check** — it validates that the environment is already provisioned (cache, profile, nipyapi version) for *this* interaction. When a step finds the environment is not yet ready, it delegates to the **bootstrap** orchestrator `references/bootstrap-cli.md` (one-time provisioning: install tooling, discover infra, create profiles, write cache). Session = per-start validation; bootstrap = one-time provisioning.

## Session Start Workflow

Execute these steps at the start of each Openflow session:

### Step 1: Check Cache File

```bash
ls ~/.snowflake/cortex/memory/openflow_infrastructure_*.json 2>/dev/null
```

| Result | Action |
|--------|--------|
| No files found | Load `references/bootstrap-cli.md` and follow Fresh Setup |
| One or more files | Continue to Step 2 |

### Step 2: Validate Cache Contents

```bash
cat ~/.snowflake/cortex/memory/openflow_infrastructure_*.json 2>/dev/null | jq '{
  connection: .connection,
  tooling: .tooling.preferred,
  runtimes: [.deployments[].runtimes[] | {name: .runtime_name, profile: .nipyapi_profile}]
}'
```

| Result | Action |
|--------|--------|
| No `tooling` section | Load `references/bootstrap-cli.md` for tooling setup |
| No runtimes listed | Load `references/bootstrap-cli.md` for discovery |
| Runtimes have no `nipyapi_profile` | Load `references/bootstrap-cli.md` for profile creation |
| All sections present | Continue to Step 3 |

### Step 3: Match Profile to Runtime

The cache contains `nipyapi_profile` for each runtime. Verify the profile exists in profiles.yml.

```bash
# Get expected profiles from cache
cat ~/.snowflake/cortex/memory/openflow_infrastructure_*.json 2>/dev/null | jq -r '.deployments[].runtimes[] | "\(.runtime_name): \(.nipyapi_profile)"'

# Check which profiles exist
grep -E "^[a-zA-Z].*:$" ~/.nipyapi/profiles.yml 2>/dev/null | tr -d ':' || echo "No profiles"
```

| Result | Action |
|--------|--------|
| No profiles file | Load `references/bootstrap-cli.md` for profile creation |
| Cache profile not in profiles.yml | Load `references/bootstrap-cli.md` to recreate profile |
| Single runtime in cache, profile exists | Before using the profile, confirm the cached connection is the one the user intends. Resolve and show its account (`snow connection list --format json` → match the connection name → `.parameters.account`) — the cache can reflect a prior session against a different account. If it's wrong, reselect the connection (see `references/bootstrap-cli.md`). |
| Multiple runtimes in cache | Ask user: "Which runtime do you want to work with?" then use that runtime's `nipyapi_profile` |

### Step 4: Validate nipyapi Version

Check the nipyapi version to ensure full functionality:

```bash
nipyapi --version
```

| Result | Action |
|--------|--------|
| `nipyapi 1.2.0` or higher | Continue to Step 5 |
| Lower version or error | Load `references/bootstrap-tooling.md` and follow "Upgrade nipyapi" section |

**Why this matters:** Older nipyapi versions may be missing CLI commands or modules that the skill references. Version 1.2.0+ includes the bulletins module and other essential features.

### Step 5: Session Ready

Once cache, profile, and version are validated:
1. Note the connection name (from cache `connection` field)
2. Note the selected profile name (from cache `nipyapi_profile` for chosen runtime)
3. Return to main skill for user intent routing
4. Use `--profile <profile_name>` with all nipyapi commands
5. Use `-c <connection>` with `snow sql` only when the deployment isn't on the active connection

**Do not repeat this check before every command** - only at session start or when user switches connections.

---

## Connection and Profile Commands

### Snowflake CLI

**Use `-c <connection>` when the target isn't the active connection.**

```bash
# Non-active connection - pass -c explicitly
snow sql -c myconnection -q "SHOW OPENFLOW DEPLOYMENTS;"

# Bare snow sql uses the default connection - fine only when that is the target
snow sql -q "SHOW OPENFLOW DEPLOYMENTS;"
```

**Legacy accounts (pre-SOM):** If `SHOW OPENFLOW DEPLOYMENTS` returns an error, use `SHOW OPENFLOW DATA PLANE INTEGRATIONS` instead. See `references/bootstrap-discovery.md` for the full legacy discovery path.

The connection name is stored in the cache file's `connection` field.

### nipyapi CLI

**Always use `--profile <name>` with every nipyapi command.**

```bash
# Correct - explicit profile
nipyapi --profile myprofile ci get_status

# Wrong - may connect to wrong runtime
nipyapi ci get_status
```

The `--profile` option should come before the subcommand.

### nipyapi Python

**When writing Python scripts, activate the profile at the start:**

```python
import nipyapi

nipyapi.profiles.switch('myprofile')

# All subsequent calls use the activated profile
status = nipyapi.canvas.get_process_group_status('root')
```

---

## Cache File Location

```
~/.snowflake/cortex/memory/openflow_infrastructure_{connection}.json
```

Where `{connection}` is the name of the Snowflake CLI connection.

## Cache File Schema

SPCS and BYOC use the same schema. The only differences are `deployment_type` (`spcs` or `byoc`) and the URL pattern (SPCS hosts start with `of--`; BYOC hosts contain `snowflake-customer.app`).

```json
{
  "connection": "az1",
  "discovered_at": "2025-12-18T15:30:00Z",
  "stale_after_days": 30,
  "som_enabled": true,
  "openflow_admin_role": "OPENFLOW_ADMIN_RL",

  "tooling": {
    "preferred": "nipyapi",
    "python_command": "python3",
    "pip_command": "uv pip",
    "updated_at": "2025-12-21T10:00:00Z"
  },

  "deployments": [
    {
      "deployment_name": "OPENFLOW_SPCS_DEPLOYMENT",
      "deployment_type": "spcs",
      "deployment_key": "dpnfce26",
      "event_table": "OPENFLOW.OPENFLOW.EVENTS",
      "runtimes": [
        {
          "runtime_name": "OPENFLOW.OPENFLOW.MY_RUNTIME",
          "runtime_key": "my-runtime-100",
          "execute_as_role": "OPENFLOWRUNTIMEROLE_MY_RUNTIME",
          "url": "https://of--account.snowflakecomputing.app/my-runtime-100/nifi-api",
          "nipyapi_profile": "account_runtime_name"
        }
      ]
    }
  ]
}
```

BYOC deployments use managed token auth by default (`SNOWFLAKE_MANAGED`) and have direct network access, so they do not require EAI configuration. Key-pair authentication is also supported as an alternative — see `references/ops-snowflake-auth.md`.

## Field Reference

### Top-Level Fields

| Field | Description |
|-------|-------------|
| `connection` | Snowflake CLI connection name |
| `discovered_at` | ISO timestamp of last discovery |
| `som_enabled` | Whether account uses SOM (`true`) or legacy integrations (`false`). Controls which SQL commands are available and whether Gen2 connectors are supported. |
| `openflow_admin_role` | Name of the Openflow admin role for this account. Owns infrastructure objects and holds account-level grants (CREATE DATABASE, CREATE ROLE, CREATE EXTERNAL ACCESS INTEGRATION, CREATE OPENFLOW DEPLOYMENT). Discovered via `SHOW ROLES LIKE '%OPENFLOW%'` during bootstrap-discovery. Default: `OPENFLOW_ADMIN_RL`. |
| `stale_after_days` | Days before cache should be refreshed |

### Tooling Section

| Field | Description |
|-------|-------------|
| `preferred` | User's preferred tool: `nipyapi` or `curl` |
| `python_command` | Detected python command: `python3` or `python` |
| `pip_command` | Detected pip command: `uv pip`, `pip3`, or `pip` |

**Use cached commands:** When running python or pip, use the cached values instead of hardcoding.

### Runtime Fields

| Field | Description |
|-------|-------------|
| `runtime_name` | Schema-qualified runtime name (from `DESCRIBE OPENFLOW RUNTIME`) |
| `runtime_key` | URL segment used in API paths |
| `url` | Full NiFi API URL for this runtime |
| `nipyapi_profile` | Profile name for nipyapi commands |
| `execute_as_role` | Snowflake role used for managed token auth (SPCS and BYOC) |

### Deployment Fields

| Field | Description |
|-------|-------------|
| `deployment_name` | Openflow deployment name |
| `deployment_key` | Internal key from `SHOW OPENFLOW DEPLOYMENTS` |
| `deployment_type` | `spcs` or `byoc` |
| `event_table` | Table for querying runtime logs |

## Related References

- `references/bootstrap-cli.md` - Populates the cache via discovery workflow
- `references/core-guidelines.md` - Tool hierarchy and safety reminders
