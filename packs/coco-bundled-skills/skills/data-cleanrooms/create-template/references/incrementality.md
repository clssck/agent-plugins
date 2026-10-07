# Reference: Incrementality / Lift Measurement (Outline)

> ⚠️ This is an **outline pattern** — not fully validated. Use as a starting point and verify against your data.

## Template Spec Structure

```yaml
api_version: "2.0.0"
spec_type: template
name: incrementality_lift_analysis_v1
version: "2024_01"
type: sql_analysis
description: >
  Measure incremental lift by comparing conversion rates between
  test (exposed) and control (unexposed) groups.
parameters:
  - name: join_column
    description: "Column to match records on (e.g., HASHED_EMAIL)"
    required: true
    type: string
  - name: group_column
    description: "Column indicating test/control group assignment"
    required: true
    type: string
  - name: conversion_column
    description: "Column with conversion value or indicator"
    required: true
    type: string
template: |
  {# Standard table/alias setup: handles both local data (my_table) and two-provider (source_table[1]) cases #}
  {% set consumer_table = my_table[0] if my_table and my_table|length > 0 else source_table[1] %}
  {% set provider_table = source_table[0] %}
  {% set provider_alias = 'p1' %}
  {% set consumer_alias = 'c1' if (my_table and my_table|length > 0) else 'p2' %}

  WITH matched AS (
    SELECT
      {{ provider_alias }}.{{ join_column | sqlsafe }} AS user_id,
      {{ provider_alias }}.{{ group_column | sqlsafe }} AS test_group,
      {{ consumer_alias }}.{{ conversion_column | sqlsafe }} AS conversion_value
    FROM identifier({{ provider_table }}) {{ provider_alias }}
    INNER JOIN identifier({{ consumer_table }}) {{ consumer_alias }}
      ON {{ provider_alias }}.{{ join_column | sqlsafe }} = {{ consumer_alias }}.{{ join_column | sqlsafe }}
  )
  SELECT
    test_group,
    COUNT(*) AS group_size,
    SUM(CASE WHEN conversion_value > 0 THEN 1 ELSE 0 END) AS converters,
    ROUND(SUM(CASE WHEN conversion_value > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS conversion_rate_pct,
    ROUND(SUM(conversion_value), 2) AS total_conversion_value
  FROM matched
  GROUP BY test_group
  ORDER BY test_group
```

## Key SQL Patterns

- **Test/Control split:** Requires `TEST_GROUP` column (typically `'test'` / `'control'`)
- **Conversion rate:** `converters / group_size` for each group
- **Lift:** `(test_rate - control_rate) / control_rate * 100`
- Statistical significance checks are advanced — consider code_spec for Z-test/chi-square
