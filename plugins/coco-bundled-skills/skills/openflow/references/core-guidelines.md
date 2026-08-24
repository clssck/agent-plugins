---
name: openflow-core-guidelines
description: Core context and guidelines for Openflow operations. Always load this reference at the start of any Openflow session.
---

# Openflow Core Guidelines

Foundational context for all Openflow operations. The main skill handles routing; this reference provides the knowledge needed to execute any workflow correctly.

**Surface scope:** This file is shared and SQL-safe — it loads on every surface. The terminal-only tooling (nipyapi runtime layer, curl, and Authorship/custom-flow mode) lives in `references/core-guidelines-cli.md`, which is loaded only on the CLI/Desktop surface when work resolves to Gen1/canvas/custom. On the Snowsight (SQL-only) surface, that content is neither loaded nor available. See `SKILL.md` Surface Detection.

## Mandatory Behavior Pattern

These rules apply to ALL operations. Violating them indicates context drift - reload skills immediately.

1. **Never guess.** If unsure of a function signature, argument, or required value - stop.
2. **Skills first.** Check the intent table in `SKILL.md` to find the correct reference for the operation.
3. **Load references when directed.** When a workflow step says to load a reference, STOP and load it. Do not substitute general knowledge for reference content. References exist because they contain domain-specific configuration that differs from standard approaches (e.g., required package extras, specific install methods, non-obvious flags). Skipping a reference and improvising from general knowledge is a common cause of cascading failures.
4. **Help second.** If skills do not cover it, run `--help` on the command to discover arguments.
5. **Ask third.** If still unsure, ask the user: "I need to do X - is this the correct approach?"
6. **No fabrication.** Do not invent commands, parameters, or API calls. Use documented examples only.
7. **No secrets in output.** Never echo passwords, tokens, or sensitive values back to the user.
8. **Verify results.** After operations, check the result matches expectations before proceeding.

**Context drift indicators** (if you notice these, reload `SKILL.md`):
- Writing custom code for operations that should have CLI commands
- Trying multiple argument variations to see what works
- Proceeding without knowing what a command will do
- Skipping a reference load because you think you already know how to do it

---

## What is Openflow?

Openflow is a Snowflake product built on Apache NiFi. It provides data integration capabilities through:

- **Connectors** - Pre-built flows for common sources (PostgreSQL, MySQL, Google Drive, etc.)
- **Custom Flows** - User-built NiFi flows for specific integration needs

## Tool Hierarchy

Three layers of tooling, each with different scope:

### 1. Snowflake SQL / CLI (Account Level)

**Run SQL on the active connection.** Use `snow sql -c <connection>` only to target a different account.

Operations on Snowflake account resources:

| Operation | Tool | Example |
|-----------|------|---------|
| Create Network Rule | SQL | `CREATE NETWORK RULE ...` |
| Create External Access Integration | SQL | `CREATE EXTERNAL ACCESS INTEGRATION ...` |
| Query Runtime Logs | SQL | `SELECT * FROM <events_table> ...` |
| Show Deployments | SQL / `snow` | `SHOW OPENFLOW DEPLOYMENTS` |

### 2. Openflow Control Plane UI or SQL (Infrastructure Level)

Infrastructure operations. On accounts using the SOM (Snowflake Object Model), these can also be done via SQL; on legacy accounts the UI is required. This skill supports both models — commands are SOM-first with legacy fallbacks noted where applicable.

