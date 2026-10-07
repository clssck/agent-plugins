# Validation Playbook

Reference for validation workers. Contains the detailed knowledge for each validation category.

---

## Category 1: Refresh Mode Validation

### refresh_mode confirmation

```sql
SHOW DYNAMIC TABLES LIKE '<model>' IN SCHEMA <test_db>.<test_schema>;
```

Read from result: `refresh_mode`, `refresh_mode_reason`, `scheduling_state`.

**refresh_mode_reason values:**

| Value | Reaction |
|-------|----------|
| NULL / None | Continue (clean) |
| QUERY_NOT_SUPPORTED_FOR_INCREMENTAL | Escalate (silent downgrade) |
| USER_SPECIFIED_FULL_REFRESH | Log (intentional) |
| UPSTREAM_USES_FULL_REFRESH | Escalate (cascade signal) |
| CHANGE_TRACKING_NOT_ENABLED | Escalate (actionable fix) |
| NO_INCREMENTAL_MAINTENANCE_SUPPORT | Escalate (internal limitation) |
| Descriptive string (regex: `Unsupported.*:.*`) | Escalate (catch-all) |
| Any unknown non-NULL value | Log + warn (future-proof) |

### NO_DATA second refresh (INCREMENTAL only)

```sql
ALTER DYNAMIC TABLE <test_db>.<test_schema>.<model> REFRESH;

SELECT refresh_action
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
  NAME => '<test_db>.<test_schema>.<model>'
))
ORDER BY refresh_start_time DESC
LIMIT 1;
```

| Result | Verdict |
|--------|---------|
| `NO_DATA` | Pass — no upstream changes, skipped recomputation |
| `INCREMENTAL` | Acceptable — source genuinely changed. Record; passes. |
| `FULL` | Fail — INC failed at runtime. Escalate. |

---

## Category 2: Data Equivalence

Checks (in order):

### 2.1 Row Count Parity

```sql
SELECT COUNT(*) FROM <test_db>.<test_schema>.<model>;
```

Compare against `baseline.row_count`. Match must be **exact** (integer equality).

### 2.2 Sum-on-Numeric Parity

For each numeric column, compare `SUM(<col>)` between DT and baseline.

| Type | Tolerance | Check |
|------|-----------|-------|
| INT / BIGINT | exact (0) | `sum_new == sum_baseline` |
| DECIMAL / NUMBER(p,s) | exact (0) | `sum_new == sum_baseline` |
| FLOAT / DOUBLE | relative 1e-9 | `abs(new - base) / greatest(abs(base), 1e-9) < 1e-9` |

**Guards:**
- Denominator: `GREATEST(ABS(baseline), 1e-9)` prevents division-by-zero
- Both-near-zero: if both < 1e-9 absolute, pass unconditionally

**SQL template (FLOAT):**

```sql
SELECT
  CASE
    WHEN ABS(sum_baseline) < 1e-9 AND ABS(sum_new) < 1e-9 THEN TRUE
    WHEN ABS(sum_new - sum_baseline) / GREATEST(ABS(sum_baseline), 1e-9) < 1e-9 THEN TRUE
    ELSE FALSE
  END AS parity_passes
FROM (
  SELECT
    (SELECT SUM(<col>) FROM <baseline_table>) AS sum_baseline,
    (SELECT SUM(<col>) FROM <test_db>.<test_schema>.<model>) AS sum_new
);
```

### 2.3 HASH_AGG Full Equivalence

```sql
SELECT
  (SELECT COUNT(*) FROM <baseline_table>) AS base_count,
  (SELECT COUNT(*) FROM <test_db>.<test_schema>.<model>) AS dt_count,
  (SELECT HASH_AGG(*) FROM <baseline_table>) AS base_hash,
  (SELECT HASH_AGG(*) FROM <test_db>.<test_schema>.<model>) AS dt_hash;
```

**Classification (4 outcomes):**

| Result | Classification | Action |
|--------|---------------|--------|
| count match AND hash match | `MATCH` | Pass. |
| hash differs, confirmed by filtered re-hash on date column | `TIMELINE_DRIFT` | Pass. |
| hash differs, core fact columns match (enrichment cols drift) | `SOURCE_DATA_DRIFT` | Pass. |
| anything else | `INVESTIGATE` | Record hypothesis + confirming query. Do NOT block. |

**TIMELINE_DRIFT confirmation:** Re-hash with date cutoff:
```sql
SELECT HASH_AGG(*) FROM <baseline> WHERE <date_col> <= '<cutoff>';
SELECT HASH_AGG(*) FROM <dt> WHERE <date_col> <= '<cutoff>';
```

**SOURCE_DATA_DRIFT confirmation:** Hash only core fact columns:
```sql
SELECT HASH_AGG(<core_col_1>, <core_col_2>, ...) FROM <baseline>;
SELECT HASH_AGG(<core_col_1>, <core_col_2>, ...) FROM <dt>;
```

**INVESTIGATE:** Record best hypothesis + confirming SQL. Do NOT block.

**Key rule:** Data equivalence results are informational — they do NOT block the batch.

---

## Category 3: dbt Tests

```bash
dbt test --select <model> --target <test_target>
```

Pass: all declared tests pass. Fail: any test fails → `status = "FAILED"`. Do NOT auto-retry — dbt tests are user-defined contracts.

---

## Category 4: Downstream Chain Check

For models with downstream DT consumers:

```sql
ALTER DYNAMIC TABLE <test_db>.<test_schema>.<upstream_dt> REFRESH;
ALTER DYNAMIC TABLE <test_db>.<test_schema>.<downstream_dt> REFRESH;
```

Pass: downstream refresh succeeds. Fail: error 091941 or similar → escalate.

---

## Group A vs Group B Framing

### Group A — Internal Changes

Mechanical changes inherent to the table→DT conversion. No external coordination needed.

Examples: materialization swap, post_hook list-form, clustering migration.

### Group B — External-Constraint Workarounds

Changes forced by something outside the project. Requires coordination with source owners.

Examples: staging-table for external-source view, models forced to FULL by upstream non-deterministic functions, models staying as table due to sharded UNION ALL sources.

**Why it matters:** Group A sizes the PR diff. Group B sizes the coordination effort. The report separates them so stakeholders see both.
