# Deployment Manifest Setup

Procedure for generating and configuring a SAR app's deployment manifest with the `snow app setup` CLI flow.

`snow app setup` writes one of two manifests, and **the CLI chooses which**:

| Written file | Layout |
|--------------|--------|
| `snowflake.yml` | Deployment config lives here; `app.yml` stays build-only. The default. |
| `app.yml` with a top-level `version: 2` | One file carries both the deployment config and the build phases; `snowflake.yml` is ignored. Emitted when the CLI's `ENABLE_SAR_APP_YML_V2` feature flag is on. |

Do not try to force one or the other. Run setup, read which file appeared, and configure that one. Full field reference and migration guidance: [`../../snowflake-apps/references/manifests.md`](../../snowflake-apps/references/manifests.md).

## Prerequisites

- An **app name** (lowercase snake_case Snowflake identifier, e.g. `sales_dashboard`)
- A human-readable **app title** (the `label`)
- A short **app description** (the `description`)
- An app **icon path** in the project (the `icon`, e.g. `public/icon.png` or `public/icon.svg`)
- A Snowflake **connection name**

## Guard: an existing manifest

**`snow app setup` never overwrites an existing manifest.** If the project already has the manifest that setup would write, it prints `<file> already exists. Skipping initialization.` and writes nothing.

- **A `snowflake.yml` already exists** → don't re-run setup; skip to [Configure the generated manifest](#configure-the-generated-manifest) and fill in any missing values.
- **An `app.yml` already exists** → this is the normal state right after scaffolding a template, and it blocks a v2 setup run **silently** (no `snowflake.yml` either). Move it aside before setup and merge the build phases back afterwards, per "Generating a manifest in a scaffolded project" in [`manifests.md`](../../snowflake-apps/references/manifests.md):

  ```bash
  mv app.yml app.yml.builder     # before setup
  mv app.yml.builder app.yml     # after, if the CLI wrote snowflake.yml
  ```

  These renames are written for a POSIX shell (macOS/Linux) and run on the user's host machine. On a different platform (e.g. Windows PowerShell), use the equivalent command for that shell.

## Confirm command surface

Before setup, confirm `snow app` is available by running `snow app setup --help` exactly as written. If it fails, the Snowflake CLI is missing or outdated — see `cli-version-check.md` to verify the version (with `snow --version`) and upgrade.

Whether the installed CLI understands `app.yml` v2 shows up in `snow app deploy --help`, which lists `--target` only on a CLI that supports it. Check that before anything v2-specific, including a migration — users routinely run older CLIs, and an older CLI cannot deploy a v2-only project.

## Generate the manifest

> **Note:** The `create` sub-skill runs this flow before dependency installation so missing setup values surface before the install step starts.

### Step 1 — Dry run

Run from the **project root directory**:

```bash
snow app setup --app-name="<app_name>" --dry-run
```

`--dry-run` shows what the manifest would contain without writing it. Each resolved value shows its source: `user input`, `account parameter`, `config table`, `default`, or `current session`.

Use `--warehouse` to resolve missing warehouse issues.

### Step 2 — Generate

Once you have a successful dry run, execute the same command without `--dry-run`.

**Do not hand-author the manifest — always invoke the setup command.** Read its output to confirm which file it wrote before continuing.

## Configure the generated manifest

After setup, update only the fields below. Do not change other generated values.

### If the CLI wrote `snowflake.yml`

Only modify:

| Field | Value |
|-------|-------|
| `identifier.name` | UPPER_SNAKE_CASE version of the app name |

The latest Snowflake CLI does not emit a `meta` field. Omit `meta` from `snowflake.yml` entirely (remove it if an older `snow app setup` added one). App metadata — `label`, `description`, `icon` — belongs in `app.yml`'s `profile` block, not in `snowflake.yml`.

#### artifacts

Update the `artifacts` field to match the app root directory:

1. Include the project root files needed for build/deploy.
2. Use glob patterns to minimize the number of `artifacts` entries.
3. Use `src`/`dest` pairs syntax.
4. The destination root should be `./`.
5. Do not include any files that match `.gitignore` rules (if exists). Add `ignore` to the artifacts rules as necessary.
6. Avoid dependency and build-output directories (e.g. anything matched by `.gitignore`) that should not be uploaded.

#### `app.yml` (build-only)

Set app metadata in the `profile` block:

```yaml
profile:
  label: "..."
  description: "..."
  icon: public/icon.svg  # .png or .svg; do not use a base64 data URI
```

- `profile.label`: Human-readable app title
- `profile.description`: Short description of what the app does
- `profile.icon`: Path to the icon file in the project (`.png` or `.svg`; do not use a base64 data URI)

### If the CLI wrote `app.yml` (`version: 2`)

Leave every value setup generated as it is — including the absence of `code_stage` / `code_workspace`, which is deliberate. Add only:

1. The build phases merged back from the template (`install:` / `build:` / `run:`), as top-level keys.
2. App metadata as **top-level** keys (no `profile:` block — a leftover one is silently ignored and the service ends up with no label, description, or icon):

```yaml
label: "..."
description: "..."
icon: public/icon.svg  # .png or .svg; do not use a base64 data URI
```

3. `secrets:` / `environment_variables:`, also top-level, if the app uses them.
4. Extra `ignore:` entries for build or dependency directories the generated list doesn't cover. v2 has no `artifacts` block; the whole project root is uploaded minus `ignore`.

Don't add a `targets:` block unless the user wants multiple environments, and delete any `snowflake.yml` left over from an earlier attempt — the CLI ignores it, so it can only drift. The field reference behind all of this is [`manifests.md`](../../snowflake-apps/references/manifests.md).
