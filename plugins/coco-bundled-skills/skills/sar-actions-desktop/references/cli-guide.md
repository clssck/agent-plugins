# Snowflake Apps CLI Guide

Reference for the `snow` CLI: command surface, connection setup, and troubleshooting.

## CLI Command Surface

Use `snow app` for all Snowflake Apps commands. Confirm it is available before running app commands:

1. Run `snow app setup --help`.
2. If it fails, the Snowflake CLI is missing or outdated — see `cli-version-check.md` to verify the version and upgrade.

`snow app` includes both Snowflake Apps and Native Apps commands. In this skill, use only commands relevant to Snowflake Apps and ignore Native-App-only commands (`publish`, `release-channel`, `release-directive`, `run`, `version`).

| Command | Purpose |
|---------|---------|
| `snow app setup --app-name="<name>"` | Initialize a new app, creates `snowflake.yml`. Falls back to SnowApps account parameters (`DEFAULT_SNOWFLAKE_APPS_*`), then config table, then current session. |
| `snow app setup --app-name="<name>" --compute-pool <pool> --build-eai <eai>` | Same, with explicit compute pool and EAI. Required if those values are not in account parameters or the config table. |
| `snow app setup --app-name="<name>" --compute-pool <pool> --build-eai <eai> --dry-run` | Preview resolved configuration without writing `snowflake.yml`. Each value shows its source: `user input`, `account parameter`, `config table`, `default`, or `current session`. |
| `snow app bundle [--entity-id "<id>"] [--project <path>]` | Resolve artifacts into `output/bundle` so you can inspect what deploy will upload. No Snowflake connection required. |
| `snow app validate` | Validate `snowflake.yml` and app structure before deploying |
| `snow app deploy [--entity-id "<id>"]` | Run the full Snowflake App Runtime pipeline (upload, build, promote). |
| `snow app deploy --upload-only/--build-only/--promote-only [--entity-id "<id>"]` | Run only one pipeline phase when retrying or debugging deploy failures. |
| `snow app events --last <n> [--entity-id "<id>"]` | Fetch recent service logs from the deployed app (`--last` defaults to 500 lines, capped at 100KB output). |
| `snow app open [--print-only] [--settings] [--entity-id "<id>"]` | Open the deployed app URL (or settings page) in the browser; `--print-only` returns the URL without launching a browser. |
| `snow app teardown [--force] [--entity-id "<id>"]` | Drop the deployed service and related Snowflake App Runtime resources. |

### Timing long-running commands

Background commands (e.g. `snow app deploy`) can run for minutes, and `bash_output` returns the cumulative buffer with **no timestamps**. To report how long something took, measure it from a clock — never estimate elapsed time from the number of status/log lines. Wrap long commands in epoch markers and report the difference.

**Pick the marker syntax that matches the shell you are running in.** The bash tool reports its shell; on Windows hosts (where the Linux sandbox is unavailable) commands run in **PowerShell**, where `date +%s` does not exist.

- **macOS / Linux (bash / zsh, or the Linux sandbox):**

  ```bash
  echo "T0=$(date +%s)"; snow app deploy --verbose; echo "T1=$(date +%s)"
  ```

- **Windows (PowerShell):**

  ```powershell
  Write-Output "T0=$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"; snow app deploy --verbose; Write-Output "T1=$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"
  ```

Both emit `T0` immediately and `T1` only when the command finishes (the `;` separator runs the trailing marker regardless of success/failure). Report duration as `T1 - T0` seconds, only once `T1` has printed. For an interim figure, subtract `T0` from a fresh foreground clock read (`date +%s`, or `[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()` in PowerShell). If you cannot determine the shell or the markers do not print, report progress by phase name and do **not** invent a minute count.

### Connection Handling

The `snow` CLI resolves connections in this order:

1. **Active connection** — Cortex Code sets `SNOWFLAKE_DEFAULT_CONNECTION_NAME` to the currently active connection, so `snow` commands use it automatically.
2. **Default connection** — If no active connection is set, `snow` falls back to the `default_connection_name` in `~/.snowflake/connections.toml`.

Because of this, you do **not** need to pass `--connection` explicitly in most cases.

- **Do NOT pass `--connection`** unless the user explicitly requests a specific connection.
- If the user says "use connection X", add `--connection X` to the command.

For commands that support `--entity-id`, pass it only when the project has multiple `snowflake-app` entities. With a single entity, CLI can infer it.

## snowflake.yml

The deployment configuration file. Created by `snow app setup` or manually. Keep deploy/runtime settings here; app title/description/icon belong in `app.yml` (`profile`).

```yaml
definition_version: "2"

entities:
  <entity_name>:
    type: snowflake-app
    identifier:
      name: MY_APP_NAME        # UPPER_SNAKE_CASE Snowflake identifier
      database: <database>      # Target database
      schema: APPS              # Target schema
    artifacts:
      - src: src/*              # Source files to upload
        dest: ./                # Destination in build context
        ignore:
          - .git
          # plus dependency/build-output dirs for your template (e.g. anything in .gitignore)
    query_warehouse: <warehouse>
    build_eai:
      name: <external_access_integration>
```

## app.yml

Set app metadata in `app.yml`:

```yaml
profile:
  label: "My App"
  description: "What the app does"
  icon: public/icon.svg
```

## Troubleshooting

| Error | Cause | Resolution |
|-------|-------|------------|
| `SPCS only supports image for amd64 architecture` | Docker image built on ARM (M1/M2 Mac) | Add `--platform linux/amd64` to `docker build`, or use remote build via `snow app deploy` |
| `Insufficient privileges` | Role lacks required grants | Grant `BIND SERVICE ENDPOINT`, `CREATE COMPUTE POOL`, or `USAGE` as needed |
| `Invalid instance family` | Wrong compute pool instance type | Use valid family (e.g., `CPU_X64_XS`, `GPU_NV_S`) |
| `Failed to list images` | Invalid registry URL or auth failure | Verify format: `<account>.registry.snowflakecomputing.com/<db>/<schema>/<repo>` |
| `Docker repository name uppercase error` | Docker requires lowercase names | Ensure database/schema/repo names are lowercase |
| Validation fails with missing fields | `snowflake.yml` has empty `database` or `query_warehouse` | Re-run `snow app setup`. Pass `--compute-pool` and `--build-eai` explicitly if not set in account parameters or the config table. |
| `snow app deploy` is not idempotent | Calling it again restarts the deployment | Check job status before re-running if build is slow |
| `snow --version` shows version earlier than 3.17 | CLI is outdated | Follow `cli-version-check.md` to detect the install method and update |
| `snow` commands fail with credential or auth errors mid-session | Snowflake CLI token has expired | Run any SQL query (e.g., `SELECT 1`) via Cortex Code to trigger a token refresh, then retry the `snow` command |
