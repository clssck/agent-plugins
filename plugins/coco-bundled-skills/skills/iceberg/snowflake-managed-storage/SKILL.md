---
name: iceberg-snowflake-managed-storage
description: "Create an Iceberg table using Snowflake-managed storage — the default, zero-setup path when a user asks to create an Iceberg table with no external catalog, external volume, or cloud-storage qualifier. Snowflake is the catalog and provides the storage (no external volume, no cloud bucket, no IAM setup). Sets CATALOG = 'SNOWFLAKE' and EXTERNAL_VOLUME = 'SNOWFLAKE_MANAGED' without asking about storage or catalog; asks the user for a table name when one wasn't provided. Triggers: create iceberg table, create an iceberg table, create a new iceberg table, make an iceberg table, set up an iceberg table, I need an iceberg table, create a snowflake-managed iceberg table, snowflake-managed iceberg, snowflake managed storage, internal storage iceberg, create iceberg table with columns, save this query as an iceberg table, load this data into an iceberg table, materialize as iceberg, create iceberg table as select, CTAS iceberg. Do NOT use when the request names Glue / Unity / Polaris / OpenCatalog / OneLake / Fabric / SAP / Delta Sharing / an external volume / S3 / Azure / GCS / S3Compat / 'my bucket' / 'my catalog' — route those via the parent iceberg skill instead."
---

# Create a Snowflake-Managed Iceberg Table

## When to Use

When the user asks to create an Iceberg table **without** naming an external catalog, external volume, or specific cloud storage (e.g. "create an Iceberg table", "make me an iceberg table called ORDERS with id and amount"), create it using **Snowflake-managed storage**. Snowflake is the catalog and Snowflake provides the storage — no external volume, no cloud bucket, no IAM setup.

The storage decision is made **for** the user (it is the default) — never ask about storage, catalog, location, or column types. The only content to ask for is a **table name and columns when the user didn't give them** (see Rule 7). Storage/catalog defaults are chosen silently, but the SQL is always presented and run through the standard execution approval (Rule 8) — it is never executed autonomously.

