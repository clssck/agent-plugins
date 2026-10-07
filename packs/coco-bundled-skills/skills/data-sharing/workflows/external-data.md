# Share External Data

Share data from cloud storage (S3 / Azure Blob / GCS) via Snowflake. Two approaches depending on where the data should live:

- **Keep data in place** — Iceberg tables let Snowflake read data directly from cloud storage without copying it
- **Move data into Snowflake** — Openflow replicates data into native Snowflake tables

**Documentation**: [Iceberg Tables](https://docs.snowflake.com/en/user-guide/tables-iceberg) | [Openflow](https://docs.snowflake.com/en/user-guide/data-load-openflow) | [Secure Data Sharing](https://docs.snowflake.com/en/user-guide/data-sharing-intro)

---

## Workflow Overview

```
Step 1: Gather requirements + verify privileges
   ↓
Step 2: Data setup (branched)
   ├─→ Keep in cloud storage (Iceberg)
   │     → delegate to iceberg/SKILL.md (handles external volume + catalog + table)
   │
   └─→ Move into Snowflake (Openflow)
         → delegate to openflow/SKILL.md
   ↓
Step 3: Route to listing skill
         → downstream skill asks which objects to include, creates share, publishes
         ├─→ Org accounts         →  workflows/org-listing.md
         └─→ Outside org / public →  external-listing.md
```

---

## Step 1: Gather Requirements and Verify Privileges

Ask the user for all of the following before proceeding:

1. **Data location** — cloud storage provider (S3 / Azure Blob / GCS) and the storage path (bucket/container and prefix)
2. **Data residency** — where should the data live?
   > "Do you want to **keep your data in cloud storage** (Iceberg — no data movement) or **move it into Snowflake** (Openflow — data replication)?"
3. **Sharing target** — who do you want to share this data with?
   > "Who do you want to share this data with?"
   >
   > 1. **Accounts in my Snowflake organization** (all internal accounts or specific org accounts)
   > 2. **Specific Snowflake accounts outside my organization**
   > 3. **Specific regions**
   > 4. **Anyone — publish publicly on Snowflake Marketplace**

   If the user chose option 1 or 2, follow up: "Which accounts specifically? (all org accounts, or list account names)"

Then verify the role has the required privileges:

```sql
SELECT CURRENT_ROLE();
SHOW GRANTS TO ROLE <your_role>;
```

Required privileges:

| Privilege | Object | Required for |
|-----------|--------|--------------|
| `CREATE EXTERNAL VOLUME` | ACCOUNT | Iceberg path only |
| `CREATE INTEGRATION` | ACCOUNT | Iceberg with external catalogs only |
| `CREATE ICEBERG TABLE` | SCHEMA | Iceberg path only |
| `CREATE SHARE` | ACCOUNT | Both paths |
| `CREATE ORGANIZATION LISTING` | ACCOUNT | Org accounts target only |
| `CREATE LISTING` | ACCOUNT | Outside org / regions / public target only (the command is `CREATE EXTERNAL LISTING`; the privilege is just `CREATE LISTING`) |

> ⚠️ **STOP** — do not proceed until data residency choice and sharing target are confirmed.

---

## Step 2: Data Setup

Branch based on the user's data residency choice from Step 1.

### Path A — Keep Data in Cloud Storage (Iceberg)

> **Load** [`data-engineering/iceberg/SKILL.md`](../../iceberg/SKILL.md)
>
> That skill handles the full Iceberg setup — external volume, catalog integration (Snowflake-managed, AWS Glue, Databricks Unity Catalog, or Polaris/OpenCatalog), and Iceberg table creation.
>
> **Return here after** the Iceberg table is verified readable:
> ```sql
> SELECT * FROM <db>.<schema>.<iceberg_table> LIMIT 10;
> ```

### Path B — Move Data into Snowflake (Openflow)

> **Load** [`data-engineering/openflow/SKILL.md`](../../openflow/SKILL.md)
>
> Follow its workflow to deploy a connector and replicate the data into Snowflake tables.
>
> **Return here after** the target tables are populated and verified:
> ```sql
> SELECT * FROM <db>.<schema>.<table> LIMIT 10;
> ```

---

## Step 3: Create Share and Listing

> **Important:** Do not assume all tables created in Step 2 should be shared. The downstream skill will ask the user which specific objects to include.

> ⚠️ **Iceberg path only:** When loading the downstream listing skill, pass this context: Iceberg tables require `GRANT SELECT ON ICEBERG TABLE` — not `GRANT SELECT ON TABLE`. `GRANT SELECT ON TABLE` will fail for Iceberg tables.

Route to the appropriate skill based on the user's sharing target from Step 1:

| Sharing target | Action |
|----------------|--------|
| **Org accounts** (all or specific) | **Load** [`workflows/org-listing.md`](org-listing.md) — it will ask which objects to share, create the share, generate a data dictionary, and publish |
| **Outside org / specific regions / public** | **Load** [`workflows/external-listing.md`](external-listing.md) — it will ask which objects to share, create/verify the share, build the listing manifest, and publish |

---

## Troubleshooting

If any step fails, load [`collaboration/data-sharing/workflows/debug.md`](debug.md) for share-level issues, or return to the relevant sub-skill for data setup errors.

Common Iceberg share errors:

| Error | Cause | Fix |
|-------|-------|-----|
| `Invalid grant on ICEBERG TABLE` | Used `ON TABLE` instead of `ON ICEBERG TABLE` | Use `GRANT SELECT ON ICEBERG TABLE` |
| `Share does not have database` | Granted objects before database | Re-grant in order: DATABASE → SCHEMA → ICEBERG TABLE |
| `External volume not found` | Volume not yet created or wrong name | Run `SHOW EXTERNAL VOLUMES` and verify |
| `Catalog integration not found` | Integration missing or wrong region | Run `SHOW INTEGRATIONS` and verify catalog integration exists |

For Openflow connector issues (data not arriving, connector errors), return to [`data-engineering/openflow/SKILL.md`](../../openflow/SKILL.md).

---

## Expected Outputs

When the workflow is complete, the user will have:

**Iceberg path:**
- An **external volume** connected to their cloud storage
- A **catalog integration** pointing to the external catalog (Glue / Unity / Polaris) — if using an external catalog
- One or more **Iceberg tables** queryable in Snowflake without data movement
- A **share** containing selected Iceberg tables with correct grants
- A **listing** (org, marketplace, or direct) published and accessible to consumers

**Openflow path:**
- An **Openflow connector** replicating data from cloud storage into Snowflake
- One or more **native Snowflake tables** with replicated data
- A **share** containing selected tables with correct grants
- A **listing** (org, marketplace, or direct) published and accessible to consumers
