# Domain vocabulary

Three nouns, used precisely throughout this skill.

| Term | Meaning | Builder-facing? |
|---|---|---|
| **Domain** | The named, persistent business intent the builder is setting up — `sales_ops`, `supply_chain`, `marketing_attribution`. One per session as the strong default. Previously called "use case"; that term is deprecated in builder-facing text. | Yes — primary noun. |
| **Domain context** | The scoped package — scope manifest, dashboards, semantic views, declared facts, instructions — assembled in conversation and fed to the offline build. A domain *has* a domain context. | Yes — secondary noun ("here's the domain context for sales ops"). |
| **Build** | The offline job that turns a domain context into the artifacts CoCo retrieves at serve time. | Mentioned only as time-framing ("build can take minutes or hours depending on scope"). Never as a noun the builder authors. |

The domain is **named** by the builder; the domain context is **proposed** by CoCo (from a background scan) and **edited** by the builder in plain English; the build **runs** when the builder confirms.

## Internal mapping

In the YAML manifest the domain is stored under the key `business_domain` (legacy name), and the CLI flag is `--domain`. User-facing copy uses **"domain"** for the named entity and **"domain context"** for the assembled scope package.

## Internal-only concepts (never surface)

`snowflake_object_search` (internal tool name), `Layer 1`, `Layer 2`, `QBE`, `ontology`, `entity`, `graph`, `in_account_instructions`, `draft` / `active`, `superseded_by`, `feedback storage`, `provenance flag`. These are mechanics, not knobs the builder turns.

When a builder concept maps to one of these internally, the **user-facing label is** what to use:

| Internal | User-facing |
|---|---|
| snowflake_object_search | "Looking at your account" / "search results" |
| streamlit_apps_metadata + `type: horizon_context` (Tableau, Power BI, Sigma, Looker) | **Dashboards** (see `DASHBOARDS.md`) |
| `type: horizon_context` (Databricks, SQL Server, PostgreSQL, Redshift) | **External tables** (see `DASHBOARDS.md`) |
| catalog_objects | **Tables** |
| concepts / relationships / associations | **Definitions** (recorded automatically) |
| additional_instructions / in_account_instructions | **Instructions** (one bucket, classified internally) |
| draft / active | hidden — internal versioning only |
| status: active | "ready to build from" |

## Re-entry

`@cortex-sense resume <domain>` loads the domain's manifest. CoCo then routes to **test** or **refine** based on what the builder says next.
