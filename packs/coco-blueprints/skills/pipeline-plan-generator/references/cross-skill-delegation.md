# Cross-Skill Delegation — pipeline-plan-generator

This skill delegates to sibling skills via **name-based skill invocation**. At runtime the agent invokes the referenced skill by name, lets it run its own workflow and templates, and consumes the structured results — the delegated skill owns its own SQL correctness, fallback logic, and error handling.

## Delegation Table

| Capability | Skill (invoke by name) | Workflow to run |
|------------|------------------------|-----------------|
| Provenance & trust assessment | `lineage` | data-discovery / provenance-verification (upstream lineage + trust tiers) |
| Downstream impact & risk | `lineage` | impact-analysis (downstream objects + risk scoring) |
| Upstream change detection | `lineage` | root-cause-analysis / change-detection (recent modifications to upstream) |
| Existing DMF discovery | `data-quality` | monitor-recommendations / preflight-check (existing DMF attachments on source) |
| Step 4c standard test generation | `data-quality` | test-generation (DMF DDL or SQL assertion per category; handles deduplication against existing DMFs) |
| Step 4e lineage-informed test generation | `data-quality` | test-generation / monitoring-recommendation (DMF DDL or SQL assertion per triggered category) |

## Delegation Pattern

```
Invoke the `lineage` (or `data-quality`) skill by name
Run its <workflow> workflow for <source_fqn>
Record results silently (do not present to user)
Use results in risk assessment and test generation
```

## Key Contract

- The plan generator NEVER writes GET_LINEAGE SQL directly — it delegates to the `lineage` skill
- The plan generator NEVER writes DMF-check SQL directly — it delegates to the `data-quality` skill
- The plan generator NEVER writes test assertion SQL (Steps 4c and 4e) — it delegates to the `data-quality` skill, which owns all test output including DMF DDL, SQL assertions, and deduplication
- Both skills handle their own API correctness, fallbacks, and privilege errors
- Results are consumed as structured data for the plan's ecosystem profile and test plan
- If a delegated skill returns "no data available" or errors, record the gap and proceed

## Why Delegate Rather Than Embed

- No duplicated SQL that could drift out of sync between skills
- The `lineage` skill owns all GET_LINEAGE patterns, output column references, and fallback chains
- Improvements to the `lineage` or `data-quality` skills automatically benefit the plan generator
- Single source of truth for API correctness (the `lineage` skill's `snowflake-apis` reference)

> **Note on invocation:** reference these skills by name (`lineage`, `data-quality`), not by file path — name-based invocation resolves correctly regardless of install layout.
