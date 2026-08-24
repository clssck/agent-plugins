---
name: multi-path-metrics
description: Multi-path metric reference — using_relationships disambiguates which join path a metric should follow when a fact has multiple FKs to the same dimension.
parent_skill: sv-modeling-patterns
---

# Multi-Path Metrics (`using_relationships`)

## How it works

A fact table can have **two foreign keys that both point to the same dimension** — flights with departure and arrival cities both joining a weather/airport dimension; orders with ship-to and bill-to addresses both joining a customer-address dimension.

Without disambiguation, the SV engine errors: `Multi-path relationship between dimension entity 'X' and base metric entity 'Y'`.

Two pieces:

1. **Define one relationship per role** (departure_weather, arrival_weather) — both pointing to the same physical dimension table.
2. **Add `using_relationships: [<name>]` on each metric** to declare which path to follow when that metric is broken down by an ambiguous dimension.

Each metric can use a different `using_relationships` path, enabling side-by-side comparisons (e.g. `late_departure_count` and `late_arrival_count` in the same query, both broken down by `weather.condition`).

## Snippet

```yaml
relationships:
  # Two paths from flights to weather — one per city role
  - name: flight_departure_weather
    left_table: flights
    right_table: weather
    relationship_columns:
      - { left_column: DEPARTURE_CITY, right_column: CITY_CODE }
      - left_column: DEPARTURE_TIME
        type: range
        right_range: { start_column: START_DATE, end_column: END_DATE }
  - name: flight_arrival_weather
    left_table: flights
    right_table: weather
    relationship_columns:
      - { left_column: ARRIVAL_CITY, right_column: CITY_CODE }
      - left_column: ARRIVAL_TIME
        type: range
        right_range: { start_column: START_DATE, end_column: END_DATE }

tables:
  - name: flights
    metrics:
      - name: late_departure_count
        synonyms: [late departures, delayed departures, flights late at departure]
        description: Late flights broken down by departure weather
        expr: COUNT_IF(IS_LATE)
        # Tells the engine which path to follow when grouping by an ambiguous dim
        using_relationships:
          - flight_departure_weather
      - name: late_arrival_count
        synonyms: [late arrivals, delayed arrivals, flights late at arrival]
        description: Late flights broken down by arrival weather
        expr: COUNT_IF(IS_LATE)
        using_relationships:
          - flight_arrival_weather
```

## Gotchas

- **Without `using_relationships`, the metric cannot be broken down by the ambiguous dimension at all.** Adding the dimension to the query produces a `Multi-path relationship` error. The fix is always `using_relationships`, never picking one of the relationships at random.
- **`using_relationships` specifies a path prefix** from the metric's entity to a disambiguating entity. The named relationship must exist in the top-level `relationships:` block.
- **Plain metrics (no `using_relationships`) are still fine** for queries that don't touch the ambiguous dimension. `total_flights: COUNT(flight_id)` works as long as the query doesn't break it down by `weather.condition`.
- **One metric per role.** You typically end up with `<metric>_departure` and `<metric>_arrival` (or `_ship_to` / `_bill_to`) variants — that's by design, so the agent can include both in one query for side-by-side analysis.

## Docs

- [Specifying the relationship for a metric when multiple relationship paths exist](https://docs.snowflake.com/en/user-guide/views-semantic/sql#specifying-the-relationship-for-a-metric-when-multiple-relationship-paths-exist)
- [YAML specification for semantic views](https://docs.snowflake.com/en/user-guide/views-semantic/semantic-view-yaml-spec)
