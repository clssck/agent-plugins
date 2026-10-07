---
name: openflow-connector-streaming-datatypes
description: Switch a streaming connector's record format from JSON to Avro or Protobuf (inline schema text, embedded Avro schema, Confluent Schema Registry, Protobuf message-name resolution). Load when incoming Kafka/Kinesis messages are Avro- or Protobuf-encoded.
---

# Streaming Connectors — Data Type Switching

## Scope

This reference covers switching the record reader for streaming connectors (Kafka high-performance, Kinesis) from JSON to:
- **Avro** (inline schema text, embedded Avro schema, Confluent Schema Registry, or AWS Glue Schema Registry)
- **Protobuf** (inline schema text or Confluent Schema Registry, with static or resolver-based message name)

**The whole workflow is identical for Kafka and Kinesis** — only the source processor differs (`ConsumeKafka` vs `ConsumeKinesisStream`). Wherever a step references `ConsumeKafka`, substitute `ConsumeKinesisStream` for a Kinesis connector; everything else (controller services, schema strategies, validation) is the same.

For custom transformations (filtering, mapping, routing, defaults, Groovy):
**Load** `references/connector-streaming-transformations.md`

For Snowflake Private Key Auth (PublishSnowpipeStreaming) and overall routing:
**Load** `references/connector-streaming-main.md`

For Kafka broker authentication (SASL → MSK IAM, mTLS):
**Load** `references/connector-kafka.md`

---

## Customization: Data Type — Avro

Switch the record reader from `JsonTreeReader` to `AvroReader` for Avro-encoded messages.

Four schema access strategies are supported:
- **Option A:** Inline schema text — you provide the Avro schema directly
- **Option B:** Embedded Avro schema — schema read from Avro container file header
- **Option C:** Confluent Schema Registry — schema ID resolved from message
- **Option D:** AWS Glue Schema Registry — schema looked up in AWS Glue (common for **Amazon MSK** customers)

### Prerequisites

| Item | Description | Collected |
|------|-------------|-----------|
| Source messages | Kafka topic / Kinesis stream produces Avro-encoded messages | [ ] |
| Schema strategy | Inline text, embedded, Confluent Schema Registry, or AWS Glue Schema Registry | [ ] |
| Schema Registry URL | (Option C only) URL of Confluent Schema Registry | [ ] |
| Registry auth | (Option C only) NONE or BASIC (username/password) | [ ] |
| AWS region / registry name | (Option D only) AWS region and Glue Schema Registry name | [ ] |
| EAI configured | (Option C/D, SPCS only) External Access Integration for the registry endpoint. **Load** `references/platform-eai.md` to create, `references/ops-network-testing.md` to validate. | [ ] |

### Workflow

This workflow follows the **inspect-modify-test** cycle from `author-building-flows.md`. Validate after every configuration change before proceeding. Property values must use **internal identifiers** (not display names) — the allowable values from the API.

**1. Stop the flow** (if running):

**Run exactly** (substitute `<profile>` and `<pg-id>` from session):
```bash
nipyapi --profile <profile> ci stop_flow --process_group_id "<pg-id>"
```

> Before creating any controller services or modifying processors, present a summary and ask for approval:
>
> "I will make the following changes to this connector:
> - Create an `AvroReader` controller service (and Schema Registry services if using Confluent/Glue)
> - Update the source processor's Record Reader to the new reader; disable the old `JsonTreeReader`
>
> Proceed? (Yes / No / Modify)"

**2. Create AvroReader controller service:**

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

