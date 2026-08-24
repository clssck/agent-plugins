---
name: snow-cli-detection
description: "Detects whether Snow CLI is installed; run before sub-skills that support CLI path"
parent_skill: native-app-provider
---

# Snow CLI Detection Probe

Loaded from the root `native-app-provider` router before routing to sub-skills that support Snow CLI. Determines whether the Snowflake CLI is available and passes the result downstream.

## Detection Steps

### Step 1: Check for Snow CLI

Run:

```bash
snow --version
```

### Step 2: Interpret Result

**If the command succeeds** and returns a version string (e.g., `Snowflake CLI version: 3.7.0`):

- Set `snow_cli_available = true`
- Record the version as `snow_cli_version`

**If the command fails** (not found / not installed):

- Set `snow_cli_available = false`

### Step 3: Check for Explicit User Request

If the user explicitly asked to use Snow CLI (e.g., "use snow cli", "use the CLI", "use snowflake cli"), set `snow_cli_available = true` regardless of the detection result — trust the user's statement. If the CLI is not actually installed, the first command will fail and you can fall back to SQL at that point.

## Passing Results to Sub-Skills

When loading a sub-skill, carry forward:

- `snow_cli_available` (true/false)
- `snow_cli_version` (version string, or empty)

Sub-skills will check for the project definition file (`snowflake.yml`) themselves after gathering the project directory from the user, and use it together with `snow_cli_available` to decide which path to take.
