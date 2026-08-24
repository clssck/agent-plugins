# Reference: Audience Overlap Template

Full pattern for the most common DCR use case — counting matched records between two datasets.

## Template Spec

```yaml
api_version: "2.0.0"
spec_type: template
name: audience_overlap_email_v1
version: "2024_01"
type: sql_analysis
description: >
  Count the overlap between two datasets by matching on a join column.
  Returns the number of distinct matched identifiers, optionally grouped
  by a dimension column.
methodology: >
  Performs an INNER JOIN on the specified join column between the provider
  and consumer datasets. Counts distinct matches. Supports optional grouping
  by a dimension (e.g., region, age band) and a minimum count threshold
  for privacy.
parameters:
  - name: join_column
    description: "Column to match records on (e.g., HASHED_EMAIL)"
    required: true
    type: string
  - name: dimension_column
    description: "Optional column to group results by (e.g., REGION)"
    required: false
    type: string
  - name: min_count
    description: "Minimum overlap count to include in results (privacy threshold)"
    required: false
    type: integer
    default: 10
template: |
  {# Standard table/alias setup: handles both local data (my_table) and two-provider (source_table[1]) cases #}
  {% set consumer_table = my_table[0] if my_table and my_table|length > 0 else source_table[1] %}
  {% set provider_table = source_table[0] %}
  {% set provider_alias = 'p1' %}
  {% set consumer_alias = 'c1' if (my_table and my_table|length > 0) else 'p2' %}

  SELECT
    {% if dimension_column %}
      {{ provider_alias }}.{{ dimension_column | sqlsafe }} AS dimension,
    {% endif %}
    COUNT(DISTINCT {{ provider_alias }}.{{ join_column | sqlsafe }}) AS overlap_count
  FROM identifier({{ provider_table }}) {{ provider_alias }}
  INNER JOIN identifier({{ consumer_table }}) {{ consumer_alias }}
    ON {{ provider_alias }}.{{ join_column | sqlsafe }} = {{ consumer_alias }}.{{ join_column | sqlsafe }}
  {% if dimension_column %}
  GROUP BY {{ provider_alias }}.{{ dimension_column | sqlsafe }}
  {% endif %}
  {% if min_count %}
  HAVING COUNT(DISTINCT {{ provider_alias }}.{{ join_column | sqlsafe }}) >= {{ min_count }}
  {% endif %}
  ORDER BY overlap_count DESC
```

## Waterfall Join Variant

When multiple join columns are available (e.g., email + phone), use waterfall logic:

```yaml
template: |
  {# Standard table/alias setup #}
  {% set consumer_table = my_table[0] if my_table and my_table|length > 0 else source_table[1] %}
  {% set provider_table = source_table[0] %}
  {% set provider_alias = 'p1' %}
  {% set consumer_alias = 'c1' if (my_table and my_table|length > 0) else 'p2' %}

  WITH email_matches AS (
    SELECT DISTINCT
      {{ provider_alias }}.{{ primary_join | sqlsafe }} AS matched_id,
      'email' AS match_type
    FROM identifier({{ provider_table }}) {{ provider_alias }}
    INNER JOIN identifier({{ consumer_table }}) {{ consumer_alias }}
      ON {{ provider_alias }}.{{ primary_join | sqlsafe }} = {{ consumer_alias }}.{{ primary_join | sqlsafe }}
  ),
  phone_matches AS (
    SELECT DISTINCT
      {{ provider_alias }}.{{ secondary_join | sqlsafe }} AS matched_id,
      'phone' AS match_type
    FROM identifier({{ provider_table }}) {{ provider_alias }}
    INNER JOIN identifier({{ consumer_table }}) {{ consumer_alias }}
      ON {{ provider_alias }}.{{ secondary_join | sqlsafe }} = {{ consumer_alias }}.{{ secondary_join | sqlsafe }}
    WHERE {{ provider_alias }}.{{ primary_join | sqlsafe }} NOT IN (
      SELECT matched_id FROM email_matches
    )
  ),
  all_matches AS (
    SELECT * FROM email_matches
    UNION ALL
    SELECT * FROM phone_matches
  )
  SELECT
    match_type,
    COUNT(*) AS match_count
  FROM all_matches
  GROUP BY match_type
  ORDER BY match_count DESC
```

## Narration Script

When generating this template, explain:

1. **Why INNER JOIN:** "I'm using an INNER JOIN because we only want records that exist in both datasets — that's the overlap."
2. **Why COUNT DISTINCT:** "COUNT DISTINCT ensures each identifier is counted once, even if there are duplicate rows."
3. **Why min_count:** "The minimum count threshold is a privacy control — it prevents reporting overlap counts that are too small and could identify individuals."
4. **Why dimension grouping:** "Grouping by a dimension like REGION lets you see where your audience overlap is strongest."
5. **Waterfall logic:** "I'm matching on email first, then trying phone only for records that didn't match on email. This avoids double-counting."

## Parameter Guide

| Parameter | For Business Users | For Data Engineers |
|-----------|-------------------|-------------------|
| `join_column` | "Which column identifies your customers? Usually a hashed email or phone." | "Equi-join key — must exist in both provider_table (source_table[0]) and consumer_table (source_table[1] or my_table[0])." |
| `dimension_column` | "Want to break results down by region, age group, etc.?" | "Optional GROUP BY column from provider_table (source_table[0])." |
| `min_count` | "Minimum overlap to show (protects small groups)." | "HAVING threshold, default 10." |
