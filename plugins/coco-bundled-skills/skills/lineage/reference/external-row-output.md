# External Lineage Rows in `GET_LINEAGE` Output

> **Applies when either of two independent conditions holds:**
> 1. The account has **Horizon Catalog connectors** (Private Preview) enabled — gates Horizon-Catalog-connector-sourced external entities (Power BI, Tableau, Sigma, Looker, and other BI-tool connectors).
> 2. The account's `GET_LINEAGE` is on a version new enough to support OpenLineage-sourced external entities (dbt, Airflow, Databricks, and other non-Horizon-Catalog-connector producers ingested via the OpenLineage API).
>
> These are two separate feature gates covering two separate producer families, not one flag with two names — an account can have either, both, or neither enabled. Everything in this file, including the multi-hop chaining below, applies independently under either gate. With both gates enabled, an account's overall lineage graph *can* involve both producer families — but in practice this is uncommon: most customers manage a given pipeline either through Horizon Catalog connectors directly or by ingesting OpenLineage events themselves, not both for the same pipeline segment. Where it does happen, a direct external-to-external edge between a Horizon Catalog connector entity and an OpenLineage entity is not expected — an external-to-external hop is between entities of the *same* family. The two families mix by sharing a Snowflake object in between, e.g. `HORIZON_CATALOG_CONNECTOR_NODE → SNOWFLAKE_TABLE → OPENLINEAGE_NODE` downstream, or the mirror image upstream (`OPENLINEAGE_NODE → SNOWFLAKE_TABLE → HORIZON_CATALOG_CONNECTOR_NODE`). Without either gate enabled, `GET_LINEAGE` never returns rows representing external systems, and nothing in this file applies.

When either condition above holds, `SNOWFLAKE.CORE.GET_LINEAGE()` traverses lineage edges that cross from Snowflake objects to external systems (Power BI, Tableau, Sigma, Looker, dbt, Databricks, …). Those edges show up as rows in the same result set as native Snowflake rows. This file describes how to recognize them and how to present them.

**Multi-hop external chains are supported, with no cap specific to external hops.** The traversal is not limited to a single external hop off the Snowflake anchor, and it is not limited to two — any number of consecutive external-to-external edges can appear in either direction, up to the query's own `DISTANCE` cap (max 5, same limit as native lineage; there is no separate, lower limit for how many of those hops are external). `SNOWFLAKE_OBJECT → EXTERNAL_A → EXTERNAL_B → … → EXTERNAL_N` (downstream) and the mirror image upstream both surface as rows, including rows where **both** `SOURCE_OBJECT_DATABASE` and `TARGET_OBJECT_DATABASE` are `NULL` (an edge entirely between two external entities). If the first external hop doesn't answer the question, increase `DISTANCE` rather than assuming the trail ends there — it can keep going external-to-external all the way to the cap.

## Recognizing an external row

A row represents an external entity when **either** side of the edge has:

| Column | Native row | External row |
|---|---|---|
| `SOURCE_OBJECT_DATABASE` / `TARGET_OBJECT_DATABASE` | populated (e.g. `'ANALYTICS_DB'`) | **`NULL`** |
| `SOURCE_OBJECT_SCHEMA` / `TARGET_OBJECT_SCHEMA` | populated | **`NULL`** |
| `SOURCE_OBJECT_DOMAIN` / `TARGET_OBJECT_DOMAIN` | `'TABLE'`, `'VIEW'`, `'COLUMN'`, etc. | **`'EXTERNAL'`** (object-level), **`'EXTERNAL_COLUMN'`** (column-level — see note below) |
| `SOURCE_NAMESPACE` / `TARGET_NAMESPACE` | `'snowflake://...'` (default) | external namespace, e.g. `'power_bi://CONNECTORS.METADATA."Sales Connector"'` |
| `SOURCE_DATASET_TYPE` / `TARGET_DATASET_TYPE` | `'TABLE'`, `'VIEW'`, `'COLUMN'`, etc. | external entity kind, e.g. `'Power BI Report'`, `'Tableau Dashboard'` |
| `SOURCE_EXTERNAL_ID` / `TARGET_EXTERNAL_ID` | `NULL` | provider-assigned ID, e.g. `'pbi-uuid-abc-def'` |

> **Note on column-level external rows:** column-level external rows correctly get their own `*_OBJECT_DOMAIN = 'EXTERNAL_COLUMN'` value — distinct from the parent object's `'EXTERNAL'` — with `*_COLUMN_NAME` populated. This is the expected, correct behavior (confirmed identical in both `GET_LINEAGE` v7 and v8's underlying SQL). Use `*_COLUMN_NAME` presence to distinguish object- vs column-level externals if you want a belt-and-suspenders check, but `*_OBJECT_DOMAIN` alone already correctly tells them apart.

**Rule of thumb:** any row whose object-side has `*_OBJECT_DATABASE IS NULL` is an external row. Use `*_NAMESPACE` and `*_DATASET_TYPE` to identify the system and entity kind.

## Presenting external rows to the user

When formatting results, render external entities differently from native ones:

- **Identifier:** use the `*_DATASET_TYPE` and `*_OBJECT_NAME`, qualified by the readable part of the namespace. Do **not** try to construct a `db.schema.table` form — they don't have one.
  - Native: `ANALYTICS_DB.REPORTING.REVENUE_SUMMARY` (Table)
  - External (object-level): `Sales Overview` (Power BI Report) — *Connector: Sales Connector*
  - External (column-level, `*_COLUMN_NAME` populated): append the column name — `Sales Overview.revenue` (Power BI Report) — *Connector: Sales Connector*. Present it the same way as object-level but with `.column_name` appended; do not try to resolve a database path.