| Operation | SQL (SOM) | UI |
|-----------|-----------|----|
| Create Deployment | `CREATE OPENFLOW DEPLOYMENT` | Supported |
| Terminate/Drop Deployment | `ALTER ... TERMINATE` + `DROP` | Supported |
| Terminate/Drop Deployment (with runtimes) | `ALTER ... TERMINATE CASCADE` + `DROP CASCADE` | Supported |
| Create Runtime | `CREATE OPENFLOW RUNTIME` | Supported |
| Suspend/Resume/Restart Runtime | `ALTER OPENFLOW RUNTIME ... SUSPEND/RESUME/RESTART` | Supported |
| Terminate/Drop Runtime | `ALTER ... TERMINATE` + `DROP` | Supported |
| Terminate/Drop Runtime (with connectors) | `ALTER ... TERMINATE CASCADE` + `DROP CASCADE` | Supported |
| Attach EAI to Runtime | `ALTER OPENFLOW RUNTIME ... SET EXTERNAL_ACCESS_INTEGRATIONS` | Supported |
| Configure Runtime Resources | `ALTER OPENFLOW RUNTIME ... SET` | Supported |
| Create Connector (Gen2) | `CREATE OPENFLOW CONNECTOR ... IN RUNTIME ... FROM DEFINITION` | Guided Wizard |
| Show Connectors | `SHOW OPENFLOW CONNECTORS IN ACCOUNT` | Supported |
| Describe Connector | `DESCRIBE OPENFLOW CONNECTOR <fqn>` | Supported |
| Show Connector Definitions | `SHOW OPENFLOW CONNECTOR DEFINITIONS` | N/A |
| Start/Stop Connector | `ALTER OPENFLOW CONNECTOR ... START/STOP` | Supported |
| Terminate/Drop Connector | `ALTER ... TERMINATE` + `DROP` | Supported |
| Edit Connector Config | `ADD LIVE VERSION FROM LAST` → PUT config → `COMMIT` | Guided Wizard |
| Abort Connector Edit | `ALTER OPENFLOW CONNECTOR ... ABORT` | N/A |
| Show Connector Versions | `SHOW VERSIONS IN OPENFLOW CONNECTOR` | N/A |
| Rollback Connector Version | `ALTER ... SET DEFAULT_VERSION = 'VERSION$N'` | N/A |
| Push Connector to Git | `ALTER OPENFLOW CONNECTOR ... PUSH TO '@GIT_REPO/...'` | N/A |

### Gen1 vs Gen2 Connectors

Connectors exist in two generations. The agent must determine which generation applies before selecting a workflow:

| Generation | Deployment Method | Configuration | Detection |
|------------|------------------|---------------|-----------|
| **Gen1** | Deploy from NiFi registry via nipyapi | Parameter contexts via NiFi API | Flow deployed as Process Group; no entry in `SHOW OPENFLOW CONNECTORS` |
| **Gen2** | `CREATE OPENFLOW CONNECTOR ... FROM DEFINITION` | Stage-based config.json via `snow://openflow_connector/` | Entry appears in `SHOW OPENFLOW CONNECTORS`; has a `connector_definition` |

**Detection logic:** See `references/connector-main.md` (Generation Detection section) for the full procedure. Whether Gen2 operations are available is determined by the SOM check at session init — the SOM probe (`SHOW OPENFLOW CONNECTOR DEFINITIONS`) on the SQL surface, or the `som_enabled` cache field on the CLI surface.

Gen1 and Gen2 connectors coexist on the same runtime without conflict, but appear in separate Canvases.

### 3. Runtime level (NiFi API) — CLI surface only

Operations *inside* a runtime — Gen1 connectors, canvas work, processors, parameter contexts, custom flows — require the NiFi API via **nipyapi** or **curl**. These are available only on the CLI/Desktop surface.

When work resolves to the "CLI + Gen1/canvas" cell of the matrix, load `references/core-guidelines-cli.md` for the nipyapi and curl tool layers (preference order, common commands, curl setup, coverage).

On the **Snowsight (SQL-only)** surface the agent can't run these (no shell, no nipyapi, no egress to the NiFi endpoint) — direct the user to the Openflow UI in Snowsight, or Cortex Code CLI/Desktop. See `SKILL.md` Surface Detection.

## Deployment Types

| Type | Description | Authentication | Network Access |
|------|-------------|----------------|----------------|
| **SPCS** | Snowflake-managed (Snowpark Container Services) | Session token (automatic) | Requires EAI for external sources |
| **BYOC** | Bring Your Own Cloud (customer-managed) | Managed token (default); Key-pair (alternative) | Direct network access |

### Detecting from URL

