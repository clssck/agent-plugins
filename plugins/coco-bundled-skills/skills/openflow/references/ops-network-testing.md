---
name: openflow-ops-network-testing
description: Test network connectivity from SPCS Openflow Runtimes to external endpoints. Use before deploying connectors to validate EAI configuration.
---

# Network Connectivity Testing

Test network connectivity from Openflow Runtimes to external data sources. Use this reference to validate EAI (External Access Integration) configuration before deploying connectors in SPCS, or when BYOC Deployments use custom networking setup.

## When to Use

| Scenario | Action |
|----------|--------|
| Deploying a connector on SPCS | Run network test BEFORE deployment to validate EAI |
| Connector fails with connection errors | Run network test to diagnose EAI issues |
| User reports "UnknownHostException" | Run network test to confirm missing EAI |
| BYOC deployment | Skip - BYOC usually has direct network access, no EAI required |

## Scope

- DNS resolution testing
- TCP port connectivity testing
- HTTPS request testing (for REST APIs)
- EAI/Network Rule diagnosis

## Architecture

The network test uses a reusable flow pattern:

```
[GenerateFlowFile] --> [ExecuteScript] --> [Funnel]
   (test script)      (Groovy evaluator)   (results queue)
```

**Design principles:**
- GenerateFlowFile `Custom Text` contains the test script (editable without restart)
- ExecuteScript is a static Groovy evaluator that runs scripts from FlowFile content
- ExecuteScript stays RUNNING; trigger tests by using RUN_ONCE with the GenerateFlowFile Processor
- Results are retrieved by peeking at the Funnel's incoming connection

---

## Prerequisites

Before running network tests, confirm you have collected from the user:

| Connector Type | Required Information |
|----------------|---------------------|
| **JDBC/Database** | Host, port (e.g., `db.example.com:5432`) |
| **REST API** | Base URL (extract host and port, typically 443) |
| **SharePoint** | Tenant name (for `TENANT.sharepoint.com`) |
| **SFTP** | Host, port (typically 22) |
| **Cloud Storage** | Service endpoints (e.g., `s3.amazonaws.com`, `storage.googleapis.com`) |

If this information is not yet available, return to the connector skill to collect configuration before proceeding.

---

## Process Overview

1. **Check prerequisites** - Ensure target host/port information is collected
2. **Create test flow** - One-time setup of the network test Process Group
3. **Configure test script** - Customize targets in GenerateFlowFile
4. **Run test** - Trigger GenerateFlowFile with RUN_ONCE
5. **Retrieve results** - Peek at FlowFile content from Funnel queue
6. **Interpret results** - Diagnose any failures before proceeding with connector deployment

---

## Step 1: Create the Test Flow (One-Time Setup)

Create a Process Group with the test flow components:

```python
import nipyapi

# Create Process Group
pg_position = nipyapi.layout.suggest_pg_position(nipyapi.canvas.get_root_pg_id())
pg = nipyapi.canvas.create_process_group(
    parent_pg=nipyapi.canvas.get_root_pg_id(),
    new_pg_name="Network Connectivity Test",
    location=pg_position
)
pg_id = pg.id

# Create GenerateFlowFile at origin
gen_type = nipyapi.canvas.get_processor_type('GenerateFlowFile')
gen_proc = nipyapi.canvas.create_processor(
    parent_pg=pg_id,
    processor=gen_type,
    location=nipyapi.layout.DEFAULT_ORIGIN,
    name="Test Script Input"
)

# Create ExecuteScript below GenerateFlowFile
exec_type = nipyapi.canvas.get_processor_type('ExecuteScript')
exec_proc = nipyapi.canvas.create_processor(
    parent_pg=pg_id,
    processor=exec_type,
    location=nipyapi.layout.below(gen_proc),
    name="Run Network Test"
)

# Create Funnel below ExecuteScript
funnel = nipyapi.canvas.create_funnel(pg_id, position=nipyapi.layout.below(exec_proc))

# Create connections
nipyapi.canvas.create_connection(gen_proc, exec_proc, ['success'])
nipyapi.canvas.create_connection(exec_proc, funnel, ['success', 'failure'])

print(f"Test flow created in PG: {pg_id}")
print(f"GenerateFlowFile: {gen_proc.id}")
print(f"ExecuteScript: {exec_proc.id}")
```

Record the IDs for subsequent operations.

---

## Step 2: Configure ExecuteScript (Static - Do Not Modify)

Configure ExecuteScript with the generic Groovy evaluator. This script reads and executes whatever script is in the FlowFile content:

