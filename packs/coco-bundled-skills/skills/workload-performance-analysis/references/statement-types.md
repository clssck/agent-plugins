# Statement Type Reference

Reference for interpreting `query_type` values in `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`.

---

## Read This When

- Interpreting `query_type` values in query results
- User asks about statement types
- Categorizing child jobs of a stored procedure by statement type
- Building summary statistics by statement type

## Do NOT Read This When

- Initial parameter gathering (Phase 1 Step 1 in any sub-skill)
- User already has `query_type` from the query results
- Looking only at the parent procedure (always `CALL`)

---

## Query Type Values

The `query_type` column in `QUERY_HISTORY` contains human-readable strings — no JOIN is required.

### Common Query Types

| Query Type | Description |
|---|---|
| `SELECT` | Read query |
| `INSERT` | Insert rows |
| `UPDATE` | Update rows |
| `DELETE` | Delete rows |
| `MERGE` | Merge operation |
| `COPY` | COPY INTO operation |
| `CALL` | Stored procedure call |
| `UNKNOWN` | Unknown or failed statement |

### DDL Query Types

| Query Type | Description |
|---|---|
| `CREATE_TABLE` | Create table |
| `CREATE_TABLE_AS_SELECT` | CTAS operation |
| `ALTER_TABLE_MODIFY_COLUMN` | Alter table |
| `DROP_TABLE` | Drop table |
| `TRUNCATE_TABLE` | Truncate table |

### Other Query Types

| Query Type | Description |
|---|---|
| `SHOW` | Show command |
| `DESCRIBE` | Describe object |
| `USE` | Use database / schema / warehouse |
| `GRANT` | Grant privileges |
| `REVOKE` | Revoke privileges |
| `SET` | Set session parameter |
| `BEGIN_TRANSACTION` | Begin transaction |
| `COMMIT` | Commit transaction |
| `ROLLBACK` | Rollback transaction |

---

## Typical Child Job Patterns (Stored Procedures)

| Procedure Type | Expected Child Statements |
|---|---|
| Data transformation | `SELECT`, `INSERT`, `UPDATE`, `MERGE` |
| Data loading | `COPY`, `INSERT` |
| Maintenance | `TRUNCATE_TABLE`, `DELETE`, `INSERT` |
| Orchestration | `CALL` (nested procedures) |
| Validation | `SELECT` only |

---

## Notes

- `query_type` is `UNKNOWN` if the query failed before its type could be determined.
- Nested `CALL` statements indicate the procedure calls other procedures — the stored-procedure analysis displays nested CALLs in the call tree (depth derived from interval containment; tree result hard-capped at LIMIT 500 by `start_time`).
- `BEGIN_TRANSACTION` / `COMMIT` / `ROLLBACK` appear as separate child entries inside a procedure that uses explicit transactions.
