---
name: openflow-platform-diagnostics
description: Diagnose Openflow Runtime issues including failures, errors, upgrades, and health problems using event table queries.
---

# Platform Diagnostics

Diagnose runtime-level issues (pod failures, upgrade failures, crash loops) by querying the Openflow event table.

**Note:** These are read-only diagnostic queries. Remediation may require UI actions or support escalation.

## Scope

- Runtime failures, errors, and health problems
- Upgrade failures and rollback issues
- Pod startup and scheduling problems
- Crash loops and repeated restarts
- Does NOT cover NiFi flow issues (see `references/ops-flow-lifecycle.md`)

## Prerequisites

Get the event table **bound to your deployment** — surface-neutral SQL. The data plane integration holds the actual binding, which can differ from the account default (`SNOWFLAKE.TELEMETRY.EVENTS`):

```sql
SHOW OPENFLOW DATA PLANE INTEGRATIONS;
-- take the integration name, then read its EVENT_TABLE property:
DESCRIBE OPENFLOW DATA PLANE INTEGRATION <integration_name>;
-- EVENT_TABLE property_value is the bound table, e.g. OPENFLOW.OPENFLOW.EVENTS
```

(CLI convenience: if a cache is populated, the resolved `event_table` is also stored there — `jq '.deployments[].event_table'`.)

## Diagnostic Approach

### Step 1: Identify the Runtime

Gather from the user or error messages:
- Runtime ID (UUID format)
- Runtime name
- Namespace (usually `runtime-{name}`)

### Step 2: Check Recent Workflow Failures

Query for recent runtime workflow failures:

```sql
SELECT TIMESTAMP, VALUE
FROM <event_table>
WHERE TIMESTAMP >= DATEADD(hour, -2, CURRENT_TIMESTAMP())
  AND (VALUE ILIKE '%Failed to upgrade runtime%'
       OR VALUE ILIKE '%Failed to create runtime%'
       OR VALUE ILIKE '%StandardUpgradeRuntimeWorkflow%'
       OR VALUE ILIKE '%StandardCreateRuntimeWorkflow%')
ORDER BY TIMESTAMP DESC
LIMIT 20;
```

### Step 3: Get Stack Trace

Once you identify a failure timestamp, get the full context:

```sql
SELECT TIMESTAMP, VALUE
FROM <event_table>
WHERE TIMESTAMP BETWEEN DATEADD(second, -1, '<failure_timestamp>')
                     AND DATEADD(second, 1, '<failure_timestamp>')
ORDER BY TIMESTAMP;
```

### Step 4: Find Pod-Level Issues

If workflow shows "WaitForRuntimeRestarted" failures, check pod startup:

```sql
SELECT TIMESTAMP,
       RESOURCE_ATTRIBUTES:"k8s.pod.name"::STRING as pod_name,
       RESOURCE_ATTRIBUTES:"k8s.container.name"::STRING as container_name,
       VALUE
FROM <event_table>
WHERE TIMESTAMP BETWEEN '<upgrade_start_time>' AND '<upgrade_end_time>'
  AND RESOURCE_ATTRIBUTES:"k8s.pod.name"::STRING = '<runtime_name>-0'
  AND RESOURCE_ATTRIBUTES:"k8s.namespace.name"::STRING = 'runtime-<runtime_name>'
  AND (VALUE ILIKE '%error%' OR VALUE ILIKE '%exception%' OR VALUE ILIKE '%failed%')
ORDER BY TIMESTAMP
LIMIT 200;
```

### Step 5: Check Common Failure Patterns

#### Configuration Issues

```sql
SELECT TIMESTAMP, VALUE
FROM <event_table>
WHERE TIMESTAMP >= DATEADD(hour, -1, CURRENT_TIMESTAMP())
  AND (VALUE ILIKE '%Could not resolve placeholder%'
       OR VALUE ILIKE '%BeanCreationException%'
       OR VALUE ILIKE '%missing%configuration%')
ORDER BY TIMESTAMP DESC;
```

#### Image Pull Issues

```sql
SELECT TIMESTAMP, VALUE
FROM <event_table>
WHERE TIMESTAMP >= DATEADD(hour, -1, CURRENT_TIMESTAMP())
  AND (VALUE ILIKE '%ImagePullBackOff%'
       OR VALUE ILIKE '%ErrImagePull%'
       OR VALUE ILIKE '%image%not%found%')
ORDER BY TIMESTAMP DESC;
```

#### Resource Constraints

```sql
SELECT TIMESTAMP, VALUE
FROM <event_table>
WHERE TIMESTAMP >= DATEADD(hour, -1, CURRENT_TIMESTAMP())
  AND (VALUE ILIKE '%insufficient%memory%'
       OR VALUE ILIKE '%insufficient%cpu%'
       OR VALUE ILIKE '%FailedScheduling%'
       OR VALUE ILIKE '%OutOfMemory%')
ORDER BY TIMESTAMP DESC;
```

### Step 6: Check State Transitions

Track runtime state changes:

```sql
SELECT TIMESTAMP, VALUE
FROM <event_table>
WHERE TIMESTAMP >= DATEADD(hour, -2, CURRENT_TIMESTAMP())
  AND VALUE ILIKE '%Transitioning runtime%<runtime_id>%'
ORDER BY TIMESTAMP;
```

