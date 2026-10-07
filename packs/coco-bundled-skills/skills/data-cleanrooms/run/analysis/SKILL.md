---
name: run-analysis
parent_skill: run
description: "Run analysis templates - standard audience overlap or custom sql_analysis templates. No segment export."
---

# Run Analysis Templates

Execute analysis templates that return result rows (no segment export).

## When to Load

- Template name matches `standard_audience_overlap_v*`
- Template type is `sql_analysis` (custom analysis template)
- User wants to measure overlap, compare audiences, run analysis

> **Note:** `{DB}` must be replaced with the actual DCR database discovered in the parent skill.

---

## Phase A: Determine Template Variant

After user selects a template in the parent skill:

**If template name matches `standard_audience_overlap_v*`:**
→ Follow **Standard Analysis Workflow** below

**Else (custom `sql_analysis` template):**
→ Follow **Custom Analysis Workflow** below

---

## Standard Analysis Workflow

For `standard_audience_overlap_v*` templates with known, fixed parameters.

### Step S-1: Determine Table Mapping (CRITICAL)

Use data offerings from **router Step 1-5**. The current account's table should always be the **count source** (where distinct counts are measured from).

#### Identify Current Account's Collaborator Name

1. From parent Step 1-1, you have the current account identifier (e.g., `ORGNAME.ACC_NAME`)
2. From the collaboration spec's `collaborator_identifier_aliases`, find the collaborator name that maps to the current account
3. Use this to match against the `SHARED_BY` column in data offerings

#### Table Placement Rules

| SHARED_WITH Value | SHARED_BY | Table Placement | Alias | Role |
|-------------------|-----------|-----------------|-------|------|
| Exactly `"LOCAL"` | Current account | `local_view_mappings.my_tables[0]` | `c1.` | YOUR data (count source) |
| Not `"LOCAL"` | Current account | `view_mappings.source_tables[1]` | `p2.` | YOUR data (count source) |
| Not `"LOCAL"` | Partner | `view_mappings.source_tables[0]` | `p1.` | PARTNER data (source) |

**Key Points:**
- Current account's table is ALWAYS the count source (`c1.` or `p2.`)
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
```

**MANDATORY STOPPING POINT** - Do NOT proceed without user selection.

Ask user to select exactly 2 tables for comparison from the available data offerings.

### Step S-2: Offer Basic vs Advanced Analysis

**MANDATORY STOPPING POINT** - Do NOT proceed without user selection.

Present choice:
```
Select analysis mode:
1. Basic Analysis - Auto-configure with defaults (recommended for first-time)
2. Advanced Analysis - Full control over all parameters

