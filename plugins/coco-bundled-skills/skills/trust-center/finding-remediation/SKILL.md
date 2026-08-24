---
name: trust-center-finding-remediation
description: "Help users understand and remediate Trust Center security findings. Use when users ask about: fixing a finding, remediating a vulnerability, understanding a specific finding, at-risk entities, suggested actions, how to fix a security issue detected by Trust Center, programmatic remediation, preview remediation, or want step-by-step remediation guidance."
---

# Trust Center Finding Remediation

Helps users understand specific Trust Center findings and guides them through actual remediation — making the correct configuration changes or account management actions to eliminate vulnerabilities or prevent detections/alerts.

**Important:** Remediation means fixing the underlying issue (e.g., altering a user, setting a parameter, creating a network policy). It is NOT the same as resolving/marking a finding as resolved in Trust Center, which is a separate Trust Center feature that only changes the finding's state without fixing the root cause.

## When to Use

- User asks how to fix or remediate a Trust Center finding
- User asks about a specific finding's details, at-risk entities, or suggested actions
- User wants to understand the impact of remediating a finding
- User asks "how do I fix this security issue?"
- User wants to prioritize which findings to remediate first
- User wants help generating remediation SQL for at-risk entities

## When NOT to Use

- User wants to mark/resolve a finding's state (use api-management skill)
- User wants a high-level summary of all findings (use findings-analysis skill)
- User wants to understand scanner configuration (use scanner-analysis skill)
- User wants to enable/disable scanners (use api-management skill)

## Prerequisites

**MANDATORY: Load** [references/trust-center-api.md](../references/trust-center-api.md) — contains all Trust Center views, columns, stored procedures, and scanner mappings. All finding data comes from `snowflake.trust_center.findings`. See the reference for full column details, AT_RISK_ENTITIES structure, finding types, and required roles.

**MANDATORY: Load** [references/programmatic-remediation-api.md](../references/programmatic-remediation-api.md) — the `preview_remediation` → execute → `record_remediation_result` API. **Prefer this path over hand-generating SQL from `SUGGESTED_ACTION` whenever it is available** for the finding's scanner (see Step 3 for the availability check). Fall back to the manual `SUGGESTED_ACTION` flow only when the feature is off or the scanner is not covered.

## Easy-to-Remediate Scanners

The following scanners have confirmed straightforward remediations. When recommending findings to remediate, **prioritize findings from these scanners first** — they produce Violation-type findings with well-defined, low-risk fixes.

**When programmatic remediation is enabled** (see Step 3), the `snowflake.trust_center.remediation_scopes` view — rows with `platform_supported = TRUE` — is the authoritative live source for which findings are programmatically remediable. Surface those first; the static table below is the fallback when the feature is off.

| Scanner ID | Package | Category |
|------------|---------|----------|
| `SECURITY_ESSENTIALS_MFA_REQUIRED_FOR_USERS_CHECK` | Security Essentials | MFA enforcement |
| `security_essentials_cis1_4` | Security Essentials | MFA enforcement |
| `cis_benchmarks_cis1_4` | CIS Benchmarks | MFA enforcement |
| `security_essentials_strong_auth_person_users_readiness` | Security Essentials | Strong auth for PERSON users |
| `cis_benchmarks_cis1_18` | CIS Benchmarks | PAT network policies |
| `cis_benchmarks_cis1_19` | CIS Benchmarks | Programmatic access token policies |
| `cis_benchmarks_cis4_1` | CIS Benchmarks | Yearly rekeying |
| `cis_benchmarks_cis4_2` | CIS Benchmarks | AES 256-bit for internal stages |
| `cis_benchmarks_cis4_4` | CIS Benchmarks | MIN_DATA_RETENTION ≥ 7 days |
| `cis_benchmarks_cis4_5` | CIS Benchmarks | REQUIRE_STORAGE_INTEGRATION for stage creation |
| `cis_benchmarks_cis4_6` | CIS Benchmarks | REQUIRE_STORAGE_INTEGRATION for stage operation |
| `cis_benchmarks_cis4_8` | CIS Benchmarks | PREVENT_UNLOAD_TO_INLINE_URL |

