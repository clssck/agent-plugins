# Writing dbt Documentation

Never generate documentation that simply restates the entity's name. Describe **why, not just what**.

## Before Writing

Inspect the model before documenting it:
- Read the `.sql` file to understand transformations, filters, and joins
- Check existing dbt YAML/properties files for descriptions already in place; enrich
  or correct them, do not blindly overwrite
- Follow the repo's YAML placement convention. Sanofi guide examples prefer one YAML
  file per model: `<model>.yml` next to the SQL, `_model.yml` when docs are kept at
  the top of the folder, or `docs/<model>.yml` when SQL folders are crowded.
- Run `dbt show --select <model_name>` to see real sample data if needed

To profile multiple columns, run one sampled query that computes cardinality, null
counts, and low-cardinality value lists instead of querying each column separately. Use
`TABLESAMPLE` on large tables.

List possible values when cardinality is low, around 25 or fewer distinct values, or
when the column name suggests a controlled vocabulary such as `_type`, `_status`,
`_category`, `_code`, `_flag`, `_level`, `_phase`, `_stage`, `_state`, `_kind`,
`_class`, `_mode`, or `_role`.

Never guess values; always derive them from `dbt show` or a direct query.

## Model (Table) Level

Every model description must include:
1. **Grain**: one row per what?
2. **Purpose**: why does this model exist, what question does it answer?
3. **Edge cases**: filters applied, known nulls, exclusions, or historical quirks

For shared marts, KPI-producing models, or models consumed outside the owning team,
also include refresh cadence and primary consumers. Put structured ownership, domain,
classification, SLA, KPI/catalog codes, or similar machine-readable fields in `meta`
when the repo already uses those conventions.

Avoid `description: All customers who are active`. Prefer grain plus purpose plus edge
case, such as "One row per customer whose contract has not expired; excludes trial
accounts and expired contracts."

## Column Level

Document columns that are non-obvious. Skip columns whose name and type are self-explanatory (e.g. `created_at timestamp`).

Always document:
- **Calculated fields**: what the formula does and why
- **Encoded/prefixed values**: legacy formats, migrations, or system-specific conventions
- **Foreign keys**: what they reference
- **Nullable columns**: when and why nulls are expected

Avoid `description: The customer's identification number`. Prefer explanations of
non-obvious behavior, such as legacy prefixes, nullable conditions, or calculation
semantics.

## Sources

Document sources with the same "why not what" principle at both source and table level:
describe the upstream system, load behavior, table grain, archived/deleted rows, and
filters that staging applies.

## Exposures

Use exposures for important downstream consumers such as dashboards, applications, ML
models, notebooks, and analyses. Include dependency refs, owner, maturity, URL when
available, and enough context for impact analysis when a shared model changes.

## Tags

Use `tags` to make models and columns discoverable in the catalog by domain, team, or sensitivity:
for example `finance`, `certified`, or `pii`.

## meta

Use `meta` to attach structured, machine-readable metadata such as ownership,
classification, and SLA. Fields are team-defined; align with catalog conventions.

On dbt >= 1.10 write `meta` and `tags` under `config:` (`config: {meta: {...}, tags: [...]}`),
on models, columns, and sources alike. Top-level `meta`/`tags` and any other custom key
(for example `owner:` beside `description:`) raise deprecation warnings that dbt v2 turns
into errors; custom keys MUST live inside `config.meta`. Only apply this form when the
resolved dbt version is 1.10 or newer; older versions keep the top-level properties.

`persist_docs` (`relation: true`, `columns: true`) pushes descriptions into Snowflake
comments. dbt allows it in `dbt_project.yml`, model properties YAML, or a `config()`
block, so the capability is not project-only; whether a model may override it is Sanofi
or team policy. Follow the repo's convention: by default set it once at project or
folder level (see `general-dbt-guide.md`) and do not add per-model overrides unless the
repo already does. Sources do not support it.

## Updating Existing Documentation

When descriptions already exist:
- **Enrich** if the existing description is correct but incomplete
- **Correct** if it is factually wrong or outdated
- **Leave unchanged** if it is accurate and complete; do not rewrite for style

## What Not to Document

- Columns whose name and type are fully self-explanatory (`created_at`, `updated_at`, `id`)
- Descriptions that just repeat the column name in different words
- Implementation details that belong in code comments, not in the catalog
