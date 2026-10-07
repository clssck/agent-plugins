# Reference: Reach & Frequency (Outline)

> ⚠️ This is an **outline pattern** — not fully validated. Use as a starting point and verify against your data.

## Template Spec Structure

```yaml
api_version: "2.0.0"
spec_type: template
name: reach_frequency_analysis_v1
version: "2024_01"
type: sql_analysis
description: >
  Measure unique reach and average frequency of ad exposures
  across matched audiences.
parameters:
  - name: join_column
    description: "Column to match records on (e.g., HASHED_EMAIL)"
    required: true
    type: string
  - name: campaign_column
    description: "Column identifying the campaign (e.g., CAMPAIGN_ID)"
    required: true
    type: string
  - name: exposure_column
    description: "Column with exposure events to count (e.g., IMPRESSION_ID or use row count)"
    required: false
    type: string
template: |
  {# Standard table/alias setup: handles both local data (my_table) and two-provider (source_table[1]) cases #}
  {% set consumer_table = my_table[0] if my_table and my_table|length > 0 else source_table[1] %}
  {% set provider_table = source_table[0] %}
  {% set provider_alias = 'p1' %}
  {% set consumer_alias = 'c1' if (my_table and my_table|length > 0) else 'p2' %}

  SELECT
    {{ provider_alias }}.{{ campaign_column | sqlsafe }} AS campaign,
    COUNT(DISTINCT {{ provider_alias }}.{{ join_column | sqlsafe }}) AS unique_reach,
    COUNT(*) AS total_impressions,
    ROUND(COUNT(*) / NULLIF(COUNT(DISTINCT {{ provider_alias }}.{{ join_column | sqlsafe }}), 0), 2) AS avg_frequency
  FROM identifier({{ provider_table }}) {{ provider_alias }}
  INNER JOIN identifier({{ consumer_table }}) {{ consumer_alias }}
    ON {{ provider_alias }}.{{ join_column | sqlsafe }} = {{ consumer_alias }}.{{ join_column | sqlsafe }}
  GROUP BY {{ provider_alias }}.{{ campaign_column | sqlsafe }}
  ORDER BY unique_reach DESC
```

## Key SQL Patterns

- **Reach** = `COUNT(DISTINCT join_column)` — unique users exposed
- **Frequency** = `COUNT(*) / reach` — average exposures per user
- Often broken down by campaign, channel, or time period
- May include frequency bins (1x, 2-3x, 4-5x, 6+)