## Workflow

### Step 1: Identify the Finding

If the user specifies a finding, query it directly. If the user asks for recommendations or which findings to remediate, use the **prioritized query** below that surfaces easy-to-remediate findings first. Otherwise, show open findings prioritized by severity.

**Get open findings prioritized by easy-to-remediate scanners, then severity:**

```sql
SELECT
    FINDING_IDENTIFIER,
    SCANNER_ID,
    SCANNER_NAME,
    SCANNER_SHORT_DESCRIPTION,
    SCANNER_TYPE,
    SCANNER_PACKAGE_NAME,
    SEVERITY,
    TOTAL_AT_RISK_COUNT,
    STATE,
    CREATED_ON,
    CASE WHEN UPPER(SCANNER_ID) IN (
        'SECURITY_ESSENTIALS_MFA_REQUIRED_FOR_USERS_CHECK',
        'SECURITY_ESSENTIALS_CIS1_4',
        'SECURITY_ESSENTIALS_STRONG_AUTH_PERSON_USERS_READINESS',
        'CIS_BENCHMARKS_CIS1_4',
        'CIS_BENCHMARKS_CIS1_18',
        'CIS_BENCHMARKS_CIS1_19',
        'CIS_BENCHMARKS_CIS4_1',
        'CIS_BENCHMARKS_CIS4_2',
        'CIS_BENCHMARKS_CIS4_4',
        'CIS_BENCHMARKS_CIS4_5',
        'CIS_BENCHMARKS_CIS4_6',
        'CIS_BENCHMARKS_CIS4_8'
    ) THEN 1 ELSE 2 END AS remediation_ease
FROM snowflake.trust_center.findings
WHERE UPPER(STATE) = 'OPEN'
  AND TOTAL_AT_RISK_COUNT > 0
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY FINDING_IDENTIFIER, SCANNER_NAME
    ORDER BY CREATED_ON DESC
) = 1
ORDER BY
    remediation_ease,
    CASE UPPER(SEVERITY)
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3
        WHEN 'LOW' THEN 4
        ELSE 5
    END,
    TOTAL_AT_RISK_COUNT DESC
LIMIT 20;
```

When presenting results from the prioritized query, label the easy-to-remediate findings clearly:

```
## Recommended Findings to Remediate

### ✅ Easy to Remediate
| # | Scanner ID | Finding | Severity | Type | At-Risk Entities |
|---|------------|---------|----------|------|-----------------|
| 1 | CIS 4.4 | MIN_DATA_RETENTION_TIME_IN_DAYS | Medium | Violation | 1 |
| 2 | CIS 4.8 | PREVENT_UNLOAD_TO_INLINE_URL | Medium | Violation | 1 |
| ... | ... | ... | ... | ... | ... |

### Other Open Findings
| # | Scanner ID | Finding | Severity | Type | At-Risk Entities |
|---|------------|---------|----------|------|-----------------|
| ... | ... | ... | ... | ... | ... |

I recommend starting with the "Easy to Remediate" findings above —
these have well-defined fixes that can typically be applied quickly
with low risk. Which finding would you like to remediate?
```

Present the results and ask the user which finding they want to remediate.

**STOP**: Wait for user to select a finding.

### Step 2: Get Full Finding Details

Once the user selects a finding, retrieve the complete details. **Always filter by `FINDING_IDENTIFIER`**, not by `SCANNER_ID` or `SCANNER_NAME` — a single scanner can have multiple distinct findings:

```sql
SELECT
    FINDING_IDENTIFIER,
    SCANNER_NAME,
    SCANNER_DESCRIPTION,
    SCANNER_SHORT_DESCRIPTION,
    SCANNER_TYPE,
    SCANNER_ID,
    SCANNER_PACKAGE_ID,
    SCANNER_PACKAGE_NAME,
    SEVERITY,
    SUGGESTED_ACTION,
    IMPACT,
    TOTAL_AT_RISK_COUNT,
    AT_RISK_ENTITIES,
    STATE,
    STATE_LAST_MODIFIED_ON,
    CREATED_ON,
    START_TIMESTAMP,
    END_TIMESTAMP,
    COMPLETION_STATUS,
    METADATA
FROM snowflake.trust_center.findings
WHERE FINDING_IDENTIFIER = '<finding_identifier>'
ORDER BY CREATED_ON DESC
LIMIT 1;
```

