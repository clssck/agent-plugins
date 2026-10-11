# Upgrading dbt 1.x

Procedure for moving a dbt Core 1.x project to a newer 1.x release. Adapted from dbt Labs' `upgrading-dbt` skill (see `licenses/sanofi/dbt/ATTRIBUTION`). Deprecation table and warning-silencing rules → [project-setup.md](project-setup.md#deprecations-and-strict-validation). Governing rule: one change at a time on a clean branch; autofix before manual edits; pin behavior flags only for behavior the project exhibits.

## Engines and Install

**Since 2026-09-14 the bare `dbt` package on PyPI is dbt v2, not dbt Core 1.x.**

- 1.x project: NEVER install the bare `dbt` package (`pip install dbt`, `uv add dbt`, `uv tool install dbt`); install `dbt-core` and `dbt-snowflake` at the repository's pins.
- Run `dbt --version` before trusting a parse or test result; another binary on `PATH` can be a different engine than the project's venv.
- Native `snow dbt` selects the engine with `DBT_VERSION`, not the lockfile ([snowflake-native-dbt.md](snowflake-native-dbt.md#runtime-version)).

## Upgrade Procedure (1.x → newer 1.x)

Clean git branch; one change at a time. No unselected builds (Command Scope in SKILL.md).

1. **Record the baseline.** `dbt --version`; resolved `dbt-core`/`dbt-snowflake` from the lockfile; `dbt parse --no-partial-parse --show-all-deprecations` on the current version, saved to a file.
2. **dbt-autofix first.** `uvx dbt-autofix deprecations --dry-run` → read diff → apply. Review placement as well as correctness (a valid change can land in the wrong block or make nearby comments wrong). `uvx dbt-autofix packages --dry-run` checks package compatibility and upgrades `packages.yml`. `--include-packages` edits are reverted by the next `dbt deps` ⇒ upgrade the package instead. Crossing minors below 1.8 (for example `tests:` → `data_tests:`): `dbt-migrate-1x --dry-run --from <x> --to <y>`; lives in the dbt-autofix repository workspace, not published on PyPI when checked.
3. **Bump both pins together**, for example `dbt-core>=1.12,<1.13` with `dbt-snowflake==1.12.*`; `dbt-snowflake>=1.10.6` at minimum ([BCR 2118 note](project-setup.md#setup-and-environment)). Check each package's `require-dbt-version`; delete `package-lock.yml` and `dbt_packages/`, then `dbt deps`.
4. **Re-run the deprecation parse**; clear every warning (silencing is not the fix).
5. **Pin behavior flags** only where the project exhibits the behavior (below).
6. **Verify, cheapest first:** `dbt parse` → `dbt compile --select <representative models>` → selected `dbt build` in dev ([state-and-ci.md](state-and-ci.md)) → compare run results with the baseline. Report what could not run.

## Behavior Flags

A behavior flag gates a change that makes the same project behave differently. For each flag matured to default `true` in the new version: **check whether the project exhibits the old behavior; pin `false` only if it does and the change is not being adopted now.**

- NEVER pin a flag the project does not exhibit.
- NEVER pin one to avoid fixing a real bug.
- NEVER leave an exhibited one unset; unset silently adopts the new behavior.

dbt 1.12 flags maturing to `true` (set in `dbt_project.yml` `flags:`):

| Flag | Project exhibits it when | Effect when `true` |
|---|---|---|
| `skip_nodes_if_on_run_start_fails` | `on-run-start` hooks exist | A failing hook skips **every** selected resource |
| `require_all_warnings_handled_by_warn_error` | CI uses `--warn-error` / `warn_error: true` | Warnings that were only logged now fail the build (for example `RunResultWarningMessage`) |
| `state_modified_compare_more_unrendered_values` | `state:modified` with `target`-aware config Jinja | Changes the selected set; rebuild the state manifest |
| `validate_macro_args` | Macro YAML lists `arguments:` | Mismatches warn at parse time, fail under `--warn-error` |
| `require_batched_execution_for_custom_microbatch_strategy` | A custom microbatch macro exists | Custom macro must handle batching |

1.12 also adds flags defaulting `false`: `latest_version_pointer_enabled_by_default` ([contracts-and-versions.md](contracts-and-versions.md#versions)), `require_valid_schema_from_generate_schema_name`, `require_sql_header_in_test_configs`, `require_corrected_analysis_fqns`, `allow_jinja_file_extensions`. Leave unless adopting the behavior on purpose.

## Verification

- Baseline deprecation parse saved; dbt-autofix diff reviewed before manual fixes.
- `dbt-core` and `dbt-snowflake` bumped together; packages' `require-dbt-version` checked.
- Flags pinned only for exhibited behavior; none pinned to hide a bug.
- No bare `dbt` install in a 1.x project; `dbt --version` confirmed.

## Sources

- [Upgrading to v1.12](https://docs.getdbt.com/docs/dbt-versions/dbt-upgrade/upgrading-to-v1.12), [Deprecations](https://docs.getdbt.com/reference/deprecations) (`--show-all-deprecations`).
- [Behavior change flags](https://docs.getdbt.com/reference/global-configs/behavior-changes) and the pages for [`skip_nodes_if_on_run_start_fails`](https://docs.getdbt.com/reference/global-configs/behavior-flags/skip_nodes_if_on_run_start_fails), [`require_all_warnings_handled_by_warn_error`](https://docs.getdbt.com/reference/global-configs/behavior-flags/require_all_warnings_handled_by_warn_error), [`validate_macro_args`](https://docs.getdbt.com/reference/global-configs/behavior-flags/validate_macro_args).
- [dbt-autofix](https://github.com/dbt-labs/dbt-autofix) README (`deprecations`, `packages`, `dbt-migrate-1x`); PyPI [`dbt`](https://pypi.org/project/dbt/), [`dbt-core`](https://pypi.org/project/dbt-core/), [`dbt-snowflake`](https://pypi.org/project/dbt-snowflake/).
