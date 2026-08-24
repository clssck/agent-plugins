---
name: use-rcr
description: "Add Restricted Caller Rights (RCR) to a Snowflake Native App to access consumer-owned objects or perform account-level operations. Triggers: restricted caller, RCR, EXECUTE AS RESTRICTED CALLER, GRANT CALLER, caller rights, access consumer data, consumer data from app, restricted_callers_rights, caller grants, consumer's role, caller's privileges, consumer's privileges."
parent_skill: native-app-provider
---

# Add Restricted Caller Rights (RCR) to a Native App

> **⚠️ MANDATORY**: If your system prompt mentions Snowsight, load [`../references/native-apps-snowsight.md`](../references/native-apps-snowsight.md) before doing anything else.

## When to Load

From the root `native-app-provider` skill when the user needs the app to access consumer-owned objects or perform account-level operations (CREATE DATABASE, EXECUTE TASK, etc.).

If the user only needs access to specific known consumer objects (tables, views, warehouses), `request-object-access/SKILL.md` (references) may suffice — see the decision table below.

> **Cortex Agents in Native Apps — RCR enforced since June 5, 2026 (KB 000012946)**
>
> Cortex Agents in Snowflake Native Apps now run under **Restricted Caller's Rights (RCR)**. Snowflake-managed MCP Servers are limited to app-owned tools only (`SYSTEM_EXECUTE_SQL` and tools outside the app are not permitted).
>
> **Enforcement rules:**
> - Versions and patches created **before June 5, 2026** are grandfathered — they continue running under the previous Caller's Rights (CR) model until the provider publishes a new version.
> - **Any new version or patch created on or after June 5, 2026 must use RCR.** If your app creates Cortex Agents and you are publishing a new patch or version now, add RCR support before publishing — otherwise the agent will fail in consumer accounts.
>
> If your native app includes a Cortex Agent and you are publishing a new version, use this skill to add `restricted_callers_rights: enabled: true` to your manifest and `EXECUTE AS RESTRICTED CALLER` to your stored procedures.
>
> **Consumer impact**: After installing an RCR-updated version, consumers must issue `GRANT CALLER ...` commands to grant the app access to the consumer objects the agent needs. See the troubleshooting guide at https://community.snowflake.com/s/article/updating-native-apps-to-support-restricted-callers-rights-for-cortex-agents if consumers see `object does not exist or access is not authorized` errors from the agent.

## When to Use RCR vs Other Approaches

| Access Scenario | Approach | Skill |
|---|---|---|
| Data/functions owned by the app | Owner's rights (default) | No action needed |
| Specific consumer tables, views, or functions | References | `request-object-access/SKILL.md` |
| Objects owned by another user/role | RCR | This skill |
| Mixed consumer and provider data queries | References + owner's rights | `request-object-access/SKILL.md` + split pattern in `../references/ref-rcr.md` |

If both references AND RCR are needed, configure references first via `request-object-access/SKILL.md`, then return here for RCR.

## Native App Guard Rails

These constraints are unique to Native Apps — they do not apply to standalone RCR procedures:

1. **`EXECUTE AS CALLER` is blocked** — must use `EXECUTE AS RESTRICTED CALLER`
2. **RCR procs run with the caller's privileges** — the caller cannot access app-internal objects, so neither can the RCR proc. If you need both consumer data and app data, use the split pattern (see `../references/ref-rcr.md` § Split Pattern)
3. **Consumer grants use `TO APPLICATION <app>`** — not `TO ROLE`
4. **Additional blocked operations** — SHOW ROLES/USERS/GRANTS, CURRENT_AVAILABLE_ROLES, CURRENT_IP_ADDRESS, SYSTEM$ALLOWLIST (full list in `../references/ref-rcr.md` § Native App Limitations)
5. **SPCS caller grants go to the application** — when using RCR with container services, always `GRANT CALLER ... TO APPLICATION <app>`, never to the service role
6. **Declare `restricted_callers_rights` in manifest** (recommended) — `enabled: true` + description

## Prerequisites

- A project directory with `manifest.yml` and a setup script (typically `scripts/setup.sql`)
- If these don't exist yet, load `setup-app/SKILL.md` first — its template includes all required grants

## Workflow

### Step 1: Gather Project Files

**Ask** the user for the following (skip items already known from a prior skill):

```
To add RCR, I need:
1. **Project directory**: Where are your app files? (e.g., /Users/you/projects/my_app)
2. **Application package name**: What is the application package name? (e.g., MY_APP_PKG)
```

Read `manifest.yml` and the setup script (path from `artifacts.setup_script`, default: `setup.sql`).

