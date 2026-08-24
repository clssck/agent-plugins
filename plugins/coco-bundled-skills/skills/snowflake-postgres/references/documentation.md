# Snowflake Postgres Documentation

Official documentation for Snowflake Postgres (managed PostgreSQL on Snowflake).

## Base URL

```
https://docs.snowflake.com/en/user-guide/snowflake-postgres/
```

All pages below are relative to this base. If a specific link breaks, navigate from the base URL.

## Core Documentation

| Topic | Path | Use When |
|-------|------|----------|
| Overview | `about` | Understanding architecture, regional availability, when to use Postgres |
| Create Instance | `postgres-create-instance` | CREATE syntax, required parameters, compute families |
| Manage Instances | `managing-instances` | ALTER, suspend, resume, fork, modify, credentials, maintenance |
| Networking | `postgres-network` | Network policies, firewall rules, Private Link, POSTGRES_INGRESS mode |
| Connecting | `connecting-to-snowflakepg` | Connection strings, clients, PgBouncer, SSL |

## Quick Reference

### Finding SQL Syntax

For any SQL command not covered in this skill:
1. Check `managing-instances` for ALTER operations
2. Check `postgres-create-instance` for CREATE parameters
3. Check `postgres-network` for network rule/policy syntax

### Common Lookups

| Question | Where to Look |
|----------|---------------|
| Valid compute families | `postgres-create-instance` |
| Storage limits | `postgres-create-instance` |
| Network policy setup | `postgres-network` |
| Connection pooling | `connecting-to-snowflakepg` |
| Major version upgrades | `managing-instances` |
| High availability | `managing-instances` |
| Maintenance windows | `managing-instances` |
| Point-in-time recovery | `managing-instances` (fork section) |

## How to Use

When a user asks about a command or feature not in this skill:

```bash
# Option 1: Fetch the specific doc page
web_fetch("https://docs.snowflake.com/en/user-guide/snowflake-postgres/<page>")

# Option 2: Search if unsure which page
web_search("site:docs.snowflake.com snowflake-postgres <topic>")
```

## Related (Not Snowflake Postgres)

Note: The "Snowflake Connector for PostgreSQL" is a different product (CDC replication from external Postgres into Snowflake). Its docs are at `/connectors/postgres6/` - do not confuse with Snowflake Postgres.
