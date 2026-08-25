# Manifests: `snowflake.yml` vs `app.yml` v2

A SAR app's deployment configuration lives in one of **two layouts**. Both are current and supported; which one a project uses is decided by the files on disk, not by this skill.

| Layout | Files | Who reads what |
|--------|-------|----------------|
| **v1** (original) | `snowflake.yml` **+** a build-only `app.yml` | The CLI reads deployment config from `snowflake.yml`; the builder service reads `install` / `build` / `run` / `profile` / `secrets` / `environment_variables` from `app.yml` |
| **v2** | a single `app.yml` with a top-level `version: 2` | The CLI reads deployment config from the **same** `app.yml`; the builder still reads the build phases from it. `snowflake.yml` is **ignored** |

**Never migrate a working project on your own initiative.** An existing app keeps its current layout unless the user explicitly asks to move. Only act on the layout that is already on disk.

---

## Step 1: Which layout drives this project?

Read the project root before running any `snow app` command:

1. **Is there an `app.yml` with a top-level `version:` of exactly 2?** → **v2 drives the project.** Any `snowflake.yml` present is ignored by the SAR flow — do not read values from it and do not "fix" it.
2. **Otherwise** → **v1 drives the project.** `snowflake.yml` holds the deployment config; `app.yml` (if present) is build-only.

The `version:` key is the entire switch, and it must be **2 exactly** — the key can sit anywhere at the top level of the file, order doesn't matter. Its form is read leniently (`2`, `2.0`, and `"2"` are all version 2), but the value itself is not:

| `version:` value | Behaviour |
|------------------|-----------|
| `2` (or `2.0`, `"2"`) | v2 drives the project |
| Missing, `1`, or non-numeric | Legacy build-only manifest — the CLI silently falls back to `snowflake.yml` |
| Above 2 (`2.1`, `3`, …) | **Hard error**: `Unsupported app.yml version '<value>': this version of Snowflake CLI supports app.yml version 2 only.` The CLI will not parse a newer schema against the v2 model, and will not fall back |

> **The most common v2 mistake:** adding `name` / `database` / `schema` / `query_warehouse` to `app.yml` but forgetting `version: 2`. Every one of those keys is then ignored, and the deploy either uses stale `snowflake.yml` values or fails because there is no `snowflake.yml` at all. If a v2 field appears to have no effect, check for `version: 2` first.

A malformed or unparseable `app.yml` is a hard error — the CLI refuses to fall back to `snowflake.yml`, so a YAML syntax error surfaces as `Could not parse app.yml` / `Invalid app.yml` rather than a silent v1 deploy.

## Step 2: Does the installed CLI support v2?

v2 arrived in a specific CLI release, and **users routinely run older CLIs**. An older CLI ignores every deployment key in `app.yml` and still requires `snowflake.yml`, so a v2-only project fails on it with a missing-project-definition error.

Probe for the capability rather than comparing version numbers:

```bash
snow app deploy --help
```

If the help output lists a `--target` option, the CLI understands `app.yml` v2. If it does not, the CLI is v1-only — say so before doing anything v2-related, and point the user at the upgrade steps in the environment skill's CLI version check.

### Making `snow app setup` emit `app.yml`

`snow app setup` writes `snowflake.yml` by default. Writing `app.yml` instead is behind a CLI feature flag (off by default), so **which file appears is the CLI's decision, not this skill's** — run setup, then look at what was written.

The flag is opt-in per CLI installation, in `~/.snowflake/config.toml`:

```toml
[cli.features]
enable_sar_app_yml_v2 = true
```

> **Setup never overwrites an existing manifest.** With the flag on, `snow app setup` skips entirely when an `app.yml` is already present — printing `app.yml already exists. Skipping initialization.` and writing **nothing at all**, not even a `snowflake.yml`. Templates ship a build-only `app.yml`, so in a freshly scaffolded project this is the default outcome. Move the template's `app.yml` aside first, run setup, then merge the build phases back into whichever file the CLI wrote (see [Generating a manifest in a scaffolded project](#generating-a-manifest-in-a-scaffolded-project)).

