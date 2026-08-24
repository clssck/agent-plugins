---
name: cost-intelligence
description: "Account-level cost analytics via SNOWFLAKE.ACCOUNT_USAGE. Credit usage by warehouse, user, service. Budgets, spending limits, custom budgets. Quotas, per-user spending limits, per-user credit caps, quota notifications, quota enforcement, exclude users from quota, quota shared resources. Resource monitors, suspend triggers. Anomaly detection, anomaly monitors, tag-based anomaly monitoring, costs, chargeback, storage, serverless, containers, data transfer, top user spend, query cost grouping. Cortex AI cost or usage including Cortex Agents, Snowflake Intelligence, Snowflake CoWork, AI function, Cortex Code, CoCo, Cortex Search, Cortex Analyst, Cortex REST API, model training/fine-tuning, and provisioned throughput. Cost insights, waste reduction, savings. Not for org-wide currency spend or multi-account billing (billing/organization-management) or warehouse DDL (warehouse)."
---

# Cost Intelligence Skill

> **⚠️ Native App costs**: If the user is asking about the cost of an **installed native app**, **do NOT continue with this skill**. Instead, load the `native-app-consumer` skill immediately — it has app-specific cost views (`APPLICATION_DAILY_USAGE_HISTORY`) and cost management instructions that this skill does not cover.

> **Do NOT search for semantic views for cost questions.**  
> Cost data lives in `SNOWFLAKE.ACCOUNT_USAGE` views, not user-created semantic views.  
> Skip `cortex semantic-views search/discover` and `SHOW DATABASES` — go directly to the routing table below.

> **⚠️ Budget Syntax Warning**  
> Budgets are **class instances**, NOT standard objects. Never use `SHOW BUDGETS` — it will fail.  
> ✅ Correct: `SHOW SNOWFLAKE.CORE.BUDGET LIKE '...'` or `SHOW SNOWFLAKE.CORE.BUDGET INSTANCES IN ACCOUNT`  
> ❌ Wrong: `SHOW BUDGETS LIKE '...'`

> **⚠️ Account Budget Limitations**  
> The **account budget** (`SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET`) monitors ALL account spending automatically.  
> It does **NOT** support tag or resource management methods:  
> - ❌ `ADD_RESOURCE`, `REMOVE_RESOURCE`, `GET_LINKED_RESOURCES`  
> - ❌ `ADD_RESOURCE_TAG`, `REMOVE_RESOURCE_TAG`, `GET_RESOURCE_TAGS`, `GET_BUDGET_SCOPE`  
> If the user asks about tags/resources on the **account budget**, tell them immediately this isn't supported.  
> They need a **custom budget** to track specific objects or tags.

---

## Routing

Match the user's question to keywords and read the corresponding file **before writing any queries**.

| Keywords | Route |
|----------|-------|
| "top spenders", "who is spending", "user costs", "top users", "user spending" | `references/queries/users-queries.md` |
| "expensive queries", "query costs", "costly queries", "parameterized hash", "query patterns", "grouped by hash" | `references/queries/users-queries.md` |
| "where is my money going", "cost breakdown", "credits by service", "overall spending" | `references/queries/overview.md` |
| "warehouse", "compute", "virtual warehouse", "warehouse costs" | `references/queries/warehouse.md` |
| "week over week", "month over month", "cost increase", "spike", "why did costs go up", "compared to last" | `references/queries/trends.md` |
| "anomalies", "unusual spending", "cost spikes", "anomaly detection", "anomaly notification", "anomaly email", "cost spike alert", "anomaly monitor", "monitor", "tag-based anomaly", "cost center / team / business unit anomaly" | `skills/anomaly-insights/SKILL.md` |
| "serverless", "tasks", "snowpipe", "serverless task credits" | `references/queries/serverless.md` |
| "storage", "database size", "storage costs", "data storage" | `references/queries/storage.md` |
| "AI cost/credits/usage/spend", "cortex cost/credits/usage/spend", "token credits", "tokens used" "analyst cost/usage", "LLM cost/usage", "cortex rest api cost/usage", "rest inference cost/usage", "cortex search cost/usage", "cortex agents cost/credits", "agent cost/usage", "coco cost/usage", "coco cli/snowsight cost/usage", "cortex code cost/usage", "cortex code cli/snowsight cost/usage", "snowflake cowork cost/usage", "snowflake intelligence cost/usage", "fine-tuning cost", "model training cost", "provisioned throughput cost", "PTU cost", "no data", "did we have usage", "why is it zero", "request drill-down", "request breakdown", "by request", "by user", "by model", "by instance", "by tag", "report in credits" | `skills/cortex-ai/SKILL.md` |
| "team costs", "department spending", "cost center", "chargeback", "showback", "tags", "attribution", "tag value", "cost by tag" | `skills/tag-attribution/SKILL.md` |
| "containers", "SPCS", "compute pools", "container services" | `references/queries/containers.md` |
| "data transfer", "cross-region", "cross-cloud", "egress" | `references/queries/data-transfer.md` |
| "over budget", "at risk budget", "list all budgets", "compare budgets", "which budgets" | `references/queries/budgets.md` |
| "create budget", "set budget", "activate budget", "spending limit", "budget notifications", "add to budget", "budget actions", "deactivate budget", "drop budget", "delete budget", "remove budget", "budget alerts", "custom budget", "account budget", "budget status", "budget spend", "budget usage" | `skills/budget/SKILL.md` |
| "cost insights", "optimization insights", "waste reduction", "what can I save", "unused resources", "idle warehouses", "savings recommendations", "never queried tables", "query gaps", "auto-clustering waste", "unused materialized views" | `skills/cost-insights/SKILL.md` |
| "quota", "per-user limit", "user quota", "per-user spending", "quota threshold", "quota notification", "create quota", "quota enforcement", "quota exclude users", "quota shared resources" | `skills/quota/SKILL.md` |

**Never write ad-hoc queries when a verified query exists in the routed file.**
