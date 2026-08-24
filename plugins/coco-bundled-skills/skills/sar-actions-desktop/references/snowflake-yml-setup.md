# snowflake.yml Setup

Procedure for generating and configuring `snowflake.yml` with the `snow app setup` CLI flow.

## Prerequisites

- An **app name** (lowercase snake_case Snowflake identifier, e.g. `sales_dashboard`)
- A human-readable **app title** (for `app.yml` `profile.label`)
- A short **app description** (for `app.yml` `profile.description`)
- An app **icon path** in the project (for `app.yml` `profile.icon`, e.g. `public/icon.png` or `public/icon.svg`)
- A Snowflake **connection name**

## Guard: existing snowflake.yml

**If a `snowflake.yml` already exists, DO NOT run setup again — it will overwrite existing settings.** Skip directly to [Configure fields](#configure-fields) to verify and fill any missing values.

## Confirm command surface

Before setup, confirm `snow app` is available by running `snow app setup --help` exactly as written. If it fails, the Snowflake CLI is missing or outdated — see `cli-version-check.md` to verify the version (with `snow --version`) and upgrade.

## Generate snowflake.yml

> **Note:** The `create` sub-skill runs this flow before dependency installation so missing setup values surface before the install step starts.


### Step 1 — Dry run

Run from the **project root directory**:

```bash
snow app setup --app-name="<app_name>" --dry-run
```

`--dry-run` shows what `snowflake.yml` would contain without writing it. Each resolved value shows its source: `user input`, `account parameter`, `config table`, `default`, or `current session`.

Use `--warehouse` to resolve missing warehouse issues.

### Step 2 — Generate

Once you have a successful dry run, execute the same command without `--dry-run`.

**Do not create `snowflake.yml` on your own, always invoke the setup command.**

## Configure generated files

After setup, update only the fields below. Do not change other generated values.

### `snowflake.yml`

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

### `app.yml`

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
