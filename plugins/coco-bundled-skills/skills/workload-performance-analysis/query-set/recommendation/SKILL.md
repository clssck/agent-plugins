# Query Set Recommendations

**This is a Phase 3 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Provide prioritized, scope-aware recommendations for a user-supplied query set. Output is text + markdown only — **no HTML reports**. Recommendations are tailored to this workload and may not be appropriate at account level.

## Prerequisites

- Phase 1 scope card and Phase 2 detection results already presented and confirmed.
- Available context: `<ID_LIST>`, `<HASH_LIST>`, `<TABLE_ID_LIST>`, `<SCOPE_START>`, `<SCOPE_END>`, plus profile classifications, failed-query list, scope-vs-account context, and concentration findings.

## Workflow

### Step 1: Map Classifications to Recommendation Blocks

| Classification (from Phase 2) | Recommendation block | Default severity |
|---|---|---|
| Failed queries | Surface every failure with `error_code` + `error_message` + offending statement; recommend retry / error-handling strategy at the workload level | **Critical** |
| Compute-intensive | Optimize the dominant statement type — review query plan, indexing, clustering, partition pruning. If a small number of `query_parameterized_hash` values dominate, recommend QUERY_PATTERN-level analysis on each | Info–High |
| Compilation-heavy | Result caching where applicable; reduce session-level setup churn (`USE` / `SET`); enable persistent compilation results when supported; check for parameter sniffing (variant SQL per call) | Medium |
| Queue / undersized | Upsize warehouse OR add multi-cluster (`MAX_CLUSTER_COUNT`); reschedule the workload off-peak; route to a dedicated warehouse if it competes with interactive work | High |
| Lock contention | Reduce concurrent DML against the same tables; shorten transactions; convert separate INSERT/UPDATE into a single MERGE | High |
| Unattributed "other" overhead | Note ACCOUNT_USAGE doesn't expose GS/scheduling overheads; check for excessive metadata operations (DDL, SHOW, USE) inside the workload | Medium |
| Scope is a small contributor (<1%) account-wide | Recommend deprioritizing in favor of larger account-level wins | Low |

### Step 2: Cross-Reference Dimension Recommendations

Do **not** duplicate spilling / pruning / cache / QAS recommendations here. Instead, point at the relevant recommendation sub-skills with the scope context:

- "See `spilling/recommendation/SKILL.md` for warehouse sizing guidance for warehouses {<list>} that show spilling within this set."
- "See `pruning/recommendation/SKILL.md` for clustering / search optimization guidance for the dominant scan tables {<list>} in this set."
- "See `cache/recommendation/SKILL.md` for cache-warming guidance for warehouses {<list>}."
- "See `qas/recommendation/SKILL.md` for QAS enablement guidance for warehouses with eligible time {<list>}."

When concentration analysis identified a small number of patterns covering 80% of time, also recommend:
- "Run QUERY_PATTERN analysis on hash {<hash>} which accounts for {X%} of total elapsed time in this set."

### Step 3: Apply Speed-vs-Cost SLA Framing

Before finalizing sizing / multi-cluster / QAS / auto-suspend recommendations, apply the standard Speed-vs-Cost framing from the parent `SKILL.md`. Ask once:

> "Is this workload **speed-priority** (latency-sensitive — minimize wall-clock time at the expense of credits) or **cost-priority** (batch/background — willing to accept longer runtime to save credits)?"

Tailor the recommendations to the chosen priority.

### Step 4: Cross-Workload Caution

Workloads typically run on shared warehouses against shared tables. When recommending any of the following, emit an explicit caution:

| Action | Caution |
|---|---|
| `ALTER TABLE … CLUSTER BY …` | Re-clusters the entire table; affects every workload that touches it. May help this set but hurt others. |
| `ALTER TABLE … ADD SEARCH OPTIMIZATION ON (…)` | Adds storage and write-amplification cost for all writes |
| `ALTER WAREHOUSE … SET WAREHOUSE_SIZE = …` | Affects every workload on the warehouse; consider a dedicated warehouse for this workload if its SLA differs |
| `ALTER WAREHOUSE … SET ENABLE_QUERY_ACCELERATION = TRUE` | Charges QAS credits for all queries on the warehouse |
| Increasing `AUTO_SUSPEND` | Keeps warehouse warm for everyone; idle credit cost for non-workload hours |

### Step 5: Present Recommendations

Output structure:

```
### Query Set Recommendations

**Scope:** X queries | Y warehouses | Z tables | T1 → T2
**Profile:** <classifications>
**Workload SLA:** speed-priority / cost-priority (after Step 3)

#### Critical
1. **<recommendation>** — <evidence (failure rate, error_code, etc.)>
   - Action: <concrete DDL or rewrite>
   - Caution: <if any cross-workload impact>

#### High Priority
2. **<recommendation>** — <evidence>
   - Action: …

#### Medium Priority
3. **<recommendation>** — <evidence>

#### Cross-Reference
- Spilling on <warehouses>: see `spilling/recommendation/SKILL.md`
- Pruning on <tables>: see `pruning/recommendation/SKILL.md`
- …
```

**[IMPORTANT]:**
- Prioritize by impact **within the set** — biggest wall-clock-time and credit wins for this workload first.
- Group related recommendations — same warehouse / table appearing under multiple classifications is presented together.
- **DO explain trade-offs** for every recommendation.
- **DO NOT** generate HTML, PDF, or any binary artifacts.

**[STOP]** Wait for user follow-up.

## Edge Cases

| Situation | Handling |
|---|---|
| All four dimensions return clean | Recommend the workload is well-tuned; suggest periodic re-analysis only |
| Internal warehouses dominate the set | Skip warehouse sizing; flag as internal, not user-configurable |
| Recommendations conflict (e.g. upsize for speed vs downsize for cost) | Show both; the SLA priority in Step 3 is the tiebreaker |
| Concentration analysis fingers a single pattern | Strongly recommend QUERY_PATTERN-level analysis for that hash; skip lower-impact recs |