| Type | URL Pattern |
|------|-------------|
| SPCS | Starts with `of--` (e.g., `https://of--account.snowflakecomputing.app/...`) |
| BYOC | Contains `snowflake-customer.app` (e.g., `https://xxx.openflow.region.snowflake-customer.app/...`) |

```python
def is_spcs_deployment(url: str) -> bool:
    from urllib.parse import urlparse
    return urlparse(url).netloc.startswith("of--")
```

### Key Differences

| Aspect | SPCS | BYOC |
|--------|------|------|
| Snowflake Auth Strategy | `SNOWFLAKE_MANAGED` (legacy: `SNOWFLAKE_SESSION_TOKEN`) | `SNOWFLAKE_MANAGED` (default) or `KEY_PAIR` (alternative) |
| Private Key Service bulletins | Ignore (not used) | Ignore when using managed token; required for key-pair |
| Account Identifier parameter | Not required | Not required (managed token); Required (key-pair) |
| Snowflake Username parameter | Not required | Not required (managed token); Required (key-pair) |
| Execute-as role | Managed by SPCS automatically | Set via `EXECUTE_AS_ROLE` on runtime (must configure) |
| External Access Integration | Required for external sources | Not required |

> **Terminology:** The **execute-as role** is the role a runtime runs as. It is
> also called the "runtime role" in some SPCS contexts; the SOM parameter is
> `EXECUTE_AS_ROLE`. This skill uses "execute-as role" throughout. On SPCS the
> role is conventionally named `RUNTIMEROLE_<service_name>` (or
> `OPENFLOWRUNTIMEROLE_<runtime>` for SOM runtimes) — recognise these existing
> names when discovering roles.

## Safety Principles

1. **NiFi has no undo.** Before bulk modifications (layout changes, parameter updates, flow restructuring), suggest the user commit to version control first.

2. **Dry-run before modifying.** When making changes, run with `--dry_run` first unless the user has explicitly instructed the change. Present the dry-run output to the user for confirmation before executing.

3. **Permission boundaries.** The agent typically operates under a limited Snowflake role (not ACCOUNTADMIN). When operations fail with privilege errors:
   - Explain the permission boundary encountered
   - Ask the user if they'd like to switch to a role with the necessary grants (e.g. "Would you like me to USE ROLE X which has this privilege?")
   - Do NOT automatically escalate to ACCOUNTADMIN or attempt to grant privileges without asking
   - Provide the user with exact SQL/commands to run with elevated privileges if they prefer to do it themselves
   - Wait for user confirmation before continuing

4. **Never CREATE OR REPLACE.** Use `CREATE IF NOT EXISTS` for new objects and `ALTER` to modify existing ones. `CREATE OR REPLACE` silently drops grants on the replaced object (EAIs, integrations, roles, etc.) and is destructive. This applies to all Snowflake object types. For example, `CREATE OR REPLACE NETWORK RULE` silently wipes the grants on any External Access Integration that references that rule — breaking every connector that relies on it until the EAI is recreated or the grants are reissued. This is a real failure mode that has broken deployment pipelines.

5. **Tag all created objects with `[openflow]`.** Every object this skill creates or adopts must have a COMMENT ending with the tag `[openflow]`. This enables future discovery via `WHERE "comment" ILIKE '%[openflow]%'` on RESULT_SCAN output. The comment format is: `<human-readable purpose>. [openflow]`. When adopting an existing object that already has a comment, append ` [openflow]` to the existing comment — do not overwrite it.

## Context Refresh Procedures

### On Resuming from Summary

When starting from a system-provided summary (indicating context was compressed):

1. Re-read `SKILL.md` to refresh the intent routing table
2. Identify which skills are relevant to the current task
3. Load those skill references into active context before proceeding

### Before Command Execution

Before running any command (a SQL statement, `snow`, or — on the CLI surface — `nipyapi`):

1. Identify the operation category from the intent table in `SKILL.md`
2. Check if the relevant skill reference is in active memory
3. If uncertain of command syntax, re-read the reference first

**Red flags requiring skill reload:**
- Writing custom code/scripts for operations that have a documented SQL statement or command
- Guessing command arguments
- Previous command failed with unexpected syntax

