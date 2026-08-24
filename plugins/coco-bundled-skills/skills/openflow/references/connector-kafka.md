---
name: openflow-connector-kafka
description: Kafka high-performance connector broker authentication. Use when switching Kafka auth from SASL to AWS MSK IAM or mTLS.
---

# Kafka Connector

## Scope

This reference covers:
- Broker authentication customizations for the Kafka high-performance connector
- Switching from default SASL to AWS MSK IAM or mTLS

For data type changes (Avro, Protobuf), custom transformations, or Snowflake Private Key Auth:
**Load** `references/connector-streaming-main.md`

For general Snowflake destination authentication (KEY_PAIR via SnowflakeConnectionService):
**Load** `references/ops-snowflake-auth.md`

For initial connector deployment:
**Load** `references/connector-main.md`

---

## Base Flow

| Property | Default Value |
|----------|--------------|
| Flow name | `kafka-high-performance-connector` |
| Broker authentication | SASL (Kafka3ConnectionService with `SASL_SSL`, `SCRAM-SHA-512`) |
| Data type | JSON (JsonTreeReader with schema inference) |
| Architecture | ConsumeKafka → PublishSnowpipeStreaming |
| Snowflake auth | SNOWFLAKE_MANAGED (session token) |
| Parameter context | `Kafka High Performance` |

The connector may already be deployed and running. If customizing an existing connector, stop the flow first using `references/ops-flow-lifecycle.md`.

---

## User Intent Detection

Ask the user what customization they need:

> "What would you like to customize on your Kafka connector? Options include:
> - **Broker authentication** (switch from SASL to AWS MSK IAM or mTLS)
> - **Data type** (switch from JSON to Avro or Protobuf)
> - **Add transformations** (filtering, mapping, routing, etc.)
> - **Snowflake authentication** (switch to Private Key Auth)
> - **A combination** of the above"

Route based on response:
- Broker auth → Continue below
- Data type, transformations, or Snowflake auth → **Load** `references/connector-streaming-main.md`
- Combination → Handle broker auth here first, then **Load** `references/connector-streaming-main.md`

---

## Customization: AWS MSK IAM Authentication

### Prerequisites

Collect from user before proceeding:

| Item | Description | Collected |
|------|-------------|-----------|
| MSK Cluster | Amazon MSK with IAM authentication enabled | [ ] |
| Deployment type | BYOC (required — IAM credentials must be available) | [ ] |
| IAM permissions | Role/user has necessary MSK permissions | [ ] |
| Bootstrap Servers | MSK bootstrap server endpoints | [ ] |
| Security Protocol | `SASL_SSL` (default for MSK IAM) | [ ] |

### Workflow

This workflow follows the **inspect-modify-test** cycle from `author-building-flows.md`. Validate after every configuration change before proceeding.

**1. Stop the flow** (if running):

**Run exactly** (substitute `<profile>` and `<pg-id>` from session):
```bash
nipyapi --profile <profile> ci stop_flow --process_group_id "<pg-id>"
```

> Before disabling, creating, or modifying any controller services or processors, present a summary and ask for approval:
>
> "I will make the following changes to this connector:
> - Disable the existing `Kafka3ConnectionService`
> - Create and configure an `AmazonMSKConnectionService` (MSK IAM authentication)
> - Update `ConsumeKafka` to use the new connection service
>
> Proceed? (Yes / No / Modify)"

**2. Disable existing Kafka3ConnectionService:**

**Run exactly** (substitute `<profile>` and `<kafka3-connection-id>` from session):
```bash
nipyapi --profile <profile> canvas schedule_controller "<kafka3-connection-id>" False
```

**3. Create AmazonMSKConnectionService:**

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

pg = nipyapi.canvas.get_process_group('<pg-name-or-id>')
cs_type = nipyapi.canvas.get_controller_type('AmazonMSKConnectionService')
msk_cs = nipyapi.canvas.create_controller(pg, cs_type, 'AmazonMSKConnectionService')
```

**4. Configure AmazonMSKConnectionService properties:**

```python
update_dto = nipyapi.nifi.ControllerServiceDTO(
    properties={
        'SASL Mechanism': 'AWS_MSK_IAM',
        'security.protocol': '#{Kafka Security Protocol}',
        'bootstrap.servers': '#{Kafka Bootstrap Servers}'
    }
)
nipyapi.canvas.update_controller(msk_cs, update_dto)
```

| Property | Value |
|----------|-------|
| SASL Mechanism | `AWS_MSK_IAM` |
| Security Protocol | `#{Kafka Security Protocol}` (parameter reference) |
| Bootstrap Servers | `#{Kafka Bootstrap Servers}` (parameter reference) |