Please select (1-2):
```

**If Basic:** Auto-detect join columns and skip to Step S-4.

**Basic Mode Defaults:**
| Parameter | Default Value |
|-----------|---------------|
| `join_clauses` | First available column from `TEMPLATE_JOIN_COLUMNS` (e.g., `hashed_email`) |
| `count_column` | Same as join column |
| `my_where_clause` | Empty (no filter) |
| `source_where_clause` | Empty (no filter) |
| `my_group_by` | Empty (no breakdown) |
| `source_group_by` | Empty (no breakdown) |

**If Advanced:** Continue to Step S-3.

### Step S-3: Configure Parameters (Advanced Mode Only)

Gather parameters ONE AT A TIME with stopping points.

**Alias Reference** (based on Step S-1 configuration):
- Config A (Local + External): YOUR data = `c1.`, PARTNER data = `p1.`
- Config B (Both External): YOUR data = `p2.`, PARTNER data = `p1.`

**Step 3a: Join Columns (required)**

**MANDATORY STOPPING POINT** - Do NOT proceed without user selection.

> "Which columns should match records between tables?
> Available: `<list from TEMPLATE_JOIN_COLUMNS>`
> 
> You can select multiple for waterfall matching (Level 1, Level 2, etc.)."

User can select multiple for waterfall matching. Construct array using appropriate aliases:
- Config A: `["p1.hashed_email = c1.hashed_email"]`
- Config B: `["p1.hashed_email = p2.hashed_email"]`

**Step 3b: Count Column (required)**

**MANDATORY STOPPING POINT** - Do NOT proceed without user selection.

> "Which column(s) to count distinct records?
> Available: `<list from TEMPLATE_JOIN_COLUMNS>`"

User can select multiple for composite count key. Construct array:
- Single: `["hashed_email"]`
- Multiple: `["hashed_email", "hashed_phone"]`

**Step 3c: Your Where Clause (optional filter)**

**MANDATORY STOPPING POINT** - Must ask user, do NOT skip this step.

> "Filter YOUR data (`c1.` for Config A, `p2.` for Config B)?
> Available columns: `<list from ANALYSIS_ALLOWED_COLUMNS for your table>`
> Example (Config A): `c1.status = 'ACTIVE'`
> Example (Config B): `p2.status = 'ACTIVE'`
> 
> Enter filter or say 'skip' to skip:"

**Step 3d: Source Where Clause (optional filter)**

**MANDATORY STOPPING POINT** - Must ask user, do NOT skip this step.

> "Filter PARTNER data (p1.)?
> Available columns: `<list from ANALYSIS_ALLOWED_COLUMNS for partner table>`
> Example: `p1.device_type = 'mobile'`
> 
> Enter filter or say 'skip' to skip:"

**Step 3e: Your Group By (optional breakdown)**

**MANDATORY STOPPING POINT** - Must ask user, do NOT skip this step.

> "Break down results by YOUR columns?
> Available columns: `<list from ANALYSIS_ALLOWED_COLUMNS for your table>`
> Example (Config A): `["c1.status", "c1.region"]`
> Example (Config B): `["p2.status", "p2.region"]`
> 
> Enter columns or say 'skip' to skip:"

**Step 3f: Source Group By (optional breakdown)**

**MANDATORY STOPPING POINT** - Must ask user, do NOT skip this step.

> "Break down results by PARTNER columns?
> Available columns: `<list from ANALYSIS_ALLOWED_COLUMNS for partner table>`
> Example: `["p1.age_band"]`
> 
> Enter columns or say 'skip' to skip:"

### Step S-4: Build ANALYSIS_SPEC

> **Reserved keywords — never suggest in ANALYSIS_SPEC arguments:** `source_table` and `my_table` are reserved by the execution engine. They are always injected from `view_mappings.source_tables` and `local_view_mappings.my_tables` respectively. Even though `VIEW_TEMPLATES` lists `source_table` as a required template parameter, do NOT add it (or `my_table`) to the `arguments` block — they will be ignored there.

**Config A (Local + External):**

```yaml
api_version: "2.0.0"
spec_type: "analysis"
name: "<descriptive_name>"
description: "<optional>"
template: "standard_audience_overlap_v0"

template_configuration:
  view_mappings:
    source_tables:
      - "<PARTNER_TABLE>"                    # p1.
  local_view_mappings:
    my_tables:
      - "<YOUR_LOCAL_TABLE>"                 # c1.
  arguments:
    join_clauses:
      - "p1.hashed_email = c1.hashed_email"
    count_column:
      - "hashed_email"
    my_where_clause: ""
    source_where_clause: ""
    my_group_by: []
    source_group_by: []
```

**Config B (Both External):**

```yaml
api_version: "2.0.0"
spec_type: "analysis"
name: "<descriptive_name>"
description: "<optional>"
template: "standard_audience_overlap_v0"

template_configuration:
  view_mappings:
    source_tables:
      - "<PARTNER_TABLE>"                    # p1. (SHARED_BY = partner)
      - "<YOUR_TABLE>"                       # p2. (SHARED_BY = current account)
  local_view_mappings:
    my_tables: []                            # Empty - no LOCAL table
  arguments:
    join_clauses:
      - "p1.hashed_email = p2.hashed_email"
    count_column:
      - "hashed_email"
    my_where_clause: ""
    source_where_clause: ""
    my_group_by: []
    source_group_by: []
