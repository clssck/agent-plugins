---
name: run-listing-custom-validation
description: >
  Validate a listing manifest against all active custom rules from LISTING_VALIDATION_RULES using Cortex AI (AI_COMPLETE).
  Works as a publish gate injected by a parent skill, or standalone to validate any listing.
  Blocks publishing if any ERROR rule fails.

  WHEN TO USE THIS SKILL:
  - User wants to validate a listing manifest against custom org rules before publishing
  - Running the publish gate as part of a listing creation workflow
  - Checking whether a listing would pass or fail custom validation rules without publishing
  - Testing a new or updated validation rule against an existing listing

  WHEN NOT TO USE THIS SKILL:
  - User wants to create or manage validation rules themselves → Use the create-internal-listing-custom-validation-rules skill instead

  Triggers: run validation, validate listing, check listing rules, run custom validation, validate before publish, listing validation gate, will this listing pass validation.
---

# Listing Publish Gate — AI-Powered Custom Validation

Evaluates a listing manifest against all active custom validation rules from `LISTING_VALIDATION_RULES` using Cortex AI (`AI_COMPLETE`). Blocks publishing if any ERROR rule fails. For draft listings, results are shown as a preview and never block.

Can be invoked two ways:
- **As a sub-skill** (from a parent listing creation skill): manifest may already be provided — use it directly. Always confirm the rules table location with the user (Step 1). The parent skill also passes whether this is a **draft** or **publish** — carry that forward to Step 4.
- **Standalone**: gather the manifest and rules table location before validating. Ask the user whether they are validating for a draft or a publish.

## Workflow

```
Entry → Step 0: Get Manifest → Step 1: Locate Rules Table → Step 2: Load Rules → Step 3: Run AI Validation → Step 4: Evaluate Results → Pass: Proceed / Fail: Block (publish) or Inform (draft)
             ↑ (standalone only)          ↑                          ↑                                                    ↑
         ⚠️ STOP (ask user)        ⚠️ STOP (custom?)        ⚠️ STOP (if no rules)                              ⚠️ STOP (if any fail, publish only)
```

---

### Step 0: Get Manifest

**If the manifest was provided by a parent skill**, use it directly — skip this step.

**If invoked standalone** (no manifest provided), ask the user:
```
What would you like to validate?
1. A published listing — provide its name and I'll fetch the manifest
2. A manifest JSON — paste it directly
```

- **Option 1**: Run `DESCRIBE LISTING <listing_name>;` and extract the manifest JSON from the result.
- **Option 2**: Use the pasted JSON as-is.

**⚠️ STOP** if the manifest cannot be obtained.

---

### Step 1: Locate the Validation Rules Table

**Goal:** Resolve where the validation rules table lives.

**Always ask the user** to confirm the rules table location — even when invoked as a sub-skill:
```
Where is your validation rules table? (press enter for default, or type a custom location e.g. MY_DB.MY_SCHEMA.MY_TABLE)
Default: INTERNAL_MARKETPLACE.VALIDATION_RULES.LISTING_VALIDATION_RULES
```

**⚠️ STOP**: Wait for the user's response before continuing. Do not assume or use any previously mentioned table location.

Use the resolved `<database>.<schema>.<table>` for all queries below.

---

### Step 2: Load Active Rules

**Goal:** Fetch all active and shadow rules from the resolved table.

```sql
SELECT
    name                        AS rule_id,
    title,
    props:severity::VARCHAR     AS severity,
    props:status::VARCHAR       AS status
FROM <database>.<schema>.<table>
WHERE config_type = 'listing_validation_rule'
  AND props:status::VARCHAR IN ('enabled', 'shadow')
ORDER BY name;
```

**If the table doesn't exist or no active/shadow rules are found:**
> No active validation rules found. → Return control to parent skill to proceed with publishing.

**If rules exist**, show the user which rules will be checked:
```
Running N validation rule(s) before publishing:
  • RULE_NAME_1 — <title>
  • RULE_NAME_2 — <title>
```

---

### Step 3: Run AI Validation

**Goal:** Evaluate the listing manifest against all active rules using Cortex AI.

**Actions:**

