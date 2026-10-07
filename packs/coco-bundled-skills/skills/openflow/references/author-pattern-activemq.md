---
name: openflow-author-pattern-activemq
description: Blueprint for JMS messaging with ActiveMQ. Load when building flows that publish or consume messages from ActiveMQ brokers.
---

# Pattern: ActiveMQ JMS Messaging

Blueprint for building flows that publish and consume messages from ActiveMQ brokers (including Amazon MQ).

---

## When to Use This Pattern

- Integrate with existing ActiveMQ/Amazon MQ message queues
- Event-driven ingestion from JMS topics or queues
- Publish events to message broker for downstream consumers
- Decouple data pipelines with message queuing

---

## Critical: Jakarta EE Compatibility

**NiFi 2.x uses Jakarta JMS (`jakarta.jms.*`), not legacy Java EE (`javax.jms.*`).**

The standard ActiveMQ client (`activemq-client`) implements the legacy `javax.jms.ConnectionFactory` interface. Using it with NiFi 2.x causes:

```
java.lang.ClassNotFoundException: javax.jms.ConnectionFactory
```

**Solution:** Use `activemq-client-jakarta` instead of `activemq-client`.

### Finding the Right JARs

When encountering `ClassNotFoundException: javax.jms.*` errors, follow this discovery process:

**Step 1: Search Maven Central for Jakarta variant**

```bash
# Search for jakarta-compatible version of the client library
curl -s "https://search.maven.org/solrsearch/select?q=g:org.apache.activemq+AND+a:activemq-client-jakarta&rows=5&wt=json" | jq '.response.docs[] | {id, latestVersion}'
```

Many Java EE libraries now provide separate `-jakarta` artifacts for Jakarta EE 9+ compatibility.

**Step 2: Analyze POM for runtime dependencies**

```bash
# Get the POM and extract runtime/compile dependencies
VERSION="5.18.7"
curl -s "https://repo1.maven.org/maven2/org/apache/activemq/activemq-client-jakarta/${VERSION}/activemq-client-jakarta-${VERSION}.pom" | grep -A3 "<dependency>"
```

Look for dependencies with `<scope>compile</scope>` or no scope (defaults to compile). Skip `<scope>provided</scope>` dependencies as NiFi supplies those.

**Step 3: Verify JAR contains jakarta classes**

```bash
# Confirm the JAR implements jakarta.jms (not javax.jms)
unzip -l activemq-client-jakarta-5.18.7.jar | grep -E "jakarta/jms|javax/jms"
```

You should see `jakarta/jms/` paths, NOT `javax/jms/` paths.

### Example: ActiveMQ 5.18.7

Following the discovery process above yields these required JARs:

| Artifact | Purpose |
|----------|---------|
| `activemq-client-jakarta-5.18.7.jar` | Jakarta-compatible ActiveMQ client |
| `jakarta.jms-api-3.1.0.jar` | Jakarta JMS interfaces |
| `hawtbuf-1.11.jar` | Buffer library |
| `geronimo-j2ee-management_1.1_spec-1.0.1.jar` | J2EE management spec |

**Do NOT include `activemq-client-5.18.7.jar`** - it contains javax.jms classes that conflict with the jakarta version. The POM lists it as a dependency, but including both causes classpath conflicts.

**Maven Central URLs (for 5.18.7):**

```
https://repo1.maven.org/maven2/org/apache/activemq/activemq-client-jakarta/5.18.7/activemq-client-jakarta-5.18.7.jar
https://repo1.maven.org/maven2/jakarta/jms/jakarta.jms-api/3.1.0/jakarta.jms-api-3.1.0.jar
https://repo1.maven.org/maven2/org/fusesource/hawtbuf/hawtbuf/1.11/hawtbuf-1.11.jar
https://repo1.maven.org/maven2/org/apache/geronimo/specs/geronimo-j2ee-management_1.1_spec/1.0.1/geronimo-j2ee-management_1.1_spec-1.0.1.jar
```

For different ActiveMQ versions, re-run the discovery steps to find the correct dependency versions.

---

## Core Components

| Tool | Purpose | See |
|------|---------|-----|
| `ConsumeJMS` | Consume messages from queue/topic | `author-component-selection.md` |
| `PublishJMS` | Publish messages to queue/topic | `author-component-selection.md` |
| `JMSConnectionFactoryProvider` | Shared connection config | `author-component-selection.md` |
| `StandardSSLContextService` | SSL/TLS for secure connections | `author-component-selection.md` |

---

## Setup

Openflow uses parameter assets for JARs (cannot access container filesystem directly).

### Step 1: Create Parameter Context

```python
import nipyapi

nipyapi.profiles.switch('<profile>')
ctx = nipyapi.parameters.create_parameter_context(
    name='JMS ActiveMQ Jakarta Assets',
    description='Jakarta-compatible ActiveMQ client JARs'
)
print(f"Context ID: {ctx.id}")
```

### Step 2: Upload JAR Assets

