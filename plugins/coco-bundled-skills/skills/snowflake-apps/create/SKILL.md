---
name: snowflake-apps-create
description: "Create a new SAR app (Snowflake App Runtime app, also called a Snowflake App) from scratch. Use when the user asks to create, build, scaffold, or start a new Snowflake App, SAR app, dashboard, or data app."
---

# Create a SAR App

Create a new application that runs on Snowflake. Copy a self-contained starter template, then modify the code in one pass to implement the user's requirements. Each template documents how to build in it via its own `README.md`; this skill handles the framework-agnostic orchestration (choosing and copying a template, platform setup, handoff).

> **Important:** A **SAR app** (Snowflake App Runtime app, also called a "Snowflake App") is a web application that runs on Snowflake and is represented by an `APPLICATION SERVICE` object — distinct from Streamlit-in-Snowflake apps and Native Apps. If the user says "Snowflake App", "create an app", or "build an app on Snowflake", use this skill.

---

## Workflow

### Step 1: Scaffold the Project

**Unless instructed otherwise, always start from a provided template. Do not copy other similar projects — they may be out of date.**

1. **Choose a template.** Templates live in this skill directory (`apps/snowflake-apps/create/`), each in its own subdirectory. Use the only one if there's a single template; otherwise pick the best fit for the request (e.g. by language/framework), asking the user if it's ambiguous.

2. **Choose the project root.** Derive a short kebab-case app name from the request (e.g. `sales-dashboard`). If the user's current directory is empty, use it as the project root; otherwise use a new `<app-name>/` directory that doesn't already exist. Tell the user the path, then **scaffold the template** — place a copy of the chosen template there. Run all remaining steps from the project root. (Scaffolding also kicks off any dependency install in the background so it runs while you continue.)

3. **Read the template's `README.md`.** It is the authoritative guide for what the template provides and how to modify its code. You'll follow it in Step 3.

4. **Generate the `snowflake.yml` deployment manifest.** Do this early so missing values surface before you start implementing. Do not set `identifier.name`, `artifacts`, or `app.yml` fields yet — that happens in Step 3. If it fails for any reason other than missing values (auth, network, tooling error), surface the full error and stop.

---

### Step 2: Understand Requirements

Before writing any code, clarify with the user:

1. **What should the app do?** (Dashboard, admin panel, data explorer, internal tool, etc.)
2. **What data should it use?** Find data — discover tables/views relevant to the request and inspect their schemas (`DESCRIBE TABLE` or sample queries). Do not ask the user to provide table names — discover them and let the user choose. See [`@../references/finding-database-and-schema.md`](../references/finding-database-and-schema.md) for discovery techniques.
3. **Which auth mode?** Owner's rights (queries run as the service identity — shared/reference data), caller's rights (queries run as the calling user — required for row-level security, masking, per-user isolation), or both.

**CRITICAL: NEVER use mock or hardcoded data. Always connect to real Snowflake tables.**

For non-trivial decisions, confirm with the user before proceeding.

---

### Step 3: Implement the Application

**Read the project's `README.md` and follow it** to modify the scaffolded project in one pass and fully implement everything the user asked for, including installing any dependencies you add.

After the app is implemented, configure the deployment manifests (platform-level, same for every template): set the allowed `snowflake.yml` fields (`identifier.name`, `artifacts`) and the `app.yml` `profile` block. Omit the `meta` field in `snowflake.yml` entirely (remove it if present).

The `profile` block structure in `app.yml`:
```yaml
profile:
  label: "Human-Readable App Name"
  description: "One sentence describing what the app does."
  icon: "./icon.png"
```

Replace `icon.png` with a custom icon specific to this app — do not leave the template's default icon.

Finally, **rewrite the project's `README.md`** so it reads like the README for *this* app, not the starter template. The template README was your build guide; once the app is implemented it should describe what this specific app does, its data sources, and how to run and deploy it. Remove template/scaffolding boilerplate that no longer applies.

---

### Step 4: Summary and Handoff

Summarize the project location, the Snowflake data sources used, the key files you changed, and confirm the app icon was replaced with a custom one.

Then ask: **"Would you like to run it locally first, or go straight to deploy?"** (Note: local dev may be unsupported in your environment — if so, offer deploy directly.)

- **Run locally**: Load `../develop/SKILL.md`.
- **Deploy now**: Load `../deploy/SKILL.md`.

## Output

- A fully implemented app in the project root
- Pre-configured `snowflake.yml` ready for deployment
- `app.yml` profile metadata configured (`label`, `description`, `icon`)