---

## Command Types in References

References contain two types of commands:

### Exact Commands

Marked with **"Run exactly"** or listed in command reference tables. These have known, fixed values - only substitute session variables.

**Session variables** depend on the surface:
- **SQL surface** (Snowsight, or CLI + Gen2): the connection (Snowsight: the current session; CLI: `-c <connection>`) and the target runtime / connector FQN (`<db>.<schema>.<name>`).
- **CLI + Gen1/canvas:** `<profile>` (nipyapi profile) and `<pg-id>` (process group ID) — available only once the nipyapi session is set up (`references/core-session-cli.md`).

When a reference shows a command with fixed values (registry names, bucket names, specific flags), use those exact values. The reference has already determined the correct syntax.

### Template Commands

Require discovery or user input before execution. The reference will indicate this with phrases like "Discover first" or show `--help` usage.

**Example:**

Discover a command's shape before constructing it. On the SQL surface, check the `SHOW`/`DESCRIBE` output first; on the CLI surface for canvas work, run `--help` on the tool (e.g. `nipyapi canvas create_processor --help` — see `references/core-guidelines-cli.md`).

### When to Discover

| Situation | Action |
|-----------|--------|
| Command marked "Run exactly" | Run as-is, substitute session variables only |
| Command in a reference table | Run as-is, these are exact |
| Command with user-specific values | Gather from user, then run |
| Command for Advanced operations | Check `--help` to understand arguments |
| Unfamiliar function | Check `--help` before first use |

For common Primary tier operations (list flows, get status, start, stop), commands are exact and don't need discovery.

## Interrupt Handling

Two types of interruptions require pausing the current workflow: system errors and user corrections.

### System Errors

When any CLI command, Python script, or API call returns an unexpected error:

1. **Save Context** - Create a todo item capturing current workflow state:
   ```
   [paused] <workflow name> - <current step>
   Error: <brief error description>
   ```

2. **Load Handler** - Load `references/core-troubleshooting.md`

3. **Resolve Error** - Follow the troubleshooting workflow to match and remediate

4. **Restore Context** - Check todos for paused items and resume where you left off

**Key Principle:** Do not attempt workarounds (writing Python scripts, trying alternative commands) until after consulting the troubleshooting reference. The error may have a known pattern with a documented fix.

**What counts as unexpected:** Any error that prevents the current operation from completing - timeouts, HTTP errors, exceptions, validation failures, permission denials.

### User Corrections

When user redirects focus, provides corrections, or requests a sidequest:

1. **Save Context** - Create a todo item capturing current workflow state:
   ```
   [paused] <workflow name> - <current step>
   Reason: User requested <brief description>
   ```

2. **Complete the Sidequest** - Give the user's new request full attention. Do not rush through it to return to the main task. Apply the same rigor (skill loading, verification, testing) as the main workflow.

3. **Confirm Completion** - Explicitly confirm the sidequest is complete before returning:
   ```
   "The [sidequest description] is complete. Returning to [main task name]."
   ```

4. **Restore Context** - Check todos for paused items and resume where you left off

**Key Principle:** Sidequests deserve full attention. Rushing through a correction to return to the main task often results in incomplete work that requires another interruption. Complete the sidequest properly, confirm it is done, then resume.

---

## Handling User Corrections

Quickly classify user corrections before responding:

**Simple corrections** (value fixes, typos, yes/no answers):
Acknowledge, apply, continue. No flow break needed.

**Significant redirections** (questions about what you did/didn't do, concepts you haven't loaded docs for, implied missed steps):
Pause. Note your position in the current workflow. Load relevant documentation BEFORE responding. Reassess task list. Resume with corrected understanding.

When uncertain, treat as significant. A brief pause to verify documentation costs less than extended troubleshooting from a missed step.

---

## Operational Pattern: Check-Act-Check

For operations that modify service state, always verify before and after:

1. **Check** - Read current state using the appropriate function
2. **Act** - Execute the operation
3. **Check** - Read state again to confirm the expected result

