---
name: run-activation
parent_skill: run
description: "Run activation templates - standard audience overlap activation or custom sql_activation templates."
---

# Run Activation Templates

Execute activation templates that export matched segments to collaborators.

## When to Load

- Template type is `sql_activation` (custom activation template)
- User wants to activate, export segments, run activation

> **Note:** `{DB}` must be replaced with the actual DCR database discovered in the parent skill.

---

## Phase B: Determine Template Variant

After user selects a template in the parent skill:

**If template name matches `standard_audience_overlap_activation_v*`:**
→ Follow **Standard Activation Workflow** below

**Else (custom `sql_activation` template):**
→ Follow **Custom Activation Workflow** below

---

## Standard Activation Workflow

For `standard_audience_overlap_activation_v*` templates with known, fixed parameters.

### Step S-1: Determine Table Mapping (CRITICAL)

Use data offerings from **router Step 1-5**. The current account's table should always be the **activation source** (where segments are exported from).

#### Identify Current Account's Collaborator Name

1. From parent Step 1-1, you have the current account identifier (e.g., `ORGNAME.ACC_NAME`)
2. From the collaboration spec's `collaborator_identifier_aliases`, find the collaborator name that maps to the current account
3. Use this to match against the `SHARED_BY` column in data offerings

#### Table Placement Rules

| SHARED_WITH Value | SHARED_BY | Table Placement | Alias | Role |
|-------------------|-----------|-----------------|-------|------|
| Exactly `"LOCAL"` | Current account | `local_view_mappings.my_tables[0]` | `c1.` | YOUR data (activation source) |
| Not `"LOCAL"` | Current account | `view_mappings.source_tables[1]` | `p2.` | YOUR data (activation source) |
| Not `"LOCAL"` | Partner | `view_mappings.source_tables[0]` | `p1.` | PARTNER data (source) |

**Key Points:**
- Current account's table is ALWAYS the activation source (`c1.` or `p2.`)
- Partner's table is ALWAYS `p1.`
- Only the exact string value `"LOCAL"` indicates a local table

**Valid Configurations:**

**Config A: Local + External**

When current account's table has `SHARED_WITH = "LOCAL"`:

```yaml
view_mappings:
  source_tables:
    - "PARTNER.offering_id.table"          # p1. (SHARED_BY = partner)
local_view_mappings:
  my_tables:
    - "LOCAL.offering_id.table"            # c1. (SHARED_WITH = "LOCAL", current account)
arguments:
  join_clauses:
    - "p1.hashed_email = c1.hashed_email"
  activation_column:
    - "c1.hashed_email"
```

**Config B: Both External (no "LOCAL" table)**

When current account's table has `SHARED_WITH ≠ "LOCAL"` (e.g., arrays like `["ADVERTISER","PUBLISHER"]`):

```yaml
view_mappings:
  source_tables:
    - "PARTNER.offering_id.table"          # p1. (SHARED_BY = partner)
    - "CURRENT_ACCT.offering_id.table"     # p2. (SHARED_BY = current account)
local_view_mappings:
  my_tables: []                            # Empty - no LOCAL table!
arguments:
  join_clauses:
    - "p1.hashed_email = p2.hashed_email"  # p1-p2 join (NOT p1-c1)
  activation_column:
    - "p2.hashed_email"                    # Use p2. alias (NOT c1.)
```

**MANDATORY STOPPING POINT** - Do NOT proceed without user selection.

Ask user to select tables for activation.

### Step S-2: Offer Basic vs Advanced Activation

**MANDATORY STOPPING POINT** - Do NOT proceed without user selection.

Present choice:
```
Select activation mode:
1. Basic Activation - Auto-configure with defaults (recommended for first-time)
2. Advanced Activation - Full control over all parameters

Please select (1-2):
```

**If Basic:** Auto-detect join columns, use all activation columns, skip to Step S-4.
**If Advanced:** Continue to Step S-3.

### Step S-3: Configure Parameters (Advanced Mode Only)

**Step 3a: Join Columns (required)**