pg = nipyapi.canvas.get_process_group('<pg-name-or-id>')
cs_type = nipyapi.canvas.get_controller_type('AvroReader')
avro_reader = nipyapi.canvas.create_controller(pg, cs_type, 'AvroReader')
```

**3. Configure schema access strategy:**

#### Option A — Inline Schema Text

```python
update_dto = nipyapi.nifi.ControllerServiceDTO(
    properties={
        'Schema Access Strategy': 'schema-text-property',
        'Schema Text': '<full-avro-schema-json>'
    }
)
nipyapi.canvas.update_controller(avro_reader, update_dto)
```

| Property | Internal Value | Display Name |
|----------|---------------|---------------|
| Schema Access Strategy | `schema-text-property` | Use 'Schema Text' Property |
| Schema Text | Full Avro schema JSON | Supports Expression Language |

#### Option B — Embedded Avro Schema

```python
update_dto = nipyapi.nifi.ControllerServiceDTO(
    properties={
        'Schema Access Strategy': 'embedded-avro-schema'
    }
)
nipyapi.canvas.update_controller(avro_reader, update_dto)
```

| Property | Internal Value | Display Name |
|----------|---------------|---------------|
| Schema Access Strategy | `embedded-avro-schema` | Use Embedded Avro Schema |

Only works with Avro Object Container Files (OCF) that include the writer schema in the file header. If messages are raw Avro records (common for Kafka producers), use Option A or C instead.

#### Option C — Confluent Schema Registry

Requires two additional services: `ConfluentSchemaRegistry` and `ConfluentEncodedSchemaReferenceReader`.

**Create parameters first** (add to the connector's parameter context using `references/ops-parameters-main.md`):

| Parameter Name | Value | Sensitive |
|----------------|-------|-----------|
| `Schema Registry URL` | The registry URL (e.g., `https://schema-registry.example.com:8081`) | No |
| `Schema Registry Username` | (BASIC only) Registry username | No |
| `Schema Registry Password` | (BASIC only) Registry password | **Yes** |

**Create ConfluentSchemaRegistry:**

```python
cs_type = nipyapi.canvas.get_controller_type('ConfluentSchemaRegistry')
confluent_sr = nipyapi.canvas.create_controller(pg, cs_type, 'ConfluentSchemaRegistry')

update_dto = nipyapi.nifi.ControllerServiceDTO(
    properties={
        'Schema Registry URLs': '#{Schema Registry URL}',
        'Communications Timeout': '30 secs',
        'Cache Size': '1000',
        'Cache Expiration': '1 hour',
        'Authentication Type': 'NONE'  # or 'BASIC'
    }
)
nipyapi.canvas.update_controller(confluent_sr, update_dto)
```

| Property | Value |
|----------|-------|
| Schema Registry URLs | Comma-separated registry URLs |
| SSL Context Service | (Optional) SSLContextService if registry requires TLS |
| Communications Timeout | How long to wait for registry response |
| Cache Size | Number of schemas to cache locally |
| Cache Expiration | How long cached schemas are valid |
| Authentication Type | `NONE` or `BASIC` |
| Username | (BASIC only) Registry username |
| Password | (BASIC only) Registry password (sensitive) |

**Guidance — `Cache Size`:** this is the number of distinct schemas kept in memory. The default (`1000`) is fine for most flows. If a single topic/stream carries **many different schemas / message types** (high-cardinality, high-throughput), raise `Cache Size` so the reader does not evict and re-fetch schemas from the registry on every batch — at the cost of higher memory consumption. For a handful of schemas, leave it at the default.

**Create ConfluentEncodedSchemaReferenceReader:**

```python
cs_type = nipyapi.canvas.get_controller_type('ConfluentEncodedSchemaReferenceReader')
schema_ref_reader = nipyapi.canvas.create_controller(pg, cs_type, 'ConfluentEncodedSchemaReferenceReader')
```

No configurable properties — reads the Confluent wire format (magic byte `0x00` + 4-byte schema ID) from message start.

**Configure AvroReader:**

```python
update_dto = nipyapi.nifi.ControllerServiceDTO(
    properties={
        'Schema Access Strategy': 'schema-reference-reader',
        'Schema Reference Reader': schema_ref_reader.id,
        'Schema Registry': confluent_sr.id
    }
)
nipyapi.canvas.update_controller(avro_reader, update_dto)
```

| Property | Internal Value |
|----------|---------------|
| Schema Access Strategy | `schema-reference-reader` |

#### Option D — AWS Glue Schema Registry

For **Amazon MSK** producers that register Avro schemas in the AWS Glue Schema Registry. Uses two additional services: `AmazonGlueSchemaRegistry` and `AmazonGlueEncodedSchemaReferenceReader`.

**Create AmazonGlueSchemaRegistry:**

