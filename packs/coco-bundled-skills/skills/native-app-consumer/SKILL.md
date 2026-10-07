---
name: native-app-consumer
description: "**[REQUIRED]** for ALL Snowflake Native App consumer tasks: installing apps from listings as a consumer, configuring installed apps (granting privileges, approving specifications, reviewing references), managing maintenance policies, understanding native app cost and credit usage, adding native apps to budgets, diagnosing and fixing agent and MCP server issues (caller grants, feature policies, role delegation), uninstalling apps. Triggers: native app, install native app, configure native app, approve spec, decline spec, maintenance policy, maintenance window, upgrade schedule, control upgrades, app cost, app budget, app spending, native app cost, native app credits, how much does my app cost, uninstalling apps, dropping apps, remove app, drop application, app-created agent not working, app agent issues, app MCP issues, caller grants for app, GRANT CALLER to app, fix agent in app, diagnose app agent, configure agent in app, app-created MCP not working, grant caller to application, app MCP configuration."
---

# Snowflake Native App — Consumer

This is a **routing skill**. It detects the user's intent and directs you to the correct sub-skill. You **MUST** load the sub-skill before doing any work — do NOT attempt native app tasks using only the information on this page.

## Running in Snowsight?

**⚠️ MANDATORY**: If your system prompt mentions Snowsight, load [`../native-app-provider/references/native-apps-snowsight.md`](../native-app-provider/references/native-apps-snowsight.md) before routing. It governs all env-specific decisions for everything below.

## Key Concepts

- **Snowflake Native App**: The application object created in the consumer account when they install the application from a listing
- **Listing**: A published entry on the Snowflake Marketplace or a private data exchange through which consumers discover and install native apps

## Routing Table

**Before starting any work**, scan the user's full request and identify ALL matching intents from the table below. If the request spans multiple intents, load each relevant sub-skill before performing that phase of work — do NOT attempt SQL from memory.

| Intent | Triggers | Sub-Skill to Load |
|--------|----------|--------------------|
| **Install Application** — Install a native app from a Marketplace listing | "install app", "install from listing", "get app", "install native app", "consumer install", "get app from marketplace", "install application from listing" | `install-app/SKILL.md` |
| **Configure Application** — Review/grant privileges, approve specs, review references for an installed app | "configure app", "review app privileges", "grant app privileges", "app specifications", "approve spec", "decline spec", "configure native app", "app references", "review app", "check app" | `configure-app/SKILL.md` |
| **Manage Maintenance Policies** — Control when Native App upgrades happen by creating and applying maintenance policies | "maintenance policy", "maintenance window", "upgrade schedule", "control upgrades", "upgrade timing", "app maintenance", "manage upgrades", "set maintenance window", "create maintenance policy", "when upgrades happen" | `manage-maintenance-policy/SKILL.md` |
| **Enable Logging & Troubleshoot** — Set up event table, enable event sharing, query app logs/traces/errors | "enable logging", "event sharing", "troubleshoot app", "app logs", "event table", "telemetry", "debug app", "app errors", "trace events", "enable events", "app diagnostics" | `enable-logging/SKILL.md` |
| **Configure Agent / MCP** — Diagnose and fix Cortex Agent and MCP server issues in an installed app: derive required caller grants from agent spec, diff against existing grants, check feature policies, delegate access to user roles | "app-created agent not working", "app agent issues", "app MCP issues", "caller grants for app", "GRANT CALLER to app", "fix agent in app", "diagnose app agent", "configure agent in app", "app-created MCP not working", "agent not found in app", "grant caller to application", "app MCP configuration", "agent missing from installed app" | `configure-agent-mcp/SKILL.md` |
| **App Cost & Budgets** — Understand and manage ongoing cost of an installed app | "app cost", "app spending", "app credits", "budget for app", "how much does app cost", "monitor app cost", "app usage", "cost of native app", "app billing" | `app-cost/SKILL.md` |
| **Uninstall / Drop Application** — Uninstall or drop an installed native app, including apps that own objects, use SPCS, or created inbound shares | "uninstall app", "drop app", "remove app", "delete app", "drop application", "uninstall native app", "remove installed app", "how to drop", "how to uninstall" | `uninstall-app/SKILL.md` |

**If the intent is ambiguous**, ask the user to clarify before proceeding.
