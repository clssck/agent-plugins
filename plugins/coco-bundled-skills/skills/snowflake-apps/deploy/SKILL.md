---
name: snowflake-apps-deploy
description: "Deploy an app to Snowflake. Summarises settings, gets approval, then builds and deploys. Use when the user asks to deploy, publish, or push a Snowflake app."
---

# Deploy Snowflake App

Use this skill when the user asks to deploy, publish, or push a Snowflake App to their account. This skill covers the environment-agnostic pre-flight: summarizing settings and getting approval, then deploying the app.

## Prerequisites

- **Snowflake app exists**: The application source code is already present in the project root.
- **A deployment manifest exists**: either a `snowflake.yml`, or an `app.yml` with a top-level `version: 2`. If neither is present, generate one (see the `create` phase) before continuing.

## Workflow

### Step 1: Decide what you are deploying

Read the values you summarise below **only** from the manifest that drives the project (see the routing skill, and [`@../references/manifests.md`](../references/manifests.md) for the fields) — mixing the two files is how deploys end up pointing somewhere the user didn't expect.

If the manifest declares `targets`, each one is a separate deployment: use the user's explicit target, otherwise the manifest's `default_target`. With targets declared and neither available, ask the user which one before going further — the CLI would refuse anyway.

### Step 2: Summarize deployment settings

1. **Summarise** for the user:
   - The account name the app will be deployed to (from the active Cortex connection)
   - The target name, if the manifest declares `targets`
   - The app name identifier (this will be the service name)
   - Which database will be used
   - Which schema will be used
   - Which warehouse will be used
   - If not empty:
      - Which compute pool will be used (`snowflake.yml` only — separate rows for build_compute_pool and service_compute_pool if values are different)
      - Which EAI will be used to build the service
      - Where the code will be uploaded to (code_stage or code_workspace). In an `app.yml` v2 project both are usually absent on purpose: the CLI picks a workspace or a `<NAME>_CODE` stage at deploy time. Say that rather than reporting it as missing configuration.
      - Which artifact repository will be used

Summarize these fields; omit others.

2. **Stop here and wait for explicit user confirmation before proceeding** — deployment cannot be easily undone.
   - If the database is a personal database (name starts with `USER$`), explain the implications (see [`@../references/personal-databases.md`](../references/personal-databases.md)) and offer to help find an alternative.
   - In an `app.yml` v2 project, mention that the deploy applies the manifest declaratively: any service setting the manifest doesn't specify — including one an earlier `ALTER APPLICATION SERVICE` set by hand — is reset to its default. If the user has out-of-band changes they want to keep, fold them into the manifest first.
   - If changes are needed → the user should update the manifest manually or regenerate it. Print the latest summary after any changes.
   - If approved → proceed to Step 3.

### Step 3: Build and deploy

1. **Tell the user** that the deploy is starting and roughly what to expect (a deploy typically takes 2–10 minutes). Explain that you will relay progress as it becomes available.

2. **Deploy the app**, selecting the target when the manifest declares any, then relay progress: surface build/upload status as it appears, and on success return the endpoint URL so the user can open the app.

3. If the deploy fails, show the full error output and help troubleshoot, then retry.

## Stopping Points

- **Step 2**: Wait for user to confirm the summarized settings before proceeding.
- **Step 3**: If the deploy fails, stop and help the user resolve the issue before continuing.

## Success Criteria

A deployed Snowflake App accessible via its `.snowflakecomputing.app` endpoint URL: the manifest has correct settings, the deploy completed without errors, and the endpoint URL was returned to the user.