### Step 3: Check Programmatic Remediation Availability

With the finding's `SCANNER_ID` and `FINDING_IDENTIFIER` known, determine whether to use the **programmatic** path (preferred) or the **manual** `SUGGESTED_ACTION` path. See [references/programmatic-remediation-api.md](../references/programmatic-remediation-api.md) for the full API.

**1. Is the feature enabled?** The `remediation_scopes` view exists only when programmatic remediation is on:

```sql
SHOW VIEWS LIKE 'REMEDIATION_SCOPES' IN SCHEMA snowflake.trust_center;
```

No row → feature off → use **Path B (manual)** in Step 5.

**2. Is this scanner remediable?**

```sql
SELECT scanner_id, risk_id, action_type, risk_level, reversible, required_permissions, platform_supported
FROM   snowflake.trust_center.remediation_scopes
WHERE  scanner_id = '<SCANNER_ID>'
  AND  platform_supported = TRUE;
```

Row(s) → use **Path A (programmatic)** in Step 5. No row → use **Path B (manual)**.

Programmatic remediation requires the `trust_center_admin` application role. If the user lacks it, fall back to Path B.

### Step 4: Present Finding Context

Present the finding in a structured format so the user understands what was detected and why it matters:

```
**Finding:** <SCANNER_NAME>
**Severity:** <SEVERITY>  |  **Type:** <SCANNER_TYPE>
**Status:** <STATE>  |  **Detected:** <CREATED_ON>
**At-Risk Entities:** <TOTAL_AT_RISK_COUNT>

**What This Checks:** <SCANNER_DESCRIPTION>

**Impact:** <IMPACT>

**Affected Entities:**
<Parse AT_RISK_ENTITIES and list up to 20 entities>
```

- Label the type prominently: **Violation** = configuration issue with a specific fix; **Detection** = threat event requiring investigation.
- **Present ALL at-risk entities.** Do not skip entities based on your own judgment (e.g., do not assume `SNOWFLAKE$...` names are internal). Let the user decide which to act on.
- **For >10 entities, summarize first** (e.g., "25 tasks owned by ACCOUNTADMIN across 3 databases") and offer to show the full list or generate SQL for all.

Based on `entity_object_type`, present details appropriately. Common types (not exhaustive — other types may appear):

- **PARAMETER**: Show parameter name and current value (`entity_detail.val`). Fix is typically `ALTER ACCOUNT SET <param> = <correct_value>;`
- **USER**: Show user name, email, relevant properties. Fix involves `ALTER USER` commands.
- **TASK**: Show task name, owning role. Fix involves `GRANT OWNERSHIP` to a custom role.
- **PROCEDURE**: Show procedure name, owning role. Fix involves `GRANT OWNERSHIP` to a custom role.
- **NETWORK_POLICY**: Show policy status. Fix involves `CREATE NETWORK POLICY` and `ALTER ACCOUNT SET`.
- **ACCOUNT**: Show account-level context. Fix depends on the specific finding.

For any other `entity_object_type`, inspect the `entity_detail` object and present relevant fields. Use the `SUGGESTED_ACTION` for remediation guidance.

### Step 3b: If the User Says the Finding Looks Like a False Positive

If the user responds to the finding context with pushback — "these are expected", "this is intentional", "this doesn't apply to us", "this fires too often" — check whether the scanner supports custom configurations before suggesting muting:

```sql
SELECT HAS_CUSTOM_CONFIGURATION
FROM snowflake.trust_center.scanners
WHERE ID = '<SCANNER_ID>'
  AND SCANNER_PACKAGE_ID = '<SCANNER_PACKAGE_ID>';
```

**If `HAS_CUSTOM_CONFIGURATION = TRUE`:** lead with tuning. Load the api-management custom configuration workflow — start at the **Inspecting Current Configuration** section to review available parameters and current values. Ask the user whether adjusting a threshold would address their concern. If they'd rather suppress the finding instead, offer muting as the next option.

