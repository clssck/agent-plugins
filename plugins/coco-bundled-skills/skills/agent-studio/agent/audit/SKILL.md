---
name: agent-studio-agent-audit
description: "Audit a Cortex Agent for quality issues: tool health, spec completeness, configuration problems. Use when: audit agent, is my agent good, review agent setup, agent health check, score my agent tools."
parent_skill: agent-studio-agent
---

# Agent Audit

> Tool usage: see parent `agent/SKILL.md`.

## When to Use

User wants to check the overall quality and configuration of an existing Cortex Agent — not edit it, not debug a specific request.

## Workflow

### Phase 1: Load Agent Spec

1. Identify the agent (ask the user for database, schema, and agent name).
2. Read the spec:
   ```bash
   cortex agent-studio agent-read --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME>
   ```

### Phase 2: Execute Checks

**2.0: SV Tool Quality**

For each `cortex_analyst_text_to_sql` tool in the spec, run via `snowflake_sql_execute`:

```sql
DESCRIBE SEMANTIC VIEW <DB>.<SCHEMA>.<VIEW_NAME>;
```

Load `references/quality_score_formula.md` (relative to this skill) for the full extraction rules, formula, and thresholds. Compute the score for each SV tool.

Also run table intelligence on each SV's base tables (extracted from DESCRIBE TABLE rows):

```bash
cortex search table-details "DB.SCHEMA.TABLE1,DB.SCHEMA.TABLE2,..."
```

Present per-tool:

```
Tool Quality:
  sales_metrics  →  DB.SCHEMA.SALES_SV       score=78%  Good
    Base tables: ORDERS (HIGH, 110 queries), CUSTOMERS (MEDIUM, 36 queries)
  docs_search    →  (Cortex Search — not scored)
  returns_tool   →  DB.SCHEMA.RETURNS_SV     score=43%  Low  (no metrics, 2 VQRs)
    Base tables: RETURNS (LOW, 5 queries)
```

Skip this check if the agent has no `cortex_analyst_text_to_sql` tools.

**2a: Spec Completeness**

Check the YAML for:
- **Instructions present**: at least one of `instructions.response`, `instructions.orchestration`, or `instructions.system` is non-empty
- **Tool descriptions**: every tool in `tools[]` has a non-empty `description`
- **Orchestration guidance**: if 2+ tools exist, `instructions.orchestration` should explain when to use each (flag WARNING if missing)
- **Sample questions**: if `instructions.sample_questions` is empty, flag INFO

**2b: Configuration Issues**

- **Warehouse set**: every analyst tool has `tool_resources.<name>.execution_environment.warehouse` defined
- **Semantic view exists**: each `tool_resources.<name>.semantic_view` is resolvable (already checked in 2.0 via DESCRIBE)
- **Search service exists**: each `tool_resources.<name>.search_service` is resolvable — run `SHOW CORTEX SEARCH SERVICES LIKE '%<name>%' IN ACCOUNT;` via `snowflake_sql_execute` if needed
- **Model valid**: if `models.orchestration` is set to something other than `"auto"`, flag INFO that a specific model is pinned

**2c: Comment Review**

Run via `snowflake_sql_execute`:
```sql
DESCRIBE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
```

Check the `comment` column:
- Missing or empty → WARNING: "No comment set — multi-agent routing will be impaired"
- Significantly exceeds 1000 chars → INFO: "Comment is very long, consider trimming"
- Present and reasonable → pass

### Phase 3: Categorize Issues

- **ERROR**: Agent will fail (missing warehouse, unresolvable SV/search service)
- **WARNING**: Should be addressed (no orchestration instructions with multiple tools, no comment, SV tool score < 50%)
- **INFO**: Recommendations (no sample questions, pinned model, long comment)

### Phase 4: Present Results

Show in this order:
1. Tool Quality section (from 2.0) — always first
2. Issues summary with severity counts
3. Detailed findings grouped by severity

### Phase 5: Next Steps

Prompt user with options based on what was found:

- Fix a low-scoring SV tool → route to the semantic-view audit skill (`../../semantic-view/audit/SKILL.md`) for that SV
- Fix spec completeness issues → route to `../edit/SKILL.md`
- Fix comment → route to `../edit/SKILL.md` (comment review step)
- **Run eval** → route to `../eval/SKILL.md`
- **Exit**

## Stopping Points

- Phase 5: After audit completion
