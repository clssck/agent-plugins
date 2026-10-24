---
description: Nest generic dbt test parameters under arguments on dbt 1.10.8 and later
condition:
  - "\\b(?:accepted_values|relationships)\\s*:"
  - "\\b(?:dbt_utils|dbt_expectations|dbt_date|audit_helper|elementary)\\.\\w+\\s*:"
  - "\\b(?:data_tests|tests)\\s*:"
scope: "tool:edit(**/*.{yml,yaml}), tool:write(**/*.{yml,yaml})"
interruptMode: never
---

Generic data test parameters belong under `arguments:`. Parameters written beside the test name (`values:`, `to:`, `field:`, `expression:`) raise `MissingArgumentsPropertyInGenericTestDeprecation`.

## Check the version first

Check `dbt --version` and `require_generic_test_arguments_property` before choosing a form.

|dbt version|Parameters|
|---|---|
|>= 1.10.8|MUST nest under `arguments:`, even when the file around them still uses the legacy form. The flag defaults to `true`.|
|1.10.5–1.10.7|Nest only when `flags: require_generic_test_arguments_property: true` is set in `dbt_project.yml`; with the default `false` the nested form warns instead.|
|< 1.10.5|Keep top-level parameters.|

## Nest parameters

Applies under `tests:` or `data_tests:`, including package tests such as `dbt_utils.expression_is_true` and `dbt_utils.accepted_range`.

```yaml
# Bad
- accepted_values:
    values: ["placed", "shipped", "returned"]
- relationships:
    to: ref('customers')
    field: id

# Good
- accepted_values:
    arguments:
      values: ["placed", "shipped", "returned"]
- relationships:
    arguments:
      to: ref('customers')
      field: id
```

## Keep test properties beside `arguments:`

`config`, `severity`, `where`, `store_failures`, `name`, and `description` stay beside `arguments:`, not inside it.

```yaml
# Bad
- dbt_utils.expression_is_true:
    arguments:
      expression: "amount >= 0"
      config:
        severity: warn

# Good
- dbt_utils.expression_is_true:
    arguments:
      expression: "amount >= 0"
    config:
      severity: warn
```

## Legacy files

Legacy file on a modern dbt? Migrate the tests you touch; `uvx dbt-autofix deprecations --dry-run` lists the rest.

## Exceptions

- Tests already written with `arguments:` and `config:` beside it are compliant; they need no edit.
- Files on dbt < 1.10.5, or 1.10.5–1.10.7 without the flag, keep top-level parameters.
- Singular tests, model-level `config:`, and literal examples in docs need no change.

This reminder matches any generic-test declaration or test block, so it can appear for compliant YAML. Decide nesting from the actual YAML and the dbt version, not from the match.
