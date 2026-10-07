
# Operating a deployed Streamlit-in-Snowflake app

Post-deploy operations for Streamlit-in-Snowflake apps: status, compute warehouse, replace, drop, ownership. Use when the user wants to monitor, troubleshoot, or manage a `STREAMLIT` object that has already been deployed via `snow streamlit deploy` (see [snowflake-deployment.md](snowflake-deployment.md) for the deploy loop).


## What this covers

- Listing & inspecting deployed Streamlit objects
- Changing the query warehouse a deployed app uses
- Renaming, replacing, or dropping a Streamlit app
- Honest answers about what is *not* available (no container logs)

## What this does NOT cover

- **Live application logs** — SiS does not expose stdout/stderr of running app sessions. There is no `SYSTEM$GET_SERVICE_LOGS` equivalent. If the user is debugging a runtime error, the only signals are:
  - The error banner shown in the Streamlit app itself
  - `SHOW STREAMLITS` `comment` / object metadata
  - Any logging the app writes into a Snowflake table the user owns
- **Restart / pause / resume** — there is no service to restart. A "restart" is `snow streamlit deploy --replace` (i.e. re-upload).

## What you can do

### List deployed Streamlit apps

```sql
SHOW STREAMLITS IN ACCOUNT;
SHOW STREAMLITS LIKE '<name>' IN ACCOUNT;
SHOW STREAMLITS IN SCHEMA <database>.<schema>;
```

Each row exposes `name`, `database_name`, `schema_name`, `query_warehouse`, `owner`, `comment`, `url_id`, and `created_on`. The Snowsight URL is

```
https://app.snowflake.com/<account>/#/streamlit-apps/<DATABASE>.<SCHEMA>.<NAME>
```

### Inspect a single app

```sql
DESCRIBE STREAMLIT <database>.<schema>.<name>;
```

Returns the manifest the deploy used (root location stage, main file, query warehouse, EAIs, comment). Use this to diagnose drift between the deployed object and the local `snowflake.yml`.

### Change the query warehouse

The `query_warehouse` controls which warehouse `st.connection("snowflake")` queries run against. To change it without redeploying:

```sql
ALTER STREAMLIT <database>.<schema>.<name>
  SET QUERY_WAREHOUSE = <new_warehouse>;
```

To clear it (fall back to the connection's default):

```sql
ALTER STREAMLIT <database>.<schema>.<name>
  UNSET QUERY_WAREHOUSE;
```

### Rename or move

```sql
ALTER STREAMLIT <database>.<schema>.<name>
  RENAME TO <database>.<schema>.<new_name>;
```

If you rename the deployed object, also update `entities.<key>.identifier.name` in the local `snowflake.yml`, otherwise the next `snow streamlit deploy --replace` will create a new object under the old name.

### Replace / redeploy

There is no in-place "restart". Re-upload the latest local sources:

```bash
snow streamlit deploy --connection <connection_name> --replace
```

This is idempotent and is the supported way to push a fix.

### Drop

```sql
DROP STREAMLIT IF EXISTS <database>.<schema>.<name>;
```

This removes the `STREAMLIT` object but leaves the staged source files behind. To clean those up too:

```sql
REMOVE @<database>.<schema>.<stage>/<entity_name>/;
```

(See [snowflake-deployment.md](snowflake-deployment.md) for which stage was used by the deploy.)

### Ownership / sharing

```sql
GRANT USAGE ON STREAMLIT <database>.<schema>.<name> TO ROLE <role>;
REVOKE USAGE ON STREAMLIT <database>.<schema>.<name> FROM ROLE <role>;
```

Note that `USAGE` is required to *open* the app; data the app shows is still gated by the user's privileges on the underlying tables (Streamlit-in-Snowflake always queries with the caller's identity).

## Common runtime issues

The most frequent SiS-specific failure modes after a successful deploy:

- **App loads but every query errors** — caller's role lacks privilege on the target table. Run `SHOW GRANTS TO ROLE <role>` and grant accordingly.
- **App fails to render after a `pyproject.toml` change** — non-default Python dependency without an External Access Integration. Either revert the dependency or wire an EAI on the entity (`external_access_integrations: [...]`) and redeploy. See [streamlit-in-snowflake-runtime.md](streamlit-in-snowflake-runtime.md).
- **`SHOW STREAMLITS` shows a row but Snowsight 404s** — staged sources were removed manually. Redeploy via `snow streamlit deploy --replace`.
- **Wrong app runs after rename** — the deployed object name and `entities.<key>.identifier.name` in `snowflake.yml` have drifted; align them and `--replace`.

For pre-deploy artifact / manifest checks (which prevent most "deploy succeeds, app 404s" failures), see the **Post-deploy verification** section of [snowflake-deployment.md](snowflake-deployment.md).