**5. Validate and verify the new service:**

```python
cs = nipyapi.canvas.get_controller(msk_cs.id, identifier_type='id')
assert cs.component.validation_status == 'VALID', (
    f"AmazonMSKConnectionService validation failed: {cs.component.validation_errors}"
)
```

For a deeper connectivity check:

```python
results = nipyapi.canvas.verify_controller(msk_cs)
for r in results:
    print(f"{r.verification_step_name}: {r.outcome}")
    if r.outcome != 'SUCCESSFUL':
        print(f"  → {r.explanation}")
```

**⚠️ MANDATORY:** Do NOT proceed to enable if validation_status is not `VALID`. Fix the configuration first.

**6. Update ConsumeKafka processor:**

Set `Kafka Connection Service` property to point to the new AmazonMSKConnectionService.

```python
consume_kafka = nipyapi.canvas.get_processor('<consume-kafka-id>', identifier_type='id')
config = nipyapi.canvas.prepare_processor_config(consume_kafka, {
    'Kafka Connection Service': msk_cs.id
})
nipyapi.canvas.update_processor(consume_kafka, update=config)

# Validate
consume_kafka = nipyapi.canvas.get_processor(consume_kafka.id, identifier_type='id')
assert consume_kafka.component.validation_status == 'VALID', (
    f"ConsumeKafka validation failed: {consume_kafka.component.validation_errors}"
)
```

**7. Enable AmazonMSKConnectionService:**

**Run exactly** (substitute `<profile>` and `<msk-cs-id>` from session):
```bash
nipyapi --profile <profile> canvas schedule_controller "<msk-cs-id>" True
```

**After enabling, verify state:**

```python
cs = nipyapi.canvas.get_controller(msk_cs.id, identifier_type='id')
assert cs.component.state == 'ENABLED', (
    f"AmazonMSKConnectionService failed to enable: {cs.component.validation_errors}"
)
```

### Verification

**8. Verify full configuration before start:**

Run batch verification to ensure all services and processors are ready:

**Run exactly** (substitute `<profile>` and `<pg-id>` from session):
```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>"
```

For details on interpreting results, see `references/ops-config-verification.md`.

**9. Ask user to start the flow:**

> "The flow is configured and ready to start. Would you like me to start it now?"

Only start if the user confirms:

**Run exactly** (substitute `<profile>` and `<pg-id>` from session):
```bash
nipyapi --profile <profile> ci start_flow --process_group_id "<pg-id>"
```

**10. Validate:** Check for bulletins and running state:

**Run exactly** (substitute `<profile>` and `<pg-id>` from session):
```bash
nipyapi --profile <profile> canvas get_bulletins --pg_id "<pg-id>"
```

**11. Cleanup — offer to remove old Kafka3ConnectionService:**

> "The old Kafka3ConnectionService is now disabled and unreferenced. Would you like me to delete it to keep the flow clean, or leave it in case you want to revert later?"

If user confirms deletion:

```python
nipyapi.canvas.delete_controller(nipyapi.canvas.get_controller('<kafka3-connection-id>', identifier_type='id'))
```

---

## Customization: mTLS Authentication

### Prerequisites

Collect from user before proceeding:

| Item | Description | Collected |
|------|-------------|-----------|
| Keystore file | Contains client private key and certificate (PKCS12, JKS, or BCFKS) | [ ] |
| Keystore password | Password protecting the keystore | [ ] |
| Keystore type | Format: `PKCS12`, `JKS`, or `BCFKS` | [ ] |
| Key password | Password for the private key (if different from keystore password) | [ ] |
| Truststore file | (Optional) Contains broker CA certificate | [ ] |
| Truststore password | (Optional) Password for the truststore | [ ] |
| Truststore type | (Optional) Format: `PKCS12`, `JKS`, or `BCFKS` | [ ] |

**Truststore is optional:** Only required if the Kafka broker certificate is NOT signed by a trusted CA. If the broker uses a well-known CA, skip truststore configuration.

### Workflow

This workflow follows the **inspect-modify-test** cycle from `author-building-flows.md`. Validate after every change.

**1. Stop the flow** (if running):

**Run exactly** (substitute `<profile>` and `<pg-id>` from session):
```bash
nipyapi --profile <profile> ci stop_flow --process_group_id "<pg-id>"
```