- **Group external entities under a separate header** when both native and external rows are present. Don't intermingle — they're meaningfully different to the user.
- **Don't apply Snowflake-style risk/trust scoring** to external rows. Schema-pattern rules from `config/schema-patterns.yaml` don't apply (no schema). Note them as "external dependency, scoring not applicable" or omit risk tier.
- **For affected-users questions:** `ACCESS_HISTORY` does not record activity on external entities. Do not claim to know how many users use a Power BI dashboard — that data lives in the external system, not Snowflake.

### Example: impact analysis with external dependents

```
Impact Analysis: ANALYTICS_DB.REPORTING.REVENUE_SUMMARY

═══════════════════════════════════════════════════════════════
SNOWFLAKE DEPENDENCIES (3 objects)
═══════════════════════════════════════════════════════════════
... existing native-row presentation ...

═══════════════════════════════════════════════════════════════
EXTERNAL DEPENDENCIES (2 entities)
═══════════════════════════════════════════════════════════════
1. Q3 Revenue Dashboard  (Power BI Report)
   Connector: corp-powerbi  |  External ID: pbi-uuid-abc-def
   → Snowflake usage stats not available for external entities.

2. Sales Performance Workbook  (Tableau Dashboard)
   Connector: analytics-tableau  |  External ID: tab-uuid-xyz-789

Summary: 3 Snowflake dependencies + 2 external entities downstream
```

## Direction conventions for external rows

External lineage edges follow the same `DIRECTION` semantics as native lineage, and both directions can chain more than one external hop:

- **Downstream from a Snowflake object:** target side may be external, and that external entity's own downstream may lead through any number of further external entities (`SNOWFLAKE_OBJECT → EXTERNAL_A → EXTERNAL_B → …`, up to `DISTANCE`) before landing back on Snowflake or terminating. Two hops is not a limit — it was only the smallest example that demonstrates the pattern.
- **Upstream from a Snowflake object:** source side may be external, chained the same way (`… → EXTERNAL_B → EXTERNAL_A → SNOWFLAKE_OBJECT`). Do not treat this as rare or exceptional — an external producer feeding one or more other external systems before the data reaches Snowflake is a supported, ordinary case, not an edge case.

If the user asks to anchor a query directly on the external entity **cold** (e.g. *"what feeds this Power BI dashboard?"* with no prior lineage result to draw from) — there's no enumeration path for that, for either producer family. Tell them to anchor on a Snowflake table or view they know is connected instead; the external entity — and anything further upstream/downstream of it, external or not — will surface in the result at increasing `DISTANCE`.

## Anchoring directly on an external entity (as a follow-up)

`GET_LINEAGE` does have an anchor mode for `OBJECT_DOMAIN => 'EXTERNAL'`, and whether it works depends on producer family — confirmed by live calls against the Private Preview account:

- **Horizon Catalog connector entity: not supported.** Anchoring fails with `Anchoring GET_LINEAGE on an external object is not enabled for this account.`
- **OpenLineage-sourced entity: supported, but only on accounts opted into the version of `GET_LINEAGE` that added this anchor mode.** This ships as a Behavior Change (BCR) — default off, then default on, then generally available for all accounts over roughly the following 3 months — so at any point in time, accounts vary in whether it's live yet. Same version threshold as the rest of this file: `VERSION_GET_LINEAGE` **v7+** (the `v7` fields carry forward as the version rolls to v8 and beyond over the BCR's rollout — this isn't a v7-only window that closes). On an account still on the older behavior, this call doesn't fail gracefully — it errors with `Unknown domain: EXTERNAL.`, since `'EXTERNAL'` isn't a real Domain value pre-cutover. **Check before attempting this call**, e.g. `SHOW PARAMETERS LIKE 'VERSION_GET_LINEAGE' IN ACCOUNT`, or infer it from whether a prior native-anchored result already had `*_NAMESPACE`/`*_DATASET_TYPE`/`*_EXTERNAL_ID` populated (only true post-cutover — and since those are exactly the identifiers this anchor call needs, you can only ever have reached this point with a pre-cutover account by fabricating them, which you should not do). On an older account, skip straight to the native-anchor redirect instead of attempting the call.

Once you have the entity's `NAMESPACE`, `OBJECT_TYPE` (its dataset type), and `EXTERNAL_ID` — read off `*_NAMESPACE`/`*_DATASET_TYPE`/`*_EXTERNAL_ID` from a prior `GET_LINEAGE` row — you can re-anchor on it directly:

```sql
SELECT * FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE(
  OBJECT_NAME   => '<TARGET_OBJECT_NAME or SOURCE_OBJECT_NAME from the prior row>',
  OBJECT_DOMAIN => 'EXTERNAL',
  DIRECTION     => 'UPSTREAM',  -- or 'DOWNSTREAM'
  MAX_DISTANCE  => 3,
  NAMESPACE     => '<TARGET_NAMESPACE or SOURCE_NAMESPACE from the prior row>',
  OBJECT_TYPE   => '<TARGET_DATASET_TYPE or SOURCE_DATASET_TYPE from the prior row>',
  EXTERNAL_ID   => '<TARGET_EXTERNAL_ID or SOURCE_EXTERNAL_ID from the prior row>'
));
```

This is a **follow-up** capability, not a cold-start one — you still need those identifiers from an earlier native-anchored `GET_LINEAGE` call before you can use it. There is still no SQL to find an external entity by name alone without already having its `NAMESPACE` (and, in practice, `EXTERNAL_ID` — omitting it can return "External node not found" even when a same-named node exists, depending on how uniquely the name+namespace+type resolve).

## What this does **not** include

- This file is primarily about external entities appearing as **edge endpoints** in lineage results from Snowflake-native-anchored queries. Direct external-anchor mode (above) is the one exception, and only for OpenLineage-sourced entities.
