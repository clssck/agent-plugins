---
name: sv-modeling-patterns
description: "Catalog of 14 advanced Semantic View modeling patterns, applied through the cortex agent-studio CLI. Load when the user wants to: compare a metric to the same period last year/month (YoY, MoM, SPLY); build a rolling average / YTD / lag-N comparison metric; model a slowly-changing-dimension lookup with `valid_from`/`valid_to` or attribute an event to the dim row active at event time (as-of, 'address active at order time'); track a snapshot fact that must not sum across time (balance / inventory / headcount); model an accumulating-snapshot funnel across multiple milestone dates ('loan funnel', 'applied → reviewed → decided → funded'); route a metric through a specific FK when one fact has two FKs to the same dim (multi-path metrics); reuse the same physical dim under multiple roles; add a cross-entity derived metric ('% of total', 'net = gross − returns'); split shared dims across multiple fact tables; expose a private (`access_modifier: private_access`) fact used only inside the SV to derive a tier or other dimension; join on a key that doesn't exist as a physical column (computed-fact FK); steer Cortex Analyst with verified queries and `module_custom_instructions`; or diagnose a fan trap, 'multi-path relationship not supported' error, or numbers that look inflated. Also load when an edit, audit, or agentic-optimization finding maps to one of these patterns."
parent_skill: semantic-view
---

# Semantic View Modeling Patterns

## When to Load

Load when an edit / audit / agentic-optimization step maps to a known modeling pattern. The same triggers as the catalog entries below — including: "year-over-year", "rolling avg", "SCD2", "valid_from / valid_to", "address active at order time", "loan funnel", "% of total", "private fact", "the SV deployed but my query errors", "verified queries", "custom instructions".

If the request matches a row in the catalog, open the corresponding `snippets/<pattern>.md` first — do not author from memory.

## CLI reference (inherits from semantic_view parent)

Use the `cortex agent-studio` CLI for all SV operations. For modeling patterns specifically:

| Command | Use for |
|---------|---------|
| `cortex agent-studio sv-read --fqn DB.SCH.VIEW` | Pull the current YAML to `cortex_project/` before editing |
| `cortex agent-studio sv-edit --file-path <path> --operations '<json>'` | Apply primitive structural edits (add table, add relationship, add metric, ...) |
| `cortex agent-studio sv-write --yaml-content '<yaml>' --source-object DB.SCH.VIEW` | Save the modified YAML back to workspace (do NOT pass `--file-path` — auto-generated) |

⚠️ **Never pass `--yaml-content` inline in bash** — shell argument length limits silently truncate large strings, producing a corrupt file. Instead, save the export result to a file, extract `yaml_content` to a temp file using Python, then pass via `$(cat)`:

```bash
# Save export output, extract yaml_content, then sv-write
cortex agent-studio backend --tool <tool> --parameters '...' > /tmp/export_result.json
# Use Python to extract yaml_content:
# result["data"]["result"] is a JSON string — parse it, then get ["yaml_content"]
# Write to /tmp/model.sv.yaml, then:
cortex agent-studio sv-write \
  --yaml-content "$(cat /tmp/model.sv.yaml)" \
  --source-object DATABASE.SCHEMA.MODEL_NAME
```
| `cortex agent-studio sv-deploy --file-path <path> --fqn DB.SCH.VIEW` | Push the YAML to Snowflake |
| `snowflake_sql_execute` | Run `SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(..., TRUE)` for dry-run validation, or any other SV inspection / management SQL |

**Forbidden:** Do NOT use plain `read`, `write`, `edit`, `multi_edit`, or `bash` on semantic-view YAML — it bypasses `cortex_project/` tracking.

## Catalog

