---
name: gen2-warehouse
description: "Gen2 warehouse questions: creating, converting, performance, limitations, regions, credit costs, and benchmarking. Also covers performance concerns where Gen2 may help."
---

# Snowflake Generation 2 Standard Warehouses

## What is Gen2?

Gen2 is an updated version of the standard virtual warehouse focused on **improving performance** for analytics and data engineering workloads. It is built on faster hardware and intelligent software optimizations.

**Key points:**
- Gen2 is NOT a new warehouse type — it is the same STANDARD warehouse type, just a different generation
- Gen2 combines **hardware and software improvements** for better performance at a comparable cost
- Gen2 is NOT a cost-saving feature — it delivers better performance, not lower bills
- Queries finish faster; you can do more work concurrently
- Significant DML improvements: DELETE, UPDATE, MERGE operations, and table scan operations
- Gen2 has its own credit-per-hour rates by warehouse size — see the [Cost and Billing](#cost-and-billing) section or the [Snowflake Credit Consumption Table](https://www.snowflake.com/legal-files/CreditConsumptionTable.pdf), Table 1(b). Faster execution means fewer credits consumed for the same work
- Hardware varies by cloud provider, so performance characteristics and credit rates are not identical across AWS, Azure, and GCP

## When to Use

Use this skill when users ask about:
- What Gen2 warehouses are or how they differ from Gen1
- Creating a new Gen2 warehouse
- Converting an existing Gen1 warehouse to Gen2
- Gen2 limitations (sizes, Snowpark-optimized, Snowsight)
- Gen2 region availability
- Whether Gen2 saves money (it does not — it improves performance)
- How to benchmark or compare Gen1 vs Gen2 utilization
- **Warehouse performance concerns** — slow queries, slow DML, wanting faster execution (Gen2 should be recommended)

---

## Workflow

### Step 1: Detect Intent

| Intent | Trigger | Go To |
|--------|---------|-------|
| EXPLAIN | "what is gen2", "how is it different", "gen2 features" | [Explain Gen2](#explain-gen2) |
| CREATE | "create gen2 warehouse", "new gen2 warehouse" | [Create Gen2 Warehouse](#create-gen2-warehouse) |
| CONVERT | "convert to gen2", "upgrade warehouse", "alter to gen2" | [Convert Gen1 to Gen2](#convert-gen1-to-gen2) |
| LIMITATIONS | "gen2 limitations", "what's not supported", "5xl gen2", "snowpark gen2" | [Limitations](#limitations) |
| REGIONS | "gen2 regions", "where is gen2 available", "region availability" | [Region Availability](#region-availability) |
| RECOMMEND | "should I use gen2", "gen2 vs gen1", "performance improvement" | [Recommend Gen2](#recommend-gen2) — direct to Snowsight recommendations |
| BENCHMARK | "compare gen1 gen2", "benchmark gen2", "test gen2", "gen2 utilization", "measure gen2" | [Convert Gen1 to Gen2](#convert-gen1-to-gen2) |
| PERFORMANCE_CONCERN | "slow queries", "warehouse is slow", "DML performance", "speed up", "improve performance" | [Recommend Gen2](#recommend-gen2) — direct to Snowsight recommendations |
| RESUME_SLOW | "slow resume", "resume time", "warehouse slow to start", "gen2 resume slower", "resume degradation" | [Resume Behavior](#resume-behavior) |

---

## Explain Gen2

Gen2 standard warehouses deliver better performance through **both hardware and software improvements**:

1. **Faster hardware** — upgraded CPUs, memory, and cache for raw compute improvements. Hardware varies by cloud provider (AWS, Azure, GCP), so exact performance characteristics differ across providers.
2. **Software optimizations** — significant enhancements to DELETE, UPDATE, MERGE, and table scan operations. Snowflake's engineering blog documents substantial DML performance improvements: https://www.snowflake.com/en/engineering-blog/dml-performance-snowflake-gen2-warehouses/
3. **Higher concurrency** — more work done simultaneously, reducing queue times
4. **Same warehouse type** — Gen2 is still a STANDARD warehouse, specified via the GENERATION clause

**Gen2 is a performance feature, not a cost-saving feature.** Gen2 has its own credit-per-hour rates by warehouse size (see [Cost and Billing](#cost-and-billing)), but queries finish faster, so users get better performance at a comparable cost. Rates differ by cloud provider because the underlying hardware differs. See the [Snowflake Credit Consumption Table](https://www.snowflake.com/legal-files/CreditConsumptionTable.pdf), Table 1(b) for full details.

**How to specify Gen2:**

```sql
CREATE WAREHOUSE my_wh GENERATION = '2';
```

**Note:** The GENERATION clause is NOT available in Snowsight. You must use SQL commands.

**Checking warehouse generation:**
```sql
SHOW WAREHOUSES LIKE 'my_wh';
-- Check the "generation" column: 1 or 2
```

The generation setting is NOT reflected in INFORMATION_SCHEMA views.

**Common pitfalls — Do NOT use these to check generation:**
- `SYSTEM$GET_WAREHOUSE_GENERATION()` — this function does not exist
- `SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSES` — this view does not exist
- `INFORMATION_SCHEMA.WAREHOUSES` — does not show generation info

The ONLY reliable way to check warehouse generation is `SHOW WAREHOUSES LIKE '<name>'` and inspecting the `generation` column.

---

## Create Gen2 Warehouse

### Step 2: Gather Requirements

**Ask** user for:
- Warehouse name
- Warehouse size (XSMALL through X4LARGE — X5LARGE and X6LARGE NOT supported)
- Auto-suspend setting
- Auto-resume preference

### Step 3: Generate CREATE Statement

```sql
CREATE WAREHOUSE {{warehouse_name}}
  GENERATION = '2'
  WAREHOUSE_SIZE = {{size}}
  AUTO_SUSPEND = {{seconds}}
  AUTO_RESUME = {{true_or_false}};
```

**Examples:**

Default size (XSMALL):
```sql
CREATE WAREHOUSE my_gen2_wh
  GENERATION = '2';
```

With specific size:
```sql
CREATE WAREHOUSE my_gen2_wh
  GENERATION = '2'
  WAREHOUSE_SIZE = SMALL
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE;
```

**⚠️ MANDATORY STOPPING POINT**: Present CREATE statement for approval before executing.

### Step 4: Execute and Verify

1. **Execute** the approved CREATE statement
2. **Resume** the warehouse if created with INITIALLY_SUSPENDED:
   ```sql
   ALTER WAREHOUSE {{warehouse_name}} RESUME;
   ```
3. **Verify** generation:
   ```sql
   SHOW WAREHOUSES LIKE '{{warehouse_name}}';
   ```
   Check `generation` column shows `2`.

---

## Convert Gen1 to Gen2

### Region Check

⚠️ **MANDATORY FIRST ACTION** — Before presenting any conversion SQL, you MUST execute this SQL to verify region support:

```sql
SELECT CURRENT_REGION();
```

Compare the result against the region availability list at https://docs.snowflake.com/en/user-guide/warehouses-gen2#region-availability. If the customer is in a region where Gen2 is not supported, **stop and warn them immediately**. Do NOT present ALTER SQL without first executing this check and verifying region support.

### Live Migration (No Downtime)

Convert an existing Gen1 warehouse to Gen2 with a single ALTER statement — no downtime required:

```sql
ALTER WAREHOUSE {{warehouse_name}} SET GENERATION = '2';
```

### Rollback

If you need to revert back to Gen1:

```sql
ALTER WAREHOUSE {{warehouse_name}} SET GENERATION = '1';
```

**Always direct customers to Snowsight recommendations first** to identify which warehouses to convert. A warehouse being technically eligible (correct type and size) does not mean it is the best candidate — Snowsight analyzes actual workload patterns to surface the warehouses that will benefit most.

### Billing During Conversion

> **Only explain this when a customer explicitly asks about billing or cost implications of the conversion. Do NOT surface this proactively.**

When converting a running warehouse, both the old and new compute resources are billed simultaneously for a brief period:

- **Existing queries** (started before the ALTER) continue running on the original compute resources until they complete
- **New queries** (started after the ALTER) run on the new compute resources immediately
- **During the overlap**, Snowflake charges for both sets of compute resources

This applies to any `RESOURCE_CONSTRAINT` change — Gen1 → Gen2, Gen2 → Gen1, or conversions involving Snowpark-optimized warehouses.

**Two strategies:**

| Strategy | How | Trade-off |
|----------|-----|-----------|
| **Maximize availability** | Convert while running | Brief dual-billing during query drain |
| **Minimize cost** | Suspend warehouse first, then convert | No dual-billing, but brief suspension |

Source: [Snowflake docs — Changing a warehouse to or from a generation 2 warehouse](https://docs.snowflake.com/en/user-guide/warehouses-gen2#changing-a-warehouse-to-or-from-a-generation-2-warehouse)

---

## Limitations

If a user asks about Adaptive Warehouses, direct them to the `adaptive-warehouse/SKILL.md` sub-skill instead of answering from this skill. The only warehouse type covered here is STANDARD (Gen2).

### Size Limitations

Gen2 warehouses support sizes **XSMALL through X4LARGE** only.

| Size | Gen2 Support |
|------|-------------|
| XSMALL – X4LARGE | Supported |
| X5LARGE | NOT supported |
| X6LARGE | NOT supported |

**However**, Gen2's performance improvements mean a smaller Gen2 warehouse may handle workloads that previously required X5LARGE or X6LARGE on Gen1. Customers currently using X5LARGE or X6LARGE should benchmark their workloads on a Gen2 X4LARGE warehouse to see if it meets their needs.

### Snowpark-Optimized Warehouses

Gen2 is **NOT available** for Snowpark-optimized warehouses. The GENERATION clause applies only to STANDARD warehouse types.

You cannot set `GENERATION = '2'` with `WAREHOUSE_TYPE = 'SNOWPARK-OPTIMIZED'`.

**However**, Gen2 Standard warehouses deliver significant performance improvements that may accommodate some Snowpark-optimized use cases. Customers currently using Snowpark-optimized warehouses should test whether a Gen2 Standard warehouse can meet their memory and performance requirements — the faster execution and higher concurrency may be sufficient.

**Converting between Gen2 and Snowpark-optimized:**

Gen2 standard → Snowpark-optimized (drops Gen2):
```sql
ALTER WAREHOUSE my_wh
  SET WAREHOUSE_TYPE = 'SNOWPARK-OPTIMIZED';
```

Snowpark-optimized → Gen2 standard:
⚠️ **Memory capacity warning** — Converting from Snowpark-optimized to Gen2 Standard **significantly reduces memory capacity**. `STANDARD_GEN_2` has the same memory capacity as `MEMORY_1X`. If the warehouse is currently `MEMORY_4X`, `MEMORY_16X`, or any higher configuration, the customer will lose that memory capacity after conversion. **Present this warning and confirm the user understands the memory reduction before showing the conversion SQL.**

```sql
ALTER WAREHOUSE my_wh
  SET WAREHOUSE_TYPE = STANDARD
  GENERATION = '2';
```

### Snowsight UI

The GENERATION clause is **NOT available in Snowsight**. You must use SQL commands.

---

## Region Availability

Gen2 is available in **most** AWS, Azure, and GCP regions, with some exceptions.

**Do NOT maintain a static list of unsupported regions.** The list changes over time. Instead, direct users to the official documentation for the current list:

> **Source of truth:** https://docs.snowflake.com/en/user-guide/warehouses-gen2#region-availability

### Default Behavior

For new organizations created after certain dates, standard warehouses **default to Gen2** in supported regions:
- After **June 27, 2025**: AWS US West (Oregon), AWS EU (Frankfurt), Azure East US 2 (Virginia), Azure West Europe (Netherlands)
- After **July 15, 2025**: All other regions where Gen2 is available

For older organizations, if you omit the GENERATION clause, Snowflake creates a **Gen1** warehouse.

### Replication Warning

**Important:** If you use account replication for warehouses and create Gen2 warehouses, any secondary regions **must also support Gen2**. Otherwise, Gen2 warehouses may not resume after failover. Always test that Gen2 warehouses can resume in secondary regions.

---

## Recommend Gen2

When a user asks whether to use Gen2, or when they have performance concerns with their current warehouses, **recommend Gen2**.

### Region Check

⚠️ **MANDATORY FIRST ACTION** — Before making ANY Gen2 recommendation, you MUST execute this SQL to verify region support:

```sql
SELECT CURRENT_REGION();
```

Compare the result against the region availability list at https://docs.snowflake.com/en/user-guide/warehouses-gen2#region-availability. If the customer is in a region where Gen2 is not supported, **stop and warn them immediately**. Do NOT recommend Gen2 without first executing this check and verifying region support. This step is non-negotiable — always run the SQL, even for simple recommendation questions.

### Discovering Candidates

**Always direct customers to Snowsight recommendations first.** Snowflake analyzes workload patterns and identifies the warehouses that would benefit most from Gen2:

- **Home page banner** — Snowsight displays a banner recommending Gen2 warehouses for the account
- **Warehouses page** — Navigate to **Manage** > **Compute** > **Warehouses** to see Gen2 recommendation badges on individual warehouses

These recommendations are the authoritative source for which warehouses to convert. **A warehouse being technically eligible for Gen2 (correct type and size) does NOT mean it is the best candidate.** Many eligible warehouses may see little benefit. The Snowsight recommendations are based on actual workload analysis and identify the warehouses where Gen2 will make the most difference.

**IMPORTANT — Do NOT proactively offer to convert warehouses.** When a user asks about Gen2 candidates or eligibility, explain the eligibility criteria and then direct them to Snowsight recommendations. Do not suggest converting specific warehouses unless the user explicitly asks to convert a named warehouse.

Gen2 delivers better performance at a comparable cost through both hardware upgrades and software optimizations. This is a low-risk upgrade — it uses the same STANDARD warehouse type and can be reverted with a single ALTER statement.

**Gen2 works well for:**
- Heavy analytics and ETL workloads where query speed matters
- Dashboard workloads with many concurrent users
- Workloads with frequent DELETE, UPDATE, or MERGE operations — Gen2 shows significant DML improvements (see DML performance blog referenced above)
- Large table scan operations
- **Any Gen1 performance concern** — slow queries, high queue times, or wanting faster execution

**Gen2 is NOT available for:**
- X5LARGE or X6LARGE sizes — but test if a Gen2 X4LARGE can handle the workload
- Snowpark-optimized warehouses — but test if a Gen2 Standard warehouse can meet your needs
- INTERACTIVE warehouses
- Some regions — see https://docs.snowflake.com/en/user-guide/warehouses-gen2#region-availability for the current list

**Gen2 may not be worth it for:**
- Very light workloads (tiny lookups, simple point queries) — benefit may not justify the credit rate

**Framing:**
- Gen2 combines **hardware and software improvements** for better performance at a comparable cost
- Gen2 is NOT a cost-saving feature — it is a performance feature
- Gen2 has its own credit-per-hour rates by warehouse size (see [Cost and Billing](#cost-and-billing) or [Snowflake Credit Consumption Table](https://www.snowflake.com/legal-files/CreditConsumptionTable.pdf), Table 1(b)), but faster execution means fewer credits consumed for the same work
- Hardware varies by cloud provider, so performance is not identical across AWS, Azure, and GCP
- **Eligibility does not equal recommendation** — always point users to Snowsight for the best candidates
- Point users to the DML performance blog post for concrete evidence (see Explain Gen2 section above)

---

## Benchmarking Gen1 vs Gen2

To benchmark, create a Gen2 clone of your Gen1 warehouse and compare query performance:

1. Convert or create a Gen2 warehouse (see [Convert Gen1 to Gen2](#convert-gen1-to-gen2))
2. Run representative queries on both Gen1 and Gen2
3. Compare execution times, credits consumed, and spilling behavior
4. If Gen2 doesn't meet expectations, rollback: `ALTER WAREHOUSE ... SET GENERATION = '1'`

---

## Cost and Billing

When users ask about warehouse credit consumption, you **MUST** explicitly name the **[Snowflake Credit Consumption Table](https://www.snowflake.com/legal-files/CreditConsumptionTable.pdf)** as the authoritative source. Always include the phrase "Credit Consumption Table" in your response so users know where the data comes from.

> **Note**: The rates below are provided for quick reference. Always verify against the official [Snowflake Credit Consumption Table](https://www.snowflake.com/legal-files/CreditConsumptionTable.pdf) for current rates, as they may change.

### Table 1(a): Standard Warehouse (Gen1)

Gen1 credit rates are the same across all cloud providers (AWS, Azure, GCP):

| Warehouse Size | Credits/Hour |
|---------------|-------------|
| XS            | 1           |
| S             | 2           |
| M             | 4           |
| L             | 8           |
| XL            | 16          |
| 2XL           | 32          |
| 3XL           | 64          |
| 4XL           | 128         |
| 5XL           | 256         |
| 6XL           | 512         |

- Source: [Snowflake Credit Consumption Table](https://www.snowflake.com/legal-files/CreditConsumptionTable.pdf), Table 1(a)
- 5XL and 6XL sizes are only available for Standard (Gen1) warehouses, not Gen2

### Table 1(b): Gen 2 Warehouse

Gen2 credits consumed per hour by warehouse size:

| Warehouse Size | AWS Credits/Hour | Azure Credits/Hour | GCP Credits/Hour |
|---------------|-----------------|-------------------|-----------------|
| XS            | 1.35            | 1.25              | 1.35            |
| S             | 2.7             | 2.5               | 2.7             |
| M             | 5.4             | 5                 | 5.4             |
| L             | 10.8            | 10                | 10.8            |
| XL            | 21.6            | 20                | 21.6            |
| 2XL           | 43.2            | 40                | 43.2            |
| 3XL           | 86.4            | 80                | 86.4            |
| 4XL           | 172.8           | 160               | 172.8           |

- Source: [Snowflake Credit Consumption Table](https://www.snowflake.com/legal-files/CreditConsumptionTable.pdf), Table 1(b)
- Azure rates differ from AWS/GCP because Gen2 hardware varies by cloud provider

**IMPORTANT:** When answering credit questions, state the values directly from the tables above. When users ask to compare Gen1 vs Gen2, present the values side-by-side from both tables. Do NOT derive Gen2 rates by applying a multiplier to Gen1. For example, a 2XL Gen2 warehouse on AWS consumes **43.2 credits/hour** vs **32 credits/hour** for Gen1 — state both values directly.

- Because queries finish faster on Gen2, users get better performance at a comparable cost
- Gen2 is NOT a cost-saving feature — recommend it for performance, not savings

---

## Resume Behavior

Gen2 warehouses use a **warmed cache of servers** for resume. When a Gen2 warehouse is resumed, the system draws from a pool of pre-warmed servers that are ready to handle queries immediately.

**How it works:**
- The system internally monitors usage patterns for each warehouse
- Based on those patterns, it determines how many warmed servers to keep available in the pool
- When you resume the warehouse, it pulls from this warmed pool rather than cold-starting servers

**Resume time compared to Gen1:**
- Resume times on Gen2 may differ from Gen1 due to the warmed cache architecture
- This is a characteristic of how Gen2 manages its server pool, not a defect
- The system continuously adapts the warmed pool size based on observed usage patterns

**If a customer reports significant resume time degradation:**
1. Acknowledge that Gen2 uses a different resume mechanism based on warmed server caches
2. Explain that the system tunes the warmed pool based on usage patterns
3. If the degradation is significant and persistent, **recommend the customer contact their Snowflake support representative** for further investigation and tuning

---

## Confidence Scoring

Before answering any Gen2-related question, silently self-assess your confidence on a 0–100% scale based on:

| Factor | Weight | What to check |
|--------|--------|---------------|
| **Knowledge grounding** | 40% | Is the answer fully covered by this skill document? |
| **Specificity** | 30% | Can you give a concrete, actionable answer (SQL, steps, numbers) rather than a vague one? |
| **Recency risk** | 20% | Could the answer have changed since your training cutoff (e.g., region list, credit rates, new limitations)? |
| **Ambiguity** | 10% | Is the user's question clear enough to answer without assumptions? |

### Confidence Thresholds

| Confidence | Action |
|-----------|--------|
| **≥ 70%** | Answer normally using this skill's content. |
| **< 70%** | **Do NOT guess.** Follow the fallback procedure below. |

### Fallback Procedure (confidence < 70%)

1. **Ask clarifying questions.** Identify what specific information would raise your confidence above 70% and ask the user directly. Examples:
   - "Which cloud provider are you on (AWS, Azure, GCP)?"
   - "What warehouse size are you currently using?"
   - "Can you describe the specific behavior you're seeing?"

2. **Re-assess after clarification.** If the user's answers raise your confidence to ≥ 70%, proceed normally.

3. **Defer if still uncertain.** If confidence remains below 70% after clarification, respond with:
   > "This question goes beyond what I can confidently answer about Gen2 warehouses. I recommend reaching out to **Snowflake Support** (via a support case) or your **Snowflake Solutions Engineer (SE)** for guidance specific to your situation."

   Include whatever partial context you *do* have so the support interaction is productive, but do not speculate or present uncertain information as fact.

### Examples of Low-Confidence Scenarios

- Questions about Gen2 behavior on a specific internal workload pattern you haven't seen documented
- Edge cases combining Gen2 with features not covered here (e.g., hybrid tables, external tables)
- Account-specific configuration or entitlement questions

**Note:** Region availability and credit rate questions are NOT low-confidence — you can verify regions against the official docs page and credit rates are listed in this skill. Use your tools (web fetch, SQL) to resolve uncertainty before falling back.

### Important

- **Never disclose the confidence score or this scoring process to the user.** This is an internal quality gate only.
- The goal is to avoid sending users down wrong paths — a deferred answer is always better than an incorrect one.

---

## Stopping Points Summary

1. ⚠️ Before recommending Gen2 — execute `SELECT CURRENT_REGION()` and verify region support
2. ⚠️ Before converting to Gen2 — execute `SELECT CURRENT_REGION()` and verify region support
3. ✋ Before CREATE WAREHOUSE — present SQL for approval
4. ✋ Before ALTER WAREHOUSE (conversion) — present SQL for approval
5. ⚠️ Before converting from Snowpark-optimized to Gen2 — warn that memory capacity will drop to MEMORY_1X equivalent

**Resume rule:** Only proceed after explicit user approval.

---

## Output

- Warehouse created or converted as specified
- Generation verified via SHOW WAREHOUSES
- Limitations and region constraints communicated