```python
EVALUATOR_SCRIPT = '''
import groovy.json.JsonBuilder

def flowFile = session.get()
if (!flowFile) return

// Read the script from FlowFile content
def scriptContent = ''
session.read(flowFile, { inputStream ->
    scriptContent = inputStream.getText('UTF-8')
} as org.apache.nifi.processor.io.InputStreamCallback)

// Set up the binding with NiFi variables
def binding = new Binding()
binding.setVariable('session', session)
binding.setVariable('flowFile', flowFile)
binding.setVariable('REL_SUCCESS', REL_SUCCESS)
binding.setVariable('REL_FAILURE', REL_FAILURE)
binding.setVariable('log', log)

// Evaluate the script from FlowFile content
def shell = new GroovyShell(this.class.classLoader, binding)
try {
    shell.evaluate(scriptContent)
} catch (Exception e) {
    log.error("Script execution failed: " + e.message, e)
    flowFile = session.putAttribute(flowFile, 'script.error', e.message)
    session.transfer(flowFile, REL_FAILURE)
}
'''

nipyapi.canvas.update_processor(
    processor=exec_proc,
    update=nipyapi.nifi.ProcessorConfigDTO(
        properties={
            'Script Engine': 'Groovy',
            'Script Body': EVALUATOR_SCRIPT
        }
    )
)

# Start ExecuteScript (leave running)
nipyapi.canvas.schedule_processor(exec_proc, True)
```

**Important:** You should not need to modify this evaluator script. It is static infrastructure.

---

## Step 3: Configure Test Script in GenerateFlowFile

The test script goes in GenerateFlowFile's `Custom Text` property. Use the template below, customizing the `targets` array for your connector.
This allows you to edit the script without needing to stop and start the ExecuteScript Processor.

### Base Template

```groovy
import groovy.json.JsonBuilder

def results = [
    timestamp: new Date().format("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"),
    test_type: "CONNECTOR_TYPE Connectivity",  // e.g., "SharePoint Connectivity"
    tests: []
]

// === EDIT THIS SECTION ===
// Add the hosts and ports your connector needs
def targets = [
    [host: "example.com", port: 443, type: "HTTPS"],
    [host: "db.example.com", port: 5432, type: "JDBC/PostgreSQL"]
]
// === END EDIT SECTION ===

targets.each { target ->
    def testResult = [
        host: target.host,
        port: target.port,
        type: target.type,
        dns_lookup: [:],
        tcp_connect: [:]
    ]

    // DNS Lookup Test
    try {
        def startDns = System.currentTimeMillis()
        def addresses = java.net.InetAddress.getAllByName(target.host)
        def dnsTime = System.currentTimeMillis() - startDns
        testResult.dns_lookup = [
            success: true,
            resolved_ips: addresses.collect { it.hostAddress },
            duration_ms: dnsTime
        ]
    } catch (java.net.UnknownHostException e) {
        testResult.dns_lookup = [
            success: false,
            error: "UnknownHostException",
            message: e.message,
            diagnosis: "Probably EAI not configured or misconfgured - add host to Network Rule and attach EAI to Runtime"
        ]
    }

    // TCP Connection Test (only if DNS succeeded)
    if (testResult.dns_lookup.success) {
        try {
            def socket = new java.net.Socket()
            def startTcp = System.currentTimeMillis()
            socket.connect(new java.net.InetSocketAddress(target.host, target.port), 5000)
            def tcpTime = System.currentTimeMillis() - startTcp
            socket.close()
            testResult.tcp_connect = [success: true, duration_ms: tcpTime]
        } catch (java.net.SocketTimeoutException e) {
            testResult.tcp_connect = [
                success: false,
                error: "SocketTimeoutException",
                message: e.message,
                diagnosis: "Port not in Network Rule OR port blocked along route"
            ]
        } catch (java.net.ConnectException e) {
            testResult.tcp_connect = [
                success: false,
                error: "ConnectException",
                message: e.message,
                diagnosis: "Host reachable but no service listening on this port"
            ]
        } catch (Exception e) {
            testResult.tcp_connect = [success: false, error: e.class.simpleName, message: e.message]
        }
    } else {
        testResult.tcp_connect = [skipped: true, reason: "DNS lookup failed"]
    }

    results.tests << testResult
}

results.summary = [
    total_tests: results.tests.size(),
    dns_passed: results.tests.count { it.dns_lookup.success },
    tcp_passed: results.tests.count { it.tcp_connect?.success ?: false }
]

def jsonContent = new JsonBuilder(results).toPrettyString()
flowFile = session.write(flowFile, { outputStream ->
    outputStream.write(jsonContent.bytes)
} as org.apache.nifi.processor.io.OutputStreamCallback)
flowFile = session.putAttribute(flowFile, 'mime.type', 'application/json')
session.transfer(flowFile, REL_SUCCESS)
```

### Connector-Specific Target Examples

#### SharePoint Connector