```python
cs_type = nipyapi.canvas.get_controller_type('AmazonGlueSchemaRegistry')
glue_sr = nipyapi.canvas.create_controller(pg, cs_type, 'AmazonGlueSchemaRegistry')

update_dto = nipyapi.nifi.ControllerServiceDTO(
    properties={
        'Schema Registry Name': '#{Glue Schema Registry Name}',
        'Region': '#{AWS Region}',
        'AWS Credentials Provider Service': '<aws-credentials-service-id>',  # reuse the connector's
        'Cache Size': '1000',
        'Cache Expiration': '1 hour'
    }
)
nipyapi.canvas.update_controller(glue_sr, update_dto)
```

| Property | Value |
|----------|-------|
| Schema Registry Name | Name of the Glue Schema Registry |
| Region | AWS region of the registry (e.g. `us-west-2`) |
| AWS Credentials Provider Service | Reuse the connector's `AWSCredentialsProviderControllerService` (Kinesis) or create one for MSK |
| Cache Size | Number of schemas cached locally (see guidance below) |
| Cache Expiration | How long cached schemas are valid |

**Create AmazonGlueEncodedSchemaReferenceReader:**

```python
cs_type = nipyapi.canvas.get_controller_type('AmazonGlueEncodedSchemaReferenceReader')
glue_schema_ref_reader = nipyapi.canvas.create_controller(pg, cs_type, 'AmazonGlueEncodedSchemaReferenceReader')
```

No configurable properties — reads the Glue wire format (8-byte header containing the schema UUID) from message start.

**Configure AvroReader** to resolve schemas from Glue using the encoded reference reader:

```python
update_dto = nipyapi.nifi.ControllerServiceDTO(
    properties={
        'Schema Access Strategy': 'schema-reference-reader',
        'Schema Reference Reader': glue_schema_ref_reader.id,
        'Schema Registry': glue_sr.id
    }
)
nipyapi.canvas.update_controller(avro_reader, update_dto)
```

| Property | Internal Value |
|----------|--------------|
| Schema Access Strategy | `schema-reference-reader` |

**Guidance — `Cache Size`:** number of distinct schemas kept in memory (default `1000`). If a single topic/stream carries **many different schemas** at high throughput, raise it so schemas are not evicted and re-fetched from Glue on every batch — at the cost of higher memory. Leave at the default for a small number of schemas.

**⚠️ Glue is Avro/JSON only here.** AWS Glue Schema Registry is **not** supported as a Protobuf source in these connectors — for Protobuf use inline schema text or Confluent Schema Registry (see the Protobuf section).

**4. Validate configuration before enabling:**

After configuring each controller service, verify it has no validation errors:

```python
# Refresh and check validation status
cs = nipyapi.canvas.get_controller(avro_reader.id, identifier_type='id')
assert cs.component.validation_status == 'VALID', (
    f"AvroReader validation failed: {cs.component.validation_errors}"
)
```

Alternatively, use `verify_controller` for a deeper connectivity check (e.g., Schema Registry reachability):

```python
results = nipyapi.canvas.verify_controller(avro_reader)
for r in results:
    print(f"{r.verification_step_name}: {r.outcome}")
    if r.outcome != 'SUCCESSFUL':
        print(f"  → {r.explanation}")
```

**⚠️ MANDATORY:** Do NOT proceed to enable if validation_status is not `VALID`. Fix the configuration first.

**5. Enable services** (order matters):

For Option C, enable in dependency order:

**Run exactly** (substitute `<profile>` and service IDs from session):
```bash
# Enable ConfluentSchemaRegistry first
nipyapi --profile <profile> canvas schedule_controller "<confluent-sr-id>" True
# Enable ConfluentEncodedSchemaReferenceReader
nipyapi --profile <profile> canvas schedule_controller "<schema-ref-reader-id>" True
# Enable AvroReader last
nipyapi --profile <profile> canvas schedule_controller "<avro-reader-id>" True
```

For Option D, enable in dependency order:

**Run exactly** (substitute `<profile>` and service IDs from session):
```bash
# Enable AmazonGlueSchemaRegistry first
nipyapi --profile <profile> canvas schedule_controller "<glue-sr-id>" True
# Enable AmazonGlueEncodedSchemaReferenceReader
nipyapi --profile <profile> canvas schedule_controller "<glue-schema-ref-reader-id>" True
# Enable AvroReader last
nipyapi --profile <profile> canvas schedule_controller "<avro-reader-id>" True
```

