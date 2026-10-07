# Connection Setup Reference

Steps 5-9 for connection configuration. See main SKILL.md for scope gathering (Steps 1-4).

## Step 5: Ask for Connection Details

Use `ask_user_question`:

```
question: "How would you like to provide connection details?"
header: "Connection"
options:
  - label: "Saved connection"
    description: "I already have a saved source connection"
  - label: "Enter source details now"
    description: "I'll provide host, port, database, and user; password stays in /secrets"
  - label: "Legacy environment file"
    description: "Use or create ~/.pg_migration_env for older shell-based workflows"
```

### If "Saved connection"

Do **not** make the user remember or inspect `~/.pg_service.conf` manually first.

Instead, proactively list the saved profiles and present a picker:

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py --list
```

Then:

1. Identify likely matches from the output (provider hints in the name, host, user, dbname, sslmode, etc.).
2. Use `ask_user_question` to present the likely saved connections as options.
3. Always include a fallback option like:
   - `A different saved connection`
   - `Enter source details now`
   - `I need clarification`
4. Only ask the user to type the exact saved connection name if no likely match is obvious or they choose the fallback.

For assessment-first workflows, start with the source only:

`I found these saved connections. Which one should I use for the assessment?`

Do not ask about the target instance here unless the workflow has already moved past assessment and into approved migration setup.

### If "Enter source details now"

Ask for the SOURCE connection's non-secret fields in normal chat:

- host
- port
- database
- user
- sslmode if the provider requires something specific

Then:

1. Ask what short service name to save it under (for example `prod_source`).
2. Tell the user to add the source password via `/secrets`.
3. Register the source profile with `pg_common.py --add-source-service ...` so the password lands in `~/.pgpass`.
4. For the Snowflake Postgres TARGET, prefer an existing target service profile or create one with `scripts/pg_connect.py --create` per `migrate/SKILL.md`.

For assessment-first workflows, stop after source setup. The target instance question comes later, after the assessment report and approval checkpoint.

Use this command shape for the source profile registration after the password is available through `/secrets`:

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/shared/pg_common.py \
    --add-source-service <NAME> \
    --host <HOST> \
    --port <PORT> \
    --dbname <DBNAME> \
    --user <USER> \
    --sslmode <SSLMODE>
```

The important contract is:

- the password is never pasted into chat
- the saved source profile ends up backed by `~/.pg_service.conf` + `~/.pgpass`
- downstream tools can still use standard libpq / pg tooling with that profile

### If "Legacy environment file"

Assume `~/.pg_migration_env` by default. If the user uses a different file, ask them to send the exact path in normal chat instead of using `ask_user_question` text/defaultValue fields.

If they need to create one, display the template at `migrate/references/pg_migration_env.template` (which also defines the `setup_connection` shell helper used by the legacy psql examples). Tell the user to:

1. Copy it to `~/.pg_migration_env`.
2. Fill in their own host / port / database / user values.
3. Put their password in `~/.pgpass` (`chmod 600`), not in the env file.
4. If they chose a custom path in Step 5, keep using that as `ENV_FILE`; otherwise use the default `~/.pg_migration_env`.
5. `source "$ENV_FILE"` at the start of each shell session.

For chat-safe workflows, recommend `--source-service` / `--target-service` (see `migrate/SKILL.md` "Credentials" callout) instead of the env-file flow — the Python scripts under `migrate/scripts/` accept service profile names and never echo credentials.

## Step 6: Load and Validate

```bash
source "$ENV_FILE"
# Validate required variables: SOURCE_PGHOST, SOURCE_PGDATABASE, SOURCE_PGUSER,
# TARGET_PGHOST, TARGET_PGDATABASE, TARGET_PGUSER
```

## Step 7: Verify Configuration

Display the loaded config and ask the user to verify, but never print passwords. For service profiles, show only service name, host, port, database, user, and ssl mode.

## Step 8: Test Connections

```bash
# Legacy psql-based smoke test: re-source the file you picked above.
source "$ENV_FILE"

# Connection details are set via environment variables (SOURCE_PGHOST, etc.)
setup_connection "SOURCE"
psql --no-psqlrc --quiet -c "SELECT version();"

setup_connection "TARGET"
psql --no-psqlrc --quiet -c "SELECT version();"
```

If you are using the recommended service-profile flow instead of the legacy
env-file path, run the Python connectivity check instead:

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/shared/test_connectivity.py \
    --source-service prod_source --target-service sf_target
```

## Step 9: Detect Source Platform

Auto-detect platform (RDS, Aurora, Azure, etc.) and load platform-specific guidance.
