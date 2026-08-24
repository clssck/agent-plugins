---
name: guardrails-guide
description: >-
  Guides CoCo /guardrails and Restricted Session Scope (RSS). Use for any request to create,
  apply, activate, store, or remove a scope; block roles for the agent (e.g. 'block
  securityadmin'); make a session read-only via RSS; deactivate or disable RSS mid-session while
  preserving session state (variables, temp tables); named scopes, session scope,
  RESTRICTED_SESSION_SCOPE, USER$<USERNAME>.RSS, 'restrict what the agent can do', 'limit agent
  SQL', 'set up RSS', 'guardrails not working'. Also use for ANY SQL error mentioning 'Restricted
  session scope' (e.g. 'Insufficient privileges to operate on schema. Restricted session scope:'):
  do NOT suggest role switches or GRANT statements — read the active scope via SYS_CONTEXT and
  guide the user to activate a scope holding the required privilege via /guardrails. Always use
  this skill before doing anything else for such requests. Do NOT search external docs or run
  `cortex search docs` for RSS syntax or DDL; all syntax is in this skill's DDL reference section.
---

## Opening context

This skill walks you through CoCo's `/guardrails` panel and Restricted Session Scope (RSS) —
the mechanism that limits which SQL operations the agent can issue and which Snowflake roles it
can assume. Use it when you want to create a named RSS scope, apply it to a session, or
diagnose why restrictions aren't taking effect.

**Scope of this skill:** RSS creation, activation, and management via `/guardrails`.
`--sql-read-only` at startup applies a `SNOWFLAKE$DATA_READ_WITH_AI` RSS scope (read-only) — it is
RSS-based and covered here.

---

## How RSS activation works

**Two ways to apply RSS:**

| Path | When to use |
|---|---|
| `/guardrails` panel → select scope → **Activate** | Mid-session — always use this |
| `cortex --with-restricted-session-scope=<name>` | At startup — bare name (auto-expanded to `USER$<USERNAME>.RSS.<name>`) or full FQN |

> **The agent must never apply RSS via `ALTER SESSION`. Always direct the user to `/guardrails`.**

**Removing RSS mid-session:**

The `/guardrails` panel includes a **Remove RSS** option that deactivates the active scope for the
current session. This mints a new child session internally, but **session state is fully preserved** —
session variables and temporary tables remain available. Use this when you want to lift restrictions
without starting a new top-level session.

---

## Workflow

Follow these steps in order to configure and verify your RSS restrictions.

### Step 1 — Open the guardrails panel

Run `/guardrails` from the cortex prompt. The panel shows:

- **Active scope** — the currently loaded RSS scope (or `none`).
- **Available named scopes** — server-side scope objects discovered in `USER$<USERNAME>.RSS`.
- **SQL read-only** — applies a `SNOWFLAKE$DATA_READ_WITH_AI` RSS scope (restricts the child session
  to read operations). This is the same restriction `--sql-read-only` applies at startup.

### Step 3 — Apply the RSS scope

**Default: use the `/guardrails` panel (recommended for all mid-session activation):**

Open `/guardrails`, select the scope from **Available named scopes**, press **Activate**.
CoCo applies the scope directly to the child session and updates the footer banner immediately.
No extra verification step is needed — the panel reflects the live state.

**At startup:**

```bash
# Bare name (recommended) — USER$<USERNAME>.RSS. prefix is auto-added
cortex --with-restricted-session-scope=MY_READ_ONLY
```
No FQN is supported for the RSS name when specified since  USER$<USERNAME>.RSS is auto-loaded and restricted it that schema.

**Important:** To change or deactivate the active scope mid-session, use `/guardrails`.

---

### Step 3b — Remove RSS mid-session (optional)

To lift the active RSS scope without ending the session:

1. Open `/guardrails`.
2. Select **Remove RSS**.

CoCo mints a new child session internally, but your **session state is preserved** — session
variables and temporary tables carry over. The footer banner clears immediately once the scope
is removed. Run `/guardrails status` to confirm no scope is active.

---

### Step 4 — Verify enforcement status

Run `/guardrails status` — it shows the active scope name and enforcement state. The footer
banner should also show `[RSS activated]`. That's all that's needed to confirm the
restriction is in force.

---

## Output format

The skill produces **step-by-step instructions** with the following structure:

1. Panel-open step (command to type).
2. Named scope activation — `/guardrails` panel (preferred) or CLI flag at startup.
4. Verification checklist.
5. Quick-reference command table (see below).
6. Troubleshooting section.

**Quick-reference command table:**

| Goal | How |
|---|---|
| Open guardrails panel | `/guardrails` |
| Check enforcement status | `/guardrails status` |
| Apply RSS mid-session | Open `/guardrails` → select scope → **Activate** |
| Activate at startup | `cortex --with-restricted-session-scope=<name>` (bare name auto-expanded) |
| Remove RSS mid-session (preserves session state) | Open `/guardrails` → **Remove RSS** |

---

## Quality rules

**Pass criteria:**
- Named scope FQN is fully qualified (three-part name: `USER$<USERNAME>.RSS.<name>`).
- Named scope activation shows the scope name in the `/guardrails` panel header.
- Scope creation is done via `/guardrails` panel — do **not** emit `CREATE RESTRICTED SESSION SCOPE` DDL unless the user explicitly asks for the creation SQL.
- Default mid-session activation is the `/guardrails` panel — the agent always directs the user there.
- The agent **never** runs `ALTER SESSION SET RESTRICTED_SESSION_SCOPE` — not even when the user says "apply it for me". Always respond with `/guardrails` instructions instead.
**Fail criteria (counterexamples):**
```yaml
# FAIL — when a SQL error contains "Restricted session scope", attempting USE ROLE, retrying
# with a different role, suggesting GRANT, or blaming RBAC before updating the RSS scope.
# "Restricted session scope" in an error = RSS is the cause, full stop.
# Role switches will not bypass it. Stop all SQL and direct user to update the scope via /guardrails.

# FAIL — agent runs ALTER SESSION to apply RSS under any circumstance
# The only correct activation paths are /guardrails panel or --with-restricted-session-scope at startup

# FAIL — trying to use the old rss.yaml inline scope format (no longer supported)
~/.snowflake/cortex/guardrails/rss.yaml  # inline scope file is gone

# FAIL — using a full FQN when a bare name was intended AND the scope is NOT in USER$<USERNAME>.RSS
# (bare name is preferred; full FQN is only needed for scopes stored in a custom schema)

# FAIL — emitting CREATE RESTRICTED SESSION SCOPE DDL unless the user explicitly asks for it
# Default path: direct user to /guardrails panel to create scopes

# FAIL — saying "no DDL needed" in output
# Do not mention DDL at all unless the user explicitly asks for it

# FAIL — using `extend` keyword (not supported, will return "unknown property 'extend'")
privilege scopes:
  extend: [SNOWFLAKE$DATA_READ_WITH_AI]   # ERROR: unknown property 'extend'
# Fix: replace with explicit allowed privileges:
privilege scopes:
  allowed privileges:
    - privilege: data read
      account: [all]

# FAIL — interpreting "read-only" or "sql read-only" as a role name
role scopes:
  blocked roles: [sql_read_only]   # ERROR: no system role named sql_read_only exists
# Fix: "read-only" means privilege scopes restricted to data read — it is NOT a role name.
# Correct approach: add privilege scopes:
privilege scopes:
  allowed privileges:
    - privilege: data read
      account: [all]
```

**Note:** `--sql-read-only` at startup applies a `SNOWFLAKE$DATA_READ_WITH_AI` RSS scope — it is
another way to activate a read-only RSS, not a separate unrelated feature.

---


## DDL reference — show ONLY when the user explicitly asks for creation syntax

> **Do not surface this section proactively.** Only use it when the user explicitly says something
> like "show me the DDL", "give me the CREATE statement", or "how do I create it manually".
> Default path is always the `/guardrails` panel.

```sql
-- Create a named scope in your personal database (three-part FQN required)
CREATE OR REPLACE RESTRICTED SESSION SCOPE USER$<USERNAME>.RSS.<name> AS $$
privilege scopes:
  allowed privileges:
    - privilege: data read      # read-only; also: data write, program usage, object management, full management
      account: [all]            # account-wide; or: databases: [db1], schemas: [db2.public]
role scopes:
  blocked roles: [securityadmin]
  allowed roles: [analyst]
  allow role switching: false   # defaults to true
$$;

-- Update an existing scope
ALTER RESTRICTED SESSION SCOPE USER$<USERNAME>.RSS.<name> AS $$ <updated_yaml> $$;

-- Drop a scope
DROP RESTRICTED SESSION SCOPE IF EXISTS USER$<USERNAME>.RSS.<name>;
```

**Key rules:**
- `OR REPLACE` and `IF NOT EXISTS` are mutually exclusive — do not combine them.
- `extend` is **not** a valid keyword — use explicit `allowed privileges` instead.
- Scopes in `USER$<USERNAME>.RSS` are auto-discovered by `/guardrails`. Scopes in other schemas will not appear in the panel.
- Do **not** search external docs for DDL syntax — all syntax is above.

---

## Out of Scope

This skill does **not** cover:

- Guardrails for non-SQL tools (file writes, shell execution) — those are governed by the
  permissions system, not RSS. Use `/permissions` for those.
- Granting Snowflake RBAC privileges to other users or roles — RSS restricts what the agent
  session may do, but does not manage underlying Snowflake object permissions.

---

## Examples

The three examples below cover the most common entry points: creating a named scope with role
restrictions, sharing a scope across a team, and troubleshooting a restriction that appears
inactive.

### Example 1 — Creating a scope that blocks securityadmin and enforces read-only

**User:** "Create a scope that prevents the agent from switching to the securityadmin role and
makes it read-only."

> **Key clarification:** "read-only" or "sql read-only" in an RSS context means restricting
> `privilege scopes` to `data read` only — it is **not** a role name. Never try to add a role
> called `sql_read_only` to `blocked roles`; no such system role exists. Combine `data read`
> under `privilege scopes` with the desired `role scopes` block.

**Response:**

1. Use `/guardrails` to create the scope — open the panel, choose **Create**, name it
   `RSS_SECURITYADMIN`, configure `data read` privilege + block `securityadmin` role.

2. Apply it in the same panel — select `RSS_SECURITYADMIN` from **Available named scopes**,
   press **Activate**. The footer banner updates immediately to `[RSS activated]`.

3. Run `/guardrails status` to confirm the scope is active.

   - **Future sessions:** Start CoCo with the flag:
     ```bash
     cortex --with-restricted-session-scope=RSS_SECURITYADMIN
     ```

---

### Example 2 — SQL error containing "Restricted session scope"

**User:** Gets an error like:
```
Insufficient privileges to operate on schema 'KHALID'. Restricted session scope: ...
```
or any error whose message contains the phrase **"Restricted session scope"** or **"restricted session scope"**.

**Immediate recognition rule — stop all other diagnostics:**

When a SQL error message contains "Restricted session scope", **stop immediately**. Do not:
- Try `USE ROLE <other_role>` to work around it
- Retry the query with a different role
- Check RBAC grants or suggest `GRANT` statements
- Ask the user if they have the right privileges
- Attempt any further SQL before the scope is updated

The phrase "Restricted session scope" in an error is a definitive signal that the **active RSS scope is blocking the operation**. Role switches and privilege grants will not help — the restriction is enforced at the session scope level, above RBAC.

**Step 1 — Read the active scope to understand what it currently allows:**

Run this SQL to see the full definition of the scope(s) in force on the session:

```sql
SELECT SYS_CONTEXT('SNOWFLAKE$SESSION', 'ACTIVE_RESTRICTED_SESSION_SCOPES')
```

This returns a JSON array where each entry has:
- `name` — the scope FQN (e.g. `USER$KHALID.RSS.DENY_SYSADMIN`)
- `definition` — the YAML body showing exactly what privileges and roles are currently allowed/blocked

Parse the `definition` YAML to identify the missing privilege (e.g. `data write` is absent when write operations fail).

**Step 2 — Tell the user specifically what to change and how:**

Based on what the definition shows, explain precisely what privilege is missing. Then direct the user to activate a scope that includes it:

> "Your active scope (`<name>`) only allows `data read`. To allow write operations, open `/guardrails`, create or select a scope that includes `data write`, and activate it."

The `/guardrails` panel has **no Edit option**. The default fix is to create or activate a scope with the right privileges — do not proactively suggest `ALTER` DDL. Only show DDL if the user explicitly asks for it.

**Fail criteria for this scenario:**
```yaml
# FAIL — attempting USE ROLE / switching roles to work around the error
USE ROLE SYSADMIN;   # will not help — RSS sits above RBAC

# FAIL — retrying the same query with a different role before updating the scope
USE ROLE ACCOUNTADMIN; SELECT ...   # still blocked by RSS

# FAIL — blaming a Snowflake RBAC privilege problem
"You need USAGE privilege on schema KHALID"

# FAIL — suggesting a role switch as the fix
"Try switching to SYSADMIN role"

# FAIL — telling user to contact an admin
"Ask your account admin to grant access"

# FAIL — any further SQL attempts before the scope is updated
# Once the error contains "Restricted session scope", stop all SQL and fix the scope first

# FAIL — telling the user to open /guardrails → Edit (no Edit option exists in the panel)
# FAIL — proactively suggesting ALTER RESTRICTED SESSION SCOPE DDL
# Default fix: open /guardrails, create or select a scope with the required privilege, activate it
# Only show ALTER DDL if the user explicitly asks for it

# FAIL — suggesting Remove RSS as the fix when the user hits an RSS error.
#        Correct response is to activate or update the scope to include the
#        required privilege, not to lift the restriction.
```

---

### Example 3 — Troubleshooting "guardrails not working"

**User:** "I set up RSS but the agent is still running write operations."

**Diagnosis checklist:**

1. Open `/guardrails` — if using a named scope, confirm **Active** shows your scope name
   (not `none`). If it shows `none`, the scope was never activated for this session.
2. Run `/guardrails status` to print the current enforcement state.
3. Check if the write operation came from a Bash or MCP tool, not `sql_execute` — those paths
   bypass RSS entirely and require `/permissions` to restrict.
4. If using a named scope, confirm the object is in the `RSS` schema of the personal database
   (not another schema — objects outside it won't auto-appear in the panel).
5. Restart the session with `--with-restricted-session-scope=<name>` (bare name) to rule
   out stale session state.
