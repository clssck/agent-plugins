# QAS Summary

**This is a Phase 1 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Present a high-level overview of Query Acceleration Service (QAS) eligibility across warehouses and queries.

## Workflow

### Step 1: Warehouse-Level QAS Opportunity

**[MANDATORY]** Fetch and execute the exact SQL from verified query: `Which warehouses have the most QAS eligible time?` in the semantic model. Do NOT rewrite or regenerate this query.

Present results:

```
## Warehouses with QAS Opportunity (Last 7 Days)

| Warehouse | Size | Eligible Queries | Total Eligible Seconds | Avg Eligible Seconds/Query | Avg Scale Factor | Max Scale Factor |
```

### Step 2: Query-Level QAS Eligibility

**[MANDATORY]** Fetch and execute the exact SQL from verified query: `Which queries are eligible for query acceleration service?` in the semantic model. Do NOT rewrite or regenerate this query.

Present results:

```
## Top QAS-Eligible Queries

| Query ID | Warehouse | Size | Eligible Acceleration (s) | Scale Factor | Start Time |
```

**[STOP]** Present both tables. Ask: "Want me to analyze QAS patterns in detail, or provide recommendations?"