**MANDATORY STOPPING POINT** - Do NOT proceed without user selection.

> "Which columns should match records?
> Available: `<list from TEMPLATE_JOIN_COLUMNS>`
> 
> You can select multiple for waterfall matching (Level 1, Level 2, etc.)."

User can select multiple for waterfall matching. Construct array:
- Single: `["p1.hashed_email = c1.hashed_email"]`
- Multiple: `["p1.hashed_email = c1.hashed_email", "p1.hashed_phone = c1.hashed_phone"]`

**Step 3b: Activation Columns (required)**

**MANDATORY STOPPING POINT** - Do NOT proceed without user selection.

> "Which columns to export in the segment?
> Available: `<list from ACTIVATION_ALLOWED_COLUMNS>`"

Present columns from `ACTIVATION_ALLOWED_COLUMNS`. Construct array:
- Single: `["c1.hashed_email"]`
- Multiple: `["c1.hashed_email", "c1.customer_id", "c1.status"]`

**Step 3c: Where Clause (optional filter)**

**MANDATORY STOPPING POINT** - Must ask user, do NOT skip this step.

> "Filter records before activation?
> Available columns: `<list from ACTIVATION_ALLOWED_COLUMNS>`
> Example: `c1.status = 'ACTIVE'`
> 
> Enter filter or say 'skip' to skip:"

### Step S-4: Configure Activation Destination

**Step 4a: Destination Collaborator (required)**

**MANDATORY STOPPING POINT** - Do NOT proceed without user selection.

> "Which collaborator receives the segment?
> Available: `<list from activation_destinations.snowflake_collaborators>`"

Present collaborators from `activation_destinations.snowflake_collaborators`.

**Step 4b: Segment Name (required)**

**MANDATORY STOPPING POINT** - Do NOT proceed without user input.

> "Name for the exported segment?"

### Step S-5: Build ANALYSIS_SPEC

**CRITICAL:** The `activation` section is a **sibling** of `arguments` under `template_configuration`, NOT inside `arguments`.

```yaml
api_version: "2.0.0"
spec_type: "analysis"
name: "<descriptive_name>"
description: "<optional>"
template: "standard_audience_overlap_activation_v0"

template_configuration:
  view_mappings:
    source_tables:
      - "<PARTNER_TABLE>"
  local_view_mappings:
    my_tables:
      - "<LOCAL_TABLE>"
  arguments:
    join_clauses:
      - "p1.hashed_email = c1.hashed_email"
    activation_column:
      - "c1.hashed_email"
      - "c1.customer_id"
    where_clause: ""
  activation:                              # SIBLING of arguments!
    snowflake_collaborator: "<PARTNER_ALIAS>"
    segment_name: "<segment_name>"
```

**Common Mistake:**
```yaml
# WRONG - activation inside arguments
arguments:
  activation:
    snowflake_collaborator: "..."

# CORRECT - activation sibling of arguments
arguments:
  join_clauses: [...]
activation:
  snowflake_collaborator: "..."
```

### Step S-6: Confirm and Execute

**MANDATORY CHECKPOINT** - Do NOT execute without explicit user approval.

Show complete spec and ask:
> "Run this activation? (yes/no)"

**On "yes":** Execute immediately (no second confirmation):

```sql
CALL {DB}.COLLABORATION.RUN(
  '<collaboration_name>',
  $$
  <ANALYSIS_SPEC_YAML>
  $$
);
```

> **Always use `$$` dollar-quoting for the ANALYSIS_SPEC.** Single or double quotes break on multi-line YAML containing colons, special characters, or embedded quotes. `$$` is the only safe quoting style for this argument. Exception: if an argument value itself contains the literal `$$` sequence, move that value into a dedicated parameter rather than embedding it inline.

**On "no":** Ask what to change, return to relevant step.

### Step S-7: Present Results

Activation returns segment table suffix. Explain:
- Data exported to specified collaborator
- Segment name can be used for targeting

**Activation Complete.** Return to parent skill or await next user request.

---

## Custom Activation Workflow

For custom `sql_activation` templates with dynamic parameters.

