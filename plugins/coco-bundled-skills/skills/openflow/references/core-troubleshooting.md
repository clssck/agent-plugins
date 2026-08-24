---
name: openflow-core-troubleshooting
description: Error patterns and remediation for Openflow operations. Load when encountering errors, connectivity issues, or when investigation is blocked.
---

# Troubleshooting Guide

Error diagnosis and remediation for Openflow operations. This reference contains observed error patterns with their signatures and fixes.

**Scope:** Connectivity errors, authentication failures, API/CLI issues, command timeouts. For flow-specific errors (bulletins, processor failures), see `references/ops-bulletins.md`.

**Transient SQL-tool errors (SQL surface):** A SQL call (e.g. `SHOW OPENFLOW ...`) that fails with a local file / credential-cache error such as `ENOENT` is usually a transient tool/environment glitch, not an Openflow or account problem. Retry the statement once before investigating; if it recurs, report the exact error to the user.

**When you arrive here:** You should have a paused todo item from `core-guidelines.md` Interrupt Handling section. If not, create one now before proceeding.

---

## Troubleshooting Workflow

1. **Verify context saved** - Confirm you have a todo noting your original workflow
2. **Capture the error** - Note the exact error message
3. **Match the pattern** - Search this file for the error signature
4. **Apply remediation** - Follow the steps for that error type
5. **Retry the operation** - Verify the fix worked
6. **Resume original task** - Check todos for paused items and continue

---

## Error Categories

