---
name: snowflake-interactive
description: "**[REQUIRED]** Use for **ALL** Snowflake Interactive Table and Interactive Warehouse operations. Triggers: interactive table, interactive warehouse, low-latency queries, high-concurrency dashboard, TARGET_LAG for interactive."
---

# Snowflake Interactive Tables & Warehouses

**Version**: 1.4

Creating and managing Snowflake Interactive Tables and Interactive Warehouses for low-latency, high-concurrency workloads.

## Prerequisites


## When to Use

Use this skill when users ask about:
- Creating interactive tables (static, dynamic with TARGET_LAG)
- Creating or managing interactive warehouses
- Querying interactive tables with low latency
- JOINs between multiple interactive tables
- UPDATE/DELETE operations on interactive tables
- Troubleshooting timeouts, errors, or performance issues

---

## Key Capabilities

- **Low-latency queries**: Sub-second response for dashboards and APIs
- **High concurrency**: Handle many queries concurrently
- **Ingestion modes**: Static (CTAS or INSERT OVERWRITE), Dynamic (TARGET_LAG)
- **Multi-table JOINs**: JOIN interactive tables within same warehouse
- **Fallback Warehouse**: Designate a non-interactive backup warehouse for queries exceeding timeout (mixed workloads)

## Key Limitations

- Interactive warehouses can **ONLY** query interactive tables
- Interactive tables do **NOT** support UPDATE/DELETE directly
- Query timeout: **5 seconds** on interactive warehouse (queries exceeding this are transparently retried on fallback warehouse if configured; otherwise fail)
- All tables in a JOIN must be interactive AND associated with the same warehouse

---

## Intent Detection

When a user makes a request, detect their intent and route to the appropriate sub-skill:

### GETTING-STARTED Intent

**Trigger phrases**: "getting started", "convert to interactive", "migrate to interactive", "set up interactive", "first time interactive", "how do I start", "new to interactive", "make my dashboards faster"

**→ Load**: [getting-started/SKILL.md](getting-started/SKILL.md)

### CREATE Intent

**Trigger phrases**: "create interactive table", "new interactive table", "static table", "dynamic table", "CTAS interactive", "INSERT INTO interactive"

**→ Load**: [create/SKILL.md](create/SKILL.md)

### CLUSTERING Intent

**Trigger phrases**: "clustering key", "pick clustering", "choose cluster by", "clustering columns", "optimize clustering", "what to cluster on"

**→ Load**: [clustering/SKILL.md](clustering/SKILL.md)

### WAREHOUSE Intent

**Trigger phrases**: "create interactive warehouse", "add tables to warehouse", "remove tables", "resume warehouse", "suspend warehouse", "associate table", "fallback warehouse", "set fallback", "timeout retry", "mixed workload"

**→ Load**: [warehouse/SKILL.md](warehouse/SKILL.md)

### QUERY Intent

**Trigger phrases**: "query interactive", "SELECT from interactive", "join interactive tables", "dashboard query", "low latency query", "benchmark interactive", "measure performance", "compare performance", "query performance", "test latency"

**→ Load**: [query/SKILL.md](query/SKILL.md)

### UPDATE-DELETE Intent

**Trigger phrases**: "update interactive table", "delete from interactive", "modify data", "DML operations", "standard + dynamic pattern"

**→ Load**: [update-delete/SKILL.md](update-delete/SKILL.md)

### TROUBLESHOOT Intent

**Trigger phrases**: "timeout", "error", "not working", "failing", "slow", "performance issue", "query timeout", "table not found"

**→ Load**: [troubleshoot/SKILL.md](troubleshoot/SKILL.md)

---

## Workflow Decision Tree

```
User Request
    ↓
Detect Intent
    ↓
    ├─→ GETTING-STARTED → Load getting-started/SKILL.md
    │   (Triggers: "getting started", "convert to interactive", "first time")
    │
    ├─→ CREATE → Load create/SKILL.md
    │   (Triggers: "create interactive table", "static/dynamic")
    │
    ├─→ CLUSTERING → Load clustering/SKILL.md
    │   (Triggers: "clustering key", "pick clustering", "optimize clustering")
    │
    ├─→ WAREHOUSE → Load warehouse/SKILL.md
    │   (Triggers: "create warehouse", "add tables", "resume/suspend")
    │
    ├─→ QUERY → Load query/SKILL.md
    │   (Triggers: "query", "join", "SELECT", "dashboard", "benchmark", "performance")
    │
    ├─→ UPDATE-DELETE → Load update-delete/SKILL.md
    │   (Triggers: "update", "delete", "modify data")
    │
    └─→ TROUBLESHOOT → Load troubleshoot/SKILL.md
        (Triggers: "timeout", "error", "not working", "failing")
```

---

## Sub-Skills

| Sub-Skill | Purpose | When to Load |
|-----------|---------|--------------|
| [getting-started/SKILL.md](getting-started/SKILL.md) | Getting started guide for first-time users | GETTING-STARTED intent |
| [create/SKILL.md](create/SKILL.md) | Create interactive tables | CREATE intent |
| [clustering/SKILL.md](clustering/SKILL.md) | Choose optimal clustering keys | CLUSTERING intent |
| [warehouse/SKILL.md](warehouse/SKILL.md) | Manage interactive warehouses | WAREHOUSE intent |
| [query/SKILL.md](query/SKILL.md) | Query patterns and JOINs | QUERY intent |
| [update-delete/SKILL.md](update-delete/SKILL.md) | UPDATE/DELETE via standard+dynamic | UPDATE-DELETE intent |
| [troubleshoot/SKILL.md](troubleshoot/SKILL.md) | Diagnose and fix issues | TROUBLESHOOT intent |

---

## References (Load On Demand)

| Reference | When to Load |
|-----------|--------------|
| [references/sql-syntax.md](references/sql-syntax.md) | For exact SQL command syntax |
| [references/best-practices.md](references/best-practices.md) | For clustering, sizing, optimization |
| [references/error-messages.md](references/error-messages.md) | For error diagnosis |
| [references/monitoring.md](references/monitoring.md) | For monitoring queries |
| [references/limitations.md](references/limitations.md) | For constraint checking |

---

## Quick Diagnostic Queries

For immediate assessment before routing:

```sql
-- Check warehouse state
SHOW WAREHOUSES LIKE '%iwh%';

-- Check interactive tables in a warehouse
SHOW TABLES;

-- Verify table type
SELECT table_name, table_type 
FROM INFORMATION_SCHEMA.TABLES 
WHERE table_schema = '<SCHEMA>';
```

---

## Stopping Points Summary

All sub-skills require user approval before making changes:
- **READ-ONLY queries**: Can run freely
- **ANY mutation**: Requires stopping point and user approval

See individual sub-skills for specific stopping points.