| Pattern | Use when | Trigger phrases | Key SV constructs | Studio action sequence |
|---|---|---|---|---|
| [time_intelligence](snippets/time_intelligence.md) | Compare current period to same period last year/month (SPLY, YoY %) | "YoY", "MoM", "SPLY", "vs prior year" | Role-playing alias of fact + computed fact (`DATEADD`) used as join key | `sv-read` → edit YAML to add the role-playing alias `tables[]` entry, the computed fact, and the relationship → `sv-deploy` |
| [asof_join](snippets/asof_join.md) | Attribute event to dim record active at event time when dim has only `start_date` | "as-of", "address active at order time" | `unique_keys` on `(key, start_date)` + `type: asof` on the date column | `sv-read` → edit YAML to add `unique_keys` and `type: asof` on the relationship column → `sv-deploy` |
| [range_join](snippets/range_join.md) | SCD2 dim with `valid_from`/`valid_to` | "SCD2", "valid_from / valid_to", "tier at time of purchase" | `constraints[].distinct_range` + compound relationship with `type: range` + `right_range` | `sv-read` → edit YAML to add `constraints` block + the range relationship column → `sv-deploy` |
| [semi_additive_metric](snippets/semi_additive_metric.md) | Snapshot facts (balance, headcount) | "current balance", "headcount over time", "inventory snapshot" | `non_additive_dimensions` on the metric + paired `AVG()` metric | `sv-edit` `add_metric` then edit YAML for `non_additive_dimensions` block → `sv-deploy` |
| [window_metrics](snippets/window_metrics.md) | Rolling avg, LAG, YTD/QTD/MTD | "7-day rolling avg", "year to date", "lag 30 days" | `OVER (PARTITION BY ... ORDER BY ... RANGE/ROWS BETWEEN ...)` + `LAG(metric, n)` | `sv-edit` `add_metric` with the window expression → `sv-deploy` |
| [multi_path_metrics](snippets/multi_path_metrics.md) | Fact has two FKs to same dim | "weather at departure vs arrival", multi-path error | One relationship per role + `using_relationships: [<name>]` per metric | `sv-edit` `add_relationship` per role + edit metric YAML for `using_relationships` → `sv-deploy` |
| [accumulating_snapshot](snippets/accumulating_snapshot.md) | Funnel with multiple milestone dates | "loan funnel", "applied → reviewed → decided → funded" | One date alias + one relationship per milestone + `using_relationships` per stage metric | Same sequence as `multi_path_metrics` — multiple `add_relationship` + per-metric `using_relationships` |
| [role_playing_dimensions](snippets/role_playing_dimensions.md) | Two FKs to same dim, independently named dim columns | "order date vs ship date in the same report" | Same physical table aliased twice in `tables:` | `sv-edit` `add_table` for each alias + `add_relationship` per alias → `sv-deploy` |
| [derived_metrics](snippets/derived_metrics.md) | Cross-entity totals and ratios | "total across channels", "% of total", "net = gross - returns" | Top-level `metrics:` block (not nested under any table) | Edit YAML directly to add the top-level metrics → `sv-deploy` |
| [entity_facts](snippets/entity_facts.md) | LTV → tier, calculated dimensions | "value tier from total spend", "age from birth_year", "private fact" | `access_modifier: private_access` fact + CASE-derived dim referencing it | `sv-edit` `add_fact` + `add_dimension`; then edit YAML to set `access_modifier: private_access` → `sv-deploy` |
| [multi_fact_table](snippets/multi_fact_table.md) | Multiple facts sharing dimensions | "three fact tables, one product dim", "net revenue across channels" | Each fact joins to shared dims; cross-fact derived metrics in top-level `metrics:` | `sv-edit` `add_table` per fact + `add_relationship` per fact-to-dim + edit top-level `metrics:` for cross-fact derivations → `sv-deploy` |
| [fact_as_relationship_key](snippets/fact_as_relationship_key.md) | Need to join on a key that doesn't exist as a physical column | "join sales to fiscal_quarters by computed key", "no FK column on source" | Computed fact (scalar expression) referenced as `left_column` inside `relationships:` | Edit YAML to add the computed fact + reference its name as `left_column` in the relationship → `sv-deploy` |
| [ai_metadata](snippets/ai_metadata.md) | Steer Cortex Analyst — SQL style, topic scope, verified queries | "always round to 2 decimals", "decline PII questions", "verified query" | `module_custom_instructions.sql_generation` + `.question_categorization` + `verified_queries:` | Edit YAML to add `module_custom_instructions:` and `verified_queries:` top-level blocks → `sv-deploy` |
| [sv_diagnostics](snippets/sv_diagnostics.md) | An SV deployed but queries error or numbers look wrong | "multi-path relationship not supported", "must be related to and have an equal or lower level of granularity", "numbers look inflated" | Six failure modes with broken/fixed YAML pairs | **Diagnostic catalog — no SV edit per se.** Match symptom → root cause → corresponding pattern's edit sequence above |