For Options A/B, only the AvroReader needs enabling:

**Run exactly** (substitute `<profile>` and `<avro-reader-id>` from session):
```bash
nipyapi --profile <profile> canvas schedule_controller "<avro-reader-id>" True
```

**After enabling, verify the service reached ENABLED state:**

```python
cs = nipyapi.canvas.get_controller(avro_reader.id, identifier_type='id')
assert cs.component.state == 'ENABLED', (
    f"AvroReader failed to enable. State: {cs.component.state}, "
    f"Errors: {cs.component.validation_errors}"
)
```

**6. Update the source processor:**

For **Kafka**:
```python
consume = nipyapi.canvas.get_processor('<consume-kafka-id>', identifier_type='id')
config = nipyapi.canvas.prepare_processor_config(consume, {
    'Record Reader': avro_reader.id
})
nipyapi.canvas.update_processor(consume, update=config)
```

For **Kinesis**:
```python
consume = nipyapi.canvas.get_processor('<consume-kinesis-id>', identifier_type='id')
config = nipyapi.canvas.prepare_processor_config(consume, {
    'Record Reader': avro_reader.id
})
nipyapi.canvas.update_processor(consume, update=config)
```

**Validate the processor after update:**

```python
consume = nipyapi.canvas.get_processor(consume.id, identifier_type='id')
assert consume.component.validation_status == 'VALID', (
    f"Source processor validation failed: {consume.component.validation_errors}"
)
```

**7. Disable old JsonTreeReader:**

**Run exactly** (substitute `<profile>` and `<json-tree-reader-id>` from session):
```bash
nipyapi --profile <profile> canvas schedule_controller "<json-tree-reader-id>" False
```

### Verification

**8. Verify configuration (full validation):**

Run batch verification to enable all services and validate all processors in one step. This catches missing dependencies, invalid references, and network issues. It does NOT start processors — the user decides when to start the flow.

**Run exactly** (substitute `<profile>` and `<pg-id>` from session):
```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>"
```

Or via Python:

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

result = nipyapi.ci.verify_config(process_group_id='<pg-id>')
print(result['summary'])
```

For details on interpreting results, see `references/ops-config-verification.md`.

**⚠️ MANDATORY:** If verification reports failures, investigate and fix before declaring the customization complete. Common causes:
- Service dependency not yet enabled (enable in dependency order)
- Network unreachable (EAI not configured for SPCS)
- Invalid property reference (ID changed or service deleted)

Once verification passes, inform the user:

> "All services are enabled and processors validated. The flow is ready to start when you are. Would you like me to start it now?"

**9. Cleanup — offer to remove unused services:**

> "The old JsonTreeReader is now disabled and unreferenced. Would you like me to delete it to keep the flow clean, or leave it in case you want to revert later?"

---

## Customization: Data Type — Protobuf

Switch the record reader from `JsonTreeReader` to `StandardProtobufReader` for Protobuf-encoded messages.

Three schema access strategies and two message name resolution strategies are supported. As with Avro, the workflow is identical for Kafka and Kinesis — substitute `ConsumeKinesisStream` for `ConsumeKafka`.

**⚠️ AWS Glue Schema Registry is not supported for Protobuf** in these connectors. For Protobuf, use inline schema text (Option A) or Confluent Schema Registry (Option B).

### Prerequisites

| Item | Description | Collected |
|------|-------------|-----------|
| Source messages | Kafka topic / Kinesis stream produces Protobuf-encoded messages | [ ] |
| Schema strategy | Inline text or Confluent Schema Registry | [ ] |
| Message name | Fully qualified Protobuf message name (e.g., `mypackage.MyMessage`) | [ ] |
| Message name resolution | Static property or Confluent resolver | [ ] |
| Schema Registry URL | (Registry only) URL of Confluent Schema Registry | [ ] |
| EAI configured | (Registry, SPCS only) External Access Integration for registry URL. **Load** `references/platform-eai.md` to create, `references/ops-network-testing.md` to validate. | [ ] |

### Workflow

This workflow follows the **inspect-modify-test** cycle from `author-building-flows.md`. Validate after every configuration change before proceeding. Property values must use **internal identifiers** (not display names).

**1. Stop the flow** (if running).

> Before creating any controller services or modifying processors, present a summary and ask for approval:
>
> "I will make the following changes to this connector:
> - Create a `StandardProtobufReader` controller service (and Schema Registry / message-name resolver services if used)
> - Update the source processor's Record Reader to the new reader; disable the old `JsonTreeReader`
>
> Proceed? (Yes / No / Modify)"

**2. Create StandardProtobufReader controller service:**

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

pg = nipyapi.canvas.get_process_group('<pg-name-or-id>')
cs_type = nipyapi.canvas.get_controller_type('StandardProtobufReader')
proto_reader = nipyapi.canvas.create_controller(pg, cs_type, 'StandardProtobufReader')
```

