# Classification Rules

Rules for assigning dbt models to one of four conversion buckets when migrating to Snowflake Dynamic Tables.

---

## The Four Buckets

| Bucket | Meaning |
|--------|---------|
| `SKIP` | DT creation would fail — DDL blocker present |
| `FULL_BY_SQL` | Convertible to DT but must use `refresh_mode='full'` — contains operator(s) that cannot run incrementally |
| `INCREMENTAL_CANDIDATE` | Eligible for `refresh_mode='adaptive'` — ALL operators confirmed ✅ |
| `FULL_AS_DEFAULT` | Pattern not clearly covered — default to FULL for safety |

---

## Operator Reference

The single source of truth for which operators support incremental refresh is:

**`../../references/incremental-operators.md`**

Load that file and use it as the lookup table for classification. Do NOT classify from memory — match against the reference.

---

## Bucket Assignment Algorithm

For each model, extract ALL SQL operators used in the query. Then evaluate in this order (first match wins):

### Step 1 — SKIP check

Does the query use any construct that makes DT conversion impossible or semantically wrong?

**DDL blockers (creation fails regardless of refresh mode):**
- `WITH RECURSIVE`
- `UNPIVOT`
- `SAMPLE`

**Semantic blockers (DT technically creates as FULL but output is non-reproducible):**
- `UUID_STRING()` in SELECT projection — generates new values on every refresh, breaks downstream joins
- `RANDOM()` in SELECT projection — same issue: non-reproducible output

Note: Semantic blockers CAN create as FULL DTs, but produce different data each refresh. Keep as table.

If YES → `bucket = "SKIP"`. Stop.

### Step 2 — Operator extraction and matching

**Extract every operator** from the model SQL. This includes:
- Join types and their predicates (equi vs non-equi)
- Set operations (UNION ALL vs UNION DISTINCT vs EXCEPT/INTERSECT)
- Aggregate functions (including what's inside: `COUNT(DISTINCT x)` is different from `COUNT(x)`)
- Window functions (ROW_NUMBER, RANK, LEAD, LAG)
- Table functions (LATERAL FLATTEN vs other LATERAL)
- Top-level DISTINCT
- Subquery patterns (scalar vs correlated vs in-WHERE)
- Non-deterministic functions and where they appear (SELECT vs WHERE)

**Match EACH extracted operator** against `incremental-operators.md`:
- ✅ = confirmed incremental support
- ⚠️ = partial/conditional support
- ❌ = requires full refresh

### Step 3 — Classify

```
IF any operator matched ❌ → FULL_BY_SQL (reason: <the specific operator>)
IF any operator matched ⚠️ → FULL_BY_SQL (reason: <operator> has partial support — defaulting to FULL)
IF ALL operators matched ✅ → INCREMENTAL_CANDIDATE
IF any operator NOT FOUND in reference → FULL_AS_DEFAULT (reason: <operator> not in reference)
```

**Key rule: ⚠️ is treated as FULL.** Partial support means the runtime may silently downgrade to FULL. We classify conservatively upfront rather than discovering the downgrade at validation time.

**Always record:**
- The complete list of operators extracted
- Which operator triggered the classification
- The specific reason string

---

## Inferred Primary Key Detection

During classification, note primary keys for each model. These feed into downstream pipeline shape resolution (primary key-based change tracking).

### GROUP BY Columns

`GROUP BY col1, col2` (basic columns only) — the GROUP BY columns form a derived PK.

**Not valid as PKs:**
- `GROUP BY ROLLUP(...)`
- `GROUP BY CUBE(...)`
- `GROUP BY GROUPING SETS(...)`

These inject subtotal rows with NULL grouping columns, breaking uniqueness.

### QUALIFY ROW_NUMBER PARTITION BY Columns

```sql
QUALIFY ROW_NUMBER() OVER (PARTITION BY pk_col ORDER BY ...) = 1
```

The PARTITION BY column(s) form a derived PK.

### Base-Table PRIMARY KEY RELY

If the model is a passthrough from a base table with `PRIMARY KEY ... RELY`, the PK propagates. Verify via:
```sql
DESCRIBE TABLE <source>;
-- or
SHOW PRIMARY KEYS IN TABLE <source>;
```

### PK Significance

If ALL FULL-classified upstreams have PKs, a downstream may still support INCREMENTAL via primary key-based change tracking.

---

## Constants

### Never Use AUTO

Always set an explicit `refresh_mode` — either `'adaptive'` or `'full'`. Never use `refresh_mode='auto'`.

### Unsure Means FULL

When uncertain whether a pattern supports incremental refresh, classify as FULL_AS_DEFAULT. Correctness over optimization.