## Apply Steps

### A1. Identify and open

Open the matching `snippets/<pattern>.md`. Read *How it works* + *Snippet* + *Gotchas* in full.

### A2. Pull the current YAML

```bash
# Step 1: Read from Snowflake
cortex agent-studio sv-read --fqn DB.SCH.VIEW

# Step 2: Write to workspace (use YAML output from step 1)
cortex agent-studio sv-write --yaml-content '<yaml_content>' --source-object DB.SCH.VIEW
```

### A3. Adapt the snippet

Replace the snippet's placeholder identifiers (table names, column names, join keys) with the real ones from the target SV. Keep the pattern's structural constructs verbatim — these are the delta the pattern adds.

### A4. Apply via the right action

Use `sv-edit` (see the operation table in `../edit/SKILL.md`) for primitive structural edits — `add_table`, `add_relationship`, `add_metric`, `add_dimension`, `add_fact`. For YAML-only knobs that the operation table doesn't cover (e.g. `non_additive_dimensions`, `using_relationships`, `access_modifier: private_access`, `type: asof` / `type: range` + `right_range`, `constraints[].distinct_range`, `module_custom_instructions`, `verified_queries`, top-level cross-table `metrics:`), edit the YAML in `cortex_project/` directly.

### A5. Validate before deploy

Dry-run validate via `snowflake_sql_execute`:

```sql
CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(
  '<DB>.<SCHEMA>',
  $$ <yaml content> $$,
  TRUE  -- TRUE = validate only
);
```

### A6. Deploy and verify

```bash
cortex agent-studio sv-deploy --file-path cortex_project/{VIEW}.sv.yaml --fqn DB.SCH.VIEW
```

Verify with `DESCRIBE SEMANTIC VIEW <DB>.<SCHEMA>.<NAME>` and a smoke query that exercises the new construct (the *How it works* section names exactly which behavior to verify).

### A7. Persist and stage for review

Confirm the YAML in `cortex_project/` reflects the deployed state.

## Hints

- **Pause before every deploy.** Pattern application changes the SV semantically; treat it like the `edit/SKILL.md` deploy step.
- **For agentic-optimization findings** (`../agentic_optimization/SKILL.md`), if the suggestion maps to a pattern in the catalog, prefer applying it via this skill (targeted, reviewable) over a free-form metric/dim addition.
- **For audit findings** (`../audit/SKILL.md`), use the catalog as a "fix recipe" lookup. The `sv_diagnostics` snippet maps every common audit finding to its underlying root cause and corresponding pattern.

## Related

- [../edit/SKILL.md](../edit/SKILL.md) — for the underlying `sv-edit` operation table.
- [../agentic_optimization/SKILL.md](../agentic_optimization/SKILL.md) — when a comprehensive AI optimization run surfaces pattern-shaped suggestions.
- [../audit/SKILL.md](../audit/SKILL.md) — when an audit identifies a structural issue that maps to one of these patterns.
- [../validate/SKILL.md](../validate/SKILL.md) — to validate the YAML before deploy.
