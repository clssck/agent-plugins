---
name: adaptive-warehouse
description: "Adaptive warehouse questions: creating, converting, tuning, billing, limitations, recommend warehouses for adaptive, which warehouses are candidates, warehouse migration candidates, good fit for adaptive, should I migrate my warehouse, queries are queuing, query is slow, query timed out, long-running query, costs are high, too expensive, reduce spend, high queue time."
parent_skill: warehouse
---

# Snowflake Adaptive Warehouses

> **Public Documentation:** https://docs.snowflake.com/en/user-guide/warehouses-adaptive
> For questions that can be answered by public documentation, always include this link in your response.

## What is an Adaptive Warehouse?

**Adaptive Compute** is a compute service focused on delivering strong performance with effortless operations. You access it through adaptive warehouses (`WAREHOUSE_TYPE = 'ADAPTIVE'`). The system decides how to allocate resources for the best performance, eliminating the need for infrastructure tuning — no warehouse sizing, no multi-cluster configuration, no QAS management.

All jobs across all adaptive warehouses in an account are routed to a **shared compute pool dedicated to your account** — it is not shared with other accounts or other warehouse types (standard, interactive, Snowpark-optimized).

**Key points:**
- Adaptive is a **new warehouse type**, not a generation of STANDARD warehouses
- Adaptive Compute routes each query to optimal resources from a shared account-level pool
- QAS usage is included in compute credits — no separate QAS charges
- Multiple adaptive warehouses are still supported for workload separation
- You still use resource monitors and budgets for cost control
- Adaptive warehouses deliver generally better performance at similar costs to Gen2

## When to Use

Use this skill when users ask about:
- What adaptive warehouses are or how they differ from standard warehouses
- Creating a new adaptive warehouse
- Converting an existing standard warehouse to adaptive
- The `MAX_QUERY_PERFORMANCE_LEVEL` or `QUERY_THROUGHPUT_MULTIPLIER` parameters
- Adaptive warehouse limitations (what cannot be converted)
- Adaptive warehouse billing or per-query credit attribution
- How to tune or right-size an adaptive warehouse
- Analyzing adaptive warehouse performance

---

## Workflow

### Step 1: Detect Intent and Load Runbook