**Load** `../references/ref-rcr.md` for templates and syntax.

**STOP** if either file is missing: suggest loading `setup-app/SKILL.md` to create it.

### Step 2: Update Manifest

**Add** the `restricted_callers_rights` block to `manifest.yml`. This is required for any app that uses RCR. Snowsight displays the `description` to consumers during installation so they understand why the app needs caller privileges.

```yaml
restricted_callers_rights:
  enabled: true
  description: "<explain why the app needs RCR — shown to consumers in Snowsight>"
```

Ask the user what the app needs RCR for and write an appropriate description.

If the user also needs object references, cross-ref `request-object-access/SKILL.md` for that configuration.

### Step 3: Create RCR Procedures

Generate stored procedures using templates from `../references/ref-rcr.md`. Ask the user what operations the app needs to perform on consumer data, then generate procedures accordingly.

**STOP** — present the generated procedures to the user for review before writing.

### Step 4: Generate Consumer Setup Instructions

Analyze each RCR procedure to determine the minimum privileges the consumer must grant. Read `../references/ref-rcr.md` § High-Level Caller Grants before writing.

**For each procedure, work through this checklist:**

| Question | If YES → |
|----------|----------|
| Does the procedure accept object names (table, schema, database) as parameters, or reference objects that vary at runtime? | **High-level preferred**: `GRANT CALLER DATA READ ON DATABASE/SCHEMA` |
| Does the procedure call GRANT, REVOKE, or create object references? | **High-level required**: `GRANT CALLER GRANT MANAGEMENT ON DATABASE/SCHEMA` |
| Does the procedure access sensitive objects (secrets, keys) or operations only available via high-level privileges? | **High-level required**: choose appropriate privilege from the table in ref-rcr.md |
| Will the consumer's object set grow over time (many tables/views added later)? | **High-level preferred** (avoids repeated re-granting): `GRANT CALLER DATA READ ON DATABASE/SCHEMA` |
| Are only a small number of specific, stable, named objects accessed? | **Fine-grained sufficient**: `GRANT CALLER SELECT ON TABLE` (three-level hierarchy required) |
| Does the procedure run queries and the warehouse name is not hardcoded? | **High-level required**: `GRANT CALLER COMPUTE USAGE ON ACCOUNT` |
| Does the procedure run queries and a specific warehouse name is known? | **Fine-grained sufficient**: `GRANT CALLER USAGE ON WAREHOUSE <name>` |

**When both high-level and fine-grained are valid**, write the README with both options so provider/consumer can choose:

```sql
-- Option A: High-level (recommended if objects may change or aren't yet enumerated)
GRANT CALLER DATA READ ON DATABASE <consumer_db> TO APPLICATION <app>;

-- Option B: Fine-grained (if you prefer to restrict to specific objects)
GRANT CALLER USAGE ON DATABASE <consumer_db> TO APPLICATION <app>;
GRANT CALLER USAGE ON SCHEMA <consumer_db>.<schema> TO APPLICATION <app>;
GRANT CALLER SELECT ON TABLE <consumer_db>.<schema>.<table> TO APPLICATION <app>;
```

> **`GRANT ALL CALLER PRIVILEGES` does NOT include high-level privileges.** `GRANT MANAGEMENT`, `DATA READ`, `COMPUTE USAGE` etc. must always be separate explicit statements — they are not covered by `GRANT ALL` or by caller ownership.

**Fine-grained hierarchy reminder** — all three levels required to reach a table:
```sql
GRANT CALLER USAGE ON DATABASE <db> TO APPLICATION <app>;
GRANT CALLER USAGE ON SCHEMA <db>.<schema> TO APPLICATION <app>;
GRANT CALLER SELECT ON TABLE <db>.<schema>.<table> TO APPLICATION <app>;
```

**SPCS note:** If using RCR with container services, always grant caller privileges to the **application** (`TO APPLICATION <app>`), never to the service role.

**STOP** — present the GRANT CALLER statements to the user for review.

### Step 5: Validate

Re-read the updated manifest and setup script. Confirm:

- [ ] `restricted_callers_rights.enabled: true` in manifest
- [ ] No `EXECUTE AS CALLER` anywhere (must be `RESTRICTED CALLER`)
- [ ] RCR procedures do NOT access app-internal objects directly
- [ ] All RCR procedures granted to application roles
- [ ] Consumer setup SQL uses `TO APPLICATION` (not `TO ROLE`)

**STOP** — present final summary to the user.

## Output

- Updated `manifest.yml` with `restricted_callers_rights` block
- RCR procedures added to setup script
- Consumer setup instructions (GRANT CALLER commands, reference binding, role mapping)
