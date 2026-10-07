# Adding `PRIMARY KEY ... RELY` — shared procedure

Used by any handler that proposes adding a `PRIMARY KEY ... RELY` constraint, whether on a base table (e.g. `HIGH_BASE_TABLE_CHANGES`) or on a dynamic table itself (e.g. `EXPENSIVE_ORDER_DEPENDENT_WINDOW_FUNCTION`).

## Why uniqueness verification is mandatory

`RELY` tells Snowflake's optimizer to **trust** the primary-key constraint **without enforcing it**. If duplicates exist, the dynamic table will produce **incorrect results or fail to refresh** — silently, without an error. Snowflake will not catch a bad key at write time; the damage only becomes apparent as wrong query results or a broken refresh.

Uniqueness must therefore be **verified against the data before the key is created** — do not accept the customer's word alone.

## Step 1 — gather the PK columns from the customer

**The customer must provide the primary-key column(s) — stop and ask; never guess them.** Ask which column(s) they believe uniquely identify a row in `<table>`. Gather these *before* running the uniqueness check.

## Step 2 — request permission and run the pre-check

**Ask the customer's permission before running the check** — unless they've already given it. The query scans `<table>`; on a very large table that has a real cost. When asking, **emphasize that verifying uniqueness is critical**, precisely because Snowflake will not catch a bad key.

- **Interactive mode:** run after they agree to the check specifically, **or** if their original request already named this exact fix — the table, the key column(s), and something like "apply the best fix" — with a blanket approval covering it. The check is an inseparable step of doing what was already asked for and approved, not a separate action that needs its own round-trip; don't manufacture an extra stop over a check that's required to deliver the very fix the customer described and approved. A genuinely generic approval unrelated to this diagnosis still doesn't satisfy this — see the *generic blanket approval* rule in [recommendation-codes.md](recommendation-codes.md).
- **Headless / pre-approved mode:** run automatically (it is read-only), and only create the key if it passes.

```sql
-- Uniqueness pre-check for the proposed key (<pk_cols>) on <DB>.<SCHEMA>.<table>.
-- Any returned row is a duplicate key ⇒ the key is NOT unique and MUST NOT be used with RELY.
SELECT <pk_cols>, COUNT(*) AS n
FROM <DB>.<SCHEMA>.<table>
GROUP BY <pk_cols>
HAVING COUNT(*) > 1
ORDER BY n DESC
LIMIT 20;
-- Also confirm no NULLs in the key columns (a PK must be non-null):
SELECT COUNT(*) AS null_key_rows
FROM <DB>.<SCHEMA>.<table>
WHERE <pk_col_1> IS NULL /* OR <pk_col_2> IS NULL ... */;
```

## Step 3 — act on the result

- **Pass** (first query returns zero rows AND `null_key_rows = 0`): proceed to add the `PRIMARY KEY ... RELY` constraint per the calling handler's instructions.
- **Fail** (duplicates or NULL keys found): **do NOT create the key.** Surface the offending values (the sample rows from the first query) to the customer and stop. Ask for a corrected key (e.g. additional columns that make it unique), or steer to an alternative remediation. Applying `RELY` on a non-unique key would corrupt the DT.
- **Customer declines the check**: require their explicit attestation that the key is unique and non-null, and repeat the warning — but strongly recommend running the check, since the cost of a wrong key (silent incorrect results) far outweighs the scan cost.