| Intent | Trigger | Action |
|--------|---------|--------|
| EXPLAIN | "what is adaptive", "how does adaptive work", "adaptive vs standard" | Answer from [Explain Adaptive](#explain-adaptive) below |
| CREATE | "create adaptive warehouse", "new adaptive warehouse" | Load `reference/create.md` |
| CONVERT | "convert to adaptive", "migrate to adaptive", "alter to adaptive", "enable warehouse", "disable warehouse", "alter warehouse enable", "alter warehouse disable" | Load `reference/convert.md` |
| LIMITATIONS | "adaptive limitations", "what can't be converted", "adaptive not supported" | Load `reference/limitations.md` |
| RECOMMEND | "should I use adaptive", "is adaptive right for me", "adaptive benefits" | Load `reference/tuning.md` |
| CANDIDATES | "which warehouses should I migrate", "recommend warehouses for adaptive", "warehouse candidates", "good fit for adaptive", "which warehouses are candidates", "warehouse migration candidates", "eligible for adaptive" | **ALWAYS run region/edition validation FIRST**, then load `reference/recommend.md` |
| TUNE | "tune adaptive", "set parameters", "MAX_QUERY_PERFORMANCE_LEVEL", "QUERY_THROUGHPUT_MULTIPLIER", "queries are queuing", "query is slow", "query timed out", "long-running query", "costs are high", "too expensive", "reduce spend", "high queue time" | Load `reference/tuning.md` |
| BILLING | "adaptive billing", "adaptive credits", "per-query cost", "warehouse_metering_history", "query_metering_history", "per-query credits" | Load `reference/billing.md` |
| ANALYZE | "analyze adaptive performance", "compare adaptive vs standard", "adaptive query analysis" | Load `reference/analysis.md` |
| REGIONS | "adaptive regions", "where is adaptive available", "adaptive availability" | Load `reference/create.md` (region availability section) |

---

## Explain Adaptive

Adaptive Warehouses remove the need to choose warehouse sizes, configure concurrency, or tune QAS. Adaptive Compute routes each query to the optimal resources from a shared pool, up to the cap you configure.

**Two user-visible parameters:**

| Parameter | What It Controls | Values | Default (Greenfield) |
|-----------|-----------------|--------|---------|
| `MAX_QUERY_PERFORMANCE_LEVEL` | Maximum performance enhancements applied per query | XSMALL, SMALL, MEDIUM, LARGE, XLARGE, XXLARGE, XXXLARGE, X4LARGE | XLARGE |
| `QUERY_THROUGHPUT_MULTIPLIER` | Peak concurrent capacity (0 = unlimited) | Integer ≥ 2, or 0 for unlimited | 2 |

- **MAX_QUERY_PERFORMANCE_LEVEL** — The maximum level of performance enhancements Adaptive Compute will apply to queries. Smaller or simpler queries may receive less than the cap.
- **QUERY_THROUGHPUT_MULTIPLIER** — A scaling factor that controls the concurrent throughput capacity for queries running at the maximum performance level. It does not map directly to a count of jobs or parallel statements — it is a multiplier on capacity. 0 means unlimited.

**New SHOW WAREHOUSES columns for adaptive warehouses:**

| Column | Description |
|--------|-------------|
| `STATE` | ENABLED or DISABLED. Use `ALTER WAREHOUSE <name> ENABLE/DISABLE` to change. See `reference/convert.md` |
| `MAX_QUERY_PERFORMANCE_LEVEL` | Current performance level cap |
| `QUERY_THROUGHPUT_MULTIPLIER` | Current throughput multiplier |
| `DISABLED_REASONS` | Why the warehouse was disabled (if applicable) |

### Gen2 vs Adaptive

| | Gen2 | Adaptive |
|---|------|----------|
| **Compute model** | Fixed warehouse size (XS–4XL) | Query performance levels + system-determined throughput |
| **Concurrency** | Multi-cluster with explicit min/max counts | `QUERY_THROUGHPUT_MULTIPLIER` — system manages the pool |
| **Sizing** | Customer chooses and manages warehouse size | Adaptive Compute selects resources per query, up to `MAX_QUERY_PERFORMANCE_LEVEL` |
| **What improved** | Better hardware/software over Gen1 | Removes the compute model entirely |
| **Migration** | Same warehouse type (`STANDARD`), different generation | New warehouse type (`ADAPTIVE`); both Gen1 and Gen2 can convert |

**Key message:** Gen2 delivers better performance within the same familiar compute model. Adaptive removes that model altogether — Snowflake handles resource decisions.

> **Framing rule:** Adaptive is a **performance improvement**, not a cost-saving feature. Do NOT frame it as cheaper, more economical, or a way to reduce spend. The value proposition is better performance at similar costs — not lower costs. If a user asks about cost savings, clarify this distinction.

---

## Confidence Scoring and Grounding Requirements

Before answering any adaptive warehouse question, silently self-assess your confidence on a 0–100% scale:

| Factor | Weight | What to check |
|--------|--------|---------------|
| **Knowledge grounding** | 40% | Is the answer covered by this skill document or a loaded runbook? |
| **Specificity** | 30% | Can you give a concrete, actionable answer (SQL, steps, numbers)? |
| **Recency risk** | 20% | Could this have changed since your training cutoff (e.g., pricing, new limits)? |
| **Ambiguity** | 10% | Is the user's question clear enough to answer without assumptions? |

| Confidence | Action |
|-----------|--------|
| **≥ 70%** | Answer normally using this skill's content. |
| **< 70%** | Ask clarifying questions. If still < 70% after clarification, direct the user to the [public documentation](https://docs.snowflake.com/en/user-guide/warehouses-adaptive) or defer to Snowflake Support or Solutions Engineer. |

**Never disclose the confidence score or this process to the user.**

### Strict Grounding Rule

**CRITICAL:** When explaining why Adaptive may or may not be suitable for a workload, you MUST cite content from this skill or its reference documents. DO NOT invent technical explanations, architectural details, or operational characteristics not explicitly documented here.

**If this skill says "not recommended for X" but doesn't explain why:**
- State the limitation as documented (e.g., "Adaptive is not optimized for hybrid table workloads")
- Do NOT speculate about technical reasons (memory allocation, resource reallocation, node management, etc.)
- If the user asks why, direct them to Snowflake documentation or their account team

**Examples of PROHIBITED speculation:**
- ❌ Inventing details about memory allocation behavior
- ❌ Describing how resources are dynamically adjusted during query execution
- ❌ Explaining internal mechanisms like "node removal mid-join" or "reshuffling data"
- ❌ Making claims about conflicts between features (e.g., "multi-cluster conflicts with Adaptive")
- ❌ Fabricating performance characteristics not documented in this skill

**When in doubt:** Say "This skill doesn't contain enough detail to explain why. Please refer to the [Adaptive Warehouse documentation](https://docs.snowflake.com/en/user-guide/warehouses-adaptive) or contact your Snowflake account team."

---

## Common Misconceptions (DO NOT REPEAT)

These are INCORRECT statements about Adaptive Warehouses. **Never make any of these claims:**

| Misconception | Truth |
|--------------|-------|
| ❌ "Spilling workloads need consistent memory, not elasticity" | Adaptive handles spilling workloads normally. Memory is allocated appropriately per query. |
| ❌ "Queries may lose memory mid-execution, causing spill cascades" | FALSE. Adaptive does not deallocate resources from running queries. |
| ❌ "Multi-cluster scaling conflicts with Adaptive" | FALSE. Multi-cluster warehouses can be converted to Adaptive. These are orthogonal features. |
| ❌ "Large warehouse sizes amplify disruption" | FALSE. Adaptive does not "reallocate" or "remove nodes" mid-query in a disruptive way. |
| ❌ "Analytical workloads are not suitable for Adaptive" | FALSE. Many analytical workloads work well with Adaptive. The documented exceptions are HTAP, hybrid tables, and SLA-sensitive workloads requiring precise guarantees. |
| ❌ "Adaptive works best only for variable/unpredictable workloads" | MISLEADING. Adaptive works well for many workload patterns, including steady analytical pipelines. |
| ❌ "Data must be reshuffled when nodes are removed" | FALSE architecture detail. Do not describe internal query execution mechanics. |

**If you catch yourself about to make any similar claim:** Stop. Re-read this skill. Answer only from documented content.

---

## Stopping Points Summary

1. ⚠️ Before CREATE or ALTER adaptive — verify both region (`SELECT CURRENT_REGION()`) and account edition (try `SHOW ORGANIZATION ACCOUNTS`, then `SHOW ACCOUNTS LIKE CURRENT_ACCOUNT()`; if both fail, ask user to check Snowsight → Admin → Account)
2. ✋ Before CREATE ADAPTIVE WAREHOUSE — present SQL for approval
3. ✋ Before ALTER WAREHOUSE (conversion or parameter change) — present SQL for approval
4. ⚠️ Before bulk migration — show dry run results and get explicit approval before ACTIVE run

**Resume rule:** Only proceed after explicit user approval.
