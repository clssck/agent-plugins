---
name: organization-management
description: "Snowflake organization management — accounts, org users, org insights, org spending, org security, globalorgadmin. ORGANIZATION_USAGE views, cross-account analytics, org-wide metrics. Use when the user asks about: 30 day summary of my organization, 30-day summary, 30 day summary, accounts in my organization, list accounts, how many accounts, account editions, account regions, account inventory, organization users, organization user groups, executive summary of my org, org overview, org spending, org cost, org security posture, org reliability, org auth posture, org hub, org usage views, trust center, MFA readiness, login failures, warehouse credits, storage trends, edition distribution, who has globalorgadmin, what is globalorgadmin, globalorgadmin role, orgadmin role, organization administrator, org admin, enable orgadmin, disable orgadmin, org admin permissions, account admins, ORGANIZATION_USAGE, org-level, cross-account, org-wide."
---

# Organization Management

Router skill for organization management workflows.

## When to Use

Use this skill for:
- Account inventory and edition visibility
- Account control-plane operations
- Organization control-plane operations
- Organization user and organization user group operations
- Org Hub executive insights
- Org Usage view mapping

## Intent Detection

**Automatically detect user intent and IMMEDIATELY load the matching sub-skill:**

| Intent | Triggers | Load |
|--------|----------|------|
| **ACCOUNT_LIFECYCLE** | "create account", "create new account", "provision account", "alter account", "modify account", "account edition", "upgrade edition", "change edition", "account region" | `account-lifecycle/SKILL.md` |
| **READER_ACCOUNTS** | "reader account", "managed account", "create reader account", "share with non-snowflake customer" | `reader-accounts/SKILL.md` |
| **CLIENT_REDIRECT** | "connection url", "client redirect", "create connection", "failover", "disaster recovery" | `client-redirect/SKILL.md` |
| **REPLICATION_SETUP** | "enable replication", "account replication", "create replication group", "replicate across accounts" | `replication-setup/SKILL.md` |
| **ACCOUNT_INSIGHTS** | "list accounts", "how many accounts", "account inventory", "account editions", "edition distribution", "reader accounts", "role analytics" | `accounts/SKILL.md` |
| **ORG_USERS_CREATE** | "create organization user", "create org user", "create organization user group", "create org group", "drop organization user", "alter organization user", "set visibility" | `organization-users/create/SKILL.md` |
| **ORG_USERS_IMPORT** | "import organization user group", "import org group", "import users into account", "add group to account", "unimport group", "enable users in account" | `organization-users/import/SKILL.md` |
| **ORG_USERS_TROUBLESHOOT** | "resolve import conflicts", "user already exists", "link user", "x/y users imported", "import shows conflicts", "matching login_name" | `organization-users/troubleshoot/SKILL.md` |
| **ORG_HUB_INSIGHTS** | "executive summary", "30 day summary of my organization", "30-day summary", "30 day summary", "org overview", "org spending", "cost drivers", "security posture", "reliability risks", "login failures", "org hub", "cost trends", "cost spikes", "cost optimizations", "compare service costs", "fastest growing costs", "service optimizations", "contract utilization", "forecast contract", "trust center violations", "violation trends", "trust center coverage", "MFA readiness", "MFA adoption", "login failure patterns", "auth method distribution", "admin distribution", "security admin coverage", "dormant users", "dormant user risk", "failed queries", "query failure patterns", "warehouse queued load", "warehouse load distribution", "capacity planning", "storage growth", "storage consumers", "storage optimization", "top queries by cost", "expensive queries" | `org-hub/SKILL.md` |
| **ORG_USAGE_VIEWS** | "which org usage views are available", "which view should I use for billing", "feature to view mapping", "what role do I need for org usage" | `org-usage-view/SKILL.md` |
| **GLOBAL_ORG_ADMIN** | "what is globalorgadmin", "who has globalorgadmin", "orgadmin role", "enable orgadmin", "org admin permissions" | `globalorgadmin/SKILL.md` |

## Routing Decision Tree

```
User Request
    ↓
Detect Intent
    ├─→ ACCOUNT_LIFECYCLE → IMMEDIATELY Load account-lifecycle/SKILL.md
    │
    ├─→ READER_ACCOUNTS → IMMEDIATELY Load reader-accounts/SKILL.md
    │
    ├─→ CLIENT_REDIRECT → IMMEDIATELY Load client-redirect/SKILL.md
    │
    ├─→ REPLICATION_SETUP → IMMEDIATELY Load replication-setup/SKILL.md
    │
    ↓
    ├─→ ACCOUNT_INSIGHTS → IMMEDIATELY Load accounts/SKILL.md
    │
    ├─→ ORG_USERS_CREATE → IMMEDIATELY Load organization-users/create/SKILL.md
    │
    ├─→ ORG_USERS_IMPORT → IMMEDIATELY Load organization-users/import/SKILL.md
    │
    ├─→ ORG_USERS_TROUBLESHOOT → IMMEDIATELY Load organization-users/troubleshoot/SKILL.md
    │
    ├─→ ORG_HUB_INSIGHTS → IMMEDIATELY Load org-hub/SKILL.md
    │
    ├─→ ORG_USAGE_VIEWS → IMMEDIATELY Load org-usage-view/SKILL.md
    │
    └─→ GLOBAL_ORG_ADMIN → IMMEDIATELY Load globalorgadmin/SKILL.md
```

## ⚠️ DO NOT PROCEED WITHOUT LOADING SUB-SKILL

This router provides NO implementation details. All workflows, SQL commands, and procedures are in the sub-skills above.

## Setup

1. **Load** `references/global_guardrails.md`: Required context for all organization management operations.
