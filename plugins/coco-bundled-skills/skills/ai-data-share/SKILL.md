---
name: ai-data-share
description: "Make a listing or data share AI-Ready. Use when: creating semantic views for listings, creating cortex agents for data shares, making data AI-ready. Triggers: AI-ready listing, share agent, data share semantic view, marketplace AI."
---

# AI Ready Data Share

## Purpose

Automatically create a complete data agent by:
1. Resolving your data source (listing or share)
2. Creating a semantic view from the source tables
3. Creating a Cortex Agent connected to the semantic view

## Workflow

### Step 0: Resolve the listing or the share

 **Load** `resolve_source.md` first. This will ask the user whether they're starting from a listing or an existing share:
- **Listing path:** Resolves the listing to extract the share, then inspects share objects.
- **Share path:** Validates the share directly, optionally reverse-looks up an associated listing for metadata enrichment, then inspects share objects.

Both paths converge on share object inspection, exclusion rules, and existing semantic view checks before proceeding to Phase 1.

---

### Phase 1: Create Semantic View

**Load:** [create_semantic_view.md](create_semantic_view.md)

This phase will:
- Collect your source tables (from listing or share)
- Ask for documentation/context about the data
- Discover table schemas and relationships
- Generate table/column comments from context (only for empty fields)
- Generate and deploy a semantic view using FastGen

---

### Phase 2: Create Agent

**Load:** [create_agent.md](create_agent.md)

This phase will:
- Check for existing agents on the same tables
- Offer choice: use existing, create new, or optimize existing
- Connect to the semantic view from Phase 1
- Generate orchestration and response prompts
- Configure tools with appropriate descriptions
- Deploy the agent to Snowflake via REST API

---

## Attaching Objects to Shares

After creating semantic views or agents, use the **attach-ai-products-to-share** skill to properly attach them to the share, if they haven't been added already:

```
<invoke name="skill">
<parameter name="command">attach-ai-products-to-share</parameter>
</invoke>
```

The skill handles:
- Correct grant ordering (database → schema → object)
- Semantic view dependencies (underlying tables)
- Agent tool dependencies
- Cortex Search Service grants

### Quick Reference (Manual Grants)

| Object Type | Syntax |
|-------------|--------|
| Show Agents | `SHOW AGENTS IN DATABASE db;` (NOT `SHOW CORTEX AGENTS`) |
| Semantic View | `GRANT SELECT, REFERENCES ON SEMANTIC VIEW db.schema.view TO SHARE share_name;` |
| Agent | `GRANT USAGE ON AGENT db.schema.agent TO SHARE share_name;` |
| Cortex Search Service | `GRANT USAGE ON CORTEX SEARCH SERVICE db.schema.css TO SHARE share_name;` |
| Table | `GRANT SELECT ON TABLE db.schema.table TO SHARE share_name;` |
| Schema | `GRANT USAGE ON SCHEMA db.schema TO SHARE share_name;` |
| Database | `GRANT USAGE ON DATABASE db TO SHARE share_name;` |

---

## Output

Upon completion, this skill produces:

| Deliverable | Description |
|-------------|-------------|
| Semantic View | Fully qualified semantic view connected to source tables |
| Cortex Agent | Agent with orchestration/response prompts, linked to semantic view |
| Share Grants | All objects properly granted to share |

**Files generated:**
- Semantic model YAML (via semantic-view skill)
- Agent specification (via cortex-agent skill)

---

## Stopping Points

- ✋ **resolve_source:** Choose entry point (listing or share)
- ✋ **resolve_source:** Select listing identification method (listing path only)
- ✋ **resolve_source:** Confirm included/excluded objects before proceeding
- ✋ **resolve_source:** If existing semantic view found, choose reuse or create new
- ✋ **create_semantic_view:** Confirm inputs and documentation sources
- ✋ **create_semantic_view:** Review semantic model before deployment
- ✋ **create_agent:** Provide agent persona, domain focus, target audience
- ✋ **create_agent:** Select agent location from eligible schemas
- ✋ **create_agent:** Review agent configuration before deployment

**Resume rule:** Upon user approval, proceed directly to next step without re-asking.

---

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| "Invalid identifier" on FastGen upload | Passed 3-part name instead of 2-part | Use `DATABASE.SCHEMA` not `DATABASE.SCHEMA.VIEW` |
| "CORTEX AGENT not found" on grant | Wrong grant syntax | Use `GRANT USAGE ON AGENT` (no CORTEX keyword) |
| pyarrow build fails | Python 3.13+ incompatible | Run `uv python install 3.11` - uv will use the correct Python version automatically |
| FastGen many-to-many warning | Missing unique keys on FK target | Informational only - relationships still work via other paths |
| "Cannot grant to share" | Object not in eligible schema | Ensure object is in a schema with USAGE grant to share |
| Agent spec empty after creation | Wrong DDL syntax | Use `FROM SPECIFICATION $$...$$` not `SPEC = '...'` |
