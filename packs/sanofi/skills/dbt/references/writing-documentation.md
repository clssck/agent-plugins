# Writing dbt Documentation

Describe **why, not just what**. NEVER generate documentation that restates the entity's name. Every description earns its place by carrying grain, purpose, edge cases, or non-obvious behavior; anything else is omitted.

## Before Writing

Inspect the model first:

- Read the `.sql` → transformations, filters, joins.
- Check existing YAML/properties files; enrich or correct descriptions, never blindly overwrite.
- Follow the repo's YAML placement. Sanofi guide examples prefer one YAML per model: `<model>.yml` next to the SQL; `_model.yml` when docs sit at the top of the folder; `docs/<model>.yml` when SQL folders are crowded.
- `dbt show --select <model_name>` for real sample data when needed.

**Profiling.** Multiple columns → one sampled query computing cardinality, null counts, and low-cardinality value lists, not one query per column. `TABLESAMPLE` on large tables.

**Listing values.** List possible values when cardinality ≲25 distinct, or when the name suggests a controlled vocabulary: `_type`, `_status`, `_category`, `_code`, `_flag`, `_level`, `_phase`, `_stage`, `_state`, `_kind`, `_class`, `_mode`, `_role`. NEVER guess values; derive from `dbt show` or a direct query.

## Model Level

Every model description MUST include:

1. **Grain:** one row per what?
2. **Purpose:** why the model exists; what question it answers.
3. **Edge cases:** filters applied, known nulls, exclusions, historical quirks.

Shared marts, KPI-producing models, or models consumed outside the owning team: also refresh cadence and primary consumers. Structured ownership, domain, classification, SLA, KPI/catalog codes → `meta`, when the repo already uses those conventions.

| Avoid | Prefer |
|---|---|
| `description: All customers who are active` | "One row per customer whose contract has not expired; excludes trial accounts and expired contracts." |

## Column Level

Document non-obvious columns only; skip those whose name and type are self-explanatory (`created_at timestamp`, `updated_at`, `id`). Always document:

- **Calculated fields:** formula and why.
- **Encoded/prefixed values:** legacy formats, migrations, system-specific conventions.
- **Foreign keys:** what they reference.
- **Nullable columns:** when and why nulls are expected.

| Avoid | Prefer |
|---|---|
| `description: The customer's identification number` | Legacy prefixes, nullable conditions, calculation semantics |

## Sources and Exposures

- **Sources:** same why-not-what at source and table level: upstream system, load behavior, table grain, archived/deleted rows, filters staging applies.
- **Exposures:** for important downstream consumers (dashboards, applications, ML models, notebooks, analyses). Include dependency refs, owner, maturity, URL when available, enough context for impact analysis when a shared model changes.

## Tags and meta

- **`tags`:** catalog discoverability by domain, team, or sensitivity (`finance`, `certified`, `pii`).
- **`meta`:** structured, machine-readable metadata (ownership, classification, SLA). Fields team-defined; align with catalog conventions.
- **dbt >= 1.10:** `meta` and `tags` under `config:` (`config: {meta: {...}, tags: [...]}`) on models, columns, and sources alike. Top-level `meta`/`tags` and any other custom key (for example `owner:` beside `description:`) raise deprecation warnings; custom keys MUST live inside `config.meta`. Older than 1.10 (check the resolved version): top-level properties stay.

## persist_docs

`persist_docs` (`relation: true`, `columns: true`) pushes descriptions into Snowflake comments. dbt allows it in `dbt_project.yml`, model properties YAML, or a `config()` block; whether a model may override it = Sanofi/team policy. Default: set once at project or folder level (`general-dbt-guide.md`); no per-model overrides unless the repo already does. Sources: unsupported.

## Updating Existing Docs

| Existing description | Action |
|---|---|
| Correct but incomplete | **Enrich** |
| Factually wrong or outdated | **Correct** |
| Accurate and complete | **Leave unchanged**; no style rewrites |

## Out of Scope

- Columns whose name and type are fully self-explanatory (`created_at`, `updated_at`, `id`).
- Descriptions repeating the column name in other words.
- Implementation details → code comments, not the catalog.
