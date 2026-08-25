---
name: sar-actions-desktop
description: "Desktop/CLI environment for building Snowflake Apps in CoCo Desktop on a local machine with a full shell, the `snow` CLI, and `npm`. Load this alongside the `snowflake-apps` skill for ANY Snowflake App request on the desktop: create, scaffold, build, develop, run locally, deploy, publish, operate, monitor, or troubleshoot. A Snowflake App is a web application (typically Next.js) deployed to SPCS via `snow app` — NOT a Streamlit app or Native App. Triggers: build me an app, new app, scaffold, web app, dashboard, data app, deploy my app, push to snowflake, ship it, deploy failed, run locally, develop, app logs, app status, app.yml, app.yml v2, snowflake.yml, snow app setup, snow app deploy --target, snowflake-app."
---

# Snowflake Apps — Desktop Environment

How to perform Snowflake App operations on **CoCo Desktop**: a local machine with a full shell, the `snow` CLI, and `npm`.

---

## Setup — verify the CLI first

Before any app work, confirm the Snowflake CLI is present and current. Run `snow --version` and follow [`references/cli-version-check.md`](references/cli-version-check.md) to verify/upgrade. Load [`references/cli-guide.md`](references/cli-guide.md) for the `snow app` command surface, connection setup, and the troubleshooting table. Run this in the background while you work; only interrupt the user if the CLI is missing/outdated.

---

## Actions

The `snowflake-apps` skill references these actions by name; below is how to perform each one on the desktop.

### Scaffold the template

Given the chosen template directory, copy its contents into the project root with a bash copy (`cp -r <template-dir>/. <project-root>/`) or the `write` tool. Exclude build artifacts and dependency directories (e.g. `node_modules/`, `.next/`, `*.tsbuildinfo`). Then, from the project root, install dependencies using the command documented in the template's `README.md` **in the background**, so it runs while you work through the rest of create.

### Generate the deployment manifest

Generate and configure the manifest using the `snow app setup` flow. Follow [`references/manifest-setup.md`](references/manifest-setup.md) for the full procedure: confirm the command surface (`snow app setup --help`), move any template-provided `app.yml` aside, dry-run (`snow app setup --app-name="<app_name>" --dry-run`, use `--warehouse` to resolve a missing warehouse), then run without `--dry-run` to write the file.

The CLI decides which manifest it writes — `snowflake.yml`, or an `app.yml` with `version: 2` — so read the output to see which one appeared and configure that one. Do not hand-author deployment values that setup can resolve.

### Run locally

First ensure dependencies are installed (run the template's `README.md` install command if `node_modules`/deps are missing or out of date). Then run the dev server and verify it. Read the template's `README.md` for the exact run commands, local-preview pitfalls, and required smoke checks (they are template-specific). Start any dev server **in the background** (long-running), then run the README's "Verify before declaring success" checks before reporting success.

### Deploy the app

Deploy with the CLI. Load [`references/cli-guide.md`](references/cli-guide.md) for semantics and, when debugging, [`../snowflake-apps/references/debugging.md`](../snowflake-apps/references/debugging.md).

1. Pick the selector every app command needs, from the manifest that drives the project: `--entity-id="<app_id>"` for a `snowflake.yml` with multiple `snowflake-app` entities, or `--target "<name>"` for an `app.yml` v2 that declares `targets`. Neither is interchangeable and neither is needed in the single-instance case — see `cli-guide.md` → "Selecting what to act on".
2. Run the deploy **in the background** with `--verbose` so logs are captured:
   ```bash
   snow app deploy --verbose [--entity-id "<app_id>" | --target "<name>"]
   ```
   Append `--connection <connection_name>` only if the user explicitly requests a specific connection.
3. **Actively poll** the terminal output — read it every 30 seconds and relay new lines (build progress, upload status, warnings). Do not go silent. **Measure elapsed time from a clock** using the epoch-marker convention in `cli-guide.md` → "Timing long-running commands"; never estimate duration from the number of log lines.
4. On success, **print the endpoint URL** returned by the command and report the deploy time from the clock markers.
5. On failure, show the full error and troubleshoot (`debugging.md`, `cli-guide.md`). Re-run a specific phase to avoid repeating successful phases: `--upload-only`, `--build-only`, `--promote-only`. Note `snow app deploy` is not idempotent — re-running restarts the deployment.

### Operate

Most operations are SQL; the CLI adds conveniences — prefer these, falling back to SQL if the CLI is unavailable or its session token has expired. Each command below takes the same selector as deploy:

- **View logs** — `snow app events` (add `--last 1000` for more lines). Requires `MONITOR`.
- **Open the app** — `snow app open` (`--print-only` for URL only, `--settings` for the Snowsight settings page). Requires `USAGE`.
- **Teardown** — `snow app teardown --force`. Drops the application service and clears its code stage/workspace subdirectory (artifact repository and built packages are not deleted). Requires `OWNERSHIP`. Cannot be undone. With targets, this tears down **only the selected target's** service — confirm which one with the user first.

## Reference docs

For the two manifest layouts, the `version: 2` field reference, and migrating between them, see [`../snowflake-apps/references/manifests.md`](../snowflake-apps/references/manifests.md); for grants and permissions, [`../snowflake-apps/references/permissions.md`](../snowflake-apps/references/permissions.md); for personal-database implications, [`../snowflake-apps/references/personal-databases.md`](../snowflake-apps/references/personal-databases.md); for finding a deployable database/schema, [`../snowflake-apps/references/finding-database-and-schema.md`](../snowflake-apps/references/finding-database-and-schema.md); for platform constraints, [`../snowflake-apps/references/limitations.md`](../snowflake-apps/references/limitations.md).