1. **Set variables for the validation call:**
```sql
-- Paste in the manifest JSON
SET manifest_json = $$<manifest_json>$$;

-- Collect publisher metadata automatically
SET supporting_metadata_json = (
    SELECT OBJECT_CONSTRUCT(
        'provider_account_name', CURRENT_ACCOUNT_NAME(),
        'current_user',          CURRENT_USER(),
        'current_role',          CURRENT_ROLE()
    )::VARCHAR
);
```

2. **Build and execute the AI validation query:**
```sql
WITH active_rules AS (
    SELECT
        OBJECT_CONSTRUCT(
            'rule_id',   name::VARCHAR,
            'title',     title::VARCHAR,
            'severity',  props:severity::VARCHAR,
            'status',    props:status::VARCHAR,
            'rule_text', props:rule_text::VARCHAR,
            'hints',     props:hints
        ) AS rule_obj
    FROM <database>.<schema>.<table>
    WHERE props:status::VARCHAR IN ('enabled', 'shadow')
      AND config_type = 'listing_validation_rule'
),
rules_aggregated AS (
    SELECT ARRAY_AGG(rule_obj)::VARCHAR AS rules_json
    FROM active_rules
),
prompt_built AS (
    SELECT CONCAT(
        'You are a listing publish validator for an organization''s Internal Marketplace in Snowflake.\n\n',
        'Your organization''s administrators have defined a set of custom validation rules that every\n',
        'listing must satisfy before it can be published. These rules enforce org-specific policies\n',
        'around data governance, access targeting, approval workflows, content quality, and data\n',
        'classification.\n\n',
        'You will be given supporting metadata about the publisher (e.g. provider_account_name), the full\n',
        'manifest of the listing, and a list of validation rules. Some rules reference fields in the\n',
        'supporting metadata — treat those fields the same way you treat manifest fields. For each rule,\n',
        'analyze the available information and determine whether the listing PASSES or FAILS that rule.\n\n',
        '---\n\n',
        'SUPPORTING METADATA:\n', $supporting_metadata_json, '\n\n',
        '---\n\n',
        'LISTING MANIFEST:\n', $manifest_json, '\n\n',
        '---\n\n',
        'VALIDATION RULES:\n', rules_json, '\n\n',
        '---\n\n',
        'INSTRUCTIONS:\n\n',
        'For each rule in the list above, evaluate whether the listing manifest satisfies it.\n\n',
        '- Return PASS if the listing satisfies the rule, or if the rule''s trigger condition is not met\n',
        '  (i.e. the rule only applies under certain conditions and those conditions are not present in\n',
        '  this listing).\n',
        '- Return FAIL if the listing clearly violates the rule.\n',
        '- In your reasoning, quote the specific field values from the manifest that determined your\n',
        '  verdict. Do not reference fields that are not present in the manifest.\n',
        '- If a field mentioned in a rule is absent from the manifest or supporting metadata, treat it as not set / empty.\n',
        '- Evaluate each rule independently — do not let your verdict for one rule influence another.\n',
        '- Keep each reasoning to ONE concise sentence (max 25 words). Brevity is required.\n\n',
        'OUTPUT FORMAT:\n',
        'Return a single JSON object where each key is a rule_id and the value is an object with\n',
        '"verdict" ("PASS" or "FAIL") and "reasoning" (one sentence, max 25 words).\n\n',
        'Example shape (do not copy these values):\n',
        '{\n',
        '  "rule_id_one": {"verdict": "PASS", "reasoning": "..."},\n',
        '  "rule_id_two": {"verdict": "FAIL", "reasoning": "..."}\n',
        '}\n\n',
        'RESPOND WITH ONLY THE JSON OBJECT. DO NOT include any text before or after it.'
    ) AS prompt_text
    FROM rules_aggregated
)
SELECT AI_COMPLETE(
    'claude-opus-4-6',
    prompt_text
) AS ai_response
FROM prompt_built;
```

3. **Store the AI response** for parsing in Step 4:
```sql
SET ai_response = (SELECT ai_response::VARCHAR FROM TABLE(RESULT_SCAN(LAST_QUERY_ID())));
```

**Model note:** `claude-opus-4-6` is the default. Substitute with another model supported by `AI_COMPLETE` (e.g. `mistral-large2`, `llama3.1-70b`) if needed. Use a capable model — multi-rule reasoning benefits from higher capacity.

---

### Step 4: Evaluate Results

**Goal:** Parse the AI response, cross-reference rule severity/status, and determine whether listing creation can proceed.

