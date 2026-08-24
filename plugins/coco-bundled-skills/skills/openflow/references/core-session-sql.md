---
name: openflow-core-session-sql
description: SQL-only session initialization for Openflow (Snowsight surface, or CLI + Gen2 work). Confirms the connection and Snowflake Object Model (SOM) availability via SQL. No nipyapi, cache, or profiles. For NiFi-API work (Gen1/canvas/custom) see core-session-cli.md.
---

# Openflow Session Management (SQL-only surface)

This reference initializes an Openflow session using **only Snowflake SQL** — no nipyapi, no local cache, no profiles, no terminal tooling. Use it for:

- the **Snowsight** surface (SQL-only capability), and
- the **CLI + Gen2** cell of the capability x intent matrix (Gen2 connector work on the CLI, where nipyapi setup is deferred until — and unless — the canvas is actually needed).

See `SKILL.md` Surface Detection for how the surface and intent are resolved before this reference is loaded.

## Step 1: Establish the connection

In Snowsight, SQL runs against the account you are signed in to (there is no connection to choose). In Cortex Code Desktop/CLI, it runs on the active connection; use `snow sql -c <connection>` to target a different account (confirm it first with `snow connection list`).

## Step 2: Confirm SOM and list available Gen2 connectors

Run the presence probe. It is deployment-independent and privilege-independent (it returns Snowflake's built-in connector definitions whenever the feature is enabled, even with zero deployments and under a minimal role):

```sql
SHOW OPENFLOW CONNECTOR DEFINITIONS;
```

| Result | Meaning | Action |
|--------|---------|--------|
| Rows returned | **SOM enabled — Gen2 available.** The returned rows are the account's canonical list of Gen2 connector types (e.g. `OPENFLOW_POSTGRES_CDC`, `OPENFLOW_MYSQL_CDC`). | Continue to Step 3. |
| **SQL compilation / syntax error** (e.g. `unexpected 'CONNECTOR'`) | The OPENFLOW SQL grammar is absent — **SOM is not enabled** on this account. | **Snowsight:** state "Openflow SQL isn't enabled on this account, so I can't operate here" and stop. **CLI:** Gen2 SQL is unavailable; offer the Gen1 (registry/nipyapi) path via `references/core-session-cli.md`. |
| Any other error | Inconclusive (transient, or an unexpected privilege issue). | Report the exact error and confirm with the user before concluding — do not assume "not Gen2". |

## Step 3: Discover deployments and runtimes (for placement)

Connectors (Gen1 and Gen2) run inside a runtime under a deployment. Discover what exists via plain SQL (same connection rules as Step 1: the current Snowsight account, or the active Desktop/CLI connection, `snow sql -c <connection>` for a different account):

```sql
SHOW OPENFLOW DEPLOYMENTS;
SHOW OPENFLOW RUNTIMES IN ACCOUNT;
```

For a chosen runtime, get its details:

```sql
DESCRIBE OPENFLOW RUNTIME <db>.<schema>.<name>;
-- note: server_url, execute_as_role, key
```

Deployment type from the URL: host starts with `of--` -> SPCS; host contains `snowflake-customer.app` -> BYOC.

| Result | Action |
|--------|--------|
| Deployments and runtimes found | Note the target runtime (schema-qualified name) and its `execute_as_role`. Continue to Step 4. |
| None found | Ask whether Openflow needs to be deployed first. If yes, route to `references/deploy-prereqs.md` (SQL greenfield path). Never conclude "not deployed" without confirming — results can be empty due to role visibility. |

**Gen2 grant note:** the runtime's `execute_as_role` needs `USAGE` on the infra database and schema for connector operations to succeed. If connector operations later fail with permission errors, verify with `SHOW GRANTS TO ROLE <execute_as_role>` and see `references/connector-prereqs-gen2.md`.

## Step 4: Session ready

Once SOM is confirmed and the target runtime (if any) is known:

1. Note the connection (Snowsight: the current session; CLI: the `-c` connection name).
2. Note the target runtime for connector operations.
3. Return to the main skill for SQL routing. For a health/status check of deployments, runtimes, or Gen2 connectors, use `references/ops-status-check-sql.md`.

No nipyapi profile, cache file, or version check is required on this surface. If the work later turns out to need the NiFi canvas (Gen1 connector, custom flow, canvas-only operation):

- **CLI:** load `references/core-session-cli.md` at that point and set up nipyapi then.
- **Snowsight:** not via SQL — the user can use the Openflow UI in Snowsight, or Cortex Code CLI/Desktop with nipyapi.

## Related References

- `references/core-session-cli.md` — the nipyapi/terminal session path (Gen1, canvas, custom flows on the CLI surface).
- `references/connector-prereqs-gen2.md` — Gen2 connector prerequisites (roles, destination DB, warehouse, secret, EAI) when deploying a connector.
- `references/core-guidelines.md` — shared tool hierarchy (SQL layer) and safety principles.
