# Snowflake-Managed Storage for Iceberg Tables

Detailed reference for the [snowflake-managed-storage subskill](../SKILL.md) fast-path. Snowflake storage is the **recommended** way to store data for Snowflake-managed Iceberg tables: Snowflake stores and manages the data and metadata files for you — no external volume, no cloud bucket, no IAM/trust-policy setup.

Use external volume storage **only** when the user must keep files in their own cloud storage or uses an external Iceberg catalog.

> The authoritative rules (CATALOG/EXTERNAL_VOLUME, no `BASE_LOCATION`, `IF NOT EXISTS` vs `CREATE OR REPLACE`, no volume hunting, approval, types) live in the sub-skill's **Rules** section (`../SKILL.md`). This doc is extended detail only — it does not restate them.

---

## Extended CREATE examples

**With columns:**
```sql
CREATE ICEBERG TABLE IF NOT EXISTS my_db.my_schema.orders (
    order_id      INT,
    customer_name STRING,
    amount        NUMBER(38, 2),
    order_ts      TIMESTAMP
)
  CATALOG = 'SNOWFLAKE'
  EXTERNAL_VOLUME = 'SNOWFLAKE_MANAGED';
```

**Transient (no Fail-safe; only supported with Snowflake storage):**
```sql
CREATE TRANSIENT ICEBERG TABLE IF NOT EXISTS my_db.my_schema.staging (
    col1 INT
)
  CATALOG = 'SNOWFLAKE'
  EXTERNAL_VOLUME = 'SNOWFLAKE_MANAGED';
```

---

## Defaults at account / database / schema level

When `CATALOG` and `EXTERNAL_VOLUME` are omitted, Snowflake resolves them from **schema > database > account** defaults. When the effective catalog is Snowflake (`CATALOG = 'SNOWFLAKE'`), the default external volume is `SNOWFLAKE_MANAGED` **unless** a different default volume is set at a lower level.

The fast-path writes both values **explicitly** for clarity and predictability — the generated SQL shows exactly what storage the table uses instead of relying on inherited defaults.

### Inheritance model (account → database → schema → table)

- A **bare database** (`CREATE DATABASE <name>;` with no `EXTERNAL_VOLUME`) is "neutral" — it does not pin children to any particular storage bucket. Iceberg tables created inside it still get Snowflake-managed storage because their per-table `CATALOG='SNOWFLAKE'` + `EXTERNAL_VOLUME='SNOWFLAKE_MANAGED'` clauses carry the catalog and storage choice explicitly.
- This means Scenario A (bare database) does **NOT** depend on the database having a catalog set. The table-level clauses are authoritative.
- Setting `CATALOG` / `EXTERNAL_VOLUME` on a database or schema is a **default for tables that omit those clauses** — it does not override tables that specify them explicitly.
- The fast-path always writes explicit per-table clauses regardless of what defaults exist at higher levels — this keeps the SQL self-documenting and copy-paste-safe.

### Opt-in database default (safety net)

When a user explicitly asks to make Snowflake-managed storage the default for an entire database (so they don't have to remember to specify it on every table), offer:

```sql
ALTER DATABASE <db> SET CATALOG = 'SNOWFLAKE';
-- Volume inherits as SNOWFLAKE_MANAGED when catalog is SNOWFLAKE.
```

See `../SKILL.md` Rule 9 for the guardrails on this path (opt-in only, never silent; still write explicit per-table clauses; check `SHOW PARAMETERS LIKE 'EXTERNAL_VOLUME' IN DATABASE <db>` first; it mutates shared DB state).

---

## Permanent vs. transient

- **Permanent (default)**: protected by Fail-safe (7-day recovery), like standard tables.
- **Transient**: no Fail-safe, no Fail-safe storage cost. Transient Iceberg tables are **only** supported with Snowflake storage (not with a customer-managed external volume). Check `kind` in `SHOW TABLES` (`TRANSIENT` vs `TABLE`).

---

## Cloud / region support and limitations

- **Available on AWS and Azure only.** Not available on GCP, government regions, or the People's Republic of China.
- **Encryption**: server-side encryption (SSE) only. Customer-managed keys (CMK) are not supported. Starting **May 26, 2026**, Tri-Secret Secure accounts may be blocked from creating these tables until enabled by Snowflake Support.
- **External engines via Horizon**: reads (and Iceberg v3 read/write via the Horizon Iceberg REST Catalog API) are supported for Snowflake-managed storage. Per-request storage fees apply when accessed through an external engine (not when accessed by the native Snowflake engine).

### Fallback if creation is unsupported

If `CREATE ICEBERG TABLE ... EXTERNAL_VOLUME = 'SNOWFLAKE_MANAGED'` fails (e.g., GCP/gov/PRC, or a Tri-Secret Secure account after the cutoff):

1. **Surface the exact error** to the user.
2. Offer the customer-managed path: load `../../external-volume/SKILL.md` to configure an external volume, then create the table with `EXTERNAL_VOLUME = '<volume_name>'` and `BASE_LOCATION = '<path>'`.

---

## CTAS (Create Table As Select)

See the CTAS template and rules in `../SKILL.md` ("Execute" → CTAS). Same managed-storage defaults; storage clauses go **before** `AS SELECT`; columns derive from the query.

---

## Post-create validation (offer to the user)

```sql
INSERT INTO my_db.my_schema.orders (order_id, customer_name, amount, order_ts)
  VALUES (1, 'Acme', 100.00, CURRENT_TIMESTAMP());

SELECT * FROM my_db.my_schema.orders LIMIT 10;
```

---

## Documentation

- [Storage for Apache Iceberg Tables (overview)](https://docs.snowflake.com/en/user-guide/tables-iceberg-storage)
- [Snowflake storage for Apache Iceberg Tables](https://docs.snowflake.com/en/user-guide/tables-iceberg-internal-storage)
- [CREATE ICEBERG TABLE (Snowflake as the Iceberg catalog)](https://docs.snowflake.com/en/sql-reference/sql/create-iceberg-table-snowflake)
- [Iceberg Data Types](https://docs.snowflake.com/en/user-guide/tables-iceberg-data-types)