```bash
PROFILE="<your-profile>"
CONTEXT_ID="<from-step-1>"

nipyapi --profile $PROFILE ci upload_asset \
  --url "https://repo1.maven.org/maven2/org/apache/activemq/activemq-client-jakarta/5.18.7/activemq-client-jakarta-5.18.7.jar" \
  --context_id "$CONTEXT_ID"

nipyapi --profile $PROFILE ci upload_asset \
  --url "https://repo1.maven.org/maven2/jakarta/jms/jakarta.jms-api/3.1.0/jakarta.jms-api-3.1.0.jar" \
  --context_id "$CONTEXT_ID"

nipyapi --profile $PROFILE ci upload_asset \
  --url "https://repo1.maven.org/maven2/org/fusesource/hawtbuf/hawtbuf/1.11/hawtbuf-1.11.jar" \
  --context_id "$CONTEXT_ID"

nipyapi --profile $PROFILE ci upload_asset \
  --url "https://repo1.maven.org/maven2/org/apache/geronimo/specs/geronimo-j2ee-management_1.1_spec/1.0.1/geronimo-j2ee-management_1.1_spec-1.0.1.jar" \
  --context_id "$CONTEXT_ID"
```

### Step 3: Create Multi-Asset Parameter

See `ops-parameters-assets.md` for details on creating parameters with multiple asset references.

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

context_id = '<context-id>'

# Get all uploaded assets and link them to a parameter
assets = nipyapi.parameters.list_assets(context_id)
param = nipyapi.parameters.prepare_parameter_with_asset(
    name='JMS Client Libraries',
    assets=assets,  # List of dicts with 'id' and 'name' keys
    description='Jakarta-compatible ActiveMQ client JARs'
)

ctx = nipyapi.parameters.get_parameter_context(context_id, identifier_type='id')
nipyapi.parameters.upsert_parameter_to_context(ctx, param)
```

### Step 4: Bind and Configure

1. Bind process group to parameter context
2. Set processor property: `JMS Client Libraries: #{JMS Client Libraries}`

### Step 5: External Access Integration

SPCS deployments require EAI for external network access:

1. Create Network Rule for ActiveMQ endpoint (port 61617 for SSL)
2. Create External Access Integration referencing the rule
3. Attach EAI to Openflow runtime via SQL (`ALTER OPENFLOW RUNTIME <name> SET EXTERNAL_ACCESS_INTEGRATIONS = (<eai>)`) or Control Plane UI if pre-SOM

See `platform-eai.md` for EAI details.

---

## Configuration Reference

| Property | Value | Notes |
|----------|-------|-------|
| JMS Client Libraries | Path or `#{param}` | Directory containing all 5 JARs |
| JMS Connection Factory Implementation Class | `org.apache.activemq.ActiveMQConnectionFactory` | Same class name for both javax and jakarta versions |
| JMS Broker URI | `ssl://host:61617` | Use `ssl://` for Amazon MQ, `tcp://` for unencrypted |
| Destination Type | `QUEUE` or `TOPIC` | |
| Acknowledgement Mode | `2` (CLIENT_ACKNOWLEDGE) | Recommended for reliability |

---

## Common Issues

### ClassNotFoundException: javax.jms.ConnectionFactory

Using wrong JARs. Ensure you have `activemq-client-jakarta` (not `activemq-client`).

### ClassCastException or duplicate class errors

Classpath conflict from including both `activemq-client-jakarta` and `activemq-client`. Use only the jakarta version.

### UnknownHostException

Network connectivity issue. For Openflow SPCS, verify EAI is created and attached.

### JMSSecurityException: User name or password is invalid

Credentials incorrect, or password not set. **Do not embed credentials in the Broker URI** - special characters in passwords break URI parsing. Instead, set credentials on the processor:

| Property | Location |
|----------|----------|
| `User Name` | ConsumeJMS / PublishJMS processor property |
| `Password` | ConsumeJMS / PublishJMS processor property |

The controller service provides the connection factory; the processor provides per-connection credentials.

### SSL Handshake Failure

For Amazon MQ, SSL is mandatory on port 61617. No additional SSL Context Service configuration typically needed - ActiveMQ uses JVM default trust store which includes Amazon's CA.

### Flow creates infinite loop

If ConsumeJMS and PublishJMS use the same queue, messages loop forever. Design flows with clear directionality:

- **Test pattern:** GenerateFlowFile -> PublishJMS(test.queue) / ConsumeJMS(test.queue) -> Funnel
- **Production pattern:** ConsumeJMS(input.queue) -> Transform -> PutSnowpipeStreaming (or PublishJMS to a *different* queue)

### GenerateFlowFile validation errors

If setting `Custom Text`, you must also set:
- `Data Format`: `Text`
- `Unique FlowFiles`: `false`
- `File Size`: `0 B` (not just `0`)

---

## Flow Patterns

### Consume to Snowflake

```
ConsumeJMS → ConvertRecord → PutSnowpipeStreaming
```

### Publish from Database

```
QueryDatabaseTable → ConvertRecord → PublishJMS
```

### Request-Reply

```
GenerateFlowFile → PublishJMS (request queue)
                         ↓
ConsumeJMS (reply queue) → Process Response
```

---

## Related References

- `author-main.md` - Authoring router
- `author-component-selection.md` - Component descriptions
- `ops-parameters-assets.md` - Uploading JARs as parameter assets
- `platform-eai.md` - External Access Integration for network access
- `author-snowflake-destination.md` - Snowflake destination