Many NiFi operations are **asynchronous** - the command returns before the action completes, and the object returned may be an intermediate state. The post-Act check confirms the operation achieved the expected result.

### Example (SQL / SOM)

SOM connector operations are also asynchronous — `ALTER ... START/STOP` returns before the connector reaches the target state. Use `SYSTEM$WAIT_FOR_OPENFLOW_CONNECTORS` (or a follow-up `SHOW`) as the post-Act check:

```sql
-- Check: current state
SHOW OPENFLOW CONNECTORS IN ACCOUNT;

-- Act: start the connector
ALTER OPENFLOW CONNECTOR <fqn> START;

-- Check: confirm it reached RUNNING
SELECT SYSTEM$WAIT_FOR_OPENFLOW_CONNECTORS(300, 'RUNNING', '<fqn>');
```

The nipyapi (NiFi runtime) form of Check-Act-Check is in `references/core-guidelines-cli.md`.

### Guidance

- Default to `get_status` for the Check step when unsure
- Use more specific read functions when `get_status` doesn't contain the required information
- If pre-Check shows unexpected state, investigate before proceeding
- If post-Check shows unexpected state, investigate and discuss corrective action with the user

Operations references (e.g., `ops-flow-lifecycle.md`) provide specific Check-Act-Check examples for each operation.

## Workflow Modes

Recognize the user's workflow mode from their intent patterns. Mode influences agent behavior and guidance.

### Mode Detection

| Mode | Intent Patterns | Examples |
|------|-----------------|----------|
| **Investigation** | "show", "list", "check", "what is", "status", "describe", "find", "get" | "Show me the flows", "What connectors are running?" |
| **Deployment** | "deploy", "start", "stop", "configure", "upgrade", "install" | "Deploy the CDC connector", "Configure the parameters" |
| **Authorship** | "create", "add", "modify", "change", "edit", "build", "customize" | "Add a processor", "Create a new flow", "Customize this connector" |

### Investigation Mode

Read-only operations focused on understanding and reporting:
- List flows, connectors, processors
- Check status and health
- Describe configuration and parameters
- Query event tables for diagnostics

No prompts about version control. Focus on reporting state and explaining what exists.

**Complex Investigations:** If the investigation exceeds 5-10 exchanges or involves customer issues, consider using the investigation diary methodology. See `references/core-investigation-diary.md` for maintaining context across extended sessions.

### Deployment Mode

Operational changes to pre-built connectors supplied by Snowflake:
- **Deploy** connectors from the Snowflake connector registry
- **Configure** parameter values on deployed flows
- **Control** process groups (start/stop) and controller services
- **Upgrade** connectors to newer versions

These are "service editing" changes - modifying operational state and configuration without altering flow structure.

**Key context:** The Snowflake connector registry (`Snowflake Openflow Connector Registry`) is pre-provisioned and read-only. No registry client setup is required for connector activities.

**Agent behavior:**
- Proceed with deployment and configuration without version control prompts
- After deploying, expect to configure parameters (this is part of the deployment workflow)
- Prompt about EAI if SPCS deployment needs external network access

### Authorship Mode

Structural changes to flow design (adding/removing/modifying processors, connections, or process groups) require the NiFi API and are **CLI-surface only**. The full Authorship guidance (registry read-only distinction, version-control prompts, feature-branch advice) is in `references/core-guidelines-cli.md`.

On the Snowsight (SQL-only) surface, direct authorship/custom-flow work to the Openflow UI in Snowsight, or Cortex Code CLI/Desktop.

### Mode Transitions

| From | To | Trigger | Agent Action |
|------|----|---------|--------------|
| Investigation | Deployment | "Deploy the connector", "Start the flow" | Proceed with deployment workflow |
| Investigation | Authorship | "Add a processor", "Modify this flow" | Prompt about version control |
| Deployment | Authorship | "Customize this connector", "Add handling for X" | Prompt about version control (Snowflake registry won't save these changes) |

When transitioning **into Authorship** from Deployment, make clear that customizations cannot be saved back to Snowflake's registry - the user needs their own Git registry client.