**3. Configure schema and message name strategy:**

#### Option A — Inline Schema + Message Name Property

```python
update_dto = nipyapi.nifi.ControllerServiceDTO(
    properties={
        'Schema Access Strategy': 'schema-text-property',
        'Schema Text': '<full-proto3-schema>',
        'Message Name Resolution Strategy': 'MESSAGE_NAME_PROPERTY',
        'Message Name': '<package.MessageName>'
    }
)
nipyapi.canvas.update_controller(proto_reader, update_dto)
```

| Property | Internal Value | Display Name |
|----------|---------------|---------------|
| Schema Access Strategy | `schema-text-property` | Use 'Schema Text' Property |
| Schema Text | Full Proto 3 schema text | Supports Expression Language |
| Message Name Resolution Strategy | `MESSAGE_NAME_PROPERTY` | — |
| Message Name | Fully qualified name including package, e.g. `mypackage.MyMessage` | — |

#### Option B — Confluent Schema Registry + Message Name Resolver

Requires three additional services:
- `ConfluentSchemaRegistry` — resolves schema ID to Proto 3 schema
- `ConfluentEncodedSchemaReferenceReader` — reads schema ID from message
- `ConfluentProtobufMessageNameResolver` — resolves message name from wire format

**Create ConfluentSchemaRegistry** (same as Avro Option C above — reuse if already created). The same **`Cache Size`** guidance applies: if one topic/stream carries many distinct Protobuf message types, raise `Cache Size` to avoid repeated registry lookups, at the cost of memory.

**Create ConfluentEncodedSchemaReferenceReader** (same as Avro Option C — reuse if already created).

**Create ConfluentProtobufMessageNameResolver:**

```python
cs_type = nipyapi.canvas.get_controller_type('ConfluentProtobufMessageNameResolver')
msg_resolver = nipyapi.canvas.create_controller(pg, cs_type, 'ConfluentProtobufMessageNameResolver')
```

No configurable properties — decodes message index sequence from Confluent Protobuf wire format.

**Configure StandardProtobufReader:**

```python
update_dto = nipyapi.nifi.ControllerServiceDTO(
    properties={
        'Schema Access Strategy': 'schema-reference-reader',
        'Schema Reference Reader': schema_ref_reader.id,
        'Schema Registry': confluent_sr.id,
        'Message Name Resolution Strategy': 'MESSAGE_NAME_RESOLVER',
        'Message Name Resolver': msg_resolver.id
    }
)
nipyapi.canvas.update_controller(proto_reader, update_dto)
```

| Property | Internal Value |
|----------|---------------|
| Schema Access Strategy | `schema-reference-reader` |

**4. Validate configuration before enabling:**

```python
cs = nipyapi.canvas.get_controller(proto_reader.id, identifier_type='id')
assert cs.component.validation_status == 'VALID', (
    f"StandardProtobufReader validation failed: {cs.component.validation_errors}"
)
```

**⚠️ MANDATORY:** Do NOT proceed to enable if validation_status is not `VALID`. Fix the configuration first.

**5. Enable services** (order: registry → reference reader → message resolver → protobuf reader):

**Run exactly** (substitute `<profile>` and service IDs from session):
```bash
# For Option B, enable in dependency order:
nipyapi --profile <profile> canvas schedule_controller "<confluent-sr-id>" True
nipyapi --profile <profile> canvas schedule_controller "<schema-ref-reader-id>" True
nipyapi --profile <profile> canvas schedule_controller "<msg-resolver-id>" True
nipyapi --profile <profile> canvas schedule_controller "<proto-reader-id>" True
```