**If `HAS_CUSTOM_CONFIGURATION = FALSE`:** skip tuning and offer muting directly. Let the api-management skill handle the `post_finding_activity` call.

**Do not offer both options simultaneously** — lead with the one that addresses the root cause (tuning), fall back to suppression (muting) only if tuning isn't applicable or the user declines.

### Step 5: Remediate

Use the path selected in Step 3.

#### Path A — Programmatic remediation (preferred when available)

When the scanner is covered (`platform_supported = TRUE`), let the platform render and validate the SQL instead of hand-generating it from `SUGGESTED_ACTION`. Full API in [references/programmatic-remediation-api.md](../references/programmatic-remediation-api.md).

1. **Preview.** Use the finding's `FINDING_IDENTIFIER` verbatim (do not hand-construct it). Pass `NULL` for inputs to accept secure defaults — the normal path; only pass `customer_inputs` if the user explicitly asks to override a value.

   ```sql
   CALL snowflake.trust_center.preview_remediation('<FINDING_IDENTIFIER>', NULL);
   ```

2. **Present the preview as the confirm gate.** Show the user the returned `rendered_sql`, `risk_level`, `reversible`, `required_permissions`, and `rendered_rollback_sql` (if reversible). **Call out prominently when `reversible` is `false` (no automatic rollback — the change cannot be undone by the platform) or when `risk_level` is not `LOW`, so the user weighs the stakes before approving.** Surface any `invalid remediation inputs: …` envelope error verbatim.

   **STOP**: Wait for explicit user approval before executing.

3. **Execute.** On approval, run the `rendered_sql` statements in array order (PER_ENTITY findings render one statement per entity — run them all). The caller executes; the platform does not auto-apply.

4. **Record the structured outcome — the `status` enum is the result, never a prose description.** Choose `status` from what the executed SQL actually did:
   - all statements succeeded → `SUCCEEDED`
   - all failed → `FAILED`
   - some succeeded, some failed (PER_ENTITY / multi-action) → `PARTIALLY_SUCCEEDED`

   ```sql
   -- success: status only (omit error_message and comment)
   CALL snowflake.trust_center.record_remediation_result('<execution_id>', 'SUCCEEDED');
   -- failure: status + the RAW SQL error verbatim (not a paraphrase); comment still omitted
   CALL snowflake.trust_center.record_remediation_result('<execution_id>', 'FAILED', '<raw SQL error>');
   ```

   For PER_ENTITY / multi-action remediations, record per-action with the structured per-entity map (status keyed by entity name, never prose):

   ```sql
   CALL snowflake.trust_center.record_remediation_action_result(
       '<execution_id>', 0, 'PARTIALLY_SUCCEEDED',          -- action_seq is 0-based, matches rendered_sql order
       OBJECT_CONSTRUCT('USER_A','SUCCEEDED','USER_B','FAILED'));
   ```

   **Do NOT write a description of what happened into `comment`, `error_message`, or any field.** `comment` is human-authored only; `error_message` holds the raw SQL error on failure (NULL on success); `status` (+ the per-entity map) is the entire result. The prose summary goes in your chat reply only.

5. **Handle drift / expiry.** If a `record_*` call raises `FINDING_DRIFT` or `preview has expired (15-minute TTL)`, re-run `preview_remediation` against the current finding. Never retry a stale `execution_id`.

Continue to Step 6 (Verify).

#### Path B — Manual remediation (fallback: feature off or scanner not covered)

Present the `SUGGESTED_ACTION` from the finding, which contains detailed markdown with SQL.

**⚠️ CRITICAL: The `SUGGESTED_ACTION` from the finding is the single source of truth for remediation guidance.** Your training data may be outdated — always follow these rules:

