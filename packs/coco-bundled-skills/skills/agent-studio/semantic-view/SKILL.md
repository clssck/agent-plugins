---
name: semantic-view
description: "Create, edit, upload, download, audit, validate, and manage Cortex Analyst semantic views. Prefer this router for semantic view work in Snowflake: create/edit/deploy YAML, descriptions, audits, relationship or VQR suggestions, filter/metric suggestions, validate semantic view YAML (and VQRs only when the user asks for VQR validation), import Tableau workbooks (.twb/.twbx/.tds/.tdsx), import Power BI files (.pbit/.pbix), import OSI (Open Semantic Interchange, also known as Ossie) YAML models, run agentic optimization, or manage VQRs (add/remove/expand/truncate). Also when users say 'analyst model' or 'semantic YAML' instead of 'semantic view'."
parent_skill: agent-studio
---

# Semantic View Skill

## CLI Reference

Use the `cortex agent-studio` CLI for ALL semantic view operations:

| Command | Purpose |
|---------|---------|
| `cortex agent-studio sv-generate --json-proto '<json>'` | Create YAML from tables/SQL |
| `cortex agent-studio sv-read --fqn DB.SCHEMA.NAME` | Read semantic view from Snowflake |
| `cortex agent-studio sv-read --source workspace --file-path <path>` | Read from workspace file |
| `cortex agent-studio sv-write --yaml-content '<yaml>' --source-object DB.SCHEMA.NAME` | Save YAML to workspace (auto-generates path). Use `--file-path <FILE_NAME>.sv.yaml` if file path from system reminder/user input |
| `cortex agent-studio sv-deploy --file-path <path> --fqn DB.SCHEMA.NAME` | Deploy YAML to Snowflake |
| `cortex agent-studio sv-edit --file-path <path> --operations '<json>'` | Edit YAML in place (combines semantic_model_edit + extract + sv-write) |
| `cortex agent-studio backend --tool suggest_relationships --file-path <path> --parameters '<json>'` | AI relationship suggestions |
| `cortex agent-studio backend --tool tableau_analyze --parameters '<json>'` | Analyze Tableau file structure |
| `cortex agent-studio backend --tool tableau_export --parameters '<json>'` | Convert Tableau file to YAML |
| `cortex agent-studio backend --tool pbi_analyze --parameters '<json>'` | Analyze Power BI file structure (.pbit/.pbix) |
| `cortex agent-studio backend --tool pbi_export --parameters '<json>'` | Convert Power BI file to YAML |
| `cortex agent-studio backend --tool osi_write_model --parameters '<json>'` | Register an OSI YAML model directly in Snowflake |

**Forbidden:** Do NOT use `read`, `write`, `edit`, `multi_edit`, or `bash` tools on semantic view YAML files. These bypass `cortex_project/` tracking.

## ⚠️ First Step: Load References

For description tasks, load:
```
Read: semantic-view/reference/description_guidelines.md
```

## Workflow Routing

**Canonical create phrases — always route to `creation/SKILL.md`, never treat as ambiguous:**
- "Help me create a semantic view"
- "Help me create a semantic model" / "Help me create an analyst model"
- "Help me build / set up / make a semantic view"

```
User Request → Route to Sub-Skill
│
├─ Create new view → creation/SKILL.md
├─ Edit existing view (user knows what to change) → edit/SKILL.md
├─ Upload/deploy YAML → upload/SKILL.md
├─ Download/export → download/SKILL.md
├─ Generate descriptions → generate_description/SKILL.md
├─ Validate semantic view YAML; validate VQRs only if the user asks → validate/SKILL.md
├─ Audit (best practices, heuristics) → audit/SKILL.md

├─ Suggest relationships → suggest_relationships/SKILL.md
├─ VQR suggestions → vqr_suggestions/SKILL.md
├─ Suggest/recommend metrics, filters, or facts → filters_and_metrics_suggestions/SKILL.md
├─ Manage VQRs (add/remove, expand/truncate, spot-validate SQL) → vqr_management/SKILL.md
├─ Run automated/agentic optimization (start, poll, cancel, list past runs) → agentic_optimization/SKILL.md
├─ Apply an advanced modeling pattern: compare a metric to the same period last year/month (YoY, MoM, SPLY); build rolling averages, YTD/QTD/MTD totals, or lag-N comparisons; model an SCD2 lookup with `valid_from`/`valid_to` or attribute an event to the dim row active at event time (ASOF); track snapshot facts that must not sum across time (balance / inventory / headcount); model an accumulating snapshot funnel across multiple milestone dates; route a metric down a specific FK when a fact has two FKs to the same dim (multi-path USING); reuse the same physical dim under multiple roles (role-playing dims); add cross-entity totals or ratios (`% of total`, `net = gross − returns`); split shared dims across multiple fact tables (multi-fact); expose a `PRIVATE` fact used only inside the SV to derive a tier or other dimension; join on a key that doesn't exist as a physical column (computed FK); steer Cortex Analyst with verified queries / `AI_SQL_GENERATION` / `AI_QUESTION_CATEGORIZATION` metadata; or diagnose a fan trap / "multi-path relationship not supported" / numbers that look inflated → patterns/SKILL.md
├─ Import Tableau file → import_tableau/SKILL.md
├─ Import Power BI file → import_powerbi/SKILL.md
├─ Import OSI (Ossie) YAML model → import_osi/SKILL.md
│
└─ Unclear → Ask:
   "Would you like to:
    1. Create a new semantic view
    2. Edit an existing view
    3. Upload/deploy a YAML file
    4. Download an existing view
    5. Generate descriptions
    6. Audit for quality issues
    7. Validate the semantic view (YAML); validate verified queries only if they ask
    8. Suggest relationships
    9. Get VQR suggestions from usage or query history
    10. Get filter & metric suggestions from query history
    11. Add, remove, or convert verified query SQL
    12. Run agentic optimization (automated AI optimization job)
    13. Import a Tableau workbook
    14. Import a Power BI file
     15. Import an OSI (Ossie) YAML model"
```

