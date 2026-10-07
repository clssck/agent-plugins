# On-Premises PostgreSQL — Source Platform Guide

Loaded by `source-platform-guide.md` when auto-detection does not match any cloud platform (i.e., self-managed PostgreSQL).

## Prerequisites

1. **Full configuration access** - edit `postgresql.conf`:
```
wal_level = logical
max_replication_slots = 10
max_wal_senders = 10
```

2. **Edit `pg_hba.conf`** for remote connections:
```
# Allow Snowflake Postgres to connect for replication
host    replication     repl_user    <snowflake_ip>/32    scram-sha-256
host    <database>      repl_user    <snowflake_ip>/32    scram-sha-256
```

3. **Restart PostgreSQL** after config changes

## On-Prem Specific Considerations

| Item | Notes |
|------|-------|
| **Network exposure** | Must expose PostgreSQL to internet or setup VPN |
| **Firewall/NAT** | Port 5432 must be accessible from Snowflake |
| **SSL certificates** | May need to configure for secure connection |
| **Static IP** | Snowflake needs stable IP to whitelist |
| **Bandwidth** | Internet bandwidth affects initial sync speed |
| **pg_hba.conf** | Often forgotten - causes connection failures |
| **listen_addresses** | Must be set to allow external connections |

## Network Options for On-Prem

1. **Direct Internet** (simplest)
   - Open port 5432, configure NAT
   - Use SSL/TLS for security
   - Whitelist Snowflake IPs only

2. **VPN Tunnel**
   - More secure
   - Requires VPN gateway on both ends
   - May need Snowflake support for setup

3. **SSH Tunnel** (for initial setup/testing)
   ```bash
   ssh -L 5432:<pg_host>:5432 <jump_host>
   ```

## On-Prem pg_dump Command

```bash
# Local dump
pg_dump \
  --host=localhost \
  --port=5432 \
  --username=postgres \
  --dbname=<database> \
  --format=custom \
  --file=dump.pgdump

# Then transfer to Snowflake-accessible location
```

## On-Prem SSL Configuration

```
# postgresql.conf
ssl = on
ssl_cert_file = '/path/to/server.crt'
ssl_key_file = '/path/to/server.key'

# pg_hba.conf - require SSL
hostssl    all    all    0.0.0.0/0    scram-sha-256
```

## Pre-Migration Checklist

- [ ] `postgresql.conf`: `wal_level = logical`
- [ ] `postgresql.conf`: `listen_addresses` includes external IP
- [ ] `pg_hba.conf`: allows Snowflake IP for replication
- [ ] PostgreSQL restarted
- [ ] Firewall/NAT configured for port 5432
- [ ] SSL configured (recommended)
- [ ] Static IP or DNS available for Snowflake connection
