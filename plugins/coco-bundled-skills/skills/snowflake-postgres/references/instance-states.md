# Instance States

Snowflake Postgres instances transition through these states during their lifecycle.

| State | Description |
|-------|-------------|
| `CREATING` | New server being provisioned |
| `RESTORING` | Backup being restored |
| `STARTING` | Postgres starting |
| `REPLAYING` | WAL being replayed |
| `FINALIZING` | Configuration finishing |
| `READY` | ✅ Instance available for connections |
| `SUSPENDING` | Being suspended |
| `SUSPENDED` | Compute stopped, data retained (storage billing continues) |
| `RESUMING` | Being resumed |
| `RESTARTING` | Restart in progress |
| `FAILED` | Creation or operation failed |
| `PROVISIONING` | Being provisioned |
| `DESTROYING` | Being deleted |
| `READY_ENABLING_HA` | Ready but enabling HA in background |

## State Transitions

```
CREATE → CREATING → STARTING → FINALIZING → READY
                                              ↓
SUSPEND ←────────────────────────────── SUSPENDING
    ↓
SUSPENDED
    ↓
RESUME → RESUMING → READY
```

## Checking State

```sql
DESCRIBE POSTGRES INSTANCE my_instance;
-- Look for 'state' field in response
```

## Common Patterns

**Waiting for READY:**
- After CREATE: typically 3-5 minutes
- After RESUME: typically 3-5 minutes
- After RESTART: typically 1-5 minutes depending on type

**When FAILED:**
- Check Snowflake account limits
- Verify compute family is valid for your account
- Contact Snowflake support if persistent