---

## `app.yml` v2 field reference

A v2 manifest is a **baseline** of top-level fields, plus an optional `targets` block of named per-environment overrides. Every field below except the builder phases can be set at the top level, per target, or both — a target's set fields win, and a baseline value shows through wherever the target leaves it unset.

```yaml
version: 2                        # required, and exactly 2 — the switch that makes the CLI read this file

name: SALES_DASHBOARD             # required on the resolved target
database: ANALYTICS               # required
schema: APPS                      # required
query_warehouse: COMPUTE_WH       # required

build_eai: PYPI_EAI               # optional: EAI the builder uses for network egress
ignore:                           # optional: globs excluded from the uploaded project root
  - node_modules
  - .next
  - .git

install:                          # builder phases — top-level ONLY, never per target
  commands:
    - ["npm", "ci", "--include=dev"]
run:
  command: ["node", ".next/standalone/server.js"]
```

### Required on the resolved target

`name`, `database`, `schema`, and `query_warehouse`. There is **no connection fallback** in v2 — unlike `snowflake.yml`, an unset `database` is not filled in from the active connection. All four must be resolvable from the baseline, the selected target, or a mix; otherwise the deploy fails with `Missing required field(s) in <target|the app.yml baseline>: ...`.

A fully-qualified `name` (`DB.SCHEMA.NAME`) overrides the separate `database` / `schema` fields; a bare name inherits them. `database: USER$` is shorthand that expands to the caller's personal database `USER$<user>`.

### Package and build

| Field | Purpose | Default when omitted |
|-------|---------|----------------------|
| `package_name` | Package name in the artifact repository | the bare `name` |
| `artifact_repo` | Artifact repository holding the built package (bare name or `DB.SCHEMA.NAME`) | `<NAME>_REPO` in the app's database/schema |
| `build_eai` | External access integration for build-time egress | none (builds needing package downloads will fail) |

### Code storage

`code_stage` and `code_workspace` are plain **strings** in v2 (a bare name or `DB.SCHEMA.NAME`), not nested `name:` blocks, and they are mutually exclusive — setting both is rejected with `Set only one of 'code_stage' or 'code_workspace'`.

**Prefer leaving both unset.** `snow app setup` omits them deliberately: the CLI then picks a backend at deploy time based on the actual destination and the role's privileges — a workspace for a personal database (which does not support stages) or when the role can `CREATE WORKSPACE`, otherwise a `<NAME>_CODE` stage. Hard-coding a backend in the manifest overrides that decision and is the usual cause of a stage failure in a personal database.

`ignore` lists glob patterns excluded from the upload. There is no `artifacts` `src`/`dest` in v2 — the whole project root is always uploaded minus these patterns.

### Service configuration

These are passed straight into the application service's inline `SPECIFICATION`, and the field names match the service manifest one-to-one:

| Field | Notes |
|-------|-------|
| `label` | Display name (the v1 `profile.label`) |
| `description` | Display description (the v1 `profile.description`) |
| `icon` | Project-relative icon path, same as the v1 `profile.icon` (e.g. `public/icon.svg`) |
| `execute_as_role` | Role the service executes as |
| `auto_resume` | `true` / `false` |
| `auto_suspend_secs` | Idle seconds before suspend. `0` = never auto-suspend; the minimum non-zero value is `300` |
| `min_instances` / `max_instances` | Instance count bounds. Scale-down never reaches zero instances — auto-suspend is what takes a service to zero, so "idle to nothing" means `auto_suspend_secs`, not `min_instances: 0` |
| `external_access_integrations` | List of EAI names active for the **running** service (the v1 `service_eai`) |
| `secrets` | List of `{name, secret}`. A bare `secret` is qualified with the target's database/schema; a `DB.SCHEMA.NAME` is used as written |
| `environment_variables` | List of `{name, value}`. Unquoted scalars are coerced to strings (`8080` → `"8080"`, `true` → `"true"`) |