This is the highest-priority Iceberg path. The parent `iceberg/SKILL.md` routes a plain create request here **without** the standard routing-confirmation checkpoint (don't re-ask whether they want a table). It still presents the SQL and runs it through the normal execution approval, per the Rules below.

### Trigger (use this fast-path)

- "create an iceberg table", "create a new iceberg table", "make an iceberg table", "set up an iceberg table", "I need an iceberg table", with **no** mention of Glue / Unity / Polaris / OpenCatalog / OneLake / Fabric / SAP / Delta Sharing / an external volume / S3 / Azure / GCS / S3Compat / "my bucket" / "my catalog".
- **CTAS (Create Table As Select)**: "save this query as an iceberg table", "load this data into an iceberg table", "materialize as iceberg", "create iceberg table as select", "CTAS iceberg". Same managed-storage defaults apply — columns derive from the query so only a table name may need asking.

### Guard (do NOT use this fast-path — route via the parent iceberg skill's Intent Detection instead)

- The request names an external catalog (Glue, Unity, Polaris/OpenCatalog, OneLake/Fabric, SAP BDC, Delta Sharing) → **CATALOG_INTEGRATION**.
- The request names an external volume, S3/Azure/GCS/S3Compat, "my bucket", or "my storage" → **EXTERNAL_VOLUME**.
- The request is about auto-discovering/syncing existing tables from a catalog → **CATALOG_LINKED_DATABASE**.

## Rules

1. Always set `CATALOG = 'SNOWFLAKE'` and `EXTERNAL_VOLUME = 'SNOWFLAKE_MANAGED'` (reserved built-in values — Snowflake is the catalog and provides the storage).
2. ⚠️ Never add `BASE_LOCATION` — it is **incompatible with `SNOWFLAKE_MANAGED`** and causes a compilation error. (`BASE_LOCATION` is an *optional* clause used only with external-volume storage; don't carry it over here.) Snowflake manages file layout automatically.
3. Do not hunt for or create an external *volume* — never run `SHOW EXTERNAL VOLUMES`, pick an existing external volume, or `CREATE EXTERNAL VOLUME`. (Reading the schema's effective default with `SHOW PARAMETERS LIKE 'EXTERNAL_VOLUME'` per the check step below is fine and expected — that is not the same as choosing a volume.)
4. Default to `CREATE ICEBERG TABLE IF NOT EXISTS` so an existing same-named table is never silently dropped. Use `CREATE OR REPLACE` only when the user explicitly asks to replace or overwrite the table, and in that case state plainly that it drops the existing table and its data.
5. Do not ask about storage, catalog, or location — those are decided for the user (Snowflake-managed defaults). Do not use the question tool for them. **One exception:** if the target schema has a customer-managed external volume configured as its default (detected by the check step below), surface it and let the user choose rather than silently overriding it. The other prompts that *are* allowed when something is missing: the **table name**, the **columns**, and the **database** (all via Rule 7).
6. Use unconstrained types: `STRING` (not `VARCHAR(N)`/`CHAR(N)`/`STRING(N)`), `INT` (not `INTEGER(N)`), `NUMBER`/`DECIMAL` for numerics, and `BOOLEAN`/`DATE`/`TIMESTAMP`/`VARIANT` as needed.
7. Names and location — **do not invent a table name**:
   - **Table name**: if the user gave one, use it. If not, ask them what to name it (a single prompt; you may also ask for columns in the same prompt). Do not fabricate a name and create the table without their input.
   - **Columns**: if the user gave columns, use them. If not, ask what columns they want — fold this into the name prompt when the name is also missing. Do not fabricate columns the user didn't ask for.
   - **Database/schema**: if the user names one, use it; otherwise use the current database/schema in context. Only if no database is in context and the user named none, ask a single question — whether to use a specific database or have one provisioned. Never auto-create a database silently.
   - **Creating a database**: when a database is needed and none exists, create it **bare** — `CREATE DATABASE <name>;` with NO `EXTERNAL_VOLUME` clause. Iceberg tables inside it default to Snowflake-managed storage because the per-table `CATALOG='SNOWFLAKE'` + `EXTERNAL_VOLUME='SNOWFLAKE_MANAGED'` clauses carry the catalog and storage choice explicitly. A bare database does not pin children to any particular bucket; each table's explicit clauses determine storage. Offer the external-volume database path (`CREATE DATABASE <name> EXTERNAL_VOLUME = '<vol>';`) only if the user explicitly says they want files in their own cloud storage.
8. Approval (DDL execution): never execute SQL autonomously. Once you have a name, columns, and target, **present the exact SQL and run it through the standard execution approval** — the user approves the SQL before it runs. Choosing the defaults (storage, catalog, types) needs no approval; *executing* the DDL does. For `CREATE OR REPLACE`, the presented SQL must be accompanied by a plain statement that it drops the existing table and its data, so the user's approval is informed.
9. **Opt-in database default (safety net)**: when the user explicitly asks to make Snowflake-managed storage the default for an entire database ("don't make me specify storage every time", "make managed the default for the whole DB"), offer `ALTER DATABASE <db> SET CATALOG = 'SNOWFLAKE';` (the volume inherits as `SNOWFLAKE_MANAGED` when catalog is `SNOWFLAKE`). This is a convenience backstop — **keep writing explicit `CATALOG` + `EXTERNAL_VOLUME` clauses on every table anyway** (self-documenting, copy-paste-safe SQL). This path is **opt-in only** — never set it silently. Before offering it, run `SHOW PARAMETERS LIKE 'EXTERNAL_VOLUME' IN DATABASE <db>;` — if a customer-managed external volume is already the intentional configured default, do NOT override it; warn the user and respect their existing configuration. This ALTER mutates shared database state — mention that to the user so approval is informed.

## Execute

**First, check the target schema's effective default** (don't silently override an intentionally-configured one):

```sql
SHOW PARAMETERS LIKE 'EXTERNAL_VOLUME' IN SCHEMA <database>.<schema>;
SHOW PARAMETERS LIKE 'CATALOG' IN SCHEMA <database>.<schema>;
```

- `value` empty, `SNOWFLAKE_MANAGED`, or `SNOWFLAKE` → no conflicting default. Proceed silently with Snowflake-managed, pinning both values explicitly (below).
- `value` is a **customer-managed external volume** (or an external catalog integration) → an admin set that default on purpose (data residency, CMK/encryption, or cost). Surface it and let the user choose — create on that configured default, or use Snowflake-managed — instead of overriding it (Rule 5 exception). This is the only storage question you may ask.

Then compose and present the SQL:

```sql
-- Table name: use the user's name, or ask for one if they gave none (Rule 7).
-- Database/schema: use what the user named, or the current one in context.
-- If no database is in context and the user named none, confirm a database
-- name with the user first (Rule 7) — do not create a database silently.

CREATE ICEBERG TABLE IF NOT EXISTS <database>.<schema>.<table_name> (
    <columns — STRING/INT/NUMBER/DECIMAL/TIMESTAMP, no length constraints;
     use the columns the user gave, or the ones they provide when asked (Rule 7)>
)
  CATALOG = 'SNOWFLAKE'
  EXTERNAL_VOLUME = 'SNOWFLAKE_MANAGED';
-- Required form: CREATE ICEBERG TABLE IF NOT EXISTS (NOT CREATE OR REPLACE unless
-- the user explicitly asked to overwrite). Do NOT add a BASE_LOCATION clause.
```

**CTAS (Create Table As Select)** — when the user wants to materialize a query result as an Iceberg table:

```sql
CREATE ICEBERG TABLE IF NOT EXISTS <database>.<schema>.<table_name>
  CATALOG = 'SNOWFLAKE'
  EXTERNAL_VOLUME = 'SNOWFLAKE_MANAGED'
  AS SELECT <query>;
-- Storage clauses come BEFORE `AS SELECT` (params after AS SELECT is a syntax error).
-- Columns derive from the SELECT — do not specify a column list.
-- Do NOT add BASE_LOCATION.
```

The same rules apply: ask for a table name if not provided (Rule 7); columns come from the query (do not ask for them); present the SQL and run through execution approval (Rule 8).

**Get the storage clause right — this is the #1 mistake:**
- ❌ `... EXTERNAL_VOLUME = 'SNOWFLAKE_MANAGED' BASE_LOCATION = 'orders';` — FAILS to compile
- ✅ `... EXTERNAL_VOLUME = 'SNOWFLAKE_MANAGED';` — correct (no BASE_LOCATION)

**Before running, verify the statement** (the two most common mistakes are carried over from external-volume Iceberg):
- uses `IF NOT EXISTS` — not `CREATE OR REPLACE`, unless the user explicitly asked to overwrite an existing table (then warn it drops the table and its data);
- contains **no** `BASE_LOCATION` clause;
- sets `CATALOG = 'SNOWFLAKE'` and `EXTERNAL_VOLUME = 'SNOWFLAKE_MANAGED'`;
- uses unconstrained types (`STRING`, not `VARCHAR(N)`).

After creating it: confirm what you built, note that it uses Snowflake-managed storage (Snowflake stores and manages the files; no external volume required), and offer a quick `INSERT` + `SELECT` to validate.

## On failure

If creation fails (for example on GCP, government regions, or PRC, where Snowflake-managed storage is not available, or for Tri-Secret Secure accounts after the cutoff), **surface the exact error**, then offer the external-volume path: load `../external-volume/SKILL.md` to configure customer-managed storage.

---

> For extended detail — additional CREATE examples (with-columns, transient), the account→database→schema→table inheritance model, cloud/region support & Tri-Secret cutoff, permanent-vs-transient, post-create validation, and docs links — see `references/snowflake-managed-storage.md`.
