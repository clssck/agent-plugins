# Reference: Activation Template

Full pattern for exporting matched audience segments to collaborators.

## Template Spec

```yaml
api_version: "2.0.0"
spec_type: template
name: audience_activation_segment_v1
version: "2024_01"
type: sql_activation
description: >
  Select matched records between provider and consumer datasets and export
  them as a named segment for activation (e.g., ad targeting, campaign delivery).
methodology: >
  Joins provider and consumer datasets on the specified join column, then
  selects the activation column (identifier) for export. Supports an optional
  WHERE clause for segment filtering.
parameters:
  - name: join_column
    description: "Column to match records on (e.g., HASHED_EMAIL)"
    required: true
    type: string
  - name: activation_column
    description: "Column to include in the exported segment (e.g., HASHED_EMAIL)"
    required: true
    type: string
  - name: where_clause
    description: "Optional SQL WHERE condition to filter the segment (e.g., REGION = 'US-EAST')"
    required: false
    type: string
template: |
  {# Standard table/alias setup: handles both local data (my_table) and two-provider (source_table[1]) cases #}
  {% set consumer_table = my_table[0] if my_table and my_table|length > 0 else source_table[1] %}
  {% set provider_table = source_table[0] %}
  {% set provider_alias = 'p1' %}
  {% set consumer_alias = 'c1' if (my_table and my_table|length > 0) else 'p2' %}

  BEGIN
    CREATE OR REPLACE TABLE cleanroom.{{ result_table | sqlsafe }} AS
    SELECT DISTINCT
      {{ consumer_alias }}.{{ activation_column | sqlsafe | activation_policy }} AS activation_id
    FROM identifier({{ provider_table }}) {{ provider_alias }}
    INNER JOIN identifier({{ consumer_table }}) {{ consumer_alias }}
      ON {{ provider_alias }}.{{ join_column | sqlsafe | join_policy }} = {{ consumer_alias }}.{{ join_column | sqlsafe | join_policy }}
    {% if where_clause %}
    WHERE {{ where_clause | sqlsafe }}
    {% endif %};
    RETURN 'analysis_results';
  END;

> **Required structure for sql_activation templates:** The template body MUST use `BEGIN / CREATE OR REPLACE TABLE cleanroom.{{ result_table | sqlsafe }} AS ... / RETURN 'analysis_results'; / END;`. A plain SELECT (without BEGIN/CREATE OR REPLACE TABLE/RETURN) will be rejected. `result_table` is a reserved DCR Jinja variable automatically injected at run time — do not declare it as a parameter.
```

## Key Differences from Analysis Templates

| Aspect | sql_analysis | sql_activation |
|--------|-------------|----------------|
| `type` field | `sql_analysis` | `sql_activation` |
| Purpose | Returns result set (counts, metrics) | Produces identifiers for export |
| Output | Query results shown to user | Segment delivered to destination |
| Activation config | Not applicable | Configured in analysis spec (sibling of `arguments`) |

## Activation Destination Configuration

The activation destination is NOT part of the template_spec. It's configured in the **analysis spec** when running the template:

```yaml
arguments:
  join_column: HASHED_EMAIL
  activation_column: HASHED_EMAIL
activation:
  - template_name: audience_activation_segment_v1
    template_version: "2024_01"
    activation_target:
      type: snowflake_collaborator
      collaborator_alias: "partner_alias"
      segment_name: "holiday_campaign_segment"
```

**Common mistake:** Nesting `activation` inside `arguments`. It is a **sibling** of `arguments`, not a child.

## Narration Script

1. **Why sql_activation:** "This is an activation template because the goal is to export identifiers for downstream use (ad targeting, campaign delivery), not to return aggregate metrics."
2. **Why activation_column:** "The activation column is the identifier that gets exported — typically the same hashed identifier used for matching."
3. **Where clause:** "The optional WHERE clause lets you filter the segment — for example, only users in a specific region or who match certain criteria."
4. **Destination is separate:** "The activation destination (which collaborator receives the segment, what to name it) is configured when you *run* the template, not in the template itself."

## Parameter Guide

| Parameter | For Business Users | For Data Engineers |
|-----------|-------------------|-------------------|
| `join_column` | "Which column matches customers between datasets?" | "Equi-join key for INNER JOIN between source and consumer tables." |
| `activation_column` | "Which identifier should be exported for targeting?" | "Column selected for the activation segment output." |
| `where_clause` | "Want to filter to a specific audience? E.g., 'REGION = US-EAST'" | "Raw SQL WHERE predicate, injected into template. Accepts arbitrary SQL — treat as a convenience parameter for trusted collaborators only. A malicious value can influence query logic beyond the intended filter." |
