---
name: run
parent_skill: data-cleanrooms
description: "Run analysis or activation templates on DCR collaborations. Triggers: run analysis, run template, audience overlap, measure overlap, compare audiences, activation, run activation, activate, export segment."
---

# Run Analysis/Activation Templates

Execute analysis or activation templates on DCR collaboration data.

> **Note:** `{DB}` must be replaced with the actual DCR database discovered in the parent skill. Do NOT use `{DB}` literally in SQL calls.

## When to Use

- User wants to run standard audience overlap analysis
- User wants to run a standard audience overlap activation to export matched segments
- User wants to execute a custom analysis or activation template
- User says "run analysis", "measure overlap", "compare audiences", "activate", "export segment"

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Template** | Pre-defined analysis or activation query |
| **Data Offering** | Tables/views shared in the collaboration |
| **ANALYSIS_SPEC** | YAML specification passed to `COLLABORATION.RUN` |
| **Waterfall Analysis** | Sequential join matching (Level 1 = first match, Level 2 = fallback) |

## Template Types

| Template Pattern | Type | Output | Sub-Skill |
|------------------|------|--------|-----------|
| `standard_audience_overlap_v*` | Analysis | Result rows | `analysis/SKILL.md` |
| Custom `sql_analysis` | Analysis | Result rows | `analysis/SKILL.md` |
| `standard_audience_overlap_activation_v*` | Activation | Segment export | `activation/SKILL.md` |
| Custom `sql_activation` | Activation | Segment export | `activation/SKILL.md` |

---

## Phase 1: Collaboration Setup (MANDATORY)

### Step 1-1: Get Current Account Identifier

Identify the current account to determine LOCAL vs EXTERNAL data mapping:

```sql
SELECT CURRENT_ORGANIZATION_NAME(), CURRENT_ACCOUNT_NAME();
```

**Result format:** `'MYORG', 'MY_ACCOUNT'` → Combine as `MYORG.MY_ACCOUNT`

**Store this identifier** for table mapping in sub-skills (used to match against `SHARED_WITH` values).

### Step 1-2: View Available Collaborations

```sql
CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS();
```

Display collaborations to user (name, status, owner).

### Step 1-3: User Selects Collaboration

**STOPPING POINT:** Ask user which collaboration to use.

### Step 1-4: Validate Collaboration Status

**Inform user:** "Collecting details for `<collaboration_name>`..."

```sql
CALL {DB}.COLLABORATION.GET_STATUS('<collaboration_name>');
```

**Check:**
- Current account's status = `JOINED`
- At least 2 parties are `JOINED`

**If NOT ready:** STOP — do NOT attempt to run any analysis or activation. The operation will fail. Inform the user why (which parties are not yet JOINED) and return to Step 1-3 to pick another collaboration.

### Step 1-5: Get Templates and Data Offerings

**ONLY proceed if Step 1-4 confirmed collaboration is ready:**

```sql
CALL {DB}.COLLABORATION.VIEW_TEMPLATES('<collaboration_name>');
CALL {DB}.COLLABORATION.VIEW_DATA_OFFERINGS('<collaboration_name>');
```

**Store these results** - sub-skills will reference them.

---

## Phase 2: Template Selection & Routing

### Step 2-1: Categorize Templates

Group templates by type:
- **Standard Audience Overlap**: Names matching `standard_audience_overlap_v*`
- **Standard Activation**: Names matching `standard_audience_overlap_activation_v*`
- **Custom Analysis**: Type = `sql_analysis` in TEMPLATE_SPEC
- **Custom Activation**: Type = `sql_activation` in TEMPLATE_SPEC

Present categorized list to user.

### Step 2-2: User Selects Template

**STOPPING POINT:** Ask user which template to run.

### Step 2-3: Route to Sub-Skill (MANDATORY)

**CRITICAL: You MUST load the appropriate sub-skill BEFORE attempting to build any ANALYSIS_SPEC or ACTIVATION_SPEC.** Use the **read tool** to load the sub-skill file; the spec format is complex and varies by template type.

Based on selection, **use the read tool** to load the matching sub-skill and continue executing its workflow (no user confirmation needed here):

**If template is `standard_audience_overlap_activation_v*` OR type = `sql_activation`:**
→ **Load** `activation/SKILL.md` and continue with its workflow

**Else (standard_audience_overlap_v* OR sql_analysis OR other):**
→ **Load** `analysis/SKILL.md` and continue with its workflow

> **Note:** This is NOT a stopping point. After loading the sub-skill, proceed directly with its instructions.

---

## Policy Requirements

Some parameters require specific policies on data offerings:

| Parameter | Required Policy |
|-----------|-----------------|
| `join_clauses` | JOIN POLICY on join columns |
| `count_column` | JOIN POLICY on count columns |
| `my_group_by` / `source_group_by` | COLUMN POLICY on group by columns |
| `activation_column` | ACTIVATION POLICY on activation columns |

If analysis fails with policy errors, user must update data offering with appropriate policies.

---

## Stopping Points

- **Step 1-3**: User selects collaboration — STOP and ask
- **Step 2-2**: User selects template — STOP and ask
- **Sub-skill stopping points**: Each sub-skill (analysis, activation) has its own mandatory stopping points for table selection, parameter configuration, and execution confirmation

**Resume rule:** Upon user approval, proceed directly without re-asking.

## Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| "Policy not found" | Missing JOIN/COLUMN/ACTIVATION policy | Update data offering with required policies |
| "Collaboration not joined" | Status not JOINED | Do NOT retry — wait for parties to join, then re-check status |
| "Template not found" | Template not in collaboration | Check VIEW_TEMPLATES output |
| "Invalid table reference" | Wrong table format | Use TEMPLATE_VIEW_NAME from VIEW_DATA_OFFERINGS |
| "Privacy threshold" | Count below 5 | Results show NULL - expected behavior |

---

## Required Privileges

| Procedure | Privilege | Scope |
|-----------|-----------|-------|
| `VIEW_COLLABORATIONS()` | `VIEW COLLABORATIONS` | Account |
| `GET_STATUS(collab)` | `GET STATUS` | Collaboration |
| `VIEW_DATA_OFFERINGS(collab)` | `VIEW DATA OFFERINGS` | Collaboration |
| `VIEW_TEMPLATES(collab)` | `VIEW TEMPLATES` | Collaboration |
| `RUN(collab, spec)` | `RUN ANALYSIS` | Collaboration |

See the parent data-cleanrooms SKILL.md "Required Privileges" section for how to grant privileges using `{DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE` or `{DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE`.
