# Snowflake Postgres Instance Options Reference

Use this reference to validate parameters before running CREATE/ALTER commands.

## ⚠️ Required Parameters for CREATE

**EVERY CREATE statement needs ALL THREE required parameters:**

```sql
CREATE POSTGRES INSTANCE <name>
  COMPUTE_FAMILY = 'STANDARD_M'
  STORAGE_SIZE_GB = 10
  AUTHENTICATION_AUTHORITY = POSTGRES
  -- Optional parameters below
  POSTGRES_VERSION = 18
  HIGH_AVAILABILITY = TRUE
  NETWORK_POLICY = 'my_policy'
  STORAGE_INTEGRATION = 'my_integration'
  POSTGRES_SETTINGS = '{"postgres:work_mem": "128MB"}'
  COMMENT = 'My instance'
  TAG (cost_center = 'engineering');
```

| Parameter | Required | Example | Notes |
|-----------|----------|---------|-------|
| `COMPUTE_FAMILY` | ✅ Yes | `'STANDARD_M'` | Quoted string |
| `STORAGE_SIZE_GB` | ✅ Yes | `10` | Number (NOT `STORAGE_SIZE`) |
| `AUTHENTICATION_AUTHORITY` | ✅ Yes | `POSTGRES` | No quotes — `POSTGRES` or `POSTGRES_OR_SNOWFLAKE` |
| `POSTGRES_VERSION` | No | `18` | Number, omit for latest |
| `HIGH_AVAILABILITY` | No | `TRUE` | Boolean, enables standby replica |
| `NETWORK_POLICY` | No | `'my_policy'` | Quoted string, must exist |
| `STORAGE_INTEGRATION` | No | `'my_integration'` | Quoted string, type `POSTGRES_EXTERNAL_STORAGE` for pg_lake |
| `POSTGRES_SETTINGS` | No | `'{"postgres:work_mem": "128MB"}'` | JSON string — use `:` not `=` as separator |
| `COMMENT` | No | `'My instance'` | Quoted string, free-form text |
| `TAG` | No | `(cost_center = 'eng')` | One or more `tag = 'value'` pairs |

---

## Compute Families

### Standard (General Purpose)

| Family | Cores | Memory | Use Case |
|--------|-------|--------|----------|
| `STANDARD_M` | 1 | 4GB | Development, small production |
| `STANDARD_L` | 2 | 8GB | Production workloads |
| `STANDARD_XL` | 4 | 16GB | High-performance production |
| `STANDARD_2XL` | 8 | 32GB | Heavy workloads |
| `STANDARD_4XL` | 16 | 64GB | Enterprise workloads |
| `STANDARD_8XL` | 32 | 128GB | Large scale |
| `STANDARD_12XL` | 48 | 192GB | Very large scale |
| `STANDARD_24XL` | 96 | 384GB | Maximum scale |

⚠️ `STANDARD_M` is **not available on Azure**

### Memory Optimized (High Memory)

| Family | Cores | Memory | Use Case |
|--------|-------|--------|----------|
| `HIGHMEM_L` | 2 | 16GB | Memory-intensive small |
| `HIGHMEM_XL` | 4 | 32GB | Memory-intensive medium |
| `HIGHMEM_2XL` | 8 | 64GB | Memory-intensive large |
| `HIGHMEM_4XL` | 16 | 128GB | Memory-intensive xlarge |
| `HIGHMEM_8XL` | 32 | 256GB | Memory-intensive 2xlarge |
| `HIGHMEM_12XL` | 48 | 384GB | Memory-intensive 3xlarge |
| `HIGHMEM_16XL` | 64 | 512GB | Memory-intensive 4xlarge |
| `HIGHMEM_24XL` | 96 | 768GB | Memory-intensive 6xlarge |
| `HIGHMEM_32XL` | 128 | 1TB | Memory-intensive max |
| `HIGHMEM_48XL` | 192 | 1.5TB | Memory-intensive ultra |

### NOT Supported

- `STANDARD_XS` - Does not exist
- `STANDARD_S` - Does not exist

### Burstable (Dev/Test only)

⚠️ **Limitations:**
- Max 100GB storage
- No High Availability support
- This type should be requested specifically by the user
- Burstable CPU (not guaranteed)