1. **SUGGESTED_ACTION is authoritative.** Base all remediation steps, SQL syntax, and feature references on what `SUGGESTED_ACTION` says. Do not override, contradict, or "improve" it with your own knowledge. Do NOT add remediation steps that are not in SUGGESTED_ACTION — for example, do not suggest changing a user's TYPE unless SUGGESTED_ACTION explicitly recommends it.
2. **If SUGGESTED_ACTION contains documentation links**, fetch and read them to get additional verified context before presenting remediation guidance.
3. **If SUGGESTED_ACTION is insufficient and you need to supplement it** (e.g., the user asks a follow-up question about a feature), **search Snowflake public documentation** at https://docs.snowflake.com/en/ before answering. Do not guess.
4. **NEVER claim a Snowflake feature is unsupported or unavailable** based on your own knowledge. Always verify by searching documentation first.
5. **Throughout the entire remediation conversation**, continuously cross-check that your responses are consistent with the SUGGESTED_ACTION content. If you find yourself about to say something that contradicts the SUGGESTED_ACTION, stop and defer to it.

**For Vulnerability findings (actionable fixes):**

1. Present the SUGGESTED_ACTION content as the primary remediation guidance
2. If `AT_RISK_ENTITIES` contains specific entities, generate entity-specific SQL by substituting entity names into the template SQL from SUGGESTED_ACTION. **Cap at 20 examples** — if there are more, note how many remain and offer to show additional batches
3. **Present the generated SQL but DO NOT execute it without explicit user approval**
4. **Do NOT add speculative context, caveats, or "common issues" lists.** Stick to what SUGGESTED_ACTION says. If the user asks why, then explain — but do not preemptively elaborate

**Example: Generating entity-specific SQL**

If the finding is CIS 1.12 (users with ACCOUNTADMIN as default role) and AT_RISK_ENTITIES contains:
```json
{"entity_name": "ADMIN_TC", "entity_detail": {"default_role": "ACCOUNTADMIN"}}
```

Generate:
```sql
-- Fix for user ADMIN_TC (current default role: ACCOUNTADMIN)
ALTER USER ADMIN_TC SET DEFAULT_ROLE = '<appropriate_role>';
```

Ask the user what role to set for each user.

**For Detection findings (investigation needed):**

1. Present the SUGGESTED_ACTION which typically includes investigative queries
2. Help the user run the investigation queries
3. Help interpret the results
4. Only suggest remediation actions (like disabling a user) after the user confirms the activity is malicious

**STOP**: Present the remediation plan and wait for user approval before generating any executable SQL.

**After approval, generate the remediation SQL.** Produce ready-to-execute SQL based on the finding type:

**Simple parameter fixes** (e.g., ALTER ACCOUNT SET):
```sql
-- Remediation for: <SCANNER_NAME>
-- Finding: <FINDING_IDENTIFIER>
<SQL from SUGGESTED_ACTION with actual values substituted>
```

**Per-entity fixes** (loop through AT_RISK_ENTITIES):
```sql
-- Remediation for: <SCANNER_NAME>
-- Entity: <entity_name> (<entity_object_type>)
<SQL from SUGGESTED_ACTION with entity name substituted>
```

**⚠️ Before presenting SQL to the user, validate every generated statement:**
- Verify correct Snowflake SQL syntax (e.g., `ALTER USER`, `ALTER ACCOUNT SET`, `CREATE NETWORK POLICY`)
- Ensure all identifiers are properly quoted if they contain special characters or are mixed-case
- **Substitute ALL placeholder values** — no `<value>`, `<db>`, `<schema>`, `<task_name>`, or similar placeholders should remain. Use actual values from `AT_RISK_ENTITIES` (entity_name, entity_detail) and `SUGGESTED_ACTION`. If a value cannot be determined from the finding data, ask the user explicitly.
- Check for common errors: missing semicolons, wrong keyword order, incorrect parameter names
- **When query results are truncated** (e.g., LIMIT applied), always state the total count and that results are limited: "Showing 50 of 40,000 results."

**STOP**: Present the SQL and get explicit confirmation before the user executes it.

Continue to Step 6 (Verify).

### Step 6: Verify Remediation

This step applies to both paths. Programmatic contracts declare `post_execution_state_claim = FULLY_RESOLVES_FINDING`, so a clean re-scan should clear the finding.

Tell the user to wait 1–2 hours (account_usage data latency) then re-run:

