---
name: key-and-secret-management
description: "Use for **ALL** requests that mention Tri-Secret Secure, customer-managed key operations, or periodic data rekeying in Snowflake. Handles CMK status checks, registration, activation (standard, Postgres, private connectivity), deactivation, key rotation, change history, and periodic data rekeying. DO NOT attempt TSS, CMK, or periodic rekeying operations manually - invoke this skill first. Triggers: tri-secret secure, TSS, CMK, BYOK, encryption key, key rotation, CMK history, activate CMK, deactivate CMK, periodic rekeying, periodic data rekeying, PERIODIC_DATA_REKEYING, data rekey, enable rekeying, disable rekeying."
---

# Key and Secret Management

Route encryption key and secret management requests to the appropriate sub-skill.

## When to Use

Activate this skill when the user asks about any of:

- **Tri-Secret Secure keywords**: "tri-secret secure", "TSS", "customer-managed key", "CMK", "encryption key", "BYOK", "bring your own key", "CMK info", "activate CMK", "register CMK", "deactivate CMK", "TSS history", "change history", "CMK history", "rekey", "rotate CMK", "private connectivity TSS", "Postgres TSS", "CMK status"
- **Periodic data rekeying keywords**: "periodic rekeying", "periodic data rekeying", "PERIODIC_DATA_REKEYING", "data rekey", "enable rekeying", "disable rekeying"

## Workflow

### Step 1: Route to Sub-skill

Identify the user's intent and load the matching sub-skill:

| User Intent | Sub-skill to Load |
|---|---|
| Tri-Secret Secure: check CMK status, register CMK, activate TSS, deactivate TSS, rekey/rotate CMK, private connectivity for TSS, Postgres TSS, TSS change history, CMK info, BYOK, encryption key management | **Load** `tri-secret-secure/SKILL.md` |
| Periodic data rekeying: periodic rekeying, periodic data rekeying, PERIODIC_DATA_REKEYING, data rekey, enable rekeying, disable rekeying | **Follow** the Snowflake public documentation directly at https://docs.snowflake.com/en/user-guide/security-encryption-manage#periodic-rekeying — Do NOT load the TSS sub-skill. Periodic data rekeying is a separate account-level feature that uses the `PERIODIC_DATA_REKEYING` account parameter (Enterprise Edition+, requires ACCOUNTADMIN). |

### Step 2: Execute Sub-skill

Follow the loaded sub-skill's workflow completely. Each sub-skill is self-contained with its own prerequisites, templates, and stopping points.

## Stopping Points

- Sub-skill stopping points: Each sub-skill has its own mandatory stopping points -- honour them