| Family | Cores | Memory | Use Case |
|--------|-------|--------|----------|
| `BURST_XS` | 2 | 1GB | Minimal testing |
| `BURST_S` | 2 | 2GB | Light development |
| `BURST_M` | 2 | 4GB | Development |

## Storage

| Parameter | Min | Max | Default |
|-----------|-----|-----|---------|
| `STORAGE_SIZE_GB` | 10 | 65535 | 10 |

- Storage can be increased or decreased
- Decrease limited to 1.4x current disk usage

**Burstable instances:** Max 100GB storage

## Postgres Versions

| Version | Status |
|---------|--------|
| 16 | Supported |
| 17 | Supported |
| 18 | Supported (latest) |

Default version is the latest (currently 18).

## High Availability

High availability maintains a live standby replica for automatic failover.

| Setting | Value |
|---------|-------|
| Parameter | `HIGH_AVAILABILITY = TRUE` |
| Default | Off (single instance) |
| Failover | Automatic on primary failure |
| Connection | Same connection string, automatic redirect |

**Restrictions:**
- ❌ Not available for Burstable instances (BURST_XS, BURST_S, BURST_M)
- ✅ Available for Standard and HighMem instances

**When to enable:**
- Production workloads requiring uptime guarantees
- Applications that cannot tolerate instance restarts

**When to skip:**
- Development/test environments
- Cost-sensitive non-critical workloads
- Burstable instances (not supported)

## Authentication

| Value | Description |
|-------|-------------|
| `POSTGRES` | Native Postgres password authentication (default) |
| `POSTGRES_OR_SNOWFLAKE` | Postgres passwords + Snowflake short-lived access tokens |