Two more fields exist but only apply behind CLI feature flags: `compute_resource` (`SERVERLESS` or `MANAGED_COMPUTE_POOL`; write-once at first deploy) and `url_prefix` (serverless only). Leave both out unless the user explicitly asks for them.

### Targets

```yaml
version: 2

name: SALES_DASHBOARD             # baseline shared by every target
database: ANALYTICS
schema: APPS
query_warehouse: DEV_WH

default_target: dev

targets:
  dev: {}                         # empty override — deploys the baseline as-is
  prod:
    schema: PROD_APPS
    query_warehouse: PROD_WH
    min_instances: 2
```

- With **no** `targets` block the baseline is deployed directly and `--target` is rejected.
- Once **any** target is declared, one must be selected: `--target <name>` wins, then the top-level `default_target`. With neither, the command fails with `No target selected. Pass --target or set 'default_target' in app.yml.`
- Overrides **replace** wholesale — a target's `external_access_integrations` or `secrets` list does not merge with the baseline's.
- A `default` key inside `targets` is a rejected pre-release form; use the top-level `default_target`.

`--target` is accepted by `deploy`, `open`, `events`, `teardown`, and `validate`. `bundle` is target-independent (all targets share one source tree) and takes no `--target`.

### Builder phases

`install`, `build`, `run`, and `dev` are consumed by the builder service, not the CLI. They are **top-level only** — putting them under a target has no effect. All four are optional and default to Node conventions: `npm ci`, `npm run build`, `npm start`, `npm run dev`. A template that needs anything else (the Next.js template runs `node .next/standalone/server.js`) must declare it explicitly.

`artifacts` (build-output copy rules) and `parameters` are likewise builder-owned and pass through untouched.

---

## v1 ↔ v2 key mapping

Use this in both directions — migrating up, or downgrading back.

| v1 location | v2 location |
|-------------|-------------|
| `snowflake.yml` `identifier.name` | `name` |
| `snowflake.yml` `identifier.database` | `database` |
| `snowflake.yml` `identifier.schema` | `schema` |
| `snowflake.yml` `query_warehouse` | `query_warehouse` |
| `snowflake.yml` `build_eai.name` | `build_eai` (plain string) |
| `snowflake.yml` `service_eai.name` | `external_access_integrations` (list) |
| `snowflake.yml` `code_stage.name` / `code_workspace` | `code_stage` / `code_workspace` (plain strings) — better omitted |
| `snowflake.yml` `artifact_repository.name` | `artifact_repo` (plain string or FQN) |
| `snowflake.yml` `artifacts[].ignore` | `ignore` |
| `snowflake.yml` `artifacts[].src` / `dest` | *(no equivalent — the whole project root is uploaded)* |
| `snowflake.yml` `meta.title` | `label` |
| `snowflake.yml` `build_compute_pool` / `service_compute_pool` / `runtime_image` | *(no equivalent — drop them; the server chooses)* |
| `app.yml` `profile.label` / `.description` / `.icon` | top-level `label` / `description` / `icon` |
| `app.yml` `secrets` / `environment_variables` | same keys, same shape (now read by the CLI) |
| `app.yml` `external_access_integrations` | same key, same shape (now read by the CLI) |
| `app.yml` `install` / `build` / `run` / `artifacts` / `parameters` | unchanged (plus a new `dev` phase) |
| *(one entity per `snowflake.yml`, selected with `--entity-id`)* | one target per environment, selected with `--target` |

> **`profile:` is v1-only.** A `profile:` block left in a v2 manifest is silently ignored by the CLI, and because v2 deploys declaratively (see below) the service's label, description, and icon end up **unset**. Moving those three keys to the top level is a required migration step, not a cosmetic one.

---

## Migrating v1 → v2

Only on explicit user request. Confirm the plan with the user before editing.

