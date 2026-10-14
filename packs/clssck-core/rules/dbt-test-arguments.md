---
description: Nest generic dbt test parameters under arguments on dbt 1.10.8 and later
condition:
  - '(?:accepted_values|relationships|(?:dbt_utils|dbt_expectations|dbt_date|audit_helper|elementary)\.\w+)["'']?:[ \t]*\n\s+(?!(?:arguments|config|severity|where|name|description|tags|meta|enabled)\s*:)\w+\s*:'
  - '(?:accepted_values|relationships|(?:dbt_utils|dbt_expectations|dbt_date|audit_helper|elementary)\.\w+)["'']?:\s*\{\s*(?!(?:arguments|config|severity|where|name|description|tags|meta|enabled)\s*:)\w+\s*:'
scope:
- 'tool:edit(**/*.{yml,yaml})'
- 'tool:write(**/*.{yml,yaml})'
interruptMode: never
---

Generic data test parameters belong under `arguments:`. Parameters written beside the test name (`values:`, `to:`, `field:`, `expression:`) raise `MissingArgumentsPropertyInGenericTestDeprecation`.

- Check `dbt --version` and `require_generic_test_arguments_property` first.
- dbt >= 1.10.8: MUST nest parameters under `arguments:`, even when the file around them still uses the legacy form. The flag defaults to `true` there.
- dbt 1.10.5-1.10.7: nest only when `flags: require_generic_test_arguments_property: true` is set in `dbt_project.yml`; with the default `false` the nested form warns instead.
- Older than 1.10.5: keep top-level parameters.
- `config`, `severity`, `where`, `store_failures`, `name`, and `description` stay beside `arguments:`, not inside it.
- The same applies to package tests such as `dbt_utils.expression_is_true` and `dbt_utils.accepted_range`, under `tests:` or `data_tests:`.
- Legacy file on a modern dbt? Migrate the tests you touch; `uvx dbt-autofix deprecations --dry-run` lists the rest.
