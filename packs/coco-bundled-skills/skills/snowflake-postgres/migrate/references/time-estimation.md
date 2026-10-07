# Time Estimation

## Duration by Database Size

| Size | pg_dump | pg_restore | Replication Sync | Downtime (dump) | Downtime (rep) |
|------|---------|------------|------------------|-----------------|----------------|
| 1 GB | ~5 min | ~3 min | ~10 min | ~15 min | <5 min |
| 10 GB | ~30 min | ~20 min | ~1 hour | ~1 hour | <5 min |
| 50 GB | ~2 hours | ~1.5 hours | ~4 hours | ~4 hours | <5 min |
| 100 GB | ~4 hours | ~3 hours | ~8 hours | ~8 hours | <5 min |
| 500 GB | ~20 hours | ~15 hours | ~2 days | ~1.5 days | <5 min |
| 1 TB | ~2 days | ~1.5 days | ~4 days | ~3-4 days | <5 min |

## Factors Affecting Speed

- Network bandwidth
- Disk I/O (SSD vs HDD)
- Parallelism (pg_dump -j N)
- Table structure
- Index count
- WAL generation rate

## Method Selection by Size

| Size | Method | Rationale |
|------|--------|-----------|
| < 10 GB | pg_dump | Simple, fast |
| 10-100 GB | Either | Depends on downtime tolerance |
| 100 GB - 1 TB | Replication | Near-zero downtime |
| > 1 TB | S3 Parquet + pg_lake | Minimize source load |
