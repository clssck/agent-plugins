---
name: openflow-connector-wizard
description: Guided Wizard workflow for Gen2 connector setup via the Openflow UI. Applies to any Gen2 connector that has a wizard variant available.
---

# Connector Guided Wizard

The Guided Wizard is a UI-based workflow in the Openflow interface for configuring Gen2 connectors step by step. It provides validation at each step and produces a config.json that can be reused for SQL-based deployments.

---

## When to Use

- First-time connector setup (validates parameters interactively)
- Generating a config.json template for subsequent SQL-based connectors
- Users who prefer UI-driven configuration

---

## Prerequisites

Before starting the wizard:

1. The user knows which Gen2 connector they want to deploy (check available definitions with `SHOW OPENFLOW CONNECTOR DEFINITIONS`)
2. A Gen2-compatible runtime exists and is ACTIVE (MEDIUM or LARGE node_type for database CDC connectors)
3. EAI is attached (SPCS only) with network rules for the source system
4. Source-specific prerequisites are met — load the connector-specific reference via `references/connector-main.md` to confirm
5. Any required credentials are stored as Snowflake Secrets

> **Infrastructure not yet set up?** If any of the above is missing — runtime,
> EAI, network rule, secret, or source Postgres configuration — load
> `references/connector-prereqs-gen2.md` before starting the wizard. Attempting
> the wizard without these in place will fail at the "Verify Configuration" step.
> For BYOC deployments, skip the network rule and EAI items in that reference.

---

## Accessing the Wizard

1. Open the Openflow UI
2. Go to the Overview tab → "View more connectors"
3. Find the connector with "(Guided Wizard)" suffix and click "Install"
   - Ensure you select the Guided Wizard version, not the plain connector
4. Select the target runtime and provide a connector name
5. Click "Begin Installation"

---

## Wizard Steps

The wizard presents a series of configuration steps specific to the connector type. The exact steps vary by connector, but the general pattern is:

1. **Source connection** — credentials, connection URL, driver/assets
2. **Data selection** — which objects to replicate (tables, schemas, patterns)
3. **Column filtering** — optional column-level inclusion/exclusion
4. **Destination** — Snowflake target database, warehouse, naming conventions
5. **Tuning** — scheduling, concurrency, performance settings
6. **Migration/Load type** — full snapshot vs incremental
7. **Summary** — review all inputs, validate, apply

**Key behaviors:**
- Each step may have a "Verify Configuration" button for interactive validation
- "Save and Close" exits without applying — re-enter via "Edit" in connector menu
- "Apply" on the summary step commits the config (equivalent to SQL `COMMIT`)
- The wizard generates a standard config.json that can be downloaded and reused

For the specific steps and parameters for each connector type, refer to the connector-specific reference via `references/connector-main.md`.

---

## After the Wizard

Once configuration is applied (committed), the connector enters STOPPED state. Start it with:

```sql
ALTER OPENFLOW CONNECTOR <db>.<schema>.<connector_name> START;
SELECT SYSTEM$WAIT_FOR_OPENFLOW_CONNECTORS(600, 'RUNNING', '<db>.<schema>.<connector_name>');
```

---

## Using Wizard Output as Template

The config.json produced by the wizard can serve as a template for creating additional connectors via SQL:

1. Download config from the wizard-created connector:
   ```sql
   DESCRIBE OPENFLOW CONNECTOR <db>.<schema>.<wizard_connector>;
   -- Get default_version_location_uri
   GET '<uri>/config.json' 'file:///local/path/';
   ```
2. Edit the config for the new connector's parameters
3. Create a new connector and upload the modified config (see the connector-specific reference for the deployment workflow)

---

## See Also

- `references/connector-main.md` — Connector routing and Gen1/Gen2 detection
- `references/core-troubleshooting.md` — Gen2 connector diagnostics