```sql
CALL snowflake.trust_center.execute_scanner('<SCANNER_PACKAGE_ID>', '<SCANNER_ID>');
```

Check the result:

```sql
SELECT FINDING_IDENTIFIER, STATE, TOTAL_AT_RISK_COUNT, CREATED_ON
FROM snowflake.trust_center.findings
WHERE FINDING_IDENTIFIER = '<finding_identifier>'
ORDER BY CREATED_ON DESC
LIMIT 1;
```

If the count hasn't changed, the data likely hasn't refreshed — wait longer and re-run. **Do not speculate about other causes or list troubleshooting checklists.** If the user asks why it persists after 2+ hours, then investigate.

### Step 7: Summarize Actions

After remediation, briefly state: what finding was addressed, what SQL was executed, and the before/after entity count (or "pending re-scan"). Keep it to a few lines — do not produce a lengthy formatted report unless the user asks for one.

## Stopping Points

- Step 1: After listing findings, wait for user to select one
- Step 3: Select the programmatic path (Path A) when the scanner is covered; otherwise the manual path (Path B)
- Step 5: After presenting the remediation plan (Path A preview or Path B SQL), wait for approval
- Step 5 (Path B): After generating SQL, wait for user to execute
- Step 6: After verification, offer next steps

## Safety Rules

- **Prefer programmatic remediation (Path A) when available** — the platform-rendered SQL is validated and carries declared risk/reversibility/required permissions. It is `trust_center_admin`-only; fall back to Path B if the user lacks the role.
- **Record only the structured `status`** (`SUCCEEDED`/`FAILED`/`PARTIALLY_SUCCEEDED`) via `record_remediation_result` / `record_remediation_action_result` — never write a prose result into `comment` or `error_message`. The prose summary goes in the chat reply.
- **ALWAYS validate generated SQL for correct Snowflake syntax before presenting to the user** — applies to Path B (hand-generated SQL); Path A SQL is platform-rendered
- **NEVER execute remediation SQL without explicit user approval**
- **ALWAYS present IMPACT before remediation** — some fixes can break existing workflows
- **For Detection findings, ALWAYS investigate before suggesting remediation** — unusual activity may be legitimate
- **For entity-level fixes with many entities (>10), suggest batching** — present first few, ask user to review before generating the rest
- **Warn about high-impact changes:** Network policy changes can lock users out. Role revocations can break workflows. Parameter changes affect the entire account.

### Anti-Hallucination Rules

- **NEVER claim a Snowflake feature or API does not exist based on your own knowledge.** Trust Center has a full SQL API for enabling/disabling scanners, changing schedules, and configuring notifications — documented in the api-management skill. If unsure, check the skill or search Snowflake documentation.
- **NEVER claim a Snowflake capability is unsupported without verifying.** If the user asks about a feature you're unsure of, search Snowflake public documentation at https://docs.snowflake.com/en/ before answering. Do not guess.
- **ALWAYS defer to SUGGESTED_ACTION** over your own training data. Your training data may be outdated — the finding's SUGGESTED_ACTION and Snowflake documentation are the sources of truth.
- **If you catch yourself contradicting the SUGGESTED_ACTION, stop and correct yourself immediately.** Do not double down on incorrect information.
- **When the user challenges your remediation advice**, do not defend your original answer. Instead, search Snowflake documentation to verify, and correct your guidance if needed.

## Output

- Finding details with severity, description, and affected entities
- Remediation steps from SUGGESTED_ACTION
- Ready-to-execute SQL with entity-specific values substituted
- Verification steps to confirm successful remediation

## Troubleshooting

**No open findings with at-risk entities:**
- All findings may already be resolved
- Try: `SELECT DISTINCT STATE, COUNT(*) FROM snowflake.trust_center.findings GROUP BY STATE;`

**SUGGESTED_ACTION is empty or NULL:**
- Some scanners (especially event-driven) may not provide structured remediation steps
- Guide the user based on the SCANNER_DESCRIPTION instead

**Permission denied:**
- User needs `trust_center_admin` or `trust_center_viewer` application role to view findings
- Remediation SQL typically requires `ACCOUNTADMIN`, `SECURITYADMIN` or equivalent privileges