| Category | Section | Common Causes |
|----------|---------|---------------|
| Timeouts | [Timeout Errors](#timeout-errors) | Long-running operations, large flows |
| Network/VPN | [Network Errors](#network-errors) | VPN disconnected, IP restrictions |
| Runtime | [Runtime Errors](#runtime-errors) | Runtime suspended, upgrading, unavailable |
| Authentication | [Authentication Errors](#authentication-errors) | Token expired, invalid credentials |
| Runtime Infrastructure | [Runtime Infrastructure Errors](#runtime-infrastructure-errors) | Deleted runtime, wrong deployment |
| API/Tooling | [API Errors](#api-errors) | Version mismatch, method signature issues |
| Flow Errors | [Flow Errors](#flow-errors) | Bulletins, processor failures, data not flowing |

---

## Timeout Errors

### start_flow Timeout

**Error signature:**
```
timed out after 120.0 seconds
```
or
```
running in foreground timed out
```

**Cause:** Large flows with many controller services take time to enable. Controllers enable sequentially, and the CLI waits for completion.
They can also get stuck on some Processor or Controller Service failing to start and blocking other progress.

**Remediation:**
1. The flow probably is starting - the timeout doesn't mean failure
2. Check progress: `nipyapi --profile <p> ci get_status --process_group_id "<id>"`
3. Poll status every 15 seconds - watch for `running_processors` to increase
4. If no progress after 2 minutes, check bulletins for errors
5. Compare actual state to expected state:
   - Did all processors that should be running start?
   - Are controllers enabled that need to be?
   - Check connector-specific guidance for expected exceptions (e.g., SPCS deployments ignore Private Key Service bulletins)

**Note:** Some connectors have processors or controller services that intentionally don't run in certain configurations. Check the connector-specific reference (e.g., `connector-cdc.md`) for expected state after start.

**Prevention:** For flows with many controllers, expect the first start to take several minutes.

### General Command Timeout

**Error signature:**
```
timed out after X seconds
```

**Cause:** The operation is taking longer than the CLI default timeout.

**Remediation:**
1. Check if the operation is still in progress (use `get_status` or UI)
2. If operation completed, continue with next step
3. If operation failed, check bulletins or runtime logs

---

## Runtime Infrastructure Errors

Errors follow this diagnostic sequence:

| Step | Failure | Error | Meaning |
|------|---------|-------|---------|
| 1. DNS resolution | Connection error / curl exit 6 | Host not found | Deployment URL wrong or deployment deleted |
| 2. Auth validation | 401 Unauthorized | Empty body | Token expired, wrong, or missing |
| 3. Runtime routing | 500 Internal Server Error | `{"status":500,"error":"Internal Server Error"}` | Runtime doesn't exist (deleted/typo) |

**Diagnosing 500 on runtime:**
```sql
-- Verify runtime exists
SHOW OPENFLOW RUNTIMES IN ACCOUNT;
```

**Legacy accounts (pre-SOM):** Use `SHOW OPENFLOW RUNTIME INTEGRATIONS` if the above command returns an error.

If runtime not listed, it was probably deleted. Refresh cache via `references/bootstrap-cli.md` and select a different runtime.

---

## Network Errors

### VPN Disconnection (IP Restriction)

**Error signature:**
```
HTTP 401 ... IP/Token X.X.X.X is not allowed to access Snowflake
```

**Key indicator:** The error includes an IP address and "not allowed to access" - this is NOT a token issue.

**Cause:** VPN disconnected. The client IP is not on the Snowflake account's network allowlist.

**Remediation:**
1. Reconnect to VPN
2. Retry the failed command
3. If still failing, verify VPN connection with `curl -s https://ifconfig.me` and check the IP

---

## Runtime Errors

### Runtime Unavailable (503 Service Unavailable)

**Error signature:**
```
status: 503
error: "Service Unavailable"
path: /<runtime-name>/nifi-api/...
```

**Key indicator:** HTTP 503 with "Service Unavailable" in the response body. The URL path includes the runtime name.

**Cause:** The Openflow runtime is not currently available. Common reasons:
- Runtime is suspended
- Runtime is mid-upgrade
- Runtime is starting up after being resumed
- Runtime encountered an error during initialization

**Remediation:**
1. Navigate to the Openflow Control Plane
2. Find the runtime in the list and check its status
3. If suspended: Resume the runtime
4. If upgrading: Wait for the upgrade to complete
5. Wait for the runtime to become healthy (may take 1-2 minutes after resume)
6. Retry the operation

**Note:** This is different from 401 (authentication) or 404 (runtime doesn't exist). A 503 means the runtime exists but is temporarily unavailable.

---

## Authentication Errors

### Token Expired

**Error signature:**
```
401 Unauthorized
```
(Without IP restriction message)

**Cause:** The PAT or session token has expired.

**Remediation:**
1. Load `references/bootstrap-auth.md`
2. Follow the token refresh workflow
3. Return here and retry the original command

---

## API Errors

### nipyapi Version Too Old

**Error signature:**
```
Cannot find key: --profile
```

**Cause:** Installed nipyapi version doesn't support the `--profile` CLI option.

**Remediation:**
1. Load `references/bootstrap-tooling.md`
2. Reinstall nipyapi with CLI extras
3. Return here and retry the original command

### Method Signature Errors

**Error signature:**
```
TypeError: <method>() got multiple values for argument '<arg>'
```

**Cause:** Usually indicates a mismatch between nipyapi version and expected API signature.

**Remediation:**
1. Load `references/bootstrap-tooling.md`
2. Follow the nipyapi installation/update instructions
3. Retry the original command

---

## Unrecognized Errors

If the error doesn't match any pattern above:

1. **Note the exact error message** - copy the full text
2. **Note the command/operation** that caused it
3. **Check basics:**
   - Is VPN connected? (if applicable)
   - Is the profile correct? (`nipyapi --profile <name> system get_nifi_version_info`)
4. **Ask the user** for guidance on how to proceed
5. **Document the error** - if resolved, add it to this reference for future sessions

---

## Flow Errors

Flow errors are issues with the NiFi flow itself rather than connectivity or tooling. These manifest as bulletins or unexpected flow behavior.

### bulletin_errors > 0

**Trigger:** `get_status` returns `bulletin_errors` or `bulletin_warnings` greater than 0

**Remediation:**
1. Get bulletins:
   ```bash
   nipyapi --profile <p> bulletins get_bulletin_board --pg_id "<id>"
   ```
2. Match bulletin message to patterns in `ops-bulletins.md`
3. For detailed investigation: Load `references/ops-bulletins.md`

### Data Not Appearing

**Trigger:** Flow is running but no data arrives at destination

**Remediation:**
1. Check status - are processors running?
2. Check bulletins - any errors?
3. Check queues - is data stuck somewhere?
4. For detailed investigation: Load `references/ops-flow-investigation.md`

### Processor Validation Errors

**Trigger:** `get_status` returns `invalid_processors` > 0

**Cause:** One or more processors have configuration errors.

**Remediation:**
1. Check parameter context is configured: Load `references/ops-parameters-main.md`
2. Verify required parameters have values based on instructions from relevant Connector guidance
3. Re-run `get_status` to confirm `invalid_processors = 0`

---

## Next Steps (Resume from Interrupt)

After resolving the error:

1. **Check your todos** - Find the paused item created when you entered troubleshooting
2. **Mark troubleshooting complete** - Update the error sub-task if you created one
3. **Resume the paused workflow** - Continue from the step noted in the todo
4. **If no paused todo exists** - Return to main skill router (`SKILL.md`)

**Example:**
```
Before: [paused] Deploy MySQL CDC - Step 4: Start connector
After:  [in_progress] Deploy MySQL CDC - Step 4: Start connector (resuming after timeout fix)
```

---

## Gen2 Connector Errors (SQL API)

These errors apply to connectors managed via the SQL API (`CREATE OPENFLOW CONNECTOR ... FROM DEFINITION`). Gen2 connectors run on an isolated canvas that is not easily accessible via the nipyapi Python client — use the event table queries below for diagnostics.

For connector-specific error interpretations (e.g. Postgres connection errors), route to the connector reference via `references/connector-main.md`.

### Querying Connector Errors via Event Table

**Step 1:** Get the runtime key or check the cache:

```sql
DESCRIBE OPENFLOW RUNTIME <db>.<schema>.<runtime_name>;
-- Note the 'key' field (e.g. 'mypostgresruntime-100')
```

**Step 2:** Find the event table. Resolve it in this order:

1. **Session cache** — the `event_table` field written during deployment/discovery
   is the authoritative value for this account's Openflow telemetry.
2. **SOM data plane integration** — the per-deployment event table (SOM mode):

   ```sql
   SHOW OPENFLOW DATA PLANE INTEGRATIONS;
   DESCRIBE OPENFLOW DATA PLANE INTEGRATION <integration_name>;
   -- Read the EVENT_TABLE property
   ```
3. **Account parameter (legacy fallback)** — only for legacy/non-SOM accounts;
   note this is the account-wide default and may differ from the deployment's
   actual event table:

   ```sql
   SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT;
   ```

**Step 3:** Discover the connector's root process group name (needed when multiple flows/connectors share a runtime):

```sql
SELECT DISTINCT
  SPLIT_PART(TRY_PARSE_JSON(VALUE):"mdc":"processGroupNamePath"::STRING, '/', 2) AS connector_root_name
FROM <event_table>
WHERE RESOURCE_ATTRIBUTES:"k8s.namespace.name"::STRING = 'runtime-<key>'
  AND RECORD_TYPE = 'LOG'
  AND TRY_PARSE_JSON(VALUE):"mdc":"processGroupNamePath" IS NOT NULL
  AND TIMESTAMP >= DATEADD(hour, -1, CURRENT_TIMESTAMP());
```

This returns the root process group name for each flow/connector on the runtime. Use it to scope the error query below.

**Step 4:** Query errors scoped to the connector:

```sql
SELECT
  TIMESTAMP,
  TRY_PARSE_JSON(VALUE):"loggerName"::STRING AS component,
  TRY_PARSE_JSON(VALUE):"mdc":"processGroupName"::STRING AS process_group,
  TRY_PARSE_JSON(VALUE):"formattedMessage"::STRING AS error_message
FROM <event_table>
WHERE RESOURCE_ATTRIBUTES:"k8s.namespace.name"::STRING = 'runtime-<key>'
  AND RECORD_TYPE = 'LOG'
  AND TRY_PARSE_JSON(VALUE):"level"::STRING = 'ERROR'
  AND TRY_PARSE_JSON(VALUE):"mdc":"processGroupNamePath"::STRING ILIKE '/<connector_root_name>%'
  AND TIMESTAMP >= DATEADD(hour, -1, CURRENT_TIMESTAMP())
ORDER BY TIMESTAMP DESC
LIMIT 20;
```

**Simplified form** (when the runtime has only one connector — skip Step 3):

```sql
SELECT
  TIMESTAMP,
  TRY_PARSE_JSON(VALUE):"loggerName"::STRING AS component,
  TRY_PARSE_JSON(VALUE):"formattedMessage"::STRING AS error_message
FROM <event_table>
WHERE RESOURCE_ATTRIBUTES:"k8s.namespace.name"::STRING = 'runtime-<key>'
  AND RECORD_TYPE = 'LOG'
  AND TRY_PARSE_JSON(VALUE):"level"::STRING = 'ERROR'
  AND TIMESTAMP >= DATEADD(hour, -1, CURRENT_TIMESTAMP())
ORDER BY TIMESTAMP DESC
LIMIT 20;
```

**Key fields in log entries:**
- `TRY_PARSE_JSON(VALUE):"level"` — log level (`ERROR`, `WARN`, `INFO`)
- `TRY_PARSE_JSON(VALUE):"loggerName"` — processor class that generated the error
- `TRY_PARSE_JSON(VALUE):"mdc":"processGroupNamePath"` — identifies which connector sub-flow
- `TRY_PARSE_JSON(VALUE):"formattedMessage"` — full error text

### Connector stuck in transitional state

**Error:** Connector remains in `CREATING`, `STARTING`, or `STOPPING` for extended periods.

**Remediation:**
1. Wait up to 10 minutes — transitions can be slow on first creation
2. Run `DESCRIBE OPENFLOW CONNECTOR <fqn>` to confirm current state
3. If runtime is not ACTIVE, the connector cannot transition — check runtime status first
4. If stuck in `STOPPING`, wait — force-termination is not available at connector level

### START_FAILED

**Error:** Connector enters `START_FAILED` instead of `RUNNING`.

**Diagnosis:** Use the event table query above to get the specific error message.

**Remediation:**
1. Stop the connector: `ALTER OPENFLOW CONNECTOR <fqn> STOP;`
2. Create live version: `ALTER OPENFLOW CONNECTOR <fqn> ADD LIVE VERSION FROM LAST;`
3. Fix config and recommit
4. Restart: `ALTER OPENFLOW CONNECTOR <fqn> START;`

For connector-specific error interpretations, route to the connector reference via `references/connector-main.md`.

### TERMINATE fails — unprocessed flowfiles

**Error:** `ALTER OPENFLOW CONNECTOR <fqn> TERMINATE` fails because the connector has unprocessed data.

**Remediation:**
1. Stop the connector first: `ALTER OPENFLOW CONNECTOR <fqn> STOP;`
2. Wait for STOPPED state
3. Retry terminate — if still failing, data may still be draining
4. Wait longer or use the UI to inspect queue depths

### Cannot PUT — no live version

**Error:** PUT to `snow://openflow_connector/.../versions/live/` fails.

**Cause:** The connector has no live version (already committed or never created).

**Remediation:**
```sql
ALTER OPENFLOW CONNECTOR <fqn> ADD LIVE VERSION FROM LAST;
-- Then retry PUT
```

### Config won't commit

- Verify config.json is valid JSON
- Verify all required sections are present
- Verify asset files referenced in ASSET_REFERENCE properties are uploaded to the live version stage

### DROP CASCADE

To remove a runtime that has connectors, use CASCADE:

```sql
ALTER OPENFLOW RUNTIME <fqn> TERMINATE CASCADE;
DROP OPENFLOW RUNTIME <fqn>;
```

This terminates all connectors on the runtime before terminating the runtime itself.

---

## Related References

- `references/connector-main.md` - Connector routing (Gen1/Gen2 detection)
- `references/bootstrap-auth.md` - Token refresh and authentication
- `references/bootstrap-tooling.md` - Tool installation and updates
- `references/bootstrap-cli.md` - Full setup workflow
- `references/ops-bulletins.md` - Flow-specific errors (processor failures)
- `references/ops-flow-investigation.md` - Data flow diagnosis
- `references/platform-diagnostics.md` - Runtime and pod diagnostics
