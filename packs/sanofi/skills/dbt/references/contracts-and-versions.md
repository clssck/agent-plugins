# Contracts, Versions, and Access

Final dbt models consumed by other teams or systems behave like APIs. Contracts enforce shape at build time, versions give consumers a migration window for breaking changes, `access`/`group` say who may `ref()` a model. Adapted from dbt Labs' `working-with-dbt-mesh`
skill (see `licenses/sanofi/dbt/ATTRIBUTION`).

## Placement

`contract`, `access`, `group` are **configs**: in properties YAML nest under `config:`; in `dbt_project.yml` use the `+` prefix (`+access`, `+group`). Top-level `access` / `group` model properties are deprecated from dbt 1.10 ([Deprecations and Strict Validation](project-setup.md#deprecations-and-strict-validation)). `versions:`, `latest_version:`, `deprecation_date:` stay model properties.

```yaml
models:
  - name: fct_orders
    latest_version: 1
    config:
      access: public
      group: finance
      contract: {enforced: true}
      on_schema_change: append_new_columns   # required for contracted incrementals
    columns:
      - name: order_id
        data_type: number(38, 0)
        constraints: [{type: not_null}]
    versions:
      - v: 1
        config: {alias: fct_orders}
```

## Contracts

**Use when** the model is `access: public`, feeds an exposure, or is read directly by BI/reverse-ETL/other teams and would break on a rename or retype. **Do NOT add** to staging models, models still being iterated, models with no external consumers (ask who depends on the schema first), dynamic/`pivot` columns, ephemeral models.

- **Every column** MUST be declared with `name` and `data_type`; build fails and the model is not materialized when the query result differs in names, types, or column count.
- **Supported:** `table`; `incremental` (with `on_schema_change: append_new_columns` or `fail`; `sync_all_columns` can remove a contracted column = breaking change); `view` (names and types only, no constraints). **Not supported:** `ephemeral`, `materialized_view`, Python models, snapshots, seeds.
- **Names and types only**, not size, precision, or scale. Declare `number(38, 6)`, not `numeric` (defaults to scale 0, coerces silently). Generic `data_type` names alias to the platform type; `alias_types: false` (under `contract:`) keeps exact Snowflake type names.
- **Breaking changes** — removing a column, changing a type, removing or changing a constraint, deleting a contracted model → new model version, not an in-place edit.

### Constraints on Snowflake

| Constraint | Snowflake |
|---|---|
| `not_null` | Enforced at build; the contract also fails the build |
| `primary_key`, `unique`, `foreign_key` | Metadata only; NOT verified on insert |
| `check` | Not supported; dbt skips it and warns |

- Keep a `unique` / `relationships` data test for every non-enforced constraint ([writing-data-tests.md](writing-data-tests.md)). Constraints still document keys for catalogs; add `rely` to the constraint `expression` only to let Snowflake use it for join elimination — Snowflake trusts it without checking.
- `warn_unenforced: false` silences the warning for a constraint kept as documentation.

## Access and Groups

| `access` | Who can `ref()` it |
|---|---|
| `private` | Models in the same `group` only; give it a `group`, or no other model can reference it |
| `protected` (default) | Models in the same project (or an installed package) |
| `public` | Any group, package, or project |

- **Groups:** define once (`groups: [{name, owner: {name, email}}]`); one group per real team with an owner who can respond, not one per model.
- **Default posture:** new internal models `private`, widen only for a real consumer. Every `public` model gets an enforced contract. Ephemeral model cannot be `public`.
- Cross-group `ref()` to a `private` model → reference error.
- `access` is a dbt concept, not a Snowflake privilege; grants stay with schema management.
- Cross-project `ref('project', 'model')` and `projects:` in `dependencies.yml` need dbt platform Enterprise → not dbt Core; share models with packages instead.

## Versions

Version a model only for a breaking change to a consumed model: removing or renaming a column, changing a type or nullability, changing the grain (versions apply with or without a contract). NEVER version for additive columns, bug fixes, performance work, or "just in case".

- **Files:** each version needs its own SQL file (`fct_orders_v1.sql`, `fct_orders_v2.sql`) or `defined_in:`. Version columns use `include: all` / `exclude: [col]` plus new entries.
- **Resolution:** without `latest_version`, the numerically greatest version is latest and unpinned `ref()` resolves to it. Pin consumers with `ref('fct_orders', v=1)`.
- **Relation names:** each version builds as `<model>_v<N>` unless it sets `alias`. Selection: `dbt build -s fct_orders_v2`, `-s "fct_orders,version:latest"`, `version:prerelease`, `version:old`.
- **Unit tests** run on all versions unless scoped with `versions: {include|exclude}` ([unit-tests.md](unit-tests.md#versioned-models)).

### Keeping an unversioned relation name

Consumers outside dbt read a fixed relation name. Pick one mechanism, NEVER two:

| Mechanism | Version | Notes |
|---|---|---|
| `latest_version_pointer` | dbt >= 1.12 | A view named after the model that follows `latest_version` |
| project `post-hook` creating the view | <= 1.11 | Pattern from dbt's versions docs; macro below |
| `alias` on one version | any | Pins that single version to the name; manual rewiring at promotion |

`latest_version_pointer` is opt-in on dbt 1.12:

```yaml
flags:
  latest_version_pointer_enabled_by_default: true        # whole project, or per model:
models:
  - name: fct_orders
    config:
      latest_version_pointer: {enabled: true, alias: fct_orders_current}   # alias optional
```

- **`dbt1005`:** raised when the latest version's `alias` equals the pointer name. Fix: drop the `alias` (preferred) · `latest_version_pointer: {enabled: false}` for that model · give the version a different alias · override the `generate_latest_version_pointer_alias` macro.
- A project that aliases its latest version and wants no pointers sets `latest_version_pointer_enabled_by_default: false` (or disables per model) ([upgrading.md](upgrading.md#behavior-flags)).
- The pointer follows `latest_version`; it does not shield consumers from a shape change.

```sql
-- macros/create_latest_version_view.sql (<= 1.11); wire as a project-wide post-hook
{% macro create_latest_version_view() %}
  {% if model.get('version') and model.get('version') == model.get('latest_version') %}
    {% set new_relation = this.incorporate(path={"identifier": model['name']}) %}
    {% set existing = load_relation(new_relation) %}
    {% if existing and not existing.is_view %}{{ drop_relation_if_exists(existing) }}{% endif %}
    create or replace view {{ new_relation }} as select * from {{ this }}
  {% else %}
    select 1 as id
  {% endif %}
{% endmacro %}
```

### Migration workflow

Introducing the new version and promoting it to `latest_version` are two separate deploys separated by the migration window.

1. Add the new version and its SQL file; keep `latest_version` on the old version. Ensure the unversioned relation exists through the mechanism above.
2. Deploy; both versions now exist in Snowflake.
3. Verify the window is open: `dbt show --inline "select <old_col> from <unversioned_relation>" --limit 1` MUST still return the old columns. `column does not exist` ⇒ latest was promoted early.
4. Notify consumers to move to `v=<new>` or pin the old one.
5. Bump `latest_version` only after every consumer confirms; for unversioned-name consumers this is the breaking release.
6. Set `deprecation_date` on the old version (`YYYY-MM-DD` or RFC 3339 with offset; no offset → dbt host's time zone). References then warn (`DeprecatedReference`, `UpcomingReferenceDeprecation`); `--warn-error-options` can promote them.
7. Remove the old version only after the date. dbt blocks deleting a model with an enforced contract before its `deprecation_date`, and never drops the relation itself: drop it through the approved schema-management path.

## Verification

- `contract`, `access`, `group` under `config:`; every contracted column has `data_type`.
- Contracted incrementals set `on_schema_change` to `append_new_columns` or `fail`.
- Non-enforced Snowflake constraints backed by tests.
- Public models contracted; private models have a group.
- Breaking change = new version with `latest_version` still on the old one; pointer/alias collision (`dbt1005`) checked; deprecation date set.

## Sources

- [Model contracts](https://docs.getdbt.com/reference/resource-configs/contract) and [constraints](https://docs.getdbt.com/reference/resource-properties/constraints) (Snowflake enforcement, `warn_unenforced`, `rely`).
- [Model versions](https://docs.getdbt.com/docs/mesh/govern/model-versions), [`latest_version_pointer`](https://docs.getdbt.com/reference/resource-configs/latest_version_pointer) (dbt 1.12+, `dbt1005`), [flag](https://docs.getdbt.com/reference/global-configs/behavior-flags/latest_version_pointer_enabled_by_default) [`deprecation_date`](https://docs.getdbt.com/reference/resource-properties/deprecation_date).
- [Upgrading to v1.10](https://docs.getdbt.com/docs/dbt-versions/dbt-upgrade/upgrading-to-v1.10): `access`/`group` move to `config:`. [Project dependencies](https://docs.getdbt.com/docs/mesh/govern/project-dependencies): cross-project refs need Enterprise.
- dbt Labs `working-with-dbt-mesh` skill (Apache-2.0).
