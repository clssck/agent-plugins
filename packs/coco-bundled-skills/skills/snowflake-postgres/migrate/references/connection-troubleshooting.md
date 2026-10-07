# Connection Troubleshooting

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Connection refused` | Wrong host/port | Verify env file |
| `password authentication failed` | Wrong password | Check .pgpass or *_PGPASSWORD |
| `database does not exist` | Wrong database name | Check *_PGDATABASE |
| `timeout expired` | Firewall/network | Check connectivity |
| `SSL connection is required` | Server requires SSL | Set *_PGSSLMODE="require" |

## Authentication Methods

### Password (.pgpass recommended)
```bash
echo "host:port:db:user:password" >> ~/.pgpass
chmod 600 ~/.pgpass
```

### Certificate
```bash
export SOURCE_AUTH_METHOD="certificate"
export SOURCE_PGSSLCERT="/path/to/client.crt"
export SOURCE_PGSSLKEY="/path/to/client.key"
```

### Kerberos
```bash
export SOURCE_AUTH_METHOD="kerberos"
kinit username@REALM
```

### IAM (AWS)
```bash
export SOURCE_AUTH_METHOD="iam"
export AWS_REGION="us-east-1"
```

## Snowflake Postgres Limitations

Known limitations that affect migration workflows:

### pg_subscription Access May Be Restricted

Some Snowflake Postgres targets reject direct reads from `pg_subscription`. When that happens, you cannot query subscription status directly:

```sql
-- This will FAIL on Snowflake Postgres:
SELECT * FROM pg_subscription;
-- ERROR: permission denied for table pg_subscription
```

**Portable workaround:** Monitor replication from the **source** side instead:
```sql
-- On SOURCE: check replication slots and lag
SELECT slot_name, active,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)) AS lag
FROM pg_replication_slots WHERE slot_type = 'logical';

-- On SOURCE: check active WAL senders
SELECT pid, application_name, state, sent_lsn, write_lsn, flush_lsn, replay_lsn
FROM pg_stat_replication;
```

On the **target**, use `pg_subscription_rel` (portable) to check per-table sync state:
```sql
SELECT srrelid::regclass, srsubstate FROM pg_subscription_rel;
-- States: i=initializing, d=data copying, s=synchronized, r=ready
```

If your target also exposes `pg_subscription`, you can use it as an additional verification query after cleanup:
```sql
-- Optional verification on TARGET (only if pg_subscription is readable)
SELECT subname
FROM pg_subscription
WHERE subname IN ('migration_sub', 'migrate_from_source', 'reverse_sub');
-- Expect 0 rows after cleanup (or filter on your custom subscription names)
```

After post-cutover cleanup, verify from the **source** side too:
```sql
-- Publication removed
SELECT pubname
FROM pg_publication
WHERE pubname = 'snowflake_migration';

-- Replication slots removed
SELECT slot_name
FROM pg_replication_slots
WHERE slot_name IN ('migration_sub', 'migrate_from_source', 'reverse_sub');
-- Expect 0 rows after cleanup (or filter on your custom slot names)
```

### Multi-IP Egress Rules

Some source hosts resolve to multiple IP addresses (e.g., RDS Multi-AZ, load-balanced endpoints). Snowflake Postgres network rules must include **all** resolved IPs:

```bash
# Check all IPs for the source host
dig +short $SOURCE_PGHOST
# Example output:
# 10.0.1.50
# 10.0.2.51
```

If multiple IPs are returned, add all of them to the egress rule:
```sql
CREATE OR REPLACE NETWORK RULE <db>.<schema>.migration_egress_rule
    TYPE = IPV4
    VALUE_LIST = ('10.0.1.50/32', '10.0.2.51/32')
    MODE = POSTGRES_EGRESS;
```

**Tip:** After DNS changes or RDS failovers, the IP may change. Re-resolve and update the network rule if replication breaks with "could not connect to publisher".

### Unsupported Extensions

Some PostgreSQL extensions are not available in Snowflake Postgres. Common ones that affect migration:

| Extension | Status | Workaround |
|-----------|--------|------------|
| `pg_trgm` | Not available | Use `LIKE` or application-level fuzzy matching |
| `pg_stat_statements` | Not available | Use Snowflake query history instead |
| `pgcrypto` | Available | Works as expected |
| `postgres_fdw` | Available | Used for connectivity testing |
| `uuid-ossp` | Available | Works as expected |

Run `SELECT * FROM pg_available_extensions` on the target to verify before migrating schema DDL.
