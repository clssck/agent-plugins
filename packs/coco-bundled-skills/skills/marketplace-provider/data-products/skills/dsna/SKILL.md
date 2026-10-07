---
name: create-dsna-listing
description: "Create a Declarative Sharing Native App (DSNA) data product for Snowflake Marketplace. Use when: provider wants to share data + code objects (notebooks, UDFs, stored procedures) using declarative YAML manifest. Triggers: DSNA, declarative sharing, declarative native app, share data and code, manifest.yml, application package TYPE=DATA."
---

# DSNA (Declarative Sharing Native App)

DSNAs let you share data and code objects — tables, views, notebooks, stored procedures, and UDFs — as a single product using a declarative YAML manifest. No traditional app development or setup script required. Versioning is handled automatically.

> **How this skill works:** Steps marked **Execute** run SQL directly. Steps marked **Invoke** hand off to another skill. Steps marked **Tell the provider** give the provider UI steps to follow in Snowsight or Provider Studio.

**When to choose DSNA over a plain Dataset:**

| | Secure Data Sharing | DSNA | Full Native App |
|---|---|---|---|
| Complexity | Low — SQL only | Medium — SQL, YAML, notebooks | High — containers, complex logic |
| Maintenance | Low | Low | High |
| Code objects | No | Yes — Notebooks, UDFs, stored procs | Yes — Full app logic |
| RBAC / app roles | No | Yes | Yes |
| Best for | Simple dataset sharing | Data + guided experiences | Complex applications |

> See [Choosing a data product](https://docs.snowflake.com/en/developer-guide/declarative-sharing/about#choosing-a-data-product) for the full comparison.

### Setup Steps

**Steps 1–2** you handle directly in this skill. **Steps 3–8** (creating the application package, authoring the manifest, uploading files, building, versioning, and publishing) are owned by the canonical `declarative-sharing` skill — see **Building the DSNA** below. The steps here give you an overview so you know what to expect; do not attempt to execute Steps 3–8 from this file.

**Step 1: Become a provider**
See [Use listings as a provider](https://docs.snowflake.com/en/collaboration/provider-becoming).

**Step 2: Create your data content**
Tables (including dynamic/Iceberg), views (including semantic views), notebooks, stored procedures, and UDFs.

**Step 3: Create an application package**

Via Snowsight: **Projects → App Packages → Share Data + Code → Create**

Or via SQL:
```sql
CREATE APPLICATION PACKAGE <package_name> TYPE = DATA;
```

This also creates a **live version** — a development workspace for editing files before publishing.

**Step 4: Create your `manifest.yml`**

The manifest defines shared databases, schemas, tables, views, and code objects. Place it at the root of the app package. Example:

```yaml
manifest_version: 1
databases:
  - name: MY_DB
    schemas:
      - name: MY_SCHEMA
        tables:
          - name: MY_TABLE
        views:
          - name: MY_VIEW
notebooks:
  - name: EXPLORE_DATA
    path: explore_data.ipynb
```

See [Manifest reference](https://docs.snowflake.com/en/developer-guide/declarative-sharing/manifest-reference).

**Step 5: Upload files & build**

In Snowsight: open the app package → **Upload files** → drag in `manifest.yml` and any `.ipynb` notebook files. A build kicks off automatically.

Or to skip ahead and release immediately:
```sql
ALTER APPLICATION PACKAGE <package_name> RELEASE LIVE VERSION;
```

**Step 6: Test**

```sql
CREATE APPLICATION <test_app> FROM APPLICATION PACKAGE <package_name>;
ALTER APPLICATION PACKAGE <package_name> UPGRADE USING VERSION LIVE;
```

**Step 7: Commit & release**

In Snowsight: **Commit & release** → creates an immutable version ready for listing.

**Step 8: Create a listing**

Same process as Native Apps — in Provider Studio, attach the released application package to a new listing.

### Versioning
Versioning is **automatic** — providers don't manually track version numbers. After each commit & release, the new version is available to existing and new consumers immediately. Rollback to previous versions is not supported.

### App Roles (Optional but Recommended)
App roles let you categorize data and give consumers different views. For example, a `PREMIUM` role sees full data; a `FREE` role sees a subset.

See [App roles](https://docs.snowflake.com/en/developer-guide/declarative-sharing/app-roles).

### Enforced Requirements (Functional Review)

| Requirement | Details |
|-------------|---------|
| Full code executability | All notebooks/functions must run without errors |
| Stability | No crashes, freezes, or abnormal behavior |
| Responsiveness | All cells and functions must complete in reasonable time |

### Building the DSNA

Do not hand-write the package, manifest, or release SQL here. Snowflake's canonical **`declarative-sharing`** skill owns the full declarative-sharing flow: creating the `TYPE = DATA` application package, authoring `manifest.yml` (or generating one from an existing share), uploading files, building, automatic versioning, and cross-account publishing.

**Use the Read tool to load the `declarative-sharing` skill file and follow its instructions** to build and release the package, then return here for the Marketplace-specific steps (functional review, listing).

Keep these DSNA specifics in scope while you run that flow:
- Include data **and** code objects (tables, views, semantic views, notebooks, stored procedures, UDFs) as needed: sharing code alongside data is what distinguishes a DSNA from a plain Dataset share.
- Versioning is automatic and rollback is not supported (see Versioning above).
- Define App Roles if consumers need tiered views (e.g. FREE vs PREMIUM).
- Meet the Enforced Requirements (notebooks and functions run without errors, stable, responsive) before submitting.

Once a version is committed and released, attach the application package to a listing (Step 8 above, then the Listings sub-skill).

### Review Process
Security scan + Metadata review + Functional review — up to 14 days total.

### References
- [About Declarative Sharing](https://docs.snowflake.com/en/developer-guide/declarative-sharing/about)
- [Application Packages in Declarative Sharing](https://docs.snowflake.com/en/developer-guide/declarative-sharing/package)
- [Live editing / notebooks](https://docs.snowflake.com/en/developer-guide/declarative-sharing/live-editing)
- [Creating a listing](https://docs.snowflake.com/en/developer-guide/declarative-sharing/listing)
- [Versioning](https://docs.snowflake.com/en/developer-guide/declarative-sharing/versioning)
- [Tutorial: Getting started with DSNAs](https://docs.snowflake.com/en/developer-guide/declarative-sharing/tutorials/getting-started)
