---
name: agent-studio-agent-templated-creation
description: "Template discovery sub-workflow for Cortex Agent creation. Infers Q1-Q4 answers from the user's request, asks only the unanswered questions, selects the right archetype (T01-T07), and loads the matching template file to write the spec via cortex agent-studio agent-write."
parent_skill: agent-studio-agent-creation
---

# Templated Agent Creation

## When to Load

Always loaded from `creation/SKILL.md` after Step 1. Every create request runs through this discovery workflow. The goal is to write a meaningful template spec instead of an empty `{}` so the user starts with a real starting point.

---

## Step A: Infer Before You Ask

Before asking anything, scan the user's original message for signals that already answer Q1–Q4:

| Signal in user's message | Inferred answer |
|--------------------------|-----------------|
| **"empty agent", "placeholder", "minimal agent", "does nothing", "no tools", "no data access"** | **Skip all questions → Use T00 immediately** |
| Names a Snowflake table, semantic view, or data domain | Q1: 1 SV (or 2–4 if multiple distinct domains named) |
| "policies", "runbooks", "documentation", "PDFs", "wiki", "knowledge base" | Q3: Yes — document search layer needed |
| "create a ticket", "update CRM", "trigger pipeline", "call API", "stored procedure", "file a ticket" | Q4: Yes — action needed (generic tool) |
| "Jira", "Salesforce", "ServiceNow", "GitHub", "Slack", "external API", "integration", "webhook", "connect to" (external system) | Q4: Yes — action needed (MCP/Integration) |
| "no structured data", "just answer questions about docs", "only documents" | Q1: 0 SVs |
| Multiple named domains ("sales and inventory and finance") | Q1: 2–4 SVs |
| "answer data questions AND look things up in docs" | Q2: Hybrid (analytics + docs) |

If all 4 questions are resolved from context, skip to Step C immediately.

---

## Step B: Ask Only Unanswered Questions

Present all remaining questions in a **single message** — never as separate conversation turns. Open with "To pick the right starting template, I have a few quick questions:" and include only the items below that are still unanswered.

**Q1 (include only if not yet inferred):**
> **1. Data domains** — What structured data should the agent query?
> How many distinct subject areas? (e.g. "sales only" = 1, "sales + inventory + finance" = 3, "none — only documents" = 0)

**Q2 (include only if not yet inferred):**
> **2. Primary job** — Finish this sentence: my users will mostly come to this agent when they want to ___
> Options: get a number or answer a data question · find a document or policy · both data AND docs · trigger an action

**Q3 (include only if not yet inferred):**
> **3. Document search** — Do users ever ask "what does our policy say about X" alongside data questions? (yes / no)

**Q4 (include only if not yet inferred):**
> **4. Actions** — Should the agent DO something — run a Snowflake procedure, trigger a pipeline, or connect to an external system (Jira, Salesforce, Slack, etc.)?
> Options: Snowflake procedure / UDF · external system via MCP · both · no

If the answer to any question is ambiguous (e.g. "I want it to answer questions about our data" doesn't clearly indicate 1 or many domains), ask a brief clarifying follow-up rather than guessing — a wrong template wastes more time than one extra question.

Wait for the user's answers, then proceed to Step C.

---

## Step C: Route to Template

| Q1 SVs | Q2 Job | Q3 Docs | Q4 Actions | Template file |
|--------|--------|---------|------------|---------------|
| **—** | **—** | **—** | **—** | **`templates/T00.md` — if user explicitly asks for empty/placeholder/minimal agent with no tools** |
| 1 | analytics | No | No | `templates/T01.md` |
| 2–4 | analytics | No | No | `templates/T02.md` |
| 1 | analytics or both | Yes | No | `templates/T03.md` |
| 1 | docs (SV is supplementary) | — | No | `templates/T03.md` |
| 2–4 | analytics or both | Yes | No | `templates/T04.md` |
| any with SVs | any | any | Yes (procedure/UDF) | `templates/T05.md` |
| any with SVs | any | any | Yes (MCP/Integration) | `templates/T05.md` — use the MCP variant section |
| 0 | docs | — | No | `templates/T06.md` |
| 0 | action | — | Yes (procedure/UDF) | `templates/T07.md` |
| 0 | action | — | Yes (MCP/Integration) | `templates/T07.md` — use the MCP variant section |
| 0 | docs | Yes | Yes | `templates/T07.md` — MCP variant + add a `cortex_search` tool |

**Upgrade signals** — if the user's answers contain any of these, upgrade even if the base routing said otherwise:

| User says | Action |
|-----------|--------|
| Multiple named domains ("sales, finance, ops") | Bump to T02 or T04 |
| "runbooks / policies / wikis" | Add search layer → T03 or T04 |
| "create a ticket / update CRM / trigger pipeline" | Add action → T05 or T07 |
| "Jira / Salesforce / Slack / external API / webhook" | Use MCP variant in T05 or T07 |
| "answer HR policy questions" / "just our docs" | Pure search → T06 |
| Cannot describe exact inputs for a procedure action | Ask: "What inputs does the procedure need — parameter names and types?" before proceeding |
| User mentions MCP but the server doesn't exist yet | Note: a Snowflake MCP Server object must be created first (`CREATE MCP SERVER` for Snowflake-native wrapping, `CREATE CUSTOM MCP SERVER` for SPCS-hosted external services) |

---

## Step D: Write the Template Spec

1. Tell the user the recommended template and why (one sentence).

2. Read the template file from Step C (`templates/T0X.md`). Build the YAML spec by combining the **tools + tool_resources** block with the **instructions starter** from that file.

3. Call `cortex agent-studio agent-write`. Write the combined YAML to a temp file first (to avoid shell-escaping issues), then pass the content via `--yaml-content`:
   ```bash
   cat > /tmp/agent_spec.yaml << 'YAML_EOF'
   <COMBINED_YAML>
   YAML_EOF
   cortex agent-studio agent-write \
     --yaml-content "$(cat /tmp/agent_spec.yaml)" \
     --source-object <DATABASE>.<SCHEMA>.<AGENT_NAME>
   ```
   (`--file-path` controls the *output* path inside `cortex_project/` — it is **not** the input.)

4. Confirm to the user: "I've written the **T0X** template to the workspace — nothing is deployed to Snowflake yet. Now let's replace the placeholders with your actual values." Then show a short checklist of what they'll need to provide in the edit flow — include only items relevant to the chosen template:
   - **Analytics templates with analyst tool (T01–T04, T05 Variant A):** Semantic view FQN (`DATABASE.SCHEMA.VIEW_NAME`)
   - **Adding search (T03, T04, T06, T07+search):** Cortex Search Service FQN, id column name, title column name
   - **Adding procedure/UDF actions (T05, T07):** Stored procedure or UDF FQN, exact input parameter names and types
   - **Adding MCP/Integration actions (T05, T07):** MCP Server FQN (`DATABASE.SCHEMA.MCP_SERVER`) — the MCP Server object must already exist in Snowflake
   - **Any template:** Snowflake role for the agent, warehouse name, persona / tone for the instructions, 3–5 sample questions

5. Load `edit/SKILL.md` and continue there for all spec content authoring and deploying to Snowflake.