## Common Failure Scenarios

### Upgrade Failures

**Symptoms:** "WaitForRuntimeRestarted" timeout, "UPGRADE_FAILED" state

**Diagnostic Steps:**
1. Find the upgrade workflow start time
2. Identify which version upgrade was attempted
3. Get pod logs from the new pod created during upgrade
4. Look for application startup errors (Spring Boot, NiFi, etc.)

**Common Root Causes:**
- Missing configuration properties (OAuth, secrets, etc.)
- Incompatible version requiring new config
- Image unavailable
- Resource limits preventing startup

### Create Failures

**Symptoms:** Runtime stuck in "CREATING" state

**Diagnostic Steps:**
1. Find the CreateRuntimeWorkflow execution
2. Check for StatefulSet creation logs
3. Look for pod scheduling or startup issues

**Common Root Causes:**
- Namespace already exists
- Missing secrets or ConfigMaps
- Invalid runtime configuration
- Resource quota exceeded

### Crash Loops

**Symptoms:** Runtime transitions between STARTING and FAILED repeatedly

**Diagnostic Steps:**
1. Get pod logs showing repeated startup attempts
2. Look for consistent error message on each attempt
3. Check liveness/readiness probe failures

**Common Root Causes:**
- Application configuration errors
- Database connection failures
- Certificate/TLS issues
- Port conflicts

## Log Pattern Reference

### Success Indicators

- "Starting reconciliation process for Runtime"
- "Runtime resource has desired observed generation"
- "Heartbeat created at ... and sent to"
- "Finished processing request (type=HEARTBEAT)"

### Failure Indicators

- "Activity failure. ActivityId=..., activityType=WaitForRuntimeRestarted"
- "Failed to upgrade runtime [ID] due to:"
- "Application run failed"
- "Error creating bean"
- "Could not resolve placeholder"
- "Transitioning runtime [ID] to [UPGRADE_FAILED]"

## Query Best Practices

1. **Use appropriate time windows** - Start with last 1-2 hours, don't query unbounded
2. **Use ILIKE for case-insensitive matching** - Event logs have mixed casing
3. **Look for stack traces** - Query timestamps around error messages to get full traces
4. **Filter by pod/namespace** - Use RESOURCE_ATTRIBUTES JSON fields to narrow results
5. **Check partitioned tables** - Events may be in EVENTS, EVENTS_1, etc.

## Example Diagnostic Session

```sql
-- Step 1: Find recent failures
SELECT TIMESTAMP, VALUE
FROM <event_table>
WHERE VALUE ILIKE '%Failed to upgrade runtime%'
  AND TIMESTAMP >= DATEADD(hour, -2, CURRENT_TIMESTAMP())
ORDER BY TIMESTAMP DESC
LIMIT 5;

-- Step 2: Get full context around failure
SELECT TIMESTAMP, VALUE
FROM <event_table>
WHERE TIMESTAMP BETWEEN DATEADD(second, -10, '<failure_timestamp>')
                     AND DATEADD(second, 2, '<failure_timestamp>')
  AND (VALUE ILIKE '%<runtime_id>%' OR VALUE ILIKE '%<runtime_name>%')
ORDER BY TIMESTAMP;

-- Step 3: Find the pod that failed to start
SELECT TIMESTAMP, VALUE
FROM <event_table>
WHERE TIMESTAMP BETWEEN '<upgrade_start>' AND '<failure_timestamp>'
  AND RESOURCE_ATTRIBUTES:"k8s.namespace.name"::STRING = 'runtime-<name>'
  AND RESOURCE_ATTRIBUTES:"k8s.pod.name"::STRING ILIKE '<name>%'
  AND (VALUE ILIKE '%error%' OR VALUE ILIKE '%exception%')
ORDER BY TIMESTAMP;

-- Step 4: Get the root cause
SELECT TIMESTAMP, VALUE
FROM <event_table>
WHERE TIMESTAMP BETWEEN '<pod_start_time>' AND '<failure_timestamp>'
  AND RESOURCE_ATTRIBUTES:"k8s.pod.name"::STRING = '<pod_name>'
  AND (VALUE ILIKE '%Caused by:%' OR VALUE ILIKE '%Exception:%')
ORDER BY TIMESTAMP;
```

## Reporting Results

When presenting findings to the user, include:

1. **What failed** - Runtime ID, name, operation (upgrade/create/restart)
2. **When it failed** - Timestamp of the failure
3. **Root cause** - The actual error message with key details
4. **Context** - What was being attempted (e.g., version upgrade from X to Y)
5. **Recommendation** - What needs to be fixed or escalated

## Next Step

After diagnosing:
- For EAI/network issues, see `references/platform-eai.md`
- For NiFi flow issues, see `references/ops-flow-lifecycle.md`
- For issues requiring infrastructure changes, attempt SQL first (e.g. `ALTER OPENFLOW RUNTIME ... RESUME/RESTART`). If SQL is insufficient or the account is pre-SOM, advise user to use Control Plane UI or contact support.

## Related References

- `references/platform-eai.md` - Network access issues (SPCS)
- `references/ops-flow-lifecycle.md` - NiFi flow operations
- `references/core-guidelines.md` - Deployment types