```

### Step S-5: Confirm and Execute

**MANDATORY CHECKPOINT** - Do NOT execute without explicit user approval.

Show complete spec and ask:
> "Run this analysis? (yes/no)"

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

### Step S-6: Present Results

Results include:
- `WATERFALL_LEVEL` - Which join condition matched
- `METRIC_TYPE` - OVERLAP or NON_OVERLAP
- `COUNT_VALUE` - Matching records (NULL if below privacy threshold of 5)
- `TOTAL_COUNT` - Total records
- `MATCH_CRITERIA` - Join clause used
- `DIMENSION_NAMES` / `DIMENSION_VALUES` - Group by breakdown

**Visualization suggestions:**
- Bar chart: OVERLAP vs NON_OVERLAP by waterfall level
- Pie chart: Match rate = OVERLAP / TOTAL_COUNT

**Analysis Complete.** Return to parent skill or await next user request.

---

## Custom Analysis Workflow

For custom `sql_analysis` templates with dynamic parameters.

### Step C-1: Read Template Specification (CRITICAL)

```sql
CALL {DB}.COLLABORATION.VIEW_TEMPLATES('<collaboration_name>');
```

From `TEMPLATE_SPEC` column, extract:

1. **Verify type is `sql_analysis`** (not `sql_activation`)
2. **Extract `parameters` array** - note required vs optional, types
3. **Read `template` SQL** - understand what table variables it expects

### Step C-2: Determine Table Mapping

Same as Step S-1. The current account's table should always be the count source:

| SHARED_WITH Value | SHARED_BY | Table Placement | Alias |
|-------------------|-----------|-----------------|-------|
| Exactly `"LOCAL"` | Current account | `my_tables[0]` | `c1.` |
| Not `"LOCAL"` | Current account | `source_tables[1]` | `p2.` |
| Not `"LOCAL"` | Partner | `source_tables[0]` | `p1.` |

Read the template SQL to understand:
- Does it expect `source_table[0]`, `source_table[1]`?
- Does it expect `my_table[0]`?

Map tables accordingly, ensuring current account's table is in the appropriate position.

**MANDATORY STOPPING POINT** - Do NOT proceed without user selection.

Ask user to select tables based on template requirements.

### Step C-3: Present Parameters Dynamically

For EACH parameter from TEMPLATE_SPEC:

| Parameter Type | Input Mode | Example |
|----------------|------------|---------|
| `string` | Single input | `"value"` |
| `integer` / `number` | Single input | `5` |
| `boolean` | Single choice | `true` / `false` |
| `array` | **MULTI-SELECT** | `["val1", "val2"]` |

**For each required parameter:**

**MANDATORY STOPPING POINT** - Do NOT proceed without user input for each parameter.

> "Parameter: `<name>` (required)
> Type: `<type>`
> Description: `<description>`"

If type is `array`, use multi-select and show available options.

**For optional parameters:** Still ask, but offer to skip.

### Step C-4: Build ANALYSIS_SPEC

> **Note:** The execution engine ignores `source_table` and `my_table` in `arguments` (they are always overwritten from `view_mappings` / `local_view_mappings`). Only pass actual query parameters in `arguments`.

```yaml
api_version: "2.0.0"
spec_type: "analysis"
name: "<descriptive_name>"
template: "<custom_template_name>"

template_configuration:
  view_mappings:
    source_tables:
      - "<TABLE_REFERENCE>"
  local_view_mappings:
    my_tables:
      - "<LOCAL_TABLE_REFERENCE>"
  arguments:
    <param1>: <value1>
    <param2>: <value2>
```

**Note:** Custom analysis templates do NOT have an `activation` section.

### Step C-5: Confirm and Execute

**MANDATORY CHECKPOINT** - Do NOT execute without explicit user approval.

Show complete spec and ask:
> "Run this analysis? (yes/no)"

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

### Step C-6: Present Results

Results vary by template. Display returned rows and offer visualization suggestions based on data shape.

**Analysis Complete.** Return to parent skill or await next user request.
