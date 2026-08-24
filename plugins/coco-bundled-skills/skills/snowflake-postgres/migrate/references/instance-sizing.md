# Snowflake Postgres Instance Sizing Guide

## Overview

This guide explains how the migration assessment should form an initial Snowflake Postgres recommendation from source-database facts.

It is intentionally **not** the source of truth for supported instance sizes or platform limits.

- For valid compute families, storage bounds, HA restrictions, and CREATE/ALTER syntax, use `../../references/instance-options.md`.
- Treat the guidance here as an operator-friendly heuristic, not an official Snowflake sizing guarantee.

## Recommendation Inputs

Use the assessment results to build a recommendation from:

1. **Source size and growth headroom**: current size, expected near-term growth, and migration-phase scratch space.
2. **Complexity and workload shape**: PostGIS, pgvector, large object counts, partitions, custom types, high table counts, or other signs that memory/CPU headroom matters.
3. **Migration method**: logical replication, pg_dump/restore, hybrid, or large-db workflow.
4. **Operational context**: existing replicas, logical slots, CDC consumers, or application traffic that indicate the source is busy and sensitive.
5. **User intent**: whether the target is temporary, staging, or the future production system.
6. **Availability expectations**: whether the user says the target needs production-grade uptime.

## Recommendation Policy

### Compute Family

- Recommend **one** compute family and briefly explain why it is the best starting point.
- Offer at most two alternatives:
  - a cheaper option with less headroom
  - a faster or safer option with more headroom
- Always validate any named family against `../../references/instance-options.md` before presenting it.
- Use HIGHMEM only when the assessment suggests a memory-heavy workload; otherwise prefer a STANDARD family.

### Storage

Storage sizing in the assessment is a heuristic to reduce migration foot guns, not a documented Snowflake recommendation.

Use an initial allocation of:

```text
recommended_storage = source_size * multiplier + headroom
```

Where the multiplier and headroom are chosen conservatively for the migration phase. Explain the calculation in the report so the user can sanity-check it.

When presenting the result, remind the user that the authoritative storage rules still live in `../../references/instance-options.md`.

### High Availability

Keep the HA recommendation separate from the instance creation timing:

- Do **not** assume source SQL can prove the system is production or already highly available.
- Use source signals only as hints, then ask the user when production intent is unclear.
- Default to **creating the migration target without HA** unless the user explicitly wants protected capacity from the start.
- If the target will become the production system, recommend **enabling HA after validation and before cutover** rather than at the initial target creation step.

That timing keeps migration costs lower while avoiding a newly live production target without failover protection.

## Recommendation Output Format

The assessment should emit recommendation data in a structure like:

```json
{
  "instance_recommendations": {
    "compute_pool": {
      "recommended": "<compute_family>",
      "alternatives": [
        {
          "pool": "<lower_cost_family>",
          "pros": ["Lower cost"],
          "cons": ["Less headroom"]
        },
        {
          "pool": "<higher_headroom_family>",
          "pros": ["More headroom"],
          "cons": ["Higher cost"]
        }
      ],
      "rationale": "..."
    },
    "storage": {
      "recommended_gb": 0,
      "minimum_gb": 0,
      "calculation": "..."
    },
    "high_availability": {
      "recommended": false,
      "rationale": "...",
      "timing": "after validation, before cutover"
    }
  }
}
```

## How To Present It

After the assessment:

1. Present the recommended compute family, storage, and HA posture with clear rationale.
2. Highlight any operational warnings that influenced the recommendation, such as existing replicas, logical slots, or heavy app traffic.
3. Point the user to `../../references/instance-options.md` for the full valid option matrix and platform limits.
4. Ask for confirmation before creating or altering any billable instance.

## Foot Guns To Surface

The assessment should explicitly call out:

- existing replication consumers that may need coordination
- active application traffic that suggests the source is not idle
- low remaining replication-slot or WAL-sender capacity
- the risk of under-sizing the target during restore or initial sync
- the difference between **recommending** HA and **turning HA on immediately**

Those notes are often more useful than the raw recommendation itself.
