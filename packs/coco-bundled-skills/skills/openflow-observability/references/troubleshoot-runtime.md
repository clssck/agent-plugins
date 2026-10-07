---
name: openflow-observability-troubleshoot-runtime
description: Diagnose runtime creation failures, OOM, stuck upgrading, SSL errors, and pod crashes via SQL-only event table queries.
---

# Troubleshoot: Runtime Issues

This file covers diagnosis and resolution for runtime lifecycle failures using SQL queries against the customer's event table.

## Scope

**Covers:**

- Runtime creation failures (WaitForRuntimeReady, WaitForRuntimeConnectedNodes)
- OOM / Java heap memory exhaustion
- Runtime stuck in Upgrading state
- SSL/certificate errors on runtime pods
- Container crash loops and restart failures
- ImagePullBackOff

**Load other files for:**

- Network/EAI issues underlying creation failures: **Load** `references/troubleshoot-network.md`
- Connector-level CDC errors after runtime is healthy: **Load** `references/connectors/connector-router-cdc.md`
- Connector-level non-CDC errors after runtime is healthy: **Load** `references/connectors/connector-router-non-cdc.md`

---

## Entry Point

Start every runtime investigation by running two queries to establish the error landscape.

### Step 1: Recent Error Logs

Run the Recent Error Logs query from `references/core-queries.md` filtered to the runtime's namespace. Substitute `{namespace}` with the runtime namespace (see core-guidelines.md for derivation).

Add this filter to the WHERE clause to scope to the specific runtime:

```sql
AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
```

### Step 2: Runtime Workflow Failures

Find recent runtime creation or upgrade workflow failures. Use this when the runtime is stuck in CREATING, UPGRADING, or showing FAILED state.

```sql
SELECT timestamp, value
FROM {event_table}
WHERE timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND (value ILIKE '%Failed to upgrade runtime%'
       OR value ILIKE '%Failed to create runtime%'
       OR value ILIKE '%StandardUpgradeRuntimeWorkflow%'
       OR value ILIKE '%StandardCreateRuntimeWorkflow%'
       OR value ILIKE '%WaitForRuntimeConnectedNodes%'
       OR value ILIKE '%WaitForRuntimeReady%'
       OR value ILIKE '%available nodes, waiting for%')
ORDER BY timestamp DESC
LIMIT 50;
```

### Step 3: Branch on Error Pattern

