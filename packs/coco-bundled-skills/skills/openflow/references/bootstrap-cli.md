---
name: openflow-bootstrap-cli
description: One-time CLI/terminal environment bootstrap for Openflow — install tooling, discover infrastructure, create nipyapi profiles, write the local cache. CLI/Desktop surface only. Not used on the Snowsight (SQL-only) surface, which has nothing to provision.
---

# Openflow CLI Bootstrap

This reference provisions the local **CLI/Desktop** environment so nipyapi-based Openflow work can run: it verifies tooling, discovers infrastructure, creates nipyapi profiles, and writes the local cache. It is the bootstrap orchestrator that `references/core-session-cli.md` delegates to when the environment is not yet ready.

**Surface note:** This is CLI-surface only. The Snowsight (SQL-only) surface has no bootstrap — session init there is `references/core-session-sql.md` (connection + SOM probe, no tooling/cache/profiles). Follow the steps below in order; each fills in what's missing.

## Step 1: Verify Tooling

```bash
which snow && which nipyapi && which python3
```

| Result | Action |
|--------|--------|
| Any tool missing | **STOP.** Load `references/bootstrap-tooling.md` and follow its instructions. Do NOT install tools using general knowledge -- the reference contains required configuration (e.g., package extras, install method) that differs from standard installation. Return here after tooling is verified. |
| All found | Continue to Step 1b |

### Step 1b: Ensure Tooling in Cache

If a cache file exists but has no `tooling` section, add it now with the commands you just verified:

```bash
# Check if tooling section exists
cat ~/.snowflake/cortex/memory/openflow_infrastructure_*.json 2>/dev/null | jq '.tooling'
```

| Result | Action |
|--------|--------|
| Returns null | Update the cache with tooling section (see below) |
| Returns object | Continue to Step 2 |

**Update cache with tooling:**
```bash
jq '.tooling = {preferred: "nipyapi", python_command: "python3", pip_command: "<PIP_CMD>", updated_at: "<TIMESTAMP>"}' \
  ~/.snowflake/cortex/memory/openflow_infrastructure_<CONNECTION>.json > tmp && mv tmp ~/.snowflake/cortex/memory/openflow_infrastructure_<CONNECTION>.json
```

Replace `<PIP_CMD>` with `uv pip` if uv is installed, otherwise `pip3`.

## Step 2: Check Cache and Select Connection

```bash
ls ~/.snowflake/cortex/memory/openflow_infrastructure_*.json 2>/dev/null
```

| Result | Action |
|--------|--------|
| No cache files | Go to Step 2a (select connection and discover) |
| One cache file | Before using it, show the cached connection name and resolve its account so the user can confirm it's the intended one — the cache may be from an earlier session against a different account. Resolve the account with `snow connection list --format json \| jq -r '.[] \| select(.connection_name=="<name>") \| .parameters.account'`, present both, and confirm before continuing to Step 3. If it's not the intended connection, go to Step 2a to reselect. |
| Multiple cache files | Ask user: "Which connection?" then continue to Step 3 |

### Step 2a: Select Snowflake Connection (No Cache)

```bash
snow connection list --format json | jq -r '.[] | "\(.connection_name)\(if .is_default then " (default)" else "" end)"'
```

| Result | Action |
|--------|--------|
| Single connection | Use it |
| Multiple connections | Ask: "Which Snowflake connection for Openflow?" |

Test the selected connection:

```bash
snow connection test -c <CONNECTION>
```

| Result | Action |
|--------|--------|
| Success | Continue to Step 2b |
| Fails | STOP. Tell user: "Fix Snowflake connection with `snow connection add` or check credentials and networking" |

### Step 2b: Discover Infrastructure

Load `references/bootstrap-discovery.md` to find deployments and runtimes, then continue to Step 3.

## Step 3: Validate Cache Contents

```bash
cat ~/.snowflake/cortex/memory/openflow_infrastructure_<CONNECTION>.json | jq '{
  runtimes: [.deployments[].runtimes[] | {name: .runtime_name, profile: .nipyapi_profile}]
}'
```

| Result | Action |
|--------|--------|
| No runtimes listed | Load `references/bootstrap-discovery.md`, then continue |
| Runtimes exist but no `nipyapi_profile` values | Go to Step 4 |
| Runtimes with profiles | Continue to Step 5 |

## Step 4: Create Profiles

Load `references/bootstrap-auth.md` to create nipyapi profiles, then continue to Step 5.

## Step 5: Select Runtime

```bash
cat ~/.snowflake/cortex/memory/openflow_infrastructure_<CONNECTION>.json | jq -r '.deployments[].runtimes[] | "\(.runtime_name): \(.nipyapi_profile)"'
```

| Result | Action |
|--------|--------|
| Single runtime | Use that profile |
| Multiple runtimes | Ask: "Which runtime do you want to work with?" |

## Step 6: Verify Connectivity

```bash
nipyapi --profile <PROFILE> system get_nifi_version_info
```

| Result | Action |
|--------|--------|
| Returns NiFi version | **Setup complete.** Return to main skill. |
| 401/403 error | Token expired or potential VPN issue. Load `references/bootstrap-auth.md` to refresh PAT. |
| Connection refused | Runtime may be stopped. Offer to resume: `ALTER OPENFLOW RUNTIME <db>.<schema>.<name> RESUME;` (ask user permission first). If unavailable or pre-SOM, check Openflow Control Plane UI. |
| "Cannot find key: --profile" | nipyapi outdated. Load `references/bootstrap-tooling.md` to reinstall. |

## Setup Complete

The environment is ready:
- Connection name is in the cache `connection` field
- Profile name is in the cache `nipyapi_profile` field for the selected runtime

Return to the main skill for routing, or to `references/core-session-cli.md` if validating session state.

## Related References

- `references/bootstrap-tooling.md` - Install missing tools
- `references/bootstrap-discovery.md` - Discover Openflow infrastructure
- `references/bootstrap-auth.md` - Create nipyapi profiles
- `references/core-session-cli.md` - Cache schema and session workflow
