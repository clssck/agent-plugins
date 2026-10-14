---
description: Nest generic dbt test parameters under arguments on dbt 1.10.8 and later
condition:
- '(?:^|\n)([ \t]*)-[ \t]+["'']?(?:accepted_values|relationships|(?:dbt_utils|dbt_expectations|dbt_date|audit_helper|elementary|dbt_project_evaluator|re_data|dbt_profiler)\.[a-z_]\w*)["'']?[ \t]*:[ \t\r]*(?:#[^\n]*)?\n(?:[ \t\r]*(?:#[^\n]*)?\n)*(\1[ \t]+)(?:(?:arguments|config|severity|where|limit|warn_if|error_if|fail_calc|store_failures|store_failures_as|tags|meta|enabled|name|description|column_name|test_name|alias|schema|database)(?![\w-])[ \t]*:[^\n]*\n(?:\2[ \t][^\n]*\n|(?!\2[ \t])[ \t\r]*(?:#[^\n]*)?\n)*\2)*(?!(?:arguments|config|severity|where|limit|warn_if|error_if|fail_calc|store_failures|store_failures_as|tags|meta|enabled|name|description|column_name|test_name|alias|schema|database)(?![\w-]))["'']?[A-Za-z_][\w-]*["'']?[ \t]*:(?=[ \t\r\n]|$)'
- '(?:-[ \t]+|[{,][ \t]*)["'']?(?:accepted_values|relationships|(?:dbt_utils|dbt_expectations|dbt_date|audit_helper|elementary|dbt_project_evaluator|re_data|dbt_profiler)\.[a-z_]\w*)["'']?[ \t]*:[ \t]*\{[ \t]*(?:(?:arguments|config|severity|where|limit|warn_if|error_if|fail_calc|store_failures|store_failures_as|tags|meta|enabled|name|description|column_name|test_name|alias|schema|database)(?![\w-])[ \t]*:(?:[^,{}\[\]\n]|\{[^{}\n]*\}|\[[^\[\]\n]*\])*,[ \t]*)*(?!(?:arguments|config|severity|where|limit|warn_if|error_if|fail_calc|store_failures|store_failures_as|tags|meta|enabled|name|description|column_name|test_name|alias|schema|database)(?![\w-]))["'']?[A-Za-z_][\w-]*["'']?[ \t]*:(?=[ \t\r\n]|$)'
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
