---
name: warehouse
description: "Warehouse configuration, DDL, Gen2, adaptive warehouses, adaptive compute, compute, MAX_QUERY_PERFORMANCE_LEVEL, QUERY_THROUGHPUT_MULTIPLIER, performance tuning, sizing, credit-per-hour rates, resume behavior, region availability, Snowpark-optimized limitations, warehouse conversion, warehouse migration, convert to adaptive, migrate to adaptive, switch to adaptive, analytical workload, analytical queries, analytical pipeline, transformation workload, data loading pipeline, ETL workload, batch processing, warehouse suitability, warehouse fit, good candidate for adaptive, should I use adaptive, is adaptive right, why didn't adaptive work, warehouse spilling, warehouse performance issues, heavy spilling on warehouse, warehouse is slow, which warehouses to migrate. Not for cost analytics or warehouse spend (cost-intelligence) or billing."
---

# Warehouse Skill Router

Route warehouse-related questions to the appropriate sub-skill.

> This router currently handles two sub-skills: gen2-warehouse and adaptive-warehouse. Additional sub-skills (sizing, monitoring, optimization, etc.) will be added here as they are developed.

## When to Use

Activate this skill when the user asks about any of:

- **Gen2 keywords**: "gen2", "generation 2", "GENERATION = '2'", "gen2 credit rate", "convert to gen2", "gen1 to gen2", "gen2 regions", "gen2 limitations", "gen2 performance", "warehouse generation", "gen2 benchmark", "compare gen1 gen2"
- **Performance keywords**: "DML performance", "slow DELETE", "slow MERGE", "slow resume", "resume time", "warehouse resume", "warehouse is slow", "speed up warehouse"
- **Warehouse creation/management**: "create warehouse", "alter warehouse", "warehouse size", "warehouse generation"
- **Warehouse cost/credits**: "warehouse credits", "warehouse cost", "how much is a warehouse", "warehouse pricing", "credits per hour"
- **Adaptive keywords**: "adaptive", "adaptive compute", "compute", "adaptive warehouse", "CREATE ADAPTIVE WAREHOUSE", "WAREHOUSE_TYPE = 'ADAPTIVE'", "MAX_QUERY_PERFORMANCE_LEVEL", "QUERY_THROUGHPUT_MULTIPLIER", "convert to adaptive", "adaptive warehouse billing"

## Critical: Always Load This Skill

**MANDATORY**: This skill MUST be loaded for ANY question that mentions:
- Warehouse types: "adaptive", "standard", "Gen2", "interactive", "Snowpark-optimized"
- Warehouse parameters: MAX_QUERY_PERFORMANCE_LEVEL, QUERY_THROUGHPUT_MULTIPLIER
- Warehouse operations: "convert warehouse", "create warehouse", "alter warehouse", "migrate warehouse"
- Warehouse suitability: "good fit", "should I use", "why didn't [X] work", "is adaptive right"
- Specific warehouse names with configuration questions

**Even if the question also mentions**:
- Performance issues (spilling, slow queries, cache problems)
- Cost concerns
- Workload characteristics
- Other Snowflake features

**The warehouse context takes precedence**. Load this skill first, then it will route to sub-skills or other skills as needed.

## When NOT to Use

**Do NOT use this skill for Interactive Warehouse Questions.**
Questions like "what is an interactive warehouse" or "how do I use an interactive warehouse" should use the `interactive-warehouse` skill.

**Do NOT use this skill for warehouse spending or cost analytics.**
Questions like "how much did my warehouse spend?" or "show me warehouse credits used" belong to the `cost-intelligence` skill, which queries `SNOWFLAKE.ACCOUNT_USAGE`.
This skill covers warehouse configuration, DDL, Gen2, adaptive warehouses, and performance only.

## Routing

Match the user's question to keywords and load the corresponding sub-skill.

| Keywords | Sub-skill to Load |
|----------|-------------------|
| interactive warehouse, create interactive warehouse, add tables to warehouse, remove tables from warehouse, resume interactive warehouse, suspend interactive warehouse | **Route to** `snowflake-interactive` skill |
| adaptive, adaptive compute, compute, adaptive warehouse, CREATE ADAPTIVE WAREHOUSE, WAREHOUSE_TYPE = 'ADAPTIVE', convert to adaptive, MAX_QUERY_PERFORMANCE_LEVEL, QUERY_THROUGHPUT_MULTIPLIER, adaptive billing, adaptive tuning | **Load** `adaptive-warehouse/SKILL.md` |
| gen2, generation 2, GENERATION = '2', create gen2, convert to gen2, gen1 to gen2, gen2 credit rate, gen2 regions, gen2 limitations, gen2 performance, gen2 benchmark, compare gen1 gen2 | **Load** `gen2-warehouse/SKILL.md` |
| DML performance, slow DELETE, slow MERGE, slow UPDATE, slow resume, resume time, warehouse resume, warehouse is slow, speed up warehouse, improve warehouse performance | **Load** `gen2-warehouse/SKILL.md` |
| warehouse creation, warehouse size, warehouse generation, alter warehouse | **Load** `gen2-warehouse/SKILL.md` |
| warehouse credits, warehouse cost, how much is a warehouse, warehouse pricing, credits per hour | **Load** `gen2-warehouse/SKILL.md` |