**After enabling, verify the service reached ENABLED state:**

```python
cs = nipyapi.canvas.get_controller(proto_reader.id, identifier_type='id')
assert cs.component.state == 'ENABLED', (
    f"StandardProtobufReader failed to enable. State: {cs.component.state}, "
    f"Errors: {cs.component.validation_errors}"
)
```

**6. Update the source processor:**

For **Kafka**:
```python
consume = nipyapi.canvas.get_processor('<consume-kafka-id>', identifier_type='id')
config = nipyapi.canvas.prepare_processor_config(consume, {
    'Record Reader': proto_reader.id
})
nipyapi.canvas.update_processor(consume, update=config)
```

For **Kinesis**:
```python
consume = nipyapi.canvas.get_processor('<consume-kinesis-id>', identifier_type='id')
config = nipyapi.canvas.prepare_processor_config(consume, {
    'Record Reader': proto_reader.id
})
nipyapi.canvas.update_processor(consume, update=config)
```

**Validate the processor after update:**
```python
consume = nipyapi.canvas.get_processor(consume.id, identifier_type='id')
assert consume.component.validation_status == 'VALID', (
    f"Source processor validation failed: {consume.component.validation_errors}"
)
```

**7. Disable old JsonTreeReader:**

**Run exactly** (substitute `<profile>` and `<json-tree-reader-id>` from session):
```bash
nipyapi --profile <profile> canvas schedule_controller "<json-tree-reader-id>" False
```

### Verification

**8. Verify configuration (full validation):**

Run batch verification to enable all services and validate all processors in one step. This does NOT start processors — the user decides when to start the flow.

**Run exactly** (substitute `<profile>` and `<pg-id>` from session):
```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>"
```

For details on interpreting results, see `references/ops-config-verification.md`.

**⚠️ MANDATORY:** If verification reports failures, investigate and fix before declaring the customization complete.

Once verification passes, inform the user:

> "All services are enabled and processors validated. The flow is ready to start when you are. Would you like me to start it now?"

**9. Cleanup — offer to remove unused services:**

> "The old JsonTreeReader is now disabled and unreferenced. Would you like me to delete it to keep the flow clean, or leave it in case you want to revert later?"

---

## Troubleshooting

| Symptom | Likely Cause |
|---------|--------------|
| `SchemaNotFoundException` at runtime | Schema ID not in registry or registry URL wrong. Verify `Schema Registry URLs` in ConfluentSchemaRegistry. |
| Parse failures / `InvalidAvroSchemaException` | Schema mismatch between producer and reader config. Compare schemas. Failed messages → the parse-failure relationship (`parse failure` for Kafka, `parse.failure` for Kinesis). |
| `ConfluentSchemaRegistry` fails to enable | Network issue — **Load** `references/ops-network-testing.md` to test connectivity, or `references/platform-eai.md` to create/fix EAI. Verify registry URL is reachable. |
| Authentication failure against registry | Registry requires Basic auth — set `Authentication Type` to `BASIC` with credentials. |

---

## Next Step

After switching the data type, if additional customizations are needed:
- Custom transformations → **Load** `references/connector-streaming-transformations.md`
- Snowflake Private Key Auth → **Load** `references/connector-streaming-main.md`

If you arrived here from `references/connector-main.md` deployment workflow, **Continue** to `references/connector-main.md` Step 9 (Verify Controllers).

Otherwise, the customization is complete.

---

## See Also

- `references/connector-streaming-main.md` — Streaming customization router + Snowflake Private Key Auth
- `references/connector-streaming-transformations.md` — Filtering, mapping, routing, defaults, Groovy
- `references/connector-kafka.md` — Kafka broker auth customizations (MSK IAM, mTLS)
- `references/connector-main.md` — General connector deployment workflow
- `references/author-building-flows.md` — Creating processors and connections (inspect-modify-test)
- `references/ops-parameters-main.md` — Parameter configuration
- `references/platform-eai.md` — External Access Integration for Schema Registry
- `references/ops-network-testing.md` — Validate network connectivity