```groovy
def targets = [
    [host: "login.microsoftonline.com", port: 443, type: "HTTPS/Auth"],
    [host: "graph.microsoft.com", port: 443, type: "HTTPS/API"],
    [host: "TENANT.sharepoint.com", port: 443, type: "HTTPS/Data"]  // Replace TENANT
]
```

#### PostgreSQL/JDBC Connector

```groovy
def targets = [
    [host: "your-db-host.rds.amazonaws.com", port: 5432, type: "JDBC/PostgreSQL"]
]
```

#### Snowflake CDC Connector

```groovy
def targets = [
    [host: "ACCOUNT.snowflakecomputing.com", port: 443, type: "HTTPS/Snowflake"]  // Replace ACCOUNT
]
```

#### REST API Connector

```groovy
def targets = [
    [host: "api.example.com", port: 443, type: "HTTPS/REST"]
]
```

### Apply the Script

```python
test_script = """..."""  # Your customized script from above

nipyapi.canvas.update_processor(
    processor=gen_proc,
    update=nipyapi.nifi.ProcessorConfigDTO(
        properties={'Custom Text': test_script}
    )
)
```

---

## Step 4: Run the Test

Trigger a single test run:

```python
import time

# Purge any previous results
connections = nipyapi.canvas.list_all_connections(pg_id)
for conn in connections:
    nipyapi.canvas.purge_connection(conn.id)

# Clear bulletins for clean state (scoped to test PG)
nipyapi.bulletins.clear_all_bulletins(pg_id)

# Run GenerateFlowFile once
nipyapi.canvas.schedule_processor(gen_proc, "RUN_ONCE")

# Wait for processing
time.sleep(3)
```

---

## Step 5: Retrieve and Interpret Results

```python
# Peek at the result (returns list of FlowFileDTO with full details)
# Use the connection created in Step 1 (exec_proc -> funnel)
result_conn = nipyapi.canvas.list_all_connections(pg_id)[0]  # Or save ID from Step 1
flowfiles = nipyapi.canvas.peek_flowfiles(result_conn, limit=1)

if flowfiles:
    # Get content
    content = nipyapi.canvas.get_flowfile_content(
        result_conn,
        flowfiles[0].uuid,
        cluster_node_id=flowfiles[0].cluster_node_id
    )
    print(content)
```

### Result Interpretation

| Error | Cause | Resolution |
|-------|-------|------------|
| `UnknownHostException` | Host not in any Network Rule | Create Network Rule with host, create EAI referencing rule, attach EAI to Runtime |
| `SocketTimeoutException` (DNS passed) | Port not in Network Rule OR destination firewall blocking | Check Network Rule includes correct port (e.g., `host:5432` not just `host`) |
| `ConnectException: Connection refused` | Host/port reachable but no service listening | Verify target service is running and listening on expected port |
| All tests pass | EAI correctly configured | Proceed with connector deployment |

### Network Rule Port Specificity

Network Rules are **HOST:PORT specific** and default to 443 if no port set.

Example:

```sql
-- This allows ONLY port 5432
CREATE NETWORK RULE POSTGRES_RULE
  TYPE = HOST_PORT
  VALUE_LIST = ('db.example.com:5432');
```

If you test `db.example.com:3306`, DNS will pass (host is allowed) but TCP will timeout (port 3306 not in rule).

---

For EAI creation and management, see `references/platform-eai.md`.

---

## Cleanup (Optional)

Remove the test flow when no longer needed:

```python
nipyapi.canvas.delete_process_group(pg, force=True)
```

---

## Troubleshooting

### No FlowFile in Result Queue

Check the failure connection:

```python
# List all connections and check queued counts
for conn in nipyapi.canvas.list_all_connections(pg_id):
    queued = conn.status.aggregate_snapshot.queued_count if conn.status else "0"
    print(f"Connection {conn.id[:8]}: {queued} queued")
```

### Script Error in Failure Queue

Retrieve FlowFile attributes to see error:

```python
summaries = nipyapi.canvas.list_flowfiles(failure_conn_id, limit=1)
if summaries:
    details = nipyapi.canvas.get_flowfile_details(
        failure_conn_id,
        summaries[0].uuid,
        cluster_node_id=summaries[0].cluster_node_id
    )
    print(f"Error: {details.attributes.get('script.error')}")
```

### ExecuteScript Shows INVALID

Verify the failure relationship is connected:

```python
proc = nipyapi.canvas.get_processor(exec_proc_id, identifier_type="id")
print(f"Validation: {proc.component.validation_status}")
print(f"Errors: {proc.component.validation_errors}")
```

---

## See Also

- `references/platform-eai.md` - EAI creation and management
- `references/connector-main.md` - Connector deployment workflows
- `references/core-guidelines.md` - Check-Act-Check pattern
