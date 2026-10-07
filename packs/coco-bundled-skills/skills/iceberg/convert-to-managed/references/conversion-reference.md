# Conversion Reference

Lookup material for the `iceberg-convert-to-managed` skill: common error patterns, post-conversion next steps, and non-goals. Loaded on demand from the main workflow.

## Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `ALTER ICEBERG TABLE with CONVERT TO MANAGED is not supported in Catalog-Linked Databases` | Source database is a CLD | Step CV3 — CLDs are not supported; recreate the table outside the CLD or use CLD tooling |
| `Conversion of the unmanaged iceberg table with catalog vended credentials '<table>' to a managed iceberg table is currently unsupported` | Catalog integration uses `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` | Step CV4 — recreate the catalog integration with `EXTERNAL_VOLUME_CREDENTIALS` |
| `External volume <name> is not writable` | `ALLOW_WRITES = FALSE` on the volume | Step CV7 — `ALTER EXTERNAL VOLUME ... SET ALLOW_WRITES = TRUE` |
| `Access Denied` / `403 Forbidden` writing to storage | IAM role lacks PutObject/Delete permissions | Step CV8 — fix IAM policy/trust per provider; **Invoke** `iceberg-external-volume` |
| `Unsupported data type: uuid` / `fixed` | Source table uses an unconvertible Iceberg type | Step CV6 — recreate via CTAS without the unsupported type |
| `Refresh failed` / stale metadata (object-store unmanaged tables) | Metadata file inaccessible | Step CV5 — fix storage access; **Load** `../auto-refresh/SKILL.md` |
| `Insufficient privileges` | Role missing OWNERSHIP/MODIFY on the table | Grant `OWNERSHIP` or `MODIFY` on the Iceberg table |

## Next Steps

After successful conversion:
- **Test writes**:
  ```sql
  INSERT INTO <database>.<schema>.<table> VALUES (...);
  UPDATE <database>.<schema>.<table> SET ... WHERE ...;
  ```
- **Stop external writers** to the underlying storage path to prevent corruption.

## What Conversion Does NOT Do

- Does **not** rewrite Parquet data files at conversion time (rewrites may happen later during maintenance).
- Does **not** lock the storage location against non-Snowflake writers — that's the user's responsibility.