> **Note:** Interactive warehouse questions route to the `snowflake-interactive` skill. Adaptive warehouse questions route to `adaptive-warehouse/SKILL.md`. All other warehouse intents route to `gen2-warehouse/SKILL.md`. As new sub-skills are added, this routing table will expand.

## Workflow

### Step 1: Look Up the Warehouse (if a specific warehouse is named)

If the user mentions a **specific warehouse by name**, you **MUST** run a lookup before routing:

```sql
SHOW WAREHOUSES LIKE '<warehouse_name>';
```

**IMPORTANT:** Always use `SHOW WAREHOUSES LIKE '<name>'` with the LIKE clause — do NOT use bare `SHOW WAREHOUSES` as it may fail with `ENABLE_ERROR_ON_FETCH_FALLBACK` errors on some accounts.

From the result, extract and note these columns:

| Column | Why It Matters |
|--------|---------------|
| `type` (warehouse_type) | Determines routing: INTERACTIVE → interactive skill, ADAPTIVE → adaptive sub-skill, SNOWPARK-OPTIMIZED → Gen1-only (not supported in Gen2 or Adaptive), STANDARD → eligible for Gen2 |
| `generation` | If already `2`, tell the user it's already Gen2. If `1` or empty, may be a Gen2 candidate |
| `size` | Gen2 supports XSMALL through X4LARGE only. X5LARGE and X6LARGE are NOT supported |
| `resource_constraint` | Shows the resource constraint variant (e.g., `STANDARD_GEN_1`, `STANDARD_GEN_2`, `MEMORY_16X`). Confirms generation and warehouse configuration |

**Routing based on lookup results:**

| Condition | Action |
|-----------|--------|
| `type` = `INTERACTIVE` | **Stop.** Tell the user this is an Interactive warehouse — Gen2 does not apply. Route to the `snowflake-interactive` skill for interactive warehouse questions |
| `type` = `ADAPTIVE` | Load `adaptive-warehouse/SKILL.md` |
| `type` = `SNOWPARK-OPTIMIZED` | **Stop.** Tell the user Snowpark-Optimized is a Gen1-only warehouse type — Gen2 and Adaptive are not supported. See Gen2 limitations in `gen2-warehouse/SKILL.md` |
| `generation` = `2` | Tell the user the warehouse is already Gen2. No conversion needed |
| `size` = `X5LARGE` or `X6LARGE` | Tell the user Gen2 does not support this size. Suggest benchmarking on a Gen2 X4LARGE |
| `type` = `STANDARD` and `generation` = `1` (or empty) | Eligible for Gen2. Proceed with keyword-based routing below |

**IMPORTANT:** Do NOT skip this lookup. Even if the user's question contains Gen2 keywords, the warehouse type takes priority — an INTERACTIVE warehouse should never receive Gen2 advice.

### Step 2: Detect Intent and Route

If no specific warehouse was named, or after the lookup confirms the warehouse is a STANDARD warehouse (Gen1 or Gen2), match the user's question to keywords and load the matching sub-skill.

### Step 3: Execute Sub-skill

Follow the loaded sub-skill's workflow completely. Each sub-skill is self-contained with its own references, workflows, and stopping points.

## Sub-skills

| Sub-skill | Skill | Purpose |
|-----------|-------|---------|
| Interactive Warehouse | `snowflake-interactive` (full skill name — not a sub-skill of this router) | Interactive warehouse creation, table management, resume/suspend |
| Adaptive Warehouse | `adaptive-warehouse/SKILL.md` | Adaptive warehouse creation, conversion, parameters, limitations, billing, tuning, analysis |
| Gen2 Warehouse | `gen2-warehouse/SKILL.md` | Gen2 explanation, creation, conversion, limitations, regions, costs, benchmarking, performance recommendations |

## Stopping Points

- If intent is ambiguous and cannot be mapped to a sub-skill, ask the user to clarify before loading any sub-skill
- Honour all stopping points defined within loaded sub-skills