### Step C-1: Read Template Specification (CRITICAL)

```sql
CALL {DB}.COLLABORATION.VIEW_TEMPLATES('<collaboration_name>');
```

From `TEMPLATE_SPEC` column:

1. **Verify type is `sql_activation`** (not `sql_analysis`)
2. **Extract `parameters` array** - note required vs optional, types
3. **Read `template` SQL** - understand table variable expectations

### Step C-2: Determine Table Mapping

Same as Step S-1. The current account's table should always be the activation source:

| SHARED_WITH Value | SHARED_BY | Table Placement | Alias |
|-------------------|-----------|-----------------|-------|
| Exactly `"LOCAL"` | Current account | `my_tables[0]` | `c1.` |
| Not `"LOCAL"` | Current account | `source_tables[1]` | `p2.` |
| Not `"LOCAL"` | Partner | `source_tables[0]` | `p1.` |

Read template SQL to understand expected table variables and ensure current account's table is in the appropriate position.

**MANDATORY STOPPING POINT** - Do NOT proceed without user selection.

Ask user to select tables based on template requirements.

### Step C-3: Present Parameters Dynamically

For EACH parameter from TEMPLATE_SPEC:

| Parameter Type | Input Mode |
|----------------|------------|
| `string` | Single input |
| `integer` / `number` | Single input |
| `boolean` | Single choice |
| `array` | **MULTI-SELECT** |

**For each required parameter:**

**MANDATORY STOPPING POINT** - Do NOT proceed without user input for each parameter.

> "Parameter: `<name>` (required)
> Type: `<type>`
> Description: `<description>`"

If type is `array`, use multi-select.

**For optional parameters:** Still ask, but offer to skip.

### Step C-4: Configure Activation Destination (REQUIRED)

**All `sql_activation` templates require the activation section.**

**MANDATORY STOPPING POINT** - Do NOT proceed without user selection.

> "Which collaborator receives the segment?
> Available: `<list from activation_destinations.snowflake_collaborators>`"

**MANDATORY STOPPING POINT** - Do NOT proceed without user input.

> "Name for the exported segment?"

### Step C-5: Build ANALYSIS_SPEC

**CRITICAL:** The `activation` section is a **sibling** of `arguments`.

```yaml
api_version: "2.0.0"
spec_type: "analysis"
name: "<descriptive_name>"
template: "<custom_activation_template>"

template_configuration:
  view_mappings:
    source_tables:
      - "<TABLE_REFERENCE>"
  local_view_mappings:
    my_tables:
      - "<LOCAL_TABLE>"
  arguments:
    <param1>: <value1>
    <param2>: <value2>
  activation:                              # SIBLING of arguments!
    snowflake_collaborator: "<PARTNER_ALIAS>"
    segment_name: "<segment_name>"
```

### Step C-6: Confirm and Execute

**MANDATORY CHECKPOINT** - Do NOT execute without explicit user approval.

Show complete spec and ask:
> "Run this activation? (yes/no)"

**On "yes":** Execute immediately:

```sql
CALL {DB}.COLLABORATION.RUN(
  '<collaboration_name>',
  $$
  <ANALYSIS_SPEC_YAML>
  $$
);
```

> **Always use `$$` dollar-quoting for the ANALYSIS_SPEC.** Single or double quotes break on multi-line YAML containing colons, special characters, or embedded quotes. `$$` is the only safe quoting style for this argument. Exception: if an argument value itself contains the literal `$$` sequence, move that value into a dedicated parameter rather than embedding it inline.

### Step C-7: Present Results

Results vary by template. Explain segment export status.

**Activation Complete.** Return to parent skill or await next user request.

---

## Activation Section Reference

| Field | Required | Constraints |
|-------|----------|-------------|
| `snowflake_collaborator` | Yes | Valid collaborator alias, max 25 chars |
| `segment_name` | Yes | Segment identifier, max 255 chars |

**Finding valid collaborators:**
Check `activation_destinations.snowflake_collaborators` in the collaboration spec from `GET_STATUS`.
