# Reference: Multi-Touch Attribution (Outline)

> ⚠️ This is an **outline pattern** — not fully validated. Use as a starting point and verify against your data.

## Template Spec Structure

```yaml
api_version: "2.0.0"
spec_type: template
name: multi_touch_attribution_v1
version: "2024_01"
type: sql_analysis
description: >
  Assign conversion credit across multiple ad touchpoints using
  a linear attribution model.
parameters:
  - name: join_column
    description: "Column to match records on (e.g., HASHED_EMAIL)"
    required: true
    type: string
  - name: channel_column
    description: "Column identifying the ad channel or touchpoint"
    required: true
    type: string
  - name: timestamp_column
    description: "Column with touchpoint timestamp for ordering"
    required: true
    type: string
  - name: conversion_value_column
    description: "Column with conversion value to attribute"
    required: true
    type: string
template: |
  {# Standard table/alias setup: handles both local data (my_table) and two-provider (source_table[1]) cases #}
  {% set consumer_table = my_table[0] if my_table and my_table|length > 0 else source_table[1] %}
  {% set provider_table = source_table[0] %}
  {% set provider_alias = 'p1' %}
  {% set consumer_alias = 'c1' if (my_table and my_table|length > 0) else 'p2' %}

  WITH touchpoints AS (
    SELECT
      {{ provider_alias }}.{{ join_column | sqlsafe }} AS user_id,
      {{ provider_alias }}.{{ channel_column | sqlsafe }} AS channel,
      {{ provider_alias }}.{{ timestamp_column | sqlsafe }} AS touch_time,
      COUNT(*) OVER (PARTITION BY {{ provider_alias }}.{{ join_column | sqlsafe }}) AS touch_count
    FROM identifier({{ provider_table }}) {{ provider_alias }}
    INNER JOIN identifier({{ consumer_table }}) {{ consumer_alias }}
      ON {{ provider_alias }}.{{ join_column | sqlsafe }} = {{ consumer_alias }}.{{ join_column | sqlsafe }}
  ),
  conversions AS (
    SELECT
      {{ consumer_alias }}.{{ join_column | sqlsafe }} AS user_id,
      {{ consumer_alias }}.{{ conversion_value_column | sqlsafe }} AS conversion_value
    FROM identifier({{ consumer_table }}) {{ consumer_alias }}
    WHERE {{ consumer_alias }}.{{ conversion_value_column | sqlsafe }} > 0
  ),
  attributed AS (
    SELECT
      t.channel,
      t.user_id,
      cv.conversion_value / t.touch_count AS attributed_value
    FROM touchpoints t
    INNER JOIN conversions cv ON t.user_id = cv.user_id
  )
  SELECT
    channel,
    COUNT(DISTINCT user_id) AS converters,
    ROUND(SUM(attributed_value), 2) AS total_attributed_value,
    ROUND(AVG(attributed_value), 2) AS avg_attributed_value
  FROM attributed
  GROUP BY channel
  ORDER BY total_attributed_value DESC
```

## Key SQL Patterns

- **Linear attribution:** Equal credit split across all touchpoints (`value / touch_count`)
- **Window functions:** `COUNT(*) OVER (PARTITION BY user)` for per-user touchpoint counting
- **Advanced models** (first-touch, last-touch, time-decay, position-based) need different weighting logic
- For ML-based attribution (e.g., Shapley values), handoff to code-spec skill