**Actions:**

1. **Parse and join AI verdicts with rule metadata:**
```sql
WITH validation_results AS (
    SELECT
        key                          AS rule_id,
        value:verdict::VARCHAR       AS verdict,
        value:reasoning::VARCHAR     AS reasoning
    FROM TABLE(FLATTEN(PARSE_JSON($ai_response)))
),
rule_details AS (
    SELECT
        name                         AS rule_id,
        title,
        props:severity::VARCHAR      AS severity,
        props:status::VARCHAR        AS status
    FROM <database>.<schema>.<table>
    WHERE props:status::VARCHAR IN ('enabled', 'shadow')
      AND config_type = 'listing_validation_rule'
)
SELECT
    v.rule_id,
    r.title,
    r.severity,
    r.status,
    v.verdict,
    v.reasoning,
    CASE
        WHEN v.verdict = 'FAIL' AND r.severity = 'ERROR'   AND r.status = 'enabled' THEN 'BLOCKING'
        WHEN v.verdict = 'FAIL' AND r.severity = 'WARNING' AND r.status = 'enabled' THEN 'WARNING'
        WHEN v.verdict = 'FAIL'                            AND r.status = 'shadow'  THEN 'SHADOW'
        ELSE 'OK'
    END AS impact
FROM validation_results v
JOIN rule_details r ON v.rule_id = r.rule_id
ORDER BY
    CASE impact
        WHEN 'BLOCKING'  THEN 1
        WHEN 'WARNING'   THEN 2
        WHEN 'SHADOW'    THEN 3
        ELSE 4
    END;
```

2. **Always display the full validation results as a markdown table** (regardless of outcome):

```markdown
| Rule ID | Title | Severity | Verdict | Impact | Reasoning |
|---------|-------|----------|---------|--------|-----------|
| <rule_id> | <title> | ERROR | ❌ FAIL | 🚫 BLOCKING | <reasoning> |
| <rule_id> | <title> | WARNING | ❌ FAIL | ⚠️ WARNING | <reasoning> |
| <rule_id> | <title> | ERROR | ✅ PASS | ✅ OK | <reasoning> |
| <rule_id> | <title> | WARNING | ✅ PASS | ✅ OK | <reasoning> |
| <rule_id> | <title> | ERROR | ❌ FAIL | 👁️ SHADOW | <reasoning> |
```

3. **Then present the outcome summary below the table:**

**When there are BLOCKING failures (publish):**
```
❌ Publish blocked — N rule(s) failed (see table above).

To resolve:
  - Fix the manifest so it satisfies each failing rule, then re-run validation.
  - OR ask your admin to update the rule definition in LISTING_VALIDATION_RULES.
  - OR set the rule's status to 'shadow' to observe without blocking.
```

**⚠️ STOP**: Do not proceed to share creation. Wait for the user to resolve failing rules before re-running validation.

**When there are BLOCKING failures (draft):**
```
⚠️  N rule(s) would block publishing (informational only — this is a draft, see table above).
```
Proceed to listing creation without stopping.

**When there are only WARNINGs (no blocking failures):**
```
⚠️  Validation passed with N warning(s) (see table above).

Proceed with listing creation? (yes / no)
```

**When all rules pass:**
```
✅ Validation passed — all rules satisfied. 
```

**Append for shadow-mode failures (any of the above):**
```
👁️  N shadow rule(s) failed (observing only — not blocking, see table above).
```

4. **Determine next action:**

| Result | Is draft? | Action |
|--------|-----------|--------|
| BLOCKING failures exist | No (publish) | **⚠️ STOP** — do not proceed; show resolution guidance above |
| BLOCKING failures exist | Yes (draft) | Show informational summary, then proceed |
| WARNINGs only | Either | **⚠️ STOP** — get user confirmation before proceeding |
| All pass (or shadow only) | Either | Return control to parent skill to execute listing creation |

---

## Notes

- This gate only evaluates the manifest provided. It does not re-gather requirements.
- Shadow rules are observed but never block. They are useful for testing new rules before enabling them.
- If `AI_COMPLETE` fails or returns malformed JSON, surface the error to the user, skip validation, and return control to the parent skill to proceed with publishing.
- The `supporting_metadata_json` provides publisher context (account, user, role) that some rules may reference alongside the manifest fields.
