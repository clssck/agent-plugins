# Feature Store Design & Organization Guide

Best practices for structuring, naming, versioning, securing, and promoting Snowflake Feature Stores.

---

## Transformation Taxonomy (MIT / MDT / ODT)

Classify every transformation before deciding where it belongs:

| Type | Full Name | Where | Reusable? | Examples |
|------|-----------|-------|-----------|----------|
| **MIT** | Model-Independent | FeatureView | Yes, across models | Aggregations, joins, derived columns |
| **MDT** | Model-Dependent | Model Registry (Pipeline) | No, tied to model | Scaling, encoding, imputation. **Fit on training data only** |
| **ODT** | On-Demand | Inference time | N/A | Time-since-last, distance, current weather |

**Anti-patterns:**
- MDT in FeatureView (hard-coded scaler params)
- MIT in training pipeline (per-model aggregation)
- ODT for stable features (30-day aggregates at request time)

---

## Naming Conventions

### Entities
- Use SCREAMING_SNAKE_CASE business domain nouns: `CUSTOMER`, `PRODUCT`, `ORDER`, `SESSION`
- Composite entities: `ORDER_LINE` (not `ORDER_AND_LINE_ITEM`)

### Feature Views
- Pattern: `<ENTITY>_<DOMAIN>_FV`
- Examples: `CUSTOMER_ORDER_FV`, `SESSION_ENGAGEMENT_FV`, `TAXI_ROUTE_TRIP_FV`
- Keep names descriptive but concise

### Feature Columns
- Use UPPER_SNAKE_CASE consistent with Snowflake conventions
- Include the aggregation and window in the name

| Suffix | Meaning | Example |
|--------|---------|---------|
| `_TS` | Timestamp | `ORDER_TS` |
| `_CNT` | Count | `ORDER_CNT` |
| `_DCNT` | Distinct count | `PRODUCT_VIEW_DCNT` |
| `_SUM` | Sum | `REVENUE_SUM` |
| `_AVG` | Average | `ORDER_VALUE_AVG` |
| `_AMT` | Amount (currency) | `TOTAL_AMT` |
| `IS_` | Boolean flag | `IS_CONVERTED` |
| `_<WINDOW>` | Aggregation window | `TOTAL_SPEND_7D` |
| `_STD` | Standard deviation | `FARE_STD` |

- Use `attach_feature_desc()` to add human-readable descriptions

### Versions
- Zero-padded sequential for lexicographic sort: `V01`, `V02`, ..., `V10`
- Also acceptable: `DEV_V01`, `1.0.0`, `20250115`
- Never reuse a version string for different logic — create a new version instead
- No built-in "latest version" alias — must sort version strings to find latest

---

## Schema Organization

### Single-Environment (Simple)

```
MY_DB/
└── FEATURE_STORE/          # Single feature store schema
    ├── Entities
    ├── Feature Views (Dynamic Tables)
    └── Tags
```

### Multi-Environment (Recommended for Production)

```
ML_FEATURES_DB/
├── DEV_FEATURE_STORE/      # Development
├── TEST_FEATURE_STORE/     # Staging / QA
└── PROD_FEATURE_STORE/     # Production
```