> Before uploading assets, creating services, or modifying processors, present a summary and ask for approval:
>
> "I will make the following changes to this connector:
> - Upload the keystore/truststore as assets and add the sensitive parameters
> - Create and configure a `StandardSSLContextService`
> - Update `Kafka3ConnectionService` to use the SSL context (mTLS)
>
> Proceed? (Yes / No / Modify)"

**2. Upload keystore (and truststore if needed) as assets:**

Upload the keystore file to the connector's parameter context using the CLI:

**Run exactly** (substitute `<profile>`, `<pg-id>`, and file path from user):
```bash
nipyapi --profile <profile> ci upload_asset \
  --process_group_id "<pg-id>" \
  --file_path "/path/to/client.p12" \
  --param_name "Keystore File"
```

If a truststore is also needed:

**Run exactly** (substitute `<profile>`, `<pg-id>`, and file path from user):
```bash
nipyapi --profile <profile> ci upload_asset \
  --process_group_id "<pg-id>" \
  --file_path "/path/to/truststore.p12" \
  --param_name "Truststore File"
```

For more asset management options, see `references/ops-parameters-assets.md`.

**3. Create parameters for sensitive values** (add to the connector's parameter context using `references/ops-parameters-main.md`):

| Parameter Name | Value | Sensitive |
|----------------|-------|-----------|
| `Keystore File` | (auto-set by asset upload above) | No (asset ref) |
| `Keystore Password` | Keystore password | **Yes** |
| `Key Password` | (Optional) Key password if different from keystore password | **Yes** |
| `Truststore File` | (Optional, auto-set by asset upload) | No (asset ref) |
| `Truststore Password` | (Optional) Truststore password | **Yes** |

**4. Create StandardSSLContextService:**

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

pg = nipyapi.canvas.get_process_group('<pg-name-or-id>')
cs_type = nipyapi.canvas.get_controller_type('StandardSSLContextService')
ssl_cs = nipyapi.canvas.create_controller(pg, cs_type, 'StandardSSLContextService')
```

**5. Configure StandardSSLContextService properties:**

```python
props = {
    'Keystore Filename': '#{Keystore File}',
    'Keystore Password': '#{Keystore Password}',
    'Keystore Type': '<PKCS12|JKS|BCFKS>',
}

# Add Key Password if different from keystore password
if key_password_differs:
    props['Key Password'] = '#{Key Password}'

# Add truststore if provided
if truststore_provided:
    props['Truststore Filename'] = '#{Truststore File}'
    props['Truststore Password'] = '#{Truststore Password}'
    props['Truststore Type'] = '<PKCS12|JKS|BCFKS>'

update_dto = nipyapi.nifi.ControllerServiceDTO(properties=props)
nipyapi.canvas.update_controller(ssl_cs, update_dto)
```

| Property | Value |
|----------|-------|
| Keystore Filename | `#{Keystore File}` (parameter referencing uploaded asset) |
| Keystore Password | `#{Keystore Password}` (sensitive parameter) |
| Keystore Type | `PKCS12`, `JKS`, or `BCFKS` |
| Key Password | `#{Key Password}` (if encrypted separately) |
| Truststore Filename | (Optional) `#{Truststore File}` (parameter referencing uploaded asset) |
| Truststore Password | (Optional) `#{Truststore Password}` (sensitive parameter) |
| Truststore Type | (Optional) `PKCS12`, `JKS`, or `BCFKS` |

**6. Validate and enable StandardSSLContextService:**

```python
cs = nipyapi.canvas.get_controller(ssl_cs.id, identifier_type='id')
assert cs.component.validation_status == 'VALID', (
    f"StandardSSLContextService validation failed: {cs.component.validation_errors}"
)
```

**⚠️ MANDATORY:** Do NOT proceed to enable if validation_status is not `VALID`.

**Run exactly** (substitute `<profile>` and `<ssl-cs-id>` from session):
```bash
nipyapi --profile <profile> canvas schedule_controller "<ssl-cs-id>" True
```

**After enabling, verify state:**

```python
cs = nipyapi.canvas.get_controller(ssl_cs.id, identifier_type='id')
assert cs.component.state == 'ENABLED', (
    f"StandardSSLContextService failed to enable: {cs.component.validation_errors}"
)
```

**7. Update Kafka3ConnectionService:**

Disable first (required before updating):

**Run exactly** (substitute `<profile>` and `<kafka3-connection-id>` from session):
```bash
nipyapi --profile <profile> canvas schedule_controller "<kafka3-connection-id>" False
```

```python
kafka3_cs = nipyapi.canvas.get_controller('<kafka3-connection-id>', identifier_type='id')
update_dto = nipyapi.nifi.ControllerServiceDTO(
    properties={
        'security.protocol': 'SSL',
        'SSL Context Service': ssl_cs.id
    }
)
nipyapi.canvas.update_controller(kafka3_cs, update_dto)
```

| Property | Value |
|----------|-------|
| Security Protocol | `SSL` |
| SSL Context Service | The StandardSSLContextService created above |

Keep all other Kafka3ConnectionService settings unchanged (bootstrap.servers, timeouts, etc.). SASL properties become unused but are harmless to leave.

**8. Validate and re-enable Kafka3ConnectionService:**

```python
cs = nipyapi.canvas.get_controller(kafka3_cs.id, identifier_type='id')
assert cs.component.validation_status == 'VALID', (
    f"Kafka3ConnectionService validation failed: {cs.component.validation_errors}"
)
```

For a deeper connectivity check:

```python
results = nipyapi.canvas.verify_controller(kafka3_cs)
for r in results:
    print(f"{r.verification_step_name}: {r.outcome}")
    if r.outcome != 'SUCCESSFUL':
        print(f"  → {r.explanation}")
```

**Run exactly** (substitute `<profile>` and `<kafka3-connection-id>` from session):
```bash
nipyapi --profile <profile> canvas schedule_controller "<kafka3-connection-id>" True
```

### Verification

**9. Verify full configuration before start:**

Run batch verification to ensure all services and processors are ready:

**Run exactly** (substitute `<profile>` and `<pg-id>` from session):
```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>"
```

For details on interpreting results, see `references/ops-config-verification.md`.

**10. Ask user to start the flow:**

> "The flow is configured and ready to start. Would you like me to start it now?"

Only start if the user confirms:

**Run exactly** (substitute `<profile>` and `<pg-id>` from session):
```bash
nipyapi --profile <profile> ci start_flow --process_group_id "<pg-id>"
```

**11. Validate:** Check for bulletins and running state:

**Run exactly** (substitute `<profile>` and `<pg-id>` from session):
```bash
nipyapi --profile <profile> canvas get_bulletins --pg_id "<pg-id>"
```

---

## Combining Customizations

Broker authentication customizations are **mutually exclusive** — choose exactly ONE:
- SASL (default, no changes needed)
- AWS MSK IAM
- mTLS

Broker auth CAN be combined with:
- Data type changes (Avro, Protobuf) — see `references/connector-streaming-datatypes.md`
- Custom transformations — see `references/connector-streaming-transformations.md`
- Snowflake Private Key Auth — see `references/connector-streaming-main.md`

**Recommended order for combined customizations:**
1. Broker authentication (this file)
2. Data type change
3. Snowflake auth
4. Custom transformations (last, as they depend on the data flow being correct)

---

## Troubleshooting

| Symptom | Likely Cause |
|---------|--------------|
| AmazonMSKConnectionService fails to verify | IAM credentials not available (SPCS?), wrong bootstrap servers, or missing MSK permissions |
| SSL handshake failure with mTLS | Keystore doesn't contain valid client cert, or truststore missing broker CA |
| `INVALID` keystore type | Mismatch between file format and configured Keystore Type |
| Connection timeout after auth change | Bootstrap servers unreachable — **Load** `references/ops-network-testing.md` to test connectivity, or `references/platform-eai.md` to create/fix EAI for SPCS |
| `SASL authentication failed` after mTLS switch | ConsumeKafka still pointing to old Kafka3ConnectionService with SASL config |

---

## Next Step

After completing the customization, if you arrived here from `references/connector-main.md` deployment workflow, **Continue** to `references/connector-main.md` Step 9 (Verify Controllers).

If additional customizations are needed (data type, transformations), **Load** `references/connector-streaming-main.md`.

Otherwise, the customization is complete.

---

## See Also

- `references/connector-streaming-main.md` — Streaming customization router + Snowflake Private Key Auth
- `references/connector-streaming-datatypes.md` — Data type switching (Avro, Protobuf)
- `references/connector-streaming-transformations.md` — Custom transformations (filter, map, route, defaults, Groovy)
- `references/connector-main.md` — General connector deployment workflow
- `references/ops-parameters-assets.md` — Upload keystore/truststore files as assets
- `references/ops-flow-lifecycle.md` — Stop/start flows
- `references/platform-eai.md` — Network access for SPCS deployments
