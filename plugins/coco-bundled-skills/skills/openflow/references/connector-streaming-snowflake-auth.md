---
name: openflow-connector-streaming-snowflake-auth
description: Configure Snowflake Private Key Auth (KEY_PAIR) for the PublishSnowpipeStreaming destination in a streaming connector (Kafka high-performance, Kinesis). Switches the processor from SNOWFLAKE_MANAGED to KEY_PAIR using a StandardPrivateKeyService controller. Load when changing how the streaming connector authenticates to Snowflake.
---

# Streaming Connectors — Snowflake Private Key Authentication

## Scope

This reference switches `PublishSnowpipeStreaming` from `SNOWFLAKE_MANAGED` (session token) to `KEY_PAIR` authentication for an already-installed streaming connector (Kafka high-performance, Kinesis).

For general key-pair setup (key generation, user assignment, service user creation, grants):
**Load** `references/ops-snowflake-auth.md`

This reference covers only the streaming-specific configuration: `StandardPrivateKeyService` controller + `PublishSnowpipeStreaming` processor properties.

---

## Workflow

**IMPORTANT:** This workflow follows the **inspect-modify-test** cycle from `author-building-flows.md`. Validate after every change.

**1. Stop the flow** (if running).

> Before creating any controller services or modifying processors, present a summary and ask for approval:
>
> "I will make the following changes to this connector:
> - Create a `StandardPrivateKeyService` controller service (with the uploaded key file)
> - Reconfigure `PublishSnowpipeStreaming` authentication from `SNOWFLAKE_MANAGED` to `KEY_PAIR` (Account, User, Role, Private Key Service)
>
> Proceed? (Yes / No / Modify)"

**2. Create and configure StandardPrivateKeyService:**

```python
import nipyapi
nipyapi.profiles.switch('<profile>')

pg = nipyapi.canvas.get_process_group('<pg-name-or-id>')
cs_type = nipyapi.canvas.get_controller_type('StandardPrivateKeyService')
pk_service = nipyapi.canvas.create_controller(pg, cs_type, 'StandardPrivateKeyService')

update_dto = nipyapi.nifi.ControllerServiceDTO(
    properties={
        'Key File': '<asset-reference-or-path>'  # Upload via ops-parameters-assets.md
        # 'Key Password': '<passphrase>'  # Only for encrypted keys
    }
)
nipyapi.canvas.update_controller(pk_service, update_dto)
```

| Property | Value |
|----------|-------|
| Key File | Path or asset reference to PKCS8 PEM key. **Load** `references/ops-parameters-assets.md` to upload. |
| Key Password | Passphrase for encrypted key (blank for unencrypted) |

**3. Validate and enable StandardPrivateKeyService:**

```python
cs = nipyapi.canvas.get_controller(pk_service.id, identifier_type='id')
assert cs.component.validation_status == 'VALID', (
    f"StandardPrivateKeyService validation failed: {cs.component.validation_errors}"
)
```

**Run exactly** (substitute `<profile>` and `<pk-service-id>` from session):
```bash
nipyapi --profile <profile> canvas schedule_controller "<pk-service-id>" True
```

**After enabling, verify state:**

```python
cs = nipyapi.canvas.get_controller(pk_service.id, identifier_type='id')
assert cs.component.state == 'ENABLED', (
    f"StandardPrivateKeyService failed to enable: {cs.component.validation_errors}"
)
```

**4. Configure PublishSnowpipeStreaming:**

```python
pss = nipyapi.canvas.get_processor('<publish-snowpipe-streaming-id>', identifier_type='id')
config = nipyapi.canvas.prepare_processor_config(pss, {
    'Authentication Strategy': 'KEY_PAIR',
    'Account': '<org>-<account>',
    'User': '<snowflake-username>',
    'Role': '<snowflake-role>',
    'Private Key Service': pk_service.id
})
nipyapi.canvas.update_processor(pss, update=config)
```

| Property | Value |
|----------|-------|
| Authentication Strategy | `KEY_PAIR` |
| Account | `<org>-<account>` (NOT full hostname) |
| User | Snowflake username |
| Role | Snowflake role |
| Private Key Service | StandardPrivateKeyService created above |

**Validate the processor:**

```python
pss = nipyapi.canvas.get_processor(pss.id, identifier_type='id')
assert pss.component.validation_status == 'VALID', (
    f"PublishSnowpipeStreaming validation failed: {pss.component.validation_errors}"
)
```

### Verification

**5. Verify configuration (full validation):**

Run batch verification to enable all services and validate all processors in one step. This does NOT start processors — the user decides when to start the flow.

**Run exactly** (substitute `<profile>` and `<pg-id>` from session):
```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>"
```

For details on interpreting results, see `references/ops-config-verification.md`.

**⚠️ MANDATORY:** If verification reports failures, investigate and fix before declaring the customization complete.

Once verification passes, inform the user:

> "All services are enabled and processors validated. The flow is ready to start when you are. Would you like me to start it now?"

---

## Troubleshooting

| Symptom | Likely Cause |
|---------|--------------|
| `PublishSnowpipeStreaming` validation error after KEY_PAIR | StandardPrivateKeyService not yet enabled — enable before starting processor. |
| Auth failure with Private Key | Public key not assigned to Snowflake user. Run `DESC USER <username>` to check `RSA_PUBLIC_KEY`. |
| Wrong account identifier format | Use `<org>-<account>` without `.snowflakecomputing.com`. |
| Encrypted key fails | `Key Password` not set on StandardPrivateKeyService for encrypted key. |

For data type or transformation troubleshooting, see the troubleshooting sections in `references/connector-streaming-datatypes.md` and `references/connector-streaming-transformations.md`.

---

## Next Step

After completing the auth change, if you arrived here from `references/connector-main.md` deployment workflow, **Continue** to `references/connector-main.md` Step 9 (Verify Controllers).

If other streaming customizations are needed, **Load** `references/connector-streaming-main.md`.

---

## See Also

- `references/connector-streaming-datatypes.md` — JSON → Avro/Protobuf data type switching
- `references/connector-streaming-transformations.md` — Filtering, mapping, routing, defaults, Groovy
- `references/connector-streaming-dlq.md` — Dead Letter Queue handling
- `references/connector-kafka.md` — Kafka broker auth customizations (MSK IAM, mTLS)
- `references/ops-snowflake-auth.md` — General Snowflake key-pair setup
- `references/ops-parameters-assets.md` — Upload certificates, keys, JARs
