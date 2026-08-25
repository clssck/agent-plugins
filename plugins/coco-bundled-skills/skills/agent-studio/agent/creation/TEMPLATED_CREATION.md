---
name: agent-studio-agent-templated-creation
description: "Template discovery sub-workflow for Cortex Agent creation. Infers Q1-Q3 answers from the user's request, asks only the unanswered questions, selects the right archetype (T01-T07), and loads the matching template file to write the spec via cortex agent-studio agent-write."
parent_skill: agent-studio-agent-creation
---

# Templated Agent Creation

## When to Load

Always loaded from `creation/SKILL.md` after Step 1. Every create request runs through this discovery workflow. The goal is to write a meaningful template spec instead of an empty `{}` so the user starts with a real starting point.

---

## Step A: Infer Before You Ask

Before asking anything, scan the user's original message for signals that already answer Q1–Q3:

| Signal in user's message | Inferred answer |
|--------------------------|-----------------|
| **"empty agent", "placeholder", "minimal agent", "does nothing", "no tools", "no data access"** | **Skip all questions → Use T00 immediately** |
| Names a Snowflake table, semantic view, or data domain | Q1: 1 domain (or multiple if several named) |
| "no tables", "just answer questions about docs", "only documents" | Q1: none |
| Multiple named domains ("sales and inventory and finance") | Q1: multiple |
| "policies", "runbooks", "documentation", "PDFs", "wiki", "knowledge base", "technical docs", "internal docs" | Q2: Yes — document search layer needed |
| "answer data questions AND look things up in docs" | Q1: 1+ domains, Q2: Yes |
| "create a ticket", "update CRM", "trigger pipeline", "call API", "stored procedure", "file a ticket" | Q3: procedure/UDF |
| "Jira", "Salesforce", "ServiceNow", "GitHub", "Slack", "external API", "integration", "webhook", "connect to" (external system) | Q3: external tool |

If all 3 questions are resolved from context, skip to Step C immediately.

---

## Step B: Ask Only Unanswered Questions

Present all remaining questions in a **single message** — never as separate conversation turns. Open with "To build the right agent for you, a few quick questions:" and include only the items below that are still unanswered.

**Q1 (include only if not yet inferred):**
> **1. Your data** — What data does this agent need to answer questions about?
> Describe it briefly — e.g. "sales tables", "sales + inventory + finance", or "none — I only need it to search documents"

**Q2 (include only if not yet inferred):**
> **2. Documents** — Will users ever ask questions based on documents or written content — like policies, runbooks, technical docs, or PDFs? (yes / no)

**Q3 (include only if not yet inferred):**
> **3. Other systems** — Does the agent need to connect to other tools or systems — for example, run a Snowflake stored procedure, trigger a pipeline, or read from / write to an external tool like Jira, Salesforce, or Slack?
> Options: Snowflake procedure or UDF · external tool (Jira, Salesforce, Slack…) · both · no

If the answer to any question is ambiguous (e.g. "I want it to answer questions about our data" doesn't clearly indicate 1 or many domains), ask a brief clarifying follow-up rather than guessing — a wrong starting point wastes more time than one extra question.

Wait for the user's answers, then proceed to Step C.

---

## Step C: Route to Template

| Q1 Data | Q2 Docs | Q3 Actions | Template file |
|---------|---------|------------|---------------|
| **—** | **—** | **—** | **`templates/T00.md` — if user explicitly asks for empty/placeholder/minimal agent with no tools** |
| none | No | No | `templates/T00.md` |
| 1 domain | No | No | `templates/T01.md` |
| multiple domains | No | No | `templates/T02.md` |
| 1 domain | Yes | No | `templates/T03.md` |
| multiple domains | Yes | No | `templates/T04.md` |
| any with tables | any | procedure/UDF | `templates/T05.md` |
| any with tables | any | external tool | `templates/T05.md` — use the external tool variant section |
| any with tables | any | both | `templates/T05.md` — include both Variant A (procedure) and external tool variant sections |
| none | Yes | No | `templates/T06.md` |
| none | No | procedure/UDF | `templates/T07.md` |
| none | No | external tool | `templates/T07.md` — use the external tool variant section |
| none | No | both | `templates/T07.md` — include both Variant A (procedure) and external tool variant sections |
| none | Yes | procedure/UDF | `templates/T07.md` — Variant A + add a `cortex_search` tool |
| none | Yes | external tool | `templates/T07.md` — external tool variant + add a `cortex_search` tool |
| none | Yes | both | `templates/T07.md` — both variants + add a `cortex_search` tool |

**Upgrade signals** — if the user's answers contain any of these, upgrade even if the base routing said otherwise:

| User says | Action |
|-----------|--------|
| Multiple named domains ("sales, finance, ops") | Bump to T02 or T04 |
| "runbooks / policies / wikis / PDFs / technical docs" | Add search layer → T03 or T04 |
| "create a ticket / update CRM / trigger pipeline" | Add action → T05 or T07 |
| "Jira / Salesforce / Slack / external API / webhook" | Use external tool variant in T05 or T07 |
| "answer HR policy questions" / "just our docs" | Pure search → T06 |
| Cannot describe exact inputs for a procedure action | Ask: "What inputs does the procedure need — parameter names and types?" before proceeding |
| User mentions an external tool but the MCP Server doesn't exist yet | Note: a Snowflake MCP Server object must be created first (`CREATE MCP SERVER` for Snowflake-native wrapping, `CREATE CUSTOM MCP SERVER` for SPCS-hosted external services) |

---

## Step D: Write the Template Spec

1. Tell the user what kind of agent this will be and why — one sentence in plain terms (e.g. "This will be a hybrid agent that can answer data questions and search your internal docs").

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

4. Confirm to the user: "I've set up a starting spec for your agent in the workspace — nothing is deployed to Snowflake yet. Now let's replace the placeholders with your actual values." Then show a short checklist of what they'll need to provide in the edit flow — include only items relevant to the chosen template:
   - **Analytics templates with analyst tool (T01–T04, T05 Variant A):** Semantic view FQN (`DATABASE.SCHEMA.VIEW_NAME`)
   - **Adding search (T03, T04, T06, T07+search):** Cortex Search Service FQN, id column name, title column name
   - **Adding procedure/UDF actions (T05, T07):** Stored procedure or UDF FQN, exact input parameter names and types
   - **Adding MCP/Integration actions (T05, T07):** MCP Server FQN (`DATABASE.SCHEMA.MCP_SERVER`) — the MCP Server object must already exist in Snowflake
   - **Any template:** Snowflake role for the agent, warehouse name, persona / tone for the instructions, 3–5 sample questions

5. Load `edit/SKILL.md` and continue there for all spec content authoring and deploying to Snowflake.