Based on the results from Steps 1 and 2, follow the matching branch below. If both queries return zero results, see [Branch: No Clear Error Pattern](#branch-no-clear-error-pattern) which includes expanded time window guidance.

---

### SSL Handshake Scan

The Recent Error Logs query filters out NiFi cluster and web.server loggers, which are the primary source of SSL errors. Use this unfiltered scan to catch them:

```sql
SELECT
  timestamp,
  resource_attributes:"k8s.pod.name"::STRING AS pod_name,
  resource_attributes:"k8s.container.name"::STRING AS container,
  TRY_PARSE_JSON(value):"loggerName"::STRING AS logger,
  TRY_PARSE_JSON(value):"throwable":"message"::STRING AS error_message
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND (value ILIKE '%SSLHandshakeException%'
       OR value ILIKE '%certificate_unknown%'
       OR value ILIKE '%CertPathValidatorException%'
       OR value ILIKE '%PKIX path%')
ORDER BY timestamp DESC
LIMIT 50;
```

---

## Branch: WaitForRuntimeConnectedNodes Timeout

**Pattern:** Runtime Workflow Failures results contain `WaitForRuntimeConnectedNodes`.

**What it means:** The runtime pods started and NiFi launched, but the NiFi nodes could not form a cluster. This is the most common creation failure.

### Diagnosis

1. **Check for EAI/network errors** in the Recent Error Logs results. Look for:
  - `ConnectException: Connection refused`
  - `UnknownHostException`
  - `SocketTimeoutException`
2. **Check for SSL/TLS errors** -- Run the [SSL Handshake Scan](#ssl-handshake-scan) above.

If SSL errors are found, the node timeout is caused by failed TLS handshakes preventing cluster communication. See [Branch: SSL / Certificate Errors](#branch-ssl--certificate-errors) for resolution.

1. **Check CPU and memory** to rule out resource starvation (**Load** `references/core-queries-resource.md` if not already loaded):
  - Run CPU Utilization by Pod scoped to `{namespace}`
  - Run Memory Utilization by Pod scoped to `{namespace}`
2. **Check container restarts** -- pods crashing during cluster formation prevent node connection:
  - Run Container Restart Count scoped to `{namespace}`

### SPCS-Specific

If EAI or network errors appear, this is likely an External Access Integration or network rule misconfiguration. **Load** `references/troubleshoot-network.md` and follow the EAI validation workflow.

If no network errors and resources are normal, the issue may be transient infrastructure.

- **Root cause:** Runtime creation failed, likely transient. Guide the customer to delete the runtime from the Openflow UI and recreate it. If recreation fails with the same error, gather the diagnostics and escalate to Snowflake support.

### BYOC-Specific

Network issues in BYOC typically relate to cloud provider networking (security groups, NAT gateways, VPC peering) which cannot be diagnosed via SQL. If network errors appear:

1. **Root cause:** Cloud networking misconfiguration. Guide the customer to check their cloud networking configuration per the error pattern. **Load** [BYOC: Network Troubleshooting](troubleshoot-network.md#byoc-network-troubleshooting).
2. Reference: [Set up Openflow - BYOC Deployment](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-byoc)

If no network errors, same as SPCS -- guide the customer to delete and recreate the runtime. If recreation fails, escalate.

---

## Branch: WaitForRuntimeReady Timeout

**Pattern:** Runtime Workflow Failures results contain `WaitForRuntimeReady` or `available nodes, waiting for`.

**What it means:** The runtime pods did not reach a healthy state in K8s within the timeout (default 10 minutes). The pods may have failed to schedule, failed to start, or started but crashed during startup (OOM, config error, health check failure). This step runs after microservices (gateway) are already ready, so the issue is specific to the NiFi server pods.

### Diagnosis

1. **Check for compute pool or scheduling issues** (SPCS only):

```sql
SELECT timestamp, value
FROM {event_table}
WHERE timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND record_type = 'LOG'
  AND (value ILIKE '%compute pool%'
       OR value ILIKE '%Insufficient%'
       OR value ILIKE '%FailedScheduling%'
       OR value ILIKE '%ImagePullBackOff%')
ORDER BY timestamp DESC
LIMIT 50;
```

### SPCS-Specific

Common causes:

- **Compute pool at capacity:** Guide the customer to check their compute pool status in Snowsight. If at capacity, they can wait for resources or use a different compute pool.
- **Image pull failures:** See [Branch: ImagePullBackOff](#branch-imagepullbackoff) below.

### BYOC-Specific

Common causes:

- **Node provisioning delays:** The EKS/GKE cluster may be scaling up nodes. This can take several minutes.
- **PVC provisioning failures:** Storage volumes may fail to provision in the customer's cloud account.

Customer-run: guide the customer to:

1. Check their cloud provider's Kubernetes cluster status
2. Verify node autoscaling is configured and has capacity
3. Retry the runtime creation after 5-10 minutes

---

## Branch: OutOfMemoryError / Java Heap

**Pattern:** Recent Error Logs results contain `java.lang.OutOfMemoryError` or `Java heap space`.

**What it means:** The NiFi JVM exhausted its heap memory. The container is either killed by the OOM killer (restart count increases) or NiFi shuts itself down. This causes cluster instability as pods crash and restart.

### Diagnosis

1. **Confirm OOM severity** -- run Memory Utilization by Pod from `references/core-queries-resource.md`:
  - Memory usage > 85% sustained = high OOM risk
  - Sudden spikes to 95%+ followed by pod restart = OOM kill confirmed
2. **Check restart count** -- run Container Restart Count:
  - Increasing `restart_count` over time = crash loop from repeated OOM
3. **Check CPU as secondary indicator** -- run CPU Utilization by Pod:
  - High CPU alongside OOM often indicates heavy data processing workload
4. **Identify the trigger** -- look for these patterns in Recent Error Logs results:
  - `Throttled due to memory pressure` = Snowpipe Streaming backpressure (common with high-volume ingestion)
  - OOM without throttling = the runtime size may be insufficient for the workload
  - OOM with light workload = possible memory leak (this is the only OOM scenario that warrants escalation)

### Resolution

**Root cause:** Memory exhaustion. Resolution depends on the pattern:

- **Backpressure or workload exceeding runtime size:** Guide the customer to resize the runtime to a larger size in the Openflow UI. Memory by size: Small ~4GB JVM heap (~8 GB container), Medium ~8GB (~16 GB), Large ~16GB (~32 GB). If the customer is already on the largest size, they may need to  split connectors across multiple runtimes if they are running multiple connectors on the same runtime.
- **Possible memory leak (OOM with light workload):** Guide the customer to restart the runtime from the Openflow UI as an immediate mitigation. If OOM recurs after restart with the same light workload, escalate to Snowflake support with: deployment ID, runtime name, error timestamps, memory utilization from Memory Utilization by Pod, and restart count from Container Restart Count.

> **Node-count scaling is not an Openflow SQL action in v1.** Adjusting `MIN_NODES` / `MAX_NODES` via SQL is not currently in the agent's allowlist (Snowflake enforces a per-connector-definition `max_node_count` cap that the agent does not yet preflight). When the diagnosis is "more pods of the same size", direct the customer to scale via the Openflow UI, OR provide the SQL as customer-run guidance: `ALTER OPENFLOW RUNTIME <fqn> SET MIN_NODES = <n>, MAX_NODES = <m>;`. Warn that Snowflake may reject the change if any connector on the runtime has a `max_node_count` cap below the proposed `MAX_NODES`. NODE_TYPE (Small / Medium / Large) is fixed at create time and cannot be changed by any path -- the only way to get more memory per pod is to create a new larger runtime in the Openflow UI.

---

## Branch: SSL / Certificate Errors

**Pattern:** Recent Error Logs results contain `CertPathValidatorException`, `SSLHandshakeException`, `certificate_unknown`, or `PKIX path validation failed`.

**What it means:** The runtime's TLS certificates are invalid, expired, or signed by an untrusted CA. This prevents secure communication between runtime components.

### Diagnosis

Run this query to find all SSL-related errors:

```sql
SELECT
  timestamp,
  resource_attributes:"k8s.pod.name"::STRING AS pod_name,
  resource_attributes:"k8s.container.name"::STRING AS container,
  TRY_PARSE_JSON(value):"throwable":"message"::STRING AS error_message
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND (value ILIKE '%CertPathValidatorException%'
       OR value ILIKE '%SSLHandshakeException%'
       OR value ILIKE '%certificate_unknown%'
       OR value ILIKE '%PKIX path%')
ORDER BY timestamp DESC
LIMIT 50;
```

Check which container is affected (`-server` vs `-gateway`) -- this determines the resolution path.

### SPCS-Specific

**Cause:** SPCS manages certificates through `trust-manager`. When the SPCS root CA is re-issued, leaf certificates signed by the old CA become untrusted.

If these SSL errors appear during `StandardUpgradeRuntimeWorkflow`, `WaitForRuntimeConnectedNodes`, or a runtime stuck in `Upgrading`, do **not** treat this as a customer-run certificate renewal case. That is a runtime upgrade failure. Follow [Branch: Runtime Stuck Upgrading](#branch-runtime-stuck-upgrading), gather the workflow failure and restart-count evidence, and make Snowflake support escalation the primary action.

**Resolution:**

- **Root cause:** Stale TLS certificates on an otherwise stable runtime. Guide the customer to restart the runtime from the Openflow UI -- a restart triggers certificate renewal. If the restart completes but SSL errors persist, escalate to Snowflake support as the certificates may need manual renewal on the Snowflake side.

#### Optional Openflow SQL action candidate (restart only)

The "stale TLS certs on otherwise-stable SPCS runtime" case is one of the few customer-safe restart patterns and is MVP-allowlisted.

- Internal action ID (do not show to customer): `runtime.restart`
- Only offer when:
  - `SHOW OPENFLOW RUNTIMES` confirms the runtime is SQL-managed.
  - SSL errors are confirmed by both Recent Error Logs and the [SSL Handshake Scan](#ssl-handshake-scan).
  - There is **no** matching `StandardUpgradeRuntimeWorkflow` failure or rising restart count -- those route to [Branch: Runtime Stuck Upgrading](#branch-runtime-stuck-upgrading), which is escalation-only.
- On acceptance, **Load** `references/openflow-sql/action-guidelines.md` and `references/openflow-sql/runtime-actions.md`, then follow the [runtime.restart](openflow-sql/runtime-actions.md#runtimerestart----restart-a-sql-managed-runtime-no-recovery-mode) template. The agent does not propose `RESTART RECOVERY` in MVP (the Openflow SQL action surface supports it, but it brings the runtime back up with all processors stopped and is reserved for customer break-glass in the Openflow UI).

### BYOC-Specific

**Cause:** BYOC uses `cert-manager` with a private CA (or Let's Encrypt). Certificates can expire if cert-manager is unhealthy or the renewal process fails.

**Resolution:**

- **Root cause:** Certificate expiry or cert-manager failure. Guide the customer to restart the runtime from the Openflow UI. If SSL errors persist after restart, the customer should check cert-manager health in their BYOC cluster. If cert-manager is healthy but certificates are still failing, escalate with the specific certificate error.

---

## Branch: Runtime Stuck Upgrading

**Pattern:** The runtime shows `Upgrading` state in the Openflow UI for more than 30 minutes, or Runtime Workflow Failures results contain `StandardUpgradeRuntimeWorkflow` or `Failed to upgrade runtime`.

**What it means:** The Runtime Operator is performing a rolling update of the runtime pods, but the process is not completing. Normal upgrades take 10-15 minutes.

### Diagnosis

1. **Run Runtime Workflow Failures first and cite the specific workflow error.** Do not rely only on generic recent error logs for stuck upgrades. Use the [Step 2: Runtime Workflow Failures](#step-2-runtime-workflow-failures) query above, then add the targeted DPS log scan below if needed for more detail.
2. **Check DPS logs for upgrade activity:**

```sql
SELECT timestamp, value
FROM {event_table}
WHERE timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND record_type = 'LOG'
  AND (resource_attributes:"k8s.pod.name"::STRING LIKE 'dataplane-service%'
       OR value ILIKE '%upgrade%'
       OR value ILIKE '%rolling%')
ORDER BY timestamp DESC
LIMIT 50;
```

1. **Check if pods are crash-looping during upgrade:**

```sql
SELECT
  timestamp,
  resource_attributes:"k8s.pod.name"::STRING AS pod_name,
  resource_attributes:"k8s.container.name"::STRING AS container_name,
  resource_attributes:"k8s.container.restart_count"::STRING AS restart_count
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND resource_attributes:"k8s.container.name"::STRING LIKE '%-server'
ORDER BY timestamp DESC
LIMIT 10;
```

- If `restart_count` >= 1 and increasing across rows, the new version is crash-looping. This is an additive finding alongside any other errors (e.g., SSL).
- Do not stop after finding SSL errors. Still check restart counts and include them in the customer-facing diagnosis.
- Check Recent Error Logs for startup errors in the new pods

1. **Check for SSL/TLS errors during cluster formation** -- Run the [SSL Handshake Scan](#ssl-handshake-scan).
  - SSL errors indicate new pods cannot establish TLS communication with existing pods (version mismatch or certificate rotation).
2. **Check memory and CPU during upgrade** -- run CPU Utilization by Pod and Memory Utilization by Pod:
  - Upgrades temporarily increase resource usage as old and new pods overlap

### Timing Guidance


| Duration  | Status                | Action                                                                                                                                   |
| --------- | --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| < 15 min  | Normal                | Wait for completion                                                                                                                      |
| 15-30 min | Slow but may complete | Continue monitoring; check for errors                                                                                                    |
| > 30 min  | Stuck                 | Investigate with queries above; if workflow failures, SSL cluster errors, or increasing restart counts are present, escalate immediately |


### Resolution

**Note:** Stuck upgrades are not customer-actionable. Runtime upgrade rollback is not available from the UI; the resolution path is Snowflake support escalation.

1. **If Runtime Workflow Failures shows `StandardUpgradeRuntimeWorkflow`, `Failed to upgrade runtime`, or `WaitForRuntimeConnectedNodes` after the runtime has been stuck > 30 minutes:**
  - Make Snowflake support escalation the primary recommended action
  - Include deployment ID, runtime name, the timestamp when the upgrade started, the exact workflow failure, and any SSL or cluster-formation errors
  - Tell the customer that runtime upgrade rollback is not available from the UI
  - Do **not** recommend restarting the runtime from the UI, retrying the upgrade, or other customer self-service remediation
2. **If restart counts are increasing during the upgrade:**
  - State explicitly that the new version is crash-looping during the rolling update
  - Treat this as confirmatory evidence of a runtime upgrade failure
  - Escalate to Snowflake support immediately with the restart-count evidence
3. **If SSL errors appear during cluster formation in the same upgrade window:**
  - State that new pods cannot form a cluster with the existing pods because TLS handshakes are failing
  - Treat this as part of the stuck upgrade failure, not as an isolated certificate-renewal task for the customer
  - Escalate to Snowflake support immediately
4. **Only if the runtime has been upgrading for less than 30 minutes and there are no workflow failures, SSL errors, or increasing restart counts:**
  - Continue monitoring until the 30-minute mark

---

## Branch: Container Crash Loop

**Pattern:** Container Restart Count shows `restart_count` >= 2 and increasing over time, or Recent Error Logs shows repeated startup failures.

**What it means:** The runtime container is starting, failing, and restarting in a loop. Kubernetes backs off exponentially between restarts (CrashLoopBackOff).

### Diagnosis

1. **Check restart count trend:**
  - Run Container Restart Count
  - Compare `restart_count` across multiple timestamps to confirm it's increasing
2. **Identify the failure cause from logs:**
  - Run Recent Error Logs filtered to `{namespace}` -- look for the earliest error after each restart
  - Common crash causes:


| Error Pattern                            | Likely Cause                                              | Action                                                          |
| ---------------------------------------- | --------------------------------------------------------- | --------------------------------------------------------------- |
| `OutOfMemoryError`                       | Heap exhaustion                                           | See [Branch: OOM](#branch-outofmemoryerror--java-heap)          |
| `EncryptionException: Decryption Failed` | Corrupted flow encryption keys (runtime state corruption) | Escalate -- requires Snowflake engineering intervention         |
| `Keystore was tampered with`             | Corrupted keystore secrets (runtime state corruption)     | Escalate -- requires Snowflake engineering intervention         |
| `CertPathValidatorException`             | Certificate issue                                         | See [Branch: SSL](#branch-ssl--certificate-errors)              |
| No error logs before crash               | Container killed externally (OOM killer, node pressure)   | Check Memory Utilization by Pod for memory spike before restart |


1. **Check disk space** -- run Disk Space per Runtime from `references/core-queries-resource.md`:
  - A full content or FlowFile repository can cause startup failures

### Resolution

- For OOM-related crashes, follow the [OOM branch](#branch-outofmemoryerror--java-heap)
- For encryption/keystore errors, escalate to Snowflake support -- these require engineering intervention to repair the runtime's encrypted flow definition
- For disk space issues, guide the customer to check if any connector can be paused or if old provenance data can be cleared. If disk is full with no customer-actionable reduction, escalate with disk utilization data from Disk Space per Runtime.
- For unknown crash causes, guide the customer to restart the runtime from the Openflow UI. If crashes continue after restart, escalate with results from Recent Error Logs, Container Restart Count, and Memory Utilization by Pod.

---

## Branch: ImagePullBackOff

**Pattern:** Event logs contain references to image pull failures, or the runtime is stuck in a creating/upgrading state with no NiFi logs appearing.

### Diagnosis

```sql
SELECT timestamp, value
FROM {event_table}
WHERE timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND record_type = 'LOG'
  AND (value ILIKE '%ImagePullBackOff%'
       OR value ILIKE '%ErrImagePull%'
       OR value ILIKE '%failed to pull image%'
       OR value ILIKE '%401 Unauthorized%')
ORDER BY timestamp DESC
LIMIT 50;
```

### SPCS-Specific

Image pulls in SPCS are managed by the platform. If image pull errors appear:

- This is typically a transient infrastructure issue
- Guide the customer to wait 10-15 minutes and retry
- If the issue persists after 30 minutes, escalate to Snowflake support -- this indicates a platform-level issue

### BYOC-Specific

Image pulls in BYOC require the `openflow-sync-images` job to have synced images to the customer's container registry (ECR, GCR, etc.).

Guide the customer to:

1. Verify their container registry credentials are not expired
2. Check that the image sync job has completed successfully (visible in deployment logs)
3. Verify network connectivity from the Kubernetes cluster to their container registry
4. If using ECR, check that the ECR token has not expired (tokens expire every 12 hours)

---

## Branch: No Clear Error Pattern

**Pattern:** Recent Error Logs and Runtime Workflow Failures return no results, or the errors don't match any branch above.

### Extended Diagnosis

1. **Expand time range** -- increase `{hours_back}` to 6, then 24 to catch older errors. If still empty after 24 hours, do not expand further -- proceed to step 4 and escalate.
2. **Check disk space** -- run Disk Space per Runtime:
  - < 1 GB free on any storage type = critical; data flow will fail
  - Content repository full = FlowFile data buildup
  - Provenance repository full = lineage data buildup
3. **Check error pattern summary** -- Error Pattern Summary:
  - This aggregates errors by type and count, which may reveal a pattern that individual log entries don't show
4. **Check DPS heartbeat** -- run DPS Heartbeat Check (in `references/core-queries-resource.md`):
  - If no heartbeat logs, the deployment itself may be unhealthy. This is a Snowflake-internal issue -- escalate to Snowflake support with deployment ID and the missing heartbeat finding.

### If Still No Root Cause

After exhausting all diagnostic steps above, this issue requires Snowflake support investigation. Present the customer with the diagnostic context to include in their support case:

> Based on the diagnostics, this issue requires Snowflake support investigation. Please open a support case with the following information:
>
> 1. **Deployment ID**: `{deployment_id}`
> 2. **Runtime name**: [name from Openflow UI]
> 3. **Error timestamp**: [specific UTC timestamp, or "no errors found in last N hours"]
> 4. **Diagnostics performed**: Ran Recent Error Logs, Runtime Workflow Failures, Disk Space per Runtime, Error Pattern Summary, and DPS Heartbeat Check -- [summarize key findings or lack thereof]
> 5. **Runtime state**: [ask the customer what state the runtime shows in the Openflow UI]
> 6. **Connectors affected**: [list any connectors on this runtime]

---

## Connector Resume After Runtime Recovery

After a runtime recovers from a crash, OOM, upgrade, or restart:

- **CDC connectors** resume from their last committed offset. No data loss expected unless the source CDC position (WAL/binlog/Change Tracking) has expired during the outage.
- **Non-CDC scheduled connectors** resume at the next scheduled interval.
- **If processors remain stopped** after runtime recovery, guide the customer to start them from the Openflow UI (right-click canvas > Start).

---

## Cross-Reference Guide


| If root cause points to...                                | Load                                                                         |
| --------------------------------------------------------- | ---------------------------------------------------------------------------- |
| EAI / network rule misconfiguration                       | **Load** `references/troubleshoot-network.md`                                |
| Deployment not reporting / DPS down                       | Snowflake-internal issue -- escalate to Snowflake support with deployment ID |
| Connector-level CDC errors (after runtime is healthy)     | **Load** `references/connectors/connector-router-cdc.md`                     |
| Connector-level non-CDC errors (after runtime is healthy) | **Load** `references/connectors/connector-router-non-cdc.md`                 |
| Customer needs step-by-step UI actions                    | Guide the customer through the Openflow UI steps directly                    |

