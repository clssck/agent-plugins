---
name: openflow-bootstrap-auth
description: Create nipyapi profiles for Openflow runtimes using PAT from Snowflake CLI config. Load when profiles are missing.
---

# Authentication Setup

Create nipyapi profiles for each runtime as instructed by the user. Each profile needs the runtime URL and a PAT.

## Prerequisites

The setup workflow has already selected `CONNECTION`. Use that value for all commands below.

## Step 1: Locate PAT

Check for PAT in order of precedence:

### Option A: SNOWFLAKE_PAT Environment Variable

```bash
[ -n "$SNOWFLAKE_PAT" ] && echo "PAT_IN_ENV" || echo "NO_ENV_PAT"
```

If `PAT_IN_ENV`, the user has exported their PAT. Ask if they'd like to use `$SNOWFLAKE_PAT` for Runtime authentication during profile creation.

### Option B: Snowflake CLI Config

```bash
cat ~/.snowflake/config.toml | grep -A 20 "\[connections.${CONNECTION}\]" | grep -qE '^password.*"eyJ' && echo "PAT_FOUND_JWT" || echo "NO_PAT_OR_NOT_JWT"
```

| Result | Action |
|--------|--------|
| `PAT_FOUND_JWT` | PAT exists in config, use it for profile creation |
| `NO_PAT_OR_NOT_JWT` | May be actual password or missing. Try Option C. |
| File not found | try connections.toml or ask the user |

### Option C: Ask User

If PAT not found in env or config:

> I couldn't find a Personal Access Token in your Snowflake CLI config or environment for connection "${CONNECTION}".
>
> To get a PAT:
> 1. Go to Snowsight → your profile → Personal Access Tokens
> 2. Create a new token (or copy existing)
> 3. Paste it here (I'll store it securely in profiles.yml)

**Never print the PAT value to console.**

## Step 2: Get Runtimes from Cache

```bash
cat ~/.snowflake/cortex/memory/openflow_infrastructure_${CONNECTION}.json | jq -r '.deployments[].runtimes[] | "\(.runtime_name)|\(.url)"'
```

This returns lines like: `spcs1runtime1|https://of--account.../spcs1runtime1/nifi-api`

## Step 3: Generate Profile Names

For each runtime, generate profile name using pattern:

```
{account_short}_{connection}_{runtime_name}
```

Example: `dchaffelson_az1_spcs1runtime1`

Extract account from connection:

```bash
snow connection list --format json | jq -r --arg conn "<CONNECTION>" '.[] | select(.connection_name == $conn) | .parameters.account' | cut -d'-' -f2 | tr '[:upper:]' '[:lower:]'
```

## Step 4: Create Profile File if not exists

```bash
mkdir -p ~/.nipyapi
```

Extract PAT directly into profile file (never echo to console):

```bash
# Extract PAT from env var or config (use head -1 to get only the first password line)
if [ -n "$SNOWFLAKE_PAT" ]; then
  PAT="$SNOWFLAKE_PAT"
else
  PAT=$(cat ~/.snowflake/config.toml | grep -A 20 "\[connections.${CONNECTION}\]" | grep -E '^password' | head -1 | sed 's/.*"\(.*\)"/\1/')
fi

# Write profile (PAT goes directly to file, not displayed)
cat >> ~/.nipyapi/profiles.yml << EOF
<profile_name>:
  nifi_url: "<runtime_url>"
  nifi_bearer_token: "${PAT}"
EOF

# Clear variable
unset PAT
```

**Important:** Use `head -1` to ensure only one password line is captured if multiple exist in the grep window.

If file already exists with profiles, append new ones. If profile name already exists, update it.

**Security note:** The PAT is extracted and written directly to the profile file without being displayed in console output.

## Step 5: Update Cache with Profile Names

Update each runtime in the cache with its `nipyapi_profile` value:

```bash
# Read current cache
CACHE=$(cat ~/.snowflake/cortex/memory/openflow_infrastructure_${CONNECTION}.json)

# Update with jq (for each runtime)
echo "$CACHE" | jq '.deployments[0].runtimes[0].nipyapi_profile = "<profile_name>"' > ~/.snowflake/cortex/memory/openflow_infrastructure_${CONNECTION}.json
```

## Step 6: Verify Profiles

For each profile created:

```bash
nipyapi --profile <profile_name> system get_nifi_version_info
```

| Result | Action |
|--------|--------|
| Returns NiFi version | Profile working |
| 401/403 error | PAT expired or invalid or potential VPN issue. Investigate or get new PAT. |
| Connection error | Runtime may not be running. Check Openflow Control Plane. |
| "Cannot find key: --profile" | nipyapi outdated. Load `references/bootstrap-tooling.md` |

## Next Step

After all profiles are verified, **continue** to `references/bootstrap-cli.md` Step 5 to select the runtime and verify full connectivity.

Do not stop here - the setup is not complete until connectivity is verified.
