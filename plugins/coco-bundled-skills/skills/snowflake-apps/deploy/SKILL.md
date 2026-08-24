---
name: snowflake-apps-deploy
description: "Deploy an app to Snowflake. Summarises settings, gets approval, then builds and deploys. Use when the user asks to deploy, publish, or push a Snowflake app."
---

# Deploy Snowflake App

Use this skill when the user asks to deploy, publish, or push a Snowflake App to their account. This skill covers the environment-agnostic pre-flight: summarizing settings and getting approval, then deploying the app.

## Prerequisites

- **Snowflake app exists**: The application source code is already present in the project root.
- **`snowflake.yml` exists**: A valid deployment manifest is present in the project root. If it doesn't exist, generate it (see the `create` phase) before continuing.

## Workflow

### Step 1: Summarize deployment settings

1. Parse `snowflake.yml` and **summarise** for the user:
   - The account name the app will be deployed to (from the active Cortex connection)
   - The app name identifier (this will be the service name)
   - Which database will be used
   - Which schema will be used
   - Which warehouse will be used
   - If not empty:
      - Which compute pool will be used (separate rows for build_compute_pool and service_compute_pool if values are different)
      - Which EAI will be used to build the service
      - Where the code will be uploaded to (code_stage or code_workspace)
      - Which artifact_repository will be used

Summarize these fields; omit others.

2. **Stop here and wait for explicit user confirmation before proceeding** — deployment cannot be easily undone.
   - If the database is a personal database (name starts with `USER$`), explain the implications (see [`@../references/personal-databases.md`](../references/personal-databases.md)) and offer to help find an alternative.
   - If changes are needed → the user should update `snowflake.yml` manually or regenerate it. Print the latest summary after any changes.
   - If approved → proceed to Step 2.

### Step 2: Build and deploy

1. **Tell the user** that the deploy is starting and roughly what to expect (a deploy typically takes 2–10 minutes). Explain that you will relay progress as it becomes available.

2. **Deploy the app**, then relay progress: surface build/upload status as it appears, and on success return the endpoint URL so the user can open the app.

3. If the deploy fails, show the full error output and help troubleshoot, then retry.

## Stopping Points

- **Step 1**: Wait for user to confirm the settings in `snowflake.yml` before proceeding.
- **Step 2**: If the deploy fails, stop and help the user resolve the issue before continuing.

## Success Criteria

A deployed Snowflake App accessible via its `.snowflakecomputing.app` endpoint URL: `snowflake.yml` has correct settings, the deploy completed without errors, and the endpoint URL was returned to the user.
