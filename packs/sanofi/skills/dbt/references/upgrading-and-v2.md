# Upgrading dbt and the dbt v2 Engine

Procedure for moving a dbt v1 project to a newer 1.x release, and for judging dbt v2
readiness. Adapted from dbt Labs' `upgrading-dbt` and `migrating-dbt-core-to-v2` skills (see
`ATTRIBUTION`). The deprecation table and warning-silencing rules are in
[project-setup.md](project-setup.md#deprecations-and-strict-validation).

## Engines and Install

Engine naming changed in September 2026: dbt Core 1.x is "dbt v1", and the Rust Fusion
engine is "dbt v2" (GA). **Since 2026-09-14 the bare `dbt` package on PyPI is dbt v2** (PyPI
shows `dbt` 2.0.8 while `dbt-core` is 1.12.5 and `dbt-snowflake` 1.12.1; the Apache-2.0
runtime is `dbt-oss`).

- For a v1 project NEVER install the bare `dbt` package (`pip install dbt`, `uv add dbt`,
  `uv tool install dbt`); install `dbt-core` and `dbt-snowflake` at the repository's pins.
  To evaluate v2, install an exact `dbt==<version>` in a throwaway environment or a copy,
  never in the project's lockfile.
- Run `dbt --version` to confirm which engine is on `PATH` before trusting a parse or test
  result; a venv can hold Core while another binary on `PATH` is v2.
- Both engines read the same project and write compatible `manifest.json` (v12) artifacts, so
  `state:modified` and `--defer` work across them.
- Validate with the repo's dbt v1 workflow unless the repo or platform explicitly adopts dbt
  v2; a local v2 binary is a developer aid, not the verification of record.
- Native `snow dbt` selects the engine with `DBT_VERSION`, not the lockfile
  ([snowflake-native-dbt.md](snowflake-native-dbt.md#runtime-version)).

## Upgrade Procedure (1.x to a newer 1.x)

Work on a clean git branch and change one thing at a time. Do not run unselected builds while
doing this; see Command Scope in SKILL.md.

1. **Record the baseline.** `dbt --version`; resolved `dbt-core`/`dbt-snowflake` from the
   lockfile; `dbt parse --no-partial-parse --show-all-deprecations` on the current version,
   saved to a file.
2. **Run dbt-autofix first.** `uvx dbt-autofix deprecations --dry-run`, read the diff,
   then apply. Review placement as well as correctness (a valid change can land in the wrong
   block or make nearby comments wrong). `uvx dbt-autofix packages --dry-run` checks
   package compatibility with dbt v2 and upgrades `packages.yml`.
   `--include-packages` edits are reverted by the next `dbt deps`; upgrade the package instead.
   Crossing minors below 1.8 (for example `tests:` to `data_tests:`) uses `dbt-migrate-1x
   --dry-run --from <x> --to <y>`, which lives in the dbt-autofix repository workspace and was
   not published on PyPI when checked.
3. **Bump both pins together**, for example `dbt-core>=1.12,<1.13` with `dbt-snowflake==1.12.*`;
   use `dbt-snowflake>=1.10.6` at minimum ([BCR 2118 note](project-setup.md#setup-and-environment)).
   Check each package's `require-dbt-version`; delete `package-lock.yml` and `dbt_packages/`,
   then `dbt deps`.
4. **Re-run the deprecation parse** and clear every warning (no silencing as the fix).
5. **Pin behavior flags only where the project exhibits the behavior** (next section).
6. **Verify, cheapest first:** `dbt parse`; `dbt compile --select <representative models>`;
   a selected `dbt build` in dev ([state-and-ci.md](state-and-ci.md)); compare run results
   with the baseline. Report what could not run.

## Behavior Flags

A behavior flag gates a change that makes the same project behave differently. For each flag
that matured to default `true` in the new version, **check whether the project exhibits the
old behavior; pin `false` only if it does and the change is not being adopted now.** Never pin
a flag the project does not exhibit, never pin one to avoid fixing a real bug, and never leave
an exhibited one unset, which silently adopts the new behavior.

dbt 1.12 flags that mature to `true` (set them in `dbt_project.yml` `flags:`):

| Flag | Project exhibits it when | Effect when `true` |
|---|---|---|
| `skip_nodes_if_on_run_start_fails` | `on-run-start` hooks exist | A failing hook skips **every** selected resource |
| `require_all_warnings_handled_by_warn_error` | CI uses `--warn-error` / `warn_error: true` | Warnings that were only logged now fail the build (for example `RunResultWarningMessage`) |
| `state_modified_compare_more_unrendered_values` | `state:modified` with `target`-aware config Jinja | Changes the selected set; rebuild the state manifest |
| `validate_macro_args` | Macro YAML lists `arguments:` | Mismatches warn at parse time, and fail under `--warn-error` |
| `require_batched_execution_for_custom_microbatch_strategy` | A custom microbatch macro exists | Custom macro must handle batching |

1.12 also adds flags that default `false`: `latest_version_pointer_enabled_by_default`
([contracts-and-versions.md](contracts-and-versions.md#versions)),
`require_valid_schema_from_generate_schema_name`, `require_sql_header_in_test_configs`,
`require_corrected_analysis_fqns`, `allow_jinja_file_extensions`. Leave them unless adopting
the behavior on purpose. Flags marked removed in dbt v2 (for example
`require_explicit_package_overrides_for_builtin_materializations`,
`source_freshness_run_project_hooks`) always behave as `true` there; remove them from
`flags:` when the project moves to v2.

## dbt v2 Readiness

v2 enforces a strict language specification at parse time: misspelled configs, unknown YAML
keys, unused `dbt_project.yml` config paths, duplicate keys, missing generic tests, missing
macros, and undefined `var()` calls fail at `dbt parse` where v1 warned or failed later.

1. Clear every v1 deprecation first; dbt-autofix and Upgrade Procedure above.
2. On 1.12, `dbt parse --use-v2-parser` runs v2's (beta) Rust parser without switching engines;
   its manifest can differ from the Python parser's in edge cases.
3. Run the project on a pinned v2 in a copy: `dbt parse`, then `dbt compile --static-analysis
   strict` (or `DBT_STATIC_ANALYSIS=strict`). Baseline mode, the default, reports column and
   schema findings as **warnings**, so a clean plain `dbt compile` does not prove readiness.
   **Strict mode needs `dbt login`; unauthenticated runs silently fall back to baseline**, so
   confirm the run actually executed strict before claiming readiness.
4. Triage what remains; do not edit before you have reviewed what autofix changed.
5. Expect v2 behavior differences: `dbt build` runs all unit tests first
   ([unit-tests.md](unit-tests.md#running-unit-tests)); `--no-partial-parse` is deprecated
   (`dbt1700`, omit it); a `dbt1065` package-version warning needs no action for a package
   dbt-autofix reports as compatible; `get_relation()` renders a fully qualified relation at
   parse time instead of `None`; `latest_version_pointer` is on by default.
6. `dbt_semantic_view` needs a version check: dbt's Snowflake page states the package needs
   dbt `>=1.0.0, <2.0.0`, while the package's own `require-dbt-version` is `<3.0.0` from v1.0.4
   (and `<2.0.0` in v1.0.0 to v1.0.3). See [snowflake-native-dbt.md](snowflake-native-dbt.md#semantic-views-with-dbt).

### Common dbt v2 error codes (dbt Labs error-patterns reference)

| Code | Signal | Fix |
|---|---|---|
| `dbt1013` | YAML mapping values not allowed | Fix quotes, indentation, extra colons |
| `dbt1060` | Unexpected key in config | Move custom keys to `config: {meta: {...}}`; first rule out a misspelling, since autofix moves typos into `meta` |
| `dbt0102` | No tables defined for source | Delete the empty source or move its config |
| `dbt1001` | Failed to parse `package-lock.yml` | Delete it; `dbt deps` regenerates |
| `dbt1005` | Package not in lookup map; source not found; unused `schema.yml` entry; pointer alias collision | Update the package pin; align `source()` names exactly (v2 does not equate spaces and underscores); remove the orphan entry; see versions doc |
| `dbt8999` | Cannot combine non-exact package versions | Use exact pins |
| `dbt1501` | `config.require('meta').key` / `dict.meta_get()` / duplicate doc block | `config.meta_require('key')`; `dict.get()`; rename the doc block |
| `dbt1000` | Nested quotes in config Jinja | Single quotes outside: `warn_if='{{ "text" }}'` |
| `dbt1502` | Unbalanced `{% endif %}` / `{% endmacro %}` | Balance the blocks |
| `dbt1021` | Seed cast error | Clean the CSV (ISO dates, lowercase `null`, consistent columns) |
| `dbt0214` | Permission denied on a hardcoded relation | Use `ref()` / `source()` or fix grants |
| `dbt0227` / `dbt0209` | Unresolved identifier / function resolution failed | See below |
| `dbt1308` | Client, connection, authentication | Not a migration issue; check profile and credentials with `dbt debug` |

**Case-sensitive identifiers (`dbt0227`, and `dbt0209` only when the message shows the same
"Available are ..." list with the name in another case):** Snowflake stores unquoted names in
upper case. Verify the real casing in `INFORMATION_SCHEMA.COLUMNS` and quote with it, source
side only: `select "DEFAULT" as "default" from {{ source(...) }}`. Never classify the error as
an engine bug from the message alone; the analyzer's column list can be stale (try `dbt clean`
and recompile first).

**Engine gaps** (MiniJinja filter differences, parser gaps, `panic!` / `internal error`,
`not yet implemented: Adapter::...`) are not fixable in the project. Search
`dbt-labs/dbt-fusion` issues for the code, tell the user what blocks and why, and apply a
workaround only with approval. `{{ config(static_analysis='off') }}` is fine for `analyses/`
files; for a production model use it only after warehouse verification and with explicit
sign-off, scoped to that model.

## Checklist

- Baseline deprecation parse saved; dbt-autofix run and its diff reviewed before manual fixes.
- `dbt-core` and `dbt-snowflake` bumped together; packages' `require-dbt-version` checked.
- Flags pinned only for behavior the project exhibits; none pinned to hide a bug.
- v2 readiness claimed only after a confirmed `--static-analysis strict` run (authenticated).
- No bare `dbt` install in a v1 project; `dbt --version` confirmed.

## Sources

- [Upgrading to v1.12](https://docs.getdbt.com/docs/dbt-versions/dbt-upgrade/upgrading-to-v1.12), [Upgrading to v2](https://docs.getdbt.com/docs/dbt-versions/dbt-upgrade/upgrading-to-v2) (strict vs baseline static analysis, `dbt login`, `--use-v2-parser`, `dbt1700`, `dbt1065`), [Deprecations](https://docs.getdbt.com/reference/deprecations) (`--show-all-deprecations`).
- [Behavior change flags](https://docs.getdbt.com/reference/global-configs/behavior-changes) and the pages for [`skip_nodes_if_on_run_start_fails`](https://docs.getdbt.com/reference/global-configs/behavior-flags/skip_nodes_if_on_run_start_fails), [`require_all_warnings_handled_by_warn_error`](https://docs.getdbt.com/reference/global-configs/behavior-flags/require_all_warnings_handled_by_warn_error), [`validate_macro_args`](https://docs.getdbt.com/reference/global-configs/behavior-flags/validate_macro_args).
- [dbt-autofix](https://github.com/dbt-labs/dbt-autofix) README (`deprecations`, `packages`, `dbt-migrate-1x`); PyPI [`dbt`](https://pypi.org/project/dbt/), [`dbt-core`](https://pypi.org/project/dbt-core/), [`dbt-snowflake`](https://pypi.org/project/dbt-snowflake/).
- Error-code table: dbt Labs `migrating-dbt-core-to-v2` `error-patterns-reference.md` (Apache-2.0); only `dbt1005` (pointer collision), `dbt1065`, and `dbt1700` were cross-checked against docs.getdbt.com.