**Edit vs suggest vs VQR vs agentic vs pattern:**
- User names a specific change ("add metric X", "rename column Y") → `edit/SKILL.md`
- User asks for ideas ("suggest / recommend metrics, filters, or facts", "what should I add?") → `filters_and_metrics_suggestions/SKILL.md`
- User wants to add, remove, or rewrite a verified query ("expand this query", "truncate VQR") → `vqr_management/SKILL.md`
- User wants to validate the YAML before deploy, or explicitly asks to bulk-validate VQRs → `validate/SKILL.md`
- User wants to start an automated AI optimization job, check whether one finished, cancel a running job, or list past optimization runs → `agentic_optimization/SKILL.md`
- User describes an advanced modeling intent — compare to same period last year/month (YoY, MoM, SPLY), build a rolling / YTD / lag-N metric, model an SCD2 lookup with `valid_from`/`valid_to` or ASOF join, track a snapshot fact that must not sum across time, model an accumulating funnel across milestone dates, route a metric through a specific FK when a fact has two FKs to one dim, add a cross-entity derived metric (`% of total`, `net = gross − returns`), expose a `PRIVATE` fact, join on a computed (non-physical) key, steer Cortex Analyst with verified-queries / `AI_SQL_GENERATION` metadata, or diagnose a fan trap / "multi-path relationship not supported" / inflated-numbers symptom → `patterns/SKILL.md`
- User asks to import a `.twb / .twbx / .tds / .tdsx` workbook → `import_tableau/SKILL.md`
- User asks to import a `.pbit / .pbix` file → `import_powerbi/SKILL.md`
- User asks to import an OSI YAML model (`.osi.yaml`, mentions "open semantic interchange" or "ossie", or provides OSI YAML inline) → `import_osi/SKILL.md`

## Sub-Skills

| Sub-Skill | Purpose |
|-----------|---------|
| [creation/SKILL.md](creation/SKILL.md) | Generate new semantic views from tables/SQL |
| [edit/SKILL.md](edit/SKILL.md) | Modify existing views (add/remove/rename) |
| [upload/SKILL.md](upload/SKILL.md) | Deploy YAML to Snowflake |
| [download/SKILL.md](download/SKILL.md) | Export views from Snowflake to workspace |
| [generate_description/SKILL.md](generate_description/SKILL.md) | AI-powered descriptions for components |
| [audit/SKILL.md](audit/SKILL.md) | Quality checks (best practices, duplicates, inconsistencies) |
| [validate/SKILL.md](validate/SKILL.md) | `SYSTEM$WRITE_SEMANTIC_MODEL_YAML(..., TRUE)` YAML check; VQR `validate_verified_queries` only when the user requests it |
| [suggest_relationships/SKILL.md](suggest_relationships/SKILL.md) | AI-powered relationship suggestions |
| [vqr_suggestions/SKILL.md](vqr_suggestions/SKILL.md) | VQR suggestions from query history or CA usage |
| [filters_and_metrics_suggestions/SKILL.md](filters_and_metrics_suggestions/SKILL.md) | Filter, metric, and fact suggestions from query history |
| [vqr_management/SKILL.md](vqr_management/SKILL.md) | Add/remove VQRs; expand/truncate SQL; spot-validate SQL strings |
| [agentic_optimization/SKILL.md](agentic_optimization/SKILL.md) | Run / poll / cancel / list automated `SYSTEM$CORTEX_ANALYST_*_AGENTIC_OPTIMIZATION` jobs and apply approved suggestions |
| [patterns/SKILL.md](patterns/SKILL.md) | 14-pattern catalog of advanced SV modeling intents — period-over-period comparisons (YoY/MoM/SPLY), rolling/YTD/lag-N metrics, SCD2/ASOF temporal joins, snapshot facts that must not sum across time, accumulating funnels, multi-path metrics, role-playing dimensions, cross-entity derived metrics, multi-fact layouts, `PRIVATE` facts, computed-FK joins, AI metadata steering Cortex Analyst, and a six-scenario structural-diagnostic catalog (fan trap, multi-path errors, wrong cardinality, etc.). Each pattern ships a tight DDL/YAML snippet plus gotchas, applied via `cortex agent-studio` CLI for YAML-supported patterns and `snowflake_sql_execute` for DDL-only ones |
| [import_tableau/SKILL.md](import_tableau/SKILL.md) | Import Tableau .twb/.twbx/.tds/.tdsx files |
| [import_powerbi/SKILL.md](import_powerbi/SKILL.md) | Import Power BI .pbit/.pbix files |
| [import_osi/SKILL.md](import_osi/SKILL.md) | Import OSI (Ossie) YAML models via `osi_write_model` |

## References

| File | Purpose |
|------|---------|
| [reference/description_guidelines.md](reference/description_guidelines.md) | Description quality standards |
| [reference/tableau_tool_reference.md](reference/tableau_tool_reference.md) | Tableau import API reference |
| [reference/pbi_tool_reference.md](reference/pbi_tool_reference.md) | Power BI import API reference |
| [reference/osi_tool_reference.md](reference/osi_tool_reference.md) | OSI `osi_write_model` API reference |

## Rules

1. **Never generate SQL queries** - wait for user to provide them
2. **Load the appropriate sub-skill** before performing operations
3. **Never deploy without explicit user approval**
