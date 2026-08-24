---
name: organization-database
description: "Organization Database (Org DB) management — centralized organization tags, tag replication, ORGANIZATION$DB. Use when the user asks about: organization database, org db, organization tags, org tags, centralized tags, replicated tags, ORGANIZATION$DB, tag replication across accounts, create org tag, apply org tag, show org tags, org-level tags, cross-account tags, define once use everywhere."
parent_skill: organization-management
---

# Organization Database (Org DB)

Router skill for Organization Database operations and organization-level tags.

## When to Use

Use this skill for:
- Creating and managing organization-level tags
- Applying replicated tags to resources
- Discovering and viewing the Organization Database
- Understanding org tag replication and lifecycle

## What is Organization Database?

The Organization Database (ORGANIZATION$DB) is a special, automatically-provisioned database that serves as a single source of truth for organization-wide schema objects. In the MVP, it supports **Organization Tags** - centralized tags that are automatically replicated to all accounts in your organization.

**Key Benefits:**
- **Define Once, Use Everywhere**: Create tags centrally, use across all accounts automatically
- **Single Source of Truth**: Consistent tag definitions organization-wide
- **Zero Cost**: No storage or replication charges for org tags
- **Automatic Replication**: Changes propagate to all accounts within ~5 minutes

**Note**: Organization Budgets will be available in a future release.

## Intent Detection

**Automatically detect user intent and IMMEDIATELY load the matching sub-skill:**

| Intent | Triggers | Load |
|--------|----------|------|
| **ORG_TAGS** | "create org tag", "organization tag", "centralized tag", "replicated tag", "manage org tags", "alter org tag", "drop org tag", "apply org tag", "tag resources", "ORGANIZATION$DB.TAGS" | `org-tags/SKILL.md` |
| **ORG_DB_DISCOVERY** | "what is org db", "show organization database", "org db status", "view org db", "check org db", "ORGANIZATION$DB", "is org db enabled", "organization database replication" | `org-db-discovery/SKILL.md` |

## Routing Decision Tree

```
User Request
    ↓
Detect Intent
    ├─→ ORG_TAGS → IMMEDIATELY Load org-tags/SKILL.md
    │
    └─→ ORG_DB_DISCOVERY → IMMEDIATELY Load org-db-discovery/SKILL.md
```

## ⚠️ DO NOT PROCEED WITHOUT LOADING SUB-SKILL

This router provides NO implementation details. All workflows, SQL commands, and procedures are in the sub-skills above.

## Setup

1. **Load** `references/org-db-concepts.md`: Core concepts and architecture.
2. **Load** `references/golden-queries.md`: Verified SQL patterns for common operations.
3. **Load** `../references/global_guardrails.md`: Required context for all organization management operations.

## Quick Reference

### For GLOBALORGADMIN (in organization account):
- Create org tags: `CREATE TAG ORGANIZATION$DB.TAGS.COST_CENTER ...`
- Manage tags: `ALTER TAG`, `DROP TAG`
- View tags: `SHOW TAGS IN DATABASE ORGANIZATION$DB`

### For ACCOUNTADMIN (in child accounts):
- View replicated tags: `SHOW TAGS IN DATABASE ORGANIZATION$DB`
- Apply tags to resources: `ALTER WAREHOUSE ... SET TAG ORGANIZATION$DB.TAGS.COST_CENTER = 'value'`
- View tagged resources: Query `SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES`

## Important Notes

- **Automatic Provisioning**: Org DB is automatically created when your organization is enrolled
- **Read-Only in Child Accounts**: Child accounts cannot modify replicated tags
- **Replication Frequency**: Changes propagate within ~5 minutes
- **Zero Cost**: No charges for org tags or replication
- **Unique Naming**: ORGANIZATION$DB is a reserved name, ensuring unique identification
