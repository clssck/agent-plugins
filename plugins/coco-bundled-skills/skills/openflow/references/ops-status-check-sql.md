---
name: openflow-ops-status-check-sql
description: Read-only health check for Openflow deployments, runtimes, and Gen2/SQL-managed connectors on the SQL surface (Snowsight, or CLI + Gen2). Lists objects, reads their state, and routes deeper diagnosis or actions to the right place. For Gen1/NiFi-canvas flow health use ops-status-check.md (nipyapi).
---

# Status Check (SQL surface)

Read-only health check for Openflow **deployments, runtimes, and Gen2 (SQL-managed) connectors** using only Snowflake SQL. This is the Primary status path on the **Snowsight (SQL-only)** surface and for **Gen2 work on the CLI**. It answers "what do I have and is it healthy" and then routes anything deeper.

For **Gen1 / NiFi-canvas** flow health (processors, bulletins, flow investigation) use `references/ops-status-check.md` (nipyapi, CLI/Desktop surface only).

This reference is read-only. It never mutates. Connector lifecycle changes, config edits, and recovery live in the connector references (see Routing below); they are not repeated here.

---

## 1. List what exists

In Snowsight, these run against the account you are signed in to. In Cortex Code Desktop/CLI, they run on the active connection; use `snow sql -c <connection>` to target a different account.

```sql
SHOW OPENFLOW DEPLOYMENTS;
SHOW OPENFLOW RUNTIMES IN ACCOUNT;
SHOW OPENFLOW CONNECTORS IN ACCOUNT;          -- add LIKE '%name%' to filter
```

If `SHOW OPENFLOW ...` returns a SQL compilation / syntax error (unexpected token near `OPENFLOW`), the SQL Object Model grammar is absent: this account is not SOM-enabled, so there is nothing to read on this surface. State that and stop (or, on the CLI, offer the Gen1/registry path via `references/core-session-cli.md`).

Empty result is not the same as an error: it means no objects are visible to the current role. Do not conclude "nothing is deployed" without confirming role visibility.

## 2. Read one object's state

```sql
DESCRIBE OPENFLOW DEPLOYMENT "<deployment_name>";   -- STATUS
DESCRIBE OPENFLOW RUNTIME <db>.<schema>.<runtime>;  -- STATUS, EXTERNAL_ACCESS_INTEGRATIONS, execute_as_role, key
DESCRIBE OPENFLOW CONNECTOR <db>.<schema>.<connector>;   -- connector status
SHOW VERSIONS IN OPENFLOW CONNECTOR <db>.<schema>.<connector>;   -- IS_DEFAULT / IS_LIVE
```

## 3. Interpret the state

| Object | Healthy value | Otherwise (needs attention) |
|--------|---------------|-----------------------------|
| Deployment (`STATUS`) | `ACTIVE` | Any other value: a failure (`CREATE_FAILED`, `DELETE_FAILED`, `UPGRADE_FAILED`), an unhealthy state (`NOT_HEALTHY`, `NOT_REPORTING`, `INACTIVE`, `DEACTIVATION_REQUIRED`), or a transitional `*ING` state. |
| Runtime (`STATUS`) | `ACTIVE`, or `SUSPENDED` if intentionally paused | Any other value: a `*_FAILED` state (`CREATE_FAILED`, `RESTART_FAILED`, `SUSPEND_FAILED`, `ACTIVATE_FAILED`, `UPDATE_FAILED`, `UPGRADE_FAILED`, `DELETE_FAILED`) or a transitional state (`CREATING`, `DELETING`, `UPGRADING`, `RESTARTING`, `SUSPENDING`, `ACTIVATING`, `UPDATING`, `CANCEL_REQUESTED`, `GENERATING_DIAGNOSTIC_BUNDLE`). |
| Connector (`status`) | `RUNNING` | Any other value: `STOPPED`, `START_FAILED`, `DELETED`, or a transitional state (`CREATING`, `STARTING`, `STOPPING`). |
| Connector version (`SHOW VERSIONS`) | one row `IS_DEFAULT = TRUE`, no live row (steady state) | `IS_LIVE = TRUE` with no `IS_DEFAULT` (DRAFT, never committed); or both a default and a live row (edits created but not committed — `ALTER OPENFLOW CONNECTOR ... COMMIT` to apply or `... ABORT` to discard; see the connector's Gen2 reference). |

The rule is simple: the healthy value is exact; treat anything else as needing attention rather than trying to memorise every failure state.

Cross-object signal: a connector reporting `RUNNING` while its runtime is not `ACTIVE` is a problem. The connector cannot actually be processing; check the runtime first.

## 4. Routing: what to do with the result

Resolve the connector's generation first (reuse `connector-main.md` Generation Detection: a type present in `SHOW OPENFLOW CONNECTOR DEFINITIONS` is Gen2/SQL-managed; otherwise Gen1).

**Gen2 / SQL-managed connector:**

| The user wants... | Route to |
|---|---|
| To change state or config (start/stop, commit/abort, version, config edit, upgrade, terminate) | The connector's own reference: `connector-postgres-gen2.md`, `connector-mysql-gen2.md`, or `connector-upgrades.md`. These own the Gen2 SQL lifecycle. |
| A CDC table stuck in `FAILED` recovered | The connector-specific recovery (e.g. `connector-postgres-gen2.md`, `connector-oracle/`, `connector-sqlserver.md`). |
| EAI / network access checked or fixed | `platform-eai.md`. |
| To know **why** it is failing at the log/metric level (error logs, error patterns, CPU/memory/disk, restart counts, CDC per-table state from logs) | **Invoke the `openflow-observability` skill.** It owns Snowsight event-table diagnosis. Do not attempt event-table log analysis here. |

**Gen1 / NiFi-canvas connector or flow:** its health, bulletins, and recovery need the NiFi API, which is not available on the SQL surface.
- **CLI/Desktop:** use `references/ops-status-check.md` (nipyapi).
- **Snowsight:** you cannot do it here. Direct the user by intent: the **Openflow UI** in Snowsight for a point-and-click fix, or **Cortex Code Desktop/CLI** with nipyapi to do it programmatically. Do not tell the user it "cannot be done" (it can, on another surface); name the surface that fits their approach.

---

## Related references

- `references/ops-status-check.md` — Gen1 / NiFi-canvas flow status (nipyapi, CLI/Desktop only).
- `references/connector-postgres-gen2.md`, `references/connector-mysql-gen2.md` — Gen2 connector lifecycle (start/stop/commit/abort/version/config).
- `references/connector-upgrades.md` — connector upgrades.
- `references/platform-eai.md` — EAI and network rule setup.
- `references/core-session-sql.md` — SQL session init and the SOM probe.