Use `POSTGRES_OR_SNOWFLAKE` when you need Snowflake token-based authentication in addition to passwords.
See [Snowflake Token Authentication for Snowflake Postgres](https://docs.snowflake.com/en/user-guide/snowflake-postgres/snowflake-token-auth) for details.

## SQL Command Reference

### Instance Management

| Action | Command |
|--------|---------|
| List instances | `SHOW POSTGRES INSTANCES;` |
| Describe | `DESCRIBE POSTGRES INSTANCE <name>;` |
| Create | `CREATE POSTGRES INSTANCE <name> ...` |
| Fork | `CREATE POSTGRES INSTANCE <name> FORK <source> [AT/BEFORE (...)]` |
| Suspend | `ALTER POSTGRES INSTANCE <name> SUSPEND;` |
| Resume | `ALTER POSTGRES INSTANCE <name> RESUME;` |
| Rename | `ALTER POSTGRES INSTANCE <name> RENAME <new_name>;` |
| Reset credentials | `ALTER POSTGRES INSTANCE <name> RESET ACCESS FOR { 'snowflake_admin' \| 'application' };` |
| Restart Postgres | `ALTER POSTGRES INSTANCE <name> RESTART POSTGRES;` |
| Restart server | `ALTER POSTGRES INSTANCE <name> RESTART SERVER;` |
| Drop | `DROP POSTGRES INSTANCE <name>;` |

### ALTER SET Parameters

```sql
ALTER POSTGRES INSTANCE <name> SET
  [ NETWORK_POLICY = '<policy>' ]
  [ AUTHENTICATION_AUTHORITY = { POSTGRES | POSTGRES_OR_SNOWFLAKE } ]
  [ COMMENT = '<text>' ]
  [ HIGH_AVAILABILITY = { TRUE | FALSE } ]
  [ COMPUTE_FAMILY = '<family>' ]
  [ STORAGE_SIZE_GB = <number> ]
  [ STORAGE_INTEGRATION = '<integration>' ]
  [ POSTGRES_VERSION = { 16 | 17 | 18 } ]
  [ MAINTENANCE_WINDOW_START = <hour_utc> ]
  [ POSTGRES_SETTINGS = '<json>' ]
  [ APPLY { IMMEDIATELY | ON '<timestamp>' } ];
```

- `APPLY IMMEDIATELY` overrides any maintenance window — applies changes as soon as ready
- `APPLY ON '<timestamp>'` schedules application up to 72 hours in the future
- Without `APPLY`, changes apply at the next maintenance window (or immediately if none is set)

### ALTER UNSET Parameters

```sql
ALTER POSTGRES INSTANCE <name>
  UNSET { COMMENT | POSTGRES_SETTINGS | NETWORK_POLICY
    | MAINTENANCE_WINDOW_START | STORAGE_INTEGRATION } [ , ... ];
```

### Tagging

```sql
-- Set tags
ALTER POSTGRES INSTANCE <name> SET TAG cost_center = 'engineering', team = 'platform';
-- Unset tags
ALTER POSTGRES INSTANCE <name> UNSET TAG cost_center, team;
```

Tags can also be set at CREATE time: `[WITH] TAG (tag_name = 'value' [, ...])`.

### Forking (Point-in-Time Recovery)

Creates a full independent copy of an instance, optionally at a specific point in time.

```sql
-- Fork at current state
CREATE POSTGRES INSTANCE my_fork FORK my_source;

-- Fork at a specific timestamp
CREATE POSTGRES INSTANCE my_fork FORK my_source
  AT (TIMESTAMP => '2026-01-15 12:00:00'::TIMESTAMP_NTZ);

-- Fork from N seconds ago
CREATE POSTGRES INSTANCE my_fork FORK my_source
  AT (OFFSET => -7200);

-- Fork with different sizing
CREATE POSTGRES INSTANCE my_fork FORK my_source
  COMPUTE_FAMILY = 'STANDARD_L'
  STORAGE_SIZE_GB = 500
  HIGH_AVAILABILITY = FALSE;
```

Fork inherits all schema objects and data. COMPUTE_FAMILY, STORAGE_SIZE_GB, HIGH_AVAILABILITY, POSTGRES_SETTINGS, COMMENT, and TAG can be overridden on the fork.

### ⚠️ Syntax Notes

- **`RENAME`**: Uses `RENAME <new_name>` (no `TO` keyword). Hostname does not change.
- **`RESET ACCESS`**: Uses `ALTER POSTGRES INSTANCE` (not `ALTER POSTGRES SERVICE`).
- **`POSTGRES_SETTINGS` JSON**: Use standard JSON colon syntax (`"key": "value"`), not `=`. The docs show `=` in some places but the server requires `:`.
- **`RESTART`**: Two options — `RESTART POSTGRES` (faster, service only) or `RESTART SERVER` (full VM restart). In-place, no failover.

### Network Rules

Network policy can be set at creation time or attached afterward.

**Option 1: Set at creation (if policy exists)**
```sql
CREATE POSTGRES INSTANCE my_instance
  COMPUTE_FAMILY = 'STANDARD_M'
  STORAGE_SIZE_GB = 10
  AUTHENTICATION_AUTHORITY = POSTGRES
  NETWORK_POLICY = 'existing_policy';
```

**Option 2: Create and attach afterward**
```sql
-- Create ingress rule (allow incoming)
CREATE NETWORK RULE my_ingress
  TYPE = IPV4
  VALUE_LIST = ('1.2.3.4/32')
  MODE = POSTGRES_INGRESS;

-- Create policy with rules
CREATE NETWORK POLICY my_policy
  ALLOWED_NETWORK_RULE_LIST = ('my_ingress');

-- Attach to instance
ALTER POSTGRES INSTANCE my_instance SET NETWORK_POLICY = 'my_policy';
```

**List existing policies:**
```sql
SHOW NETWORK POLICIES;
```

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| "Missing option(s): [AUTHENTICATION_AUTHORITY]" | Required param missing | Add `AUTHENTICATION_AUTHORITY = POSTGRES` |
| "invalid property 'STORAGE_SIZE'" | Wrong parameter name | Use `STORAGE_SIZE_GB` (with `_GB` suffix) |
| "must contain at least one...POSTGRES_INGRESS" | Wrong network policy type | Use Network RULE with `MODE = POSTGRES_INGRESS` |
| "Compute Family X is not supported" | Invalid compute size | Use valid family from tables above |
| "Storage size must be at least 10 GB" | Storage too small | Set STORAGE_SIZE_GB >= 10 |
| "Instance name already exists" | Duplicate name | Choose a different name |
| "High availability not supported" | HA on Burstable instance | Use Standard or HighMem for HA |
| "Network policy does not exist" | Invalid policy name | Create policy first or check spelling |
| "Postgres version X not supported" | Invalid version | Run `SHOW POSTGRES VERSIONS;` for valid options |
| "Invalid JSON format in settings string" | Wrong separator in POSTGRES_SETTINGS | Use `:` not `=` — e.g. `'{"postgres:work_mem": "128MB"}'` |
