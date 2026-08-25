---
name: snowflake-apps
description: "Build and deploy web applications on Snowflake. Use for ALL app requests: create, scaffold, build, deploy, publish, develop, test, operate, monitor, or troubleshoot a SAR app (Snowflake App Runtime app, also called a Snowflake App). A SAR app is a web application (typically Next.js) that runs on Snowflake and is represented by an APPLICATION SERVICE object — distinct from Streamlit-in-Snowflake apps and Native Apps. Also load this skill when the user's current directory is a Snowflake App Runtime project: if the directory contains an `app.yml` file, or if it contains a `snowflake.yml` file with `type: snowflake-app` anywhere in it. Also use it for questions about a SAR app's deployment manifest, including which of the two supported layouts a project uses (`snowflake.yml` plus a build-only `app.yml`, or a single `app.yml` with `version: 2`) and moving between them. Triggers: build me an app, new app, scaffold, web app, dashboard, data app, deploy my app, push to snowflake, ship it, deploy failed, fix deploy, run locally, develop, app logs, app status, restart app, app.yml, app.yml v2, app.yml version 2, snowflake.yml, migrate to app.yml, downgrade to snowflake.yml, deployment targets, default_target, --target, snowflake-app-runtime, snowflake-app, application service, show application services, alter application service."
---

# SAR Apps (Snowflake App Runtime)

This is the **routing skill** for building web applications on Snowflake. Detect the user's intent from the table below and load the correct sub-skill before doing any work.

> A **SAR app** (Snowflake App Runtime app, also called a "Snowflake App") is a web application that runs on Snowflake and is represented by an **`APPLICATION SERVICE`** object — distinct from Streamlit-in-Snowflake apps and Native Apps. The rest of this skill just says "app". If the user says "Snowflake App", "SAR app", "create an app", "build an app", "deploy my app", or "data app", use this skill.

> **For Streamlit-in-Snowflake apps** (Python projects deployed via `snow streamlit deploy`, visible in Snowsight under Streamlit Apps), use [`streamlit-in-snowflake/developing-with-streamlit-in-snowflake/`](../developing-with-streamlit-in-snowflake/SKILL.md) instead. That skill covers the full create / develop / deploy / operate lifecycle for SiS — manifest shape, `snow streamlit deploy`, post-deploy `SHOW STREAMLITS` verification, local-preview troubleshooting, and `ALTER STREAMLIT` lifecycle SQL.

## Load the environment skill first

This skill describes *what* each phase does; a companion **environment skill** defines *how* to perform it where you're running:

- `sar-actions-desktop` — CoCo Desktop / CLI (full shell, the `snow` CLI, and `npm`).
- `sar-actions-workspaces` — Snowsight workspace (SQL only; the filesystem is a stage mount).

Exactly one of these exists in any given environment. **If neither is already loaded, load the one available here now**, before doing any app work — the phase sub-skills below reference actions (scaffold, generate the manifest, deploy, run locally, operate) that only the environment skill knows how to carry out.

## Identify the deployment manifest

An app's deployment configuration lives in one of two supported layouts. **Establish which one before any phase below** — each of them reads or writes the manifest, and this is the only place the rule is stated:

- **`app.yml` with a top-level `version:` of exactly 2** → that file holds the deployment config, and any `snowflake.yml` present is ignored.
- **Anything else** → `snowflake.yml` holds the deployment config, and `app.yml` (if present) is build-only. (A `version:` *above* 2 is neither: the CLI rejects it outright.)

Both layouts are current. **Treat the files on disk as the source of truth and never migrate a working project unprompted.**

Everything else about the two layouts — field reference, defaults, target selection, CLI-version caveats, migration in either direction, and the errors each layout produces — lives in [`@references/manifests.md`](references/manifests.md). The sub-skills below name the decisions that depend on the layout and defer to that file for the details; load it whenever you need to read or write manifest fields.

## Routing Table

Scan the user's full request and identify the matching intent. If the request spans multiple intents (e.g., create AND deploy), execute them sequentially — load each sub-skill before performing that phase of work.

| Intent | Triggers | Sub-Skill to Load |
|--------|----------|--------------------|
| **Create** — Scaffold a new app | "build me an app", "new app", "scaffold", "web app", "create an app", "start a new project", "build a dashboard", "data app", "data explorer" | `create/SKILL.md` |
| **Deploy** — Ship to Snowflake | "deploy my app", "push to snowflake", "ship it", "deploy", "publish", "deploy failed", "fix deploy", "redeploy" | `deploy/SKILL.md` |
| **Develop** — Local dev, test, iterate | "run locally", "develop", "iterate", "hot reload", "add a feature", "test my app", "run the dev server" | `develop/SKILL.md` |
| **Operate** — Post-deploy monitoring | "app logs", "why is my app down", "restart", "scale", "status", "rollback", "troubleshoot", "cpu usage", "memory usage", "resource limits", "app health", "is my app healthy", "crash loop", "restart count", "cache headroom" | `operate/SKILL.md` |
| **Change the manifest layout** — Move between `snowflake.yml` and `app.yml` v2 | "migrate to app.yml", "use app.yml v2", "switch to the new manifest", "go back to snowflake.yml", "downgrade the manifest", "add a prod target" | `references/manifests.md` |

**If the intent is ambiguous**, ask the user to clarify before proceeding.

## Typical User Journeys

Chain sub-skills to match the request:

- **New app:** Create → Develop → Deploy
- **Deploy an existing app:** Deploy
- **Iterate on a deployed app:** Develop → Deploy
- **Troubleshoot a running app:** Operate
- **Full lifecycle:** Create → Develop → Deploy → Operate

## Framework Scope

The `create` sub-skill scaffolds an app from a **self-contained template**. Templates live as subdirectories under `create/`, and more can be added over time across different languages and frameworks. Each template documents what it provides and how to build in it via its own `README.md`, so the sub-skills stay framework-agnostic and defer to the chosen template's README for code-level guidance.
