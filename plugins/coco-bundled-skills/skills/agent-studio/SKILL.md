---
name: agent-studio
description: >-
  Semantic View, Semantic Model, Cortex Analyst, and Cortex Agent skill. Use for ALL
  requests that mention these — including create, build, edit, deploy, validate, audit,
  optimize, evaluate, suggest VQRs/relationships, or manage verified queries.
  Keywords: semantic view, semantic model, Cortex Analyst, Cortex Agent, analyst YAML,
  semantic YAML, analyst model, VQR, verified query, verified query representation,
  agentic optimization, optimize agent, improve agent accuracy, production-ready agent,
  sql_correctness, SQL generation accuracy, audit semantic view,
  suggest relationships, suggest metrics, suggest filters, agent alias, agent version,
  importing Tableau workbooks (.twb/.twbx/.tds/.tdsx), importing Power BI files (.pbit/.pbix),
  importing OSI (Open Semantic Interchange, also known as Ossie) YAML models.
  DO NOT attempt these operations manually — this is the entry point.
---

# Agent Studio Skills

## When to Use

When a user wants to work with **Cortex Agents**, **Semantic Views**, or **debug agent requests** in Snowflake.

## Routing Rules

```
User Request → Determine Intent
│
├─ Semantic View operations (create, edit, upload, download, validate YAML or VQRs, suggest VQRs, suggest metrics/filters/relationships)
│  └─> Load semantic-view/SKILL.md
│
├─ Agent operations (create, edit, test, download, upload, optimize agent)
│  └─> Load agent/SKILL.md
│
├─ Debug agent request / troubleshoot agent
│  └─> Load debug/SKILL.md
│
└─ Unclear intent → Ask:
   "What would you like to do?
    1. Work with Semantic Views (create, edit, upload, download, validate, suggestions)
    2. Work with Cortex Agents (create, edit, test, download, upload, optimize)
    3. Debug a Cortex Agent request"
```

| Domain | Trigger Phrases | Route To |
|--------|----------------|----------|
| **Semantic View** | create / build / edit / modify / update a semantic view; add a table, column, metric; upload or deploy a YAML; download or export a semantic view; generate or improve descriptions; audit a semantic view; validate a semantic-view YAML; bulk-validate verified queries (VQRs); mine VQR suggestions; suggest metrics, filters, or facts; run agentic optimization (on a semantic view); import a Tableau workbook (.twb/.twbx/.tds/.tdsx); import a Power BI file (.pbit/.pbix); import an OSI (Open Semantic Interchange, also known as Ossie) YAML model | `semantic-view/SKILL.md` |
| **Agent** | create agent, build agent, new agent, edit agent, modify agent, update agent, change agent instructions, add tool to agent, test agent, try agent, ask agent, chat with agent, verify agent, download agent, export agent, save agent locally, upload agent, save agent, deploy agent, push agent, publish agent, connect to CoWork, add to Snowflake Intelligence, create eval dataset, evaluation dataset, curate dataset, ground truth data, evaluate agent, run evaluation, benchmark agent, audit agent, score my agent, optimize agent, improve agent accuracy, prepare agent for production, generalize agent instructions | `agent/SKILL.md` |
| **Debug** | debug agent, troubleshoot agent, agent error, fix agent, agent not working, wrong answer, agent logs, analyst logs, observability logs, request logs, check logs, show logs, what happened with request | `debug/SKILL.md` |

Bare **"optimize"** without a target: if the user named an agent (or `get_page_context` has `agentName`) → Agent. If they named a semantic view, or said **agentic optimization** → Semantic View. If still unclear, ask.

## Sub-Skills

### 1. **Semantic View** — Create, edit, upload, download, validate, and generate descriptions for semantic views
- **Entry Point**: [semantic-view/SKILL.md](semantic-view/SKILL.md)

### 2. **Agent** — Create, edit, test, download, upload, and optimize Cortex Agents
- **Entry Point**: [agent/SKILL.md](agent/SKILL.md)

### 3. **Debug** — Debug Cortex Agent requests
- **Entry Point**: [debug/SKILL.md](debug/SKILL.md)

## Action

1. Identify the domain (Semantic View vs Agent vs Debug) from user request using the routing rules above
2. Load the appropriate sub-skill SKILL.md file
3. That sub-skill has its own routing to more specific workflows — follow it exactly