1. **Check the CLI supports v2** ([Step 2](#step-2-does-the-installed-cli-support-v2)). If it doesn't, stop — migrating would break the user's own deploys.
2. **Warn about the blast radius.** Teammates, scripts, and CI running an older CLI will fail on a v2-only project until they upgrade. Get the user's acknowledgement.
3. **Read the current values** from `snowflake.yml` and `app.yml`. If `snowflake.yml` holds a single `snowflake-app` entity, produce a **baseline-only** manifest (no `targets`). If it holds **several** entities that represent different environments, map one target per entity and set `default_target` to whichever the user deploys by default.
4. **Write the merged `app.yml`**: add a top-level `version: 2`, add the deployment keys per the mapping table, promote `profile.*` to top-level `label` / `description` / `icon`, keep the existing `install` / `build` / `run` blocks untouched, and drop the compute-pool and `runtime_image` fields entirely. Prefer omitting `code_stage` / `code_workspace` unless the project deliberately pins one.
5. **Validate before deploying**: `snow app validate` (add `--target <name>` when targets exist). It checks the database and schema exist and that the bundle resolves.
6. **Deploy and verify** the endpoint URL still serves the app.
7. **Delete `snowflake.yml`** once that deploy succeeds. The CLI ignores it while `app.yml` v2 is present, so leaving it behind only invites the two files to drift apart. Keep it until the deploy is verified, then remove it.

## Downgrading v2 → v1

Only on explicit user request, and **confirm the plan with the user before editing** — this rewrites the project's deployment configuration and the deploy that follows it changes live state.

1. Reconstruct `snowflake.yml` — preferably by running `snow app setup` (with the v2 feature flag **off**) in a project with no `snowflake.yml`, then transferring any values the manifest customised. Read the mapping table right-to-left.
2. If the v2 manifest used `targets`, pick the one target to keep (ask the user) — v1 has no equivalent, so per-target overrides must be folded into the single entity, or split across multiple entities selected with `--entity-id`.
3. In `app.yml`, **remove** `version:` and every deployment key (`name`, `database`, `schema`, `query_warehouse`, `build_eai`, `ignore`, `artifact_repo`, `package_name`, `code_*`, `targets`, `default_target`, and the service-configuration fields), and move `label` / `description` / `icon` back under a `profile:` block. Keep `install` / `build` / `run` and `secrets` / `environment_variables` where they are.
4. Leaving `version:` behind is the failure mode here: the CLI would keep reading the now-gutted `app.yml` and ignore the rebuilt `snowflake.yml`.
5. Validate, deploy, verify.

---

## Behavioural differences that matter when debugging

**The deploy phase is declarative.** v1 issues `CREATE APPLICATION SERVICE` and falls back to `ALTER APPLICATION SERVICE ... UPGRADE` when it already exists. v2 issues a single `CREATE OR ALTER APPLICATION SERVICE ... FROM ARTIFACT REPOSITORY <repo> PACKAGE <pkg> VERSION LATEST SPECIFICATION = $$...$$`, which converges the service to the full desired state on both first deploy and redeploy.

Two consequences:

- **Anything omitted from the manifest is cleared on the service.** A field that was set by hand — or by a previous manifest that had it — is reset on the next deploy. This is why a stale `profile:` block silently wipes the label/description/icon.
- **Ad-hoc `ALTER APPLICATION SERVICE ... SET` changes do not survive a redeploy.** In v1 they persisted across `UPGRADE`. In v2, a property the user tweaks in SQL (`AUTO_SUSPEND_SECS`, `QUERY_WAREHOUSE`, `EXTERNAL_ACCESS_INTEGRATIONS`, ...) is reverted to whatever `app.yml` says the next time anyone deploys. Persistent changes belong in the manifest. Say this out loud when a user asks for a lasting property change on a v2 project.

**Values are embedded verbatim in a dollar-quoted specification**, so a literal `$$` anywhere in `label`, `description`, or an environment-variable value is rejected up front with `Application service specification must not contain '$$'`.

**Phase flags still exist** (`--upload-only`, `--build-only`, `--promote-only`) and the shared upload/build pipeline is identical to v1: bundle → upload to the resolved backend → artifact-repo build. Only `--promote-only` changes meaning: with no `ALTER ... UPGRADE` in the v2 path, it re-applies `CREATE OR ALTER` against the already-built package at `VERSION LATEST`, so it re-converges the service to the manifest rather than upgrading it. When the CLI created a temporary `<NAME>_CODE` stage for the upload, it drops it once the build has consumed it; a pre-existing stage is left alone.

## Errors and gotchas

| Symptom | Cause | Fix |
|---------|-------|-----|
| v2 fields have no effect; deploy uses old values | No top-level `version: 2` in `app.yml` | Add it |
| `Unsupported app.yml version '<value>': this version of Snowflake CLI supports app.yml version 2 only` | `version:` is above 2 (`2.1`, `3`, …) | Set it to `2`, or upgrade the CLI if the project really targets a newer schema |
| `--target is only supported for Snowflake App Runtime projects that define deployment targets in app.yml (version 2)` | `--target` passed in a v1 project | Drop the flag, or migrate |
| `No target selected. Pass --target or set 'default_target' in app.yml` | `targets` declared with no selection | Pass `--target`, or add `default_target` |
| `Target '<x>' is not defined in app.yml` | Typo, or no `targets` block at all | Check the listed available targets |
| `'targets.default' is no longer supported` | Pre-release manifest shape | Replace with a top-level `default_target` |
| `Missing required field(s) ...: name, database, schema, query_warehouse` | v2 has no connection fallback | Set them on the baseline or the target |
| `Set only one of 'code_stage' or 'code_workspace'` | Both configured | Keep one, or omit both |
| `Application service specification must not contain '$$'` | A `label`, `description`, or environment-variable value contains `$$`, which would break the dollar-quoted specification | Remove the `$$` sequence |
| `Deployment failed while applying application service '<fqn>'` | Privilege gap on the declarative apply | Needs `CREATE OR ALTER APPLICATION SERVICE` (so `OWNERSHIP` of an existing service) plus `USAGE` on the warehouse, secrets, and external access integrations the target references — see [`permissions.md`](permissions.md) |
| `app.yml already exists. Skipping initialization.` and no file written | `snow app setup` refuses to overwrite | Move the existing `app.yml` aside, re-run, merge the build phases back |
| `Could not parse app.yml` / `Invalid app.yml` | Malformed manifest — no silent fallback | Fix the YAML; check indentation of `targets` |
| Missing-project-definition error on a v2-only project | CLI predates v2 support | Probe `snow app deploy --help` for `--target`; upgrade the CLI |
| Deploy warns that a target declares a different `account` | Per-target account binding is not supported yet | The active connection is always used; ignore or remove the key |
| Label/description/icon disappeared after a deploy | Still using a v1 `profile:` block under v2 | Promote them to top-level fields |

## Generating a manifest in a scaffolded project

Templates ship a build-only `app.yml` (`install` / `run`, and often a `profile:` block), which blocks `snow app setup` when the v2 flag is on. Use this sequence so the CLI still decides the layout:

1. Move the template's `app.yml` out of the way (e.g. to `app.yml.builder`), keeping its contents.
2. Run `snow app setup` as the environment skill describes (dry run first, then for real).
3. Look at **which file the CLI wrote**:
   - **`snowflake.yml`** → v1. Restore the template's `app.yml` unchanged and set its `profile` metadata.
   - **`app.yml`** → v2. Merge the saved `install` / `build` / `run` (and `secrets` / `environment_variables`, if any) into the generated file, and convert the saved `profile:` block into top-level `label` / `description` / `icon`. Delete the saved copy — one `app.yml`, not two.
4. Don't leave the saved copy behind. A stray `app.yml.builder` next to a `version: 2` `app.yml` is harmless to the CLI but guarantees the two drift apart, and the next reader won't know which one is live.
