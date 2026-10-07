# Error Tables — Additional Reference

## Error Codes

These are the runtime data error codes that Error Tables captures. Use in all queries.

| Code | Error Type |
|------|-----------|
| 100072 | NOT NULL violation |
| 100078 | String truncation |
| 100046 | Numeric overflow |
| 100038 | Numeric not recognized |
| 100035 | Type mismatch |
| 100040 | Invalid date/time |
| 100051 | Division by zero |
| 100069 | Unsupported conversion |
| 100320 | CHECK constraint violation |

**CHECK constraint notes (error code 100320):**
- `ERROR_METADATA:error_source` is **NULL** (not tied to a single column — constraints can span multiple columns)
- `ERROR_METADATA:error_message` contains the **constraint name and the full CHECK expression** — use this for diagnostics
- `ERROR_DATA` values are **not array-wrapped** (no `[]` brackets, unlike other error types)
- When a row violates multiple CHECK constraints, only the **first** violation is captured
- Requires Snowflake version 10.12+

## Performance overhead

- **Happy path (no errors):** Minimal overhead — slightly more memory during statement execution, no additional I/O.
- **Error path:** Proportional to the number of bad rows (serialized to JSON, written to error table). Negligible for a small error rate in a large batch.
- **Billing:** Data scanned is billed the same whether it lands in the target table or the error table. No extra warehouse cost. How error table storage appears in billing views is unconfirmed — do not claim inclusion/exclusion in `TABLE_STORAGE_METRICS`.
- **Main behavioral change:** Statements that previously failed and rolled back now **succeed with partial results**.

## Column evolution details

Adding, dropping, renaming, or modifying columns on the base table has **zero impact** on the error table structure. The error table always has the same 5 fixed columns (`TIMESTAMP`, `QUERY_ID`, `ERROR_CODE`, `ERROR_METADATA`, `ERROR_DATA`). Only the **contents** of `ERROR_DATA` and `ERROR_METADATA:error_source` are affected:

- **ADD COLUMN** → New errors include the new column in `ERROR_DATA`; absent from older rows
- **DROP COLUMN** → New errors omit it; old error rows retain it
- **RENAME** (e.g. `NAME` → `FULL_NAME`) → Error rows captured before the rename contain `ERROR_DATA:NAME` and `error_source = 'NAME'`; rows captured after contain `ERROR_DATA:FULL_NAME` and `error_source = 'FULL_NAME'`
- **MODIFY** → New errors reflect the change; old error rows are untouched

## Disabling and re-enabling error logging

`ALTER TABLE ... SET ERROR_LOGGING = FALSE` **drops the error table and all its data**. Re-enabling with `SET ERROR_LOGGING = TRUE` creates a fresh, empty error table. This is permanent, not a pause. To temporarily stop capturing errors without losing history, use `ALTER SESSION SET OPT_OUT_ERROR_LOGGING = TRUE` instead (the Session Opt-Out sub-skill).

## General notes

- All queries run against standard Snowflake views (`ACCOUNT_USAGE`, `INFORMATION_SCHEMA`, `ERROR_TABLE()`)
- Error tables are **nested objects under the base table** and are only exposed via `ERROR_TABLE(<base_table>)` (they are not standalone tables with their own DB/SCHEMA identity)
- ACCOUNT_USAGE views have up to 45-minute latency; ERROR_TABLE() is real-time