Separate warehouses per environment for cost attribution — see
[Warehouse Sizing](#warehouse-sizing) below for the recommended tiers.

### Hybrid Organization (Larger Orgs)

```
ML_FEATURES_DB/
├── SHARED_FEATURE_STORE/    (core cross-domain entities)
├── MARKETING_FEATURES/      (domain-specific)
├── FRAUD_FEATURES/          (domain-specific)
└── RECOMMENDATION_FEATURES/ (domain-specific)
```

---

## Warehouse Sizing

Canonical warehouse-sizing guidance for Feature Store objects. Size by query
complexity:

| Complexity | Warehouse | Use Case |
|------------|-----------|----------|
| Simple aggregations | X-Small to Small | Count, sum, avg |
| Complex joins | Medium to Large | Multi-table joins |
| ML transformations | Large to X-Large | UDF-based features |

Recommended per-environment tiers (for cost attribution):
- `DEV_WH` (XSMALL) — development
- `TEST_WH` (SMALL) — testing
- `PROD_WH` (MEDIUM) — production FV refresh
- `PROD_OFT_WH` (SMALL) — dedicated OFT refresh

Right-sizing depends on data volume and refresh cadence — confirm row counts and
target `refresh_freq` before committing to a size. For the migration-specific
breakdown of which warehouse plays which role (default / refresh / init-backfill),
see [`migrate/SKILL.md`](../migrate/SKILL.md#warehouse-sizing).

---

## Environment Promotion (DEV → TEST → PROD)

### Zero-Copy Clone (Quick)

```sql
CREATE OR REPLACE SCHEMA PROD_FEATURE_STORE CLONE DEV_FEATURE_STORE;
```

### Python-Based Promotion (Controlled)

```python
dev_fs = FeatureStore(session, database, "DEV_FEATURE_STORE", warehouse, CreationMode.FAIL_IF_NOT_EXIST)
prod_fs = FeatureStore(session, database, "PROD_FEATURE_STORE", warehouse, CreationMode.CREATE_IF_NOT_EXIST)

fv = dev_fs.get_feature_view("USER_PURCHASE_FV", "V01")
# Recreate in prod with same query and metadata
```

Promotion means re-creating the FeatureView with identical logic but pointing to the target schema's source tables.

### Validation After Promotion

Schema match, row counts, sample value comparison.

### CI/CD Flow

Feature definitions as code → GitHub Actions → validate → test → deploy DEV → integration test → deploy PROD (approval gate required).

---

## Versioning Strategy

### When to Create a New Version
- Feature logic changes (different transformations)
- Source data schema changes
- Aggregation windows change
- New features added to the view

### When NOT to Create a New Version
- Data refreshes (handled automatically by Dynamic Tables)
- Bug fixes to source data (features auto-refresh)

### Deprecation Pattern
1. Create new version with updated logic
2. Update downstream consumers to reference new version
3. Suspend old version: `fs.suspend_feature_view("MY_FV", "V01")`
4. After confirmation period, delete: `fs.delete_feature_view("MY_FV", "V01")`

---

## Access Control (RBAC)

### Recommended Roles

| Role | Permissions | Users |
|------|------------|-------|
| `FS_ADMIN` | CREATE SCHEMA, manage entities and feature views | ML platform team |
| `FS_DEVELOPER` | CREATE DYNAMIC TABLE, register feature views | Data engineers, ML engineers |
| `FS_CONSUMER` | SELECT on feature views, generate datasets | Data scientists |
| `FS_READER` | SELECT on feature views (read-only) | Analysts, downstream services |

Hierarchy: FS_READER < FS_CONSUMER < FS_DEVELOPER < FS_ADMIN < SYSADMIN

### Grant Pattern

```sql
SET FS_DATABASE = 'ML_FEATURES_DB';
SET FS_SCHEMA = 'PROD_FEATURE_STORE';
SET FS_WAREHOUSE = 'PROD_WH';

CREATE ROLE IF NOT EXISTS FS_ADMIN;
CREATE ROLE IF NOT EXISTS FS_DEVELOPER;
CREATE ROLE IF NOT EXISTS FS_CONSUMER;
CREATE ROLE IF NOT EXISTS FS_READER;

GRANT ROLE FS_READER TO ROLE FS_CONSUMER;
GRANT ROLE FS_CONSUMER TO ROLE FS_DEVELOPER;
GRANT ROLE FS_DEVELOPER TO ROLE FS_ADMIN;
GRANT ROLE FS_ADMIN TO ROLE SYSADMIN;

-- Admin privileges
GRANT CREATE SCHEMA ON DATABASE IDENTIFIER($FS_DATABASE) TO ROLE FS_ADMIN;
GRANT USAGE ON DATABASE IDENTIFIER($FS_DATABASE) TO ROLE FS_ADMIN;
GRANT ALL ON SCHEMA IDENTIFIER($FS_DATABASE || '.' || $FS_SCHEMA) TO ROLE FS_ADMIN;

-- Developer privileges
GRANT USAGE ON DATABASE IDENTIFIER($FS_DATABASE) TO ROLE FS_DEVELOPER;
GRANT ALL ON SCHEMA IDENTIFIER($FS_DATABASE || '.' || $FS_SCHEMA) TO ROLE FS_DEVELOPER;
GRANT USAGE ON WAREHOUSE IDENTIFIER($FS_WAREHOUSE) TO ROLE FS_DEVELOPER;
GRANT CREATE DYNAMIC TABLE ON SCHEMA IDENTIFIER($FS_DATABASE || '.' || $FS_SCHEMA) TO ROLE FS_DEVELOPER;
GRANT CREATE VIEW ON SCHEMA IDENTIFIER($FS_DATABASE || '.' || $FS_SCHEMA) TO ROLE FS_DEVELOPER;
GRANT CREATE TAG ON SCHEMA IDENTIFIER($FS_DATABASE || '.' || $FS_SCHEMA) TO ROLE FS_DEVELOPER;

-- Consumer privileges
GRANT USAGE ON DATABASE IDENTIFIER($FS_DATABASE) TO ROLE FS_CONSUMER;
GRANT USAGE ON SCHEMA IDENTIFIER($FS_DATABASE || '.' || $FS_SCHEMA) TO ROLE FS_CONSUMER;
GRANT USAGE ON WAREHOUSE IDENTIFIER($FS_WAREHOUSE) TO ROLE FS_CONSUMER;
GRANT SELECT ON ALL DYNAMIC TABLES IN SCHEMA IDENTIFIER($FS_DATABASE || '.' || $FS_SCHEMA) TO ROLE FS_CONSUMER;
GRANT SELECT ON FUTURE DYNAMIC TABLES IN SCHEMA IDENTIFIER($FS_DATABASE || '.' || $FS_SCHEMA) TO ROLE FS_CONSUMER;
GRANT SELECT ON ALL VIEWS IN SCHEMA IDENTIFIER($FS_DATABASE || '.' || $FS_SCHEMA) TO ROLE FS_CONSUMER;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA IDENTIFIER($FS_DATABASE || '.' || $FS_SCHEMA) TO ROLE FS_CONSUMER;

-- Reader privileges (read-only)
GRANT USAGE ON DATABASE IDENTIFIER($FS_DATABASE) TO ROLE FS_READER;
GRANT USAGE ON SCHEMA IDENTIFIER($FS_DATABASE || '.' || $FS_SCHEMA) TO ROLE FS_READER;
GRANT SELECT ON ALL DYNAMIC TABLES IN SCHEMA IDENTIFIER($FS_DATABASE || '.' || $FS_SCHEMA) TO ROLE FS_READER;
GRANT SELECT ON ALL VIEWS IN SCHEMA IDENTIFIER($FS_DATABASE || '.' || $FS_SCHEMA) TO ROLE FS_READER;
```

### Environment-Specific Roles (Optional)

```sql
CREATE ROLE IF NOT EXISTS FS_DEV_DEVELOPER;
CREATE ROLE IF NOT EXISTS FS_PROD_INFERENCE;
```

---

## Feature Categorization

| Category | Description | Example |
|----------|-------------|---------|
| **Raw** | Direct columns from source | `CUSTOMER_AGE`, `PRODUCT_PRICE` |
| **Derived** | Per-row transformations | `DAY_OF_WEEK`, `IS_WEEKEND`, `AMOUNT_TIER` |
| **Aggregated** | Group-by or window aggregations | `TX_SUM_7D`, `AVG_ORDER_VALUE_30D` |
| **Temporal** | Time-based patterns | `DAYS_SINCE_LAST_PURCHASE`, `IS_PEAK_HOUR`, `ORIG_MONTH` |
| **Cross-Entity** | Features joining multiple entities | `CUSTOMER_PRODUCT_AFFINITY_SCORE` |

---

## Performance Guidelines

- **Prefer incremental refresh** over full refresh for large datasets
- **Enable change tracking** on source tables before creating managed feature views
- **Use explicit column lists** in feature DataFrames (avoid `SELECT *`)
- **Cluster feature views** by frequently filtered columns
- **Set appropriate refresh_freq** — balance freshness needs against compute cost
- **Use DOWNSTREAM target lag** for intermediate pipeline stages
- **Dedicate warehouses** for large or critical feature pipelines
- **Cast float columns to DECIMAL** before aggregation to preserve incremental refresh
