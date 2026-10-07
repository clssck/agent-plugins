# Platform-Specific Clone/Snapshot Reference

Cloud platforms don't support pausing WAL replay on replicas. Use clone or snapshot restore instead.

## AWS RDS/Aurora

AWS read replicas don't support pausing WAL replay. Use **clone or snapshot restore** instead.

### Option A: Aurora Clone (Fastest)

```bash
# Create Aurora clone (copy-on-write, very fast)
aws rds restore-db-cluster-to-point-in-time \
    --source-db-cluster-identifier <source-cluster> \
    --db-cluster-identifier <clone-cluster> \
    --restore-type copy-on-write \
    --use-latest-restorable-time
```

```sql
-- On SOURCE: Note the LSN at clone time
-- Run immediately after clone creation
SELECT pg_current_wal_lsn() AS clone_lsn;
```

### Option B: RDS Snapshot Restore

```bash
# Create snapshot
aws rds create-db-snapshot \
    --db-instance-identifier <source-instance> \
    --db-snapshot-identifier migration-snapshot

# Restore to new instance
aws rds restore-db-instance-from-db-snapshot \
    --db-instance-identifier <export-instance> \
    --db-snapshot-identifier migration-snapshot
```

```sql
-- Get LSN from snapshot metadata (approximate)
-- Or query the restored instance:
SELECT pg_current_wal_lsn() AS snapshot_lsn;
```

### AWS Workflow

1. Create publication on source (disabled)
2. Create replication slot on source
3. **Clone/restore database** - note the LSN
4. pg_dump from clone (not production)
5. pg_restore to Snowflake Postgres
6. Advance slot to clone LSN
7. Enable subscription
8. **Delete clone** when catch-up complete

## Azure Flexible Server

Azure also supports point-in-time restore for creating export snapshots:

```bash
# Create point-in-time restore via Azure CLI
az postgres flexible-server restore \
    --resource-group <rg> \
    --name <clone-server> \
    --source-server <source-server> \
    --restore-time "2026-02-12T10:00:00Z"
```

```sql
-- On SOURCE: Get LSN at restore point time
-- Query this BEFORE the restore point time passes
SELECT pg_current_wal_lsn() AS restore_point_lsn;

-- Or on restored clone (after it's available):
SELECT pg_current_wal_lsn();
```

### Azure Workflow

1. Create publication on source
2. Create replication slot on source  
3. **Point-in-time restore** to new server - note the LSN
4. pg_dump from restored server
5. pg_restore to Snowflake Postgres
6. Advance slot to restore point LSN
7. Enable subscription
8. **Delete restored server** when done

## Google Cloud SQL

```bash
# Clone instance
gcloud sql instances clone <source-instance> <clone-instance>
```

The clone LSN can be determined from the clone creation time or by querying the clone.

## On-Premises (Replica Pause)

On-prem has full control - can pause WAL replay on replica.

```sql
-- On REPLICA
SELECT pg_wal_replay_pause();
SELECT pg_last_wal_replay_lsn() AS snapshot_lsn;

-- After export complete
SELECT pg_wal_replay_resume();
```

## LSN Capture Summary

| Platform | LSN Capture Method |
|----------|-------------------|
| On-Premises | `pg_last_wal_replay_lsn()` after pausing replica |
| Aurora | `pg_current_wal_lsn()` immediately after clone creation |
| RDS | `pg_current_wal_lsn()` on restored snapshot instance |
| Azure | `pg_current_wal_lsn()` on restored server |
| GCP | `pg_current_wal_lsn()` on cloned instance |
