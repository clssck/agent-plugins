---
name: register
parent_skill: data-cleanrooms
description: "Register data offerings and templates for use in DCR collaborations. Triggers: register data offering, register template, share table."
---

# Register Data Offerings and Templates

Register data offerings (tables/views) and templates (analysis queries) for use in DCR collaborations.

## When to Use

- User wants to share their data in a collaboration (register data offering)
- User wants to define analysis logic for collaborations (register template)
- User wants to make tables/views available for clean room analysis

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Data Offering** | A group of tables/views that can be shared with analysis runners |
| **Template** | A JinjaSQL query template that defines what analysis can be performed |
| **Registry** | Account-level storage for registered offerings and templates |

## Workflow A: Register Data Offering

### Step 1: Gather Information

If the user already has a complete data offering spec, validate it against the rules below and go directly to Step 3 (confirm).

Otherwise, ask:
- Which tables/views to include?
- What columns should be available?
- Any columns to exclude (private data)?
- What analysis types should be allowed? (`template_only` = only pre-defined templates can query this data, `template_and_freeform_sql` = templates AND ad-hoc SQL queries)

### Step 2: Build Data Offering Specification

```yaml
api_version: 2.0.0
spec_type: data_offering
name: <offering_name>
version: <version_string>
description: <optional description>

datasets:
  - alias: <dataset_alias>
    data_object_fqn: <DATABASE>.<SCHEMA>.<TABLE_OR_VIEW>
    allowed_analyses: template_only  # or template_and_freeform_sql
    object_class: custom  # or ads_log
    schema_and_template_policies:
      <COLUMN_NAME>:
        category: join_standard
        column_type: hashed_email_sha256
        activation_allowed: true
      <COLUMN_NAME>:
        category: passthrough
```

### Data Offering Spec Rules

| Field | Constraint |
|-------|-----------|
| `api_version` | Required. String, semver format: `x.y.z` (e.g., `"2.0.0"`) |
| `spec_type` | Required. Must be exactly `data_offering` |
| `name` | Required. Max 75 chars, must start with letter or underscore: `^[A-Za-z_][A-Za-z0-9_]{0,74}$` |
| `version` | Required. String, max 20 chars: `^[A-Za-z0-9_]{1,20}$` |
| `description` | Optional. Max 1000 chars |
| `datasets` | Required. At least 1 dataset |
| `datasets[].alias` | Required. Max 75 chars, must start with letter or underscore: `^[A-Za-z_][A-Za-z0-9_]{0,74}$` |
| `datasets[].data_object_fqn` | Required. Fully qualified: `DATABASE.SCHEMA.TABLE` (max 773 chars) |
| `datasets[].allowed_analyses` | Required. `template_only` or `template_and_freeform_sql` |
| `datasets[].object_class` | Optional. `custom` or `ads_log` |
| `datasets[].schema_and_template_policies` | Required. At least 1 column policy (keys are column names, max 255 chars each) |
| `datasets[].require_freeform_sql_policy` | Optional. Boolean. Only relevant when `allowed_analyses: template_and_freeform_sql`. Defaults to `true` (policies required). Set to `false` to allow freeform SQL without policies. |
| No extra fields | `additionalProperties: false` — do NOT add fields not listed above |

### allowed_analyses Options

| Value | `freeform_sql_policies` | `require_freeform_sql_policy` | Behavior |
|-------|------------------------|-------------------------------|----------|
| `template_only` | N/A | N/A | Only pre-defined templates can query this data |
| `template_and_freeform_sql` | Provided | `true` (default) | Templates AND freeform SQL; policies enforced |
| `template_and_freeform_sql` | Not provided | `false` | Templates AND freeform SQL; no policy enforcement |
| `template_and_freeform_sql` | Not provided | `true` (default) | **Invalid** — policies required but not provided |

### Column Categories

| Category | Description | Requires column_type? |
|----------|-------------|----------------------|
| `join_standard` | Standard join columns (hashed email, phone, device ID) | Yes |
| `join_custom` | Custom join columns (user-defined identifiers) | No |
| `passthrough` | Columns passed through to results | No |
| `timestamp` | Timestamp columns | No |
| `event_type` | Event type columns | No |

### Column Types (for join_standard)

`email`, `hashed_email_sha256`, `hashed_email_b64_encoded`, `phone`, `hashed_phone_sha256`, `hashed_phone_b64_encoded`, `device_id`, `hashed_device_id_sha256`, `hashed_device_b64_encoded`, `ip_address`, `hashed_ip_address_sha256`, `hashed_ip_address_b64_encoded`, `first_name`, `hashed_first_name_sha256`, `hashed_first_name_b64_encoded`

### Step 3: Confirm with User

**MANDATORY STOPPING POINT**: Display the full data offering specification to the user.

Ask: "Does this specification look correct? (Yes/No/Modify)"

NEVER proceed to Step 4 without explicit user approval.

### Step 4: Register Data Offering

Disable secondary roles before REGISTER_DATA_OFFERING and restore after

```sql
USE SECONDARY ROLES NONE;
CALL {DB}.REGISTRY.REGISTER_DATA_OFFERING($$
api_version: 2.0.0
spec_type: data_offering
name: my_customers_v1
version: "2024_01"
description: Customer data for marketing analysis

datasets:
  - alias: customers
    data_object_fqn: MY_DB.ANALYTICS.CUSTOMERS
    allowed_analyses: template_only
    object_class: custom
    schema_and_template_policies:
      HASHED_EMAIL:
        category: join_standard
        column_type: hashed_email_sha256
      REGION:
        category: passthrough
      EVENT_DATE:
        category: timestamp
$$);
USE SECONDARY ROLES ALL;
```

**If REGISTER_DATA_OFFERING is canceled unexpectedly**: Inform the user: "The register data offering operation was canceled. Please run `USE SECONDARY ROLES ALL` (or start a new session) to restore your secondary roles."

### Freeform SQL Examples

#### With Policies (default: `require_freeform_sql_policy: true`)

When `allowed_analyses: template_and_freeform_sql` and `require_freeform_sql_policy` is `true` (default), you **must** provide `freeform_sql_policies` with **at least one** sub-policy. No individual sub-policy is required — include whichever ones exist for the dataset:

| Sub-policy | Type | Description |
|------------|------|-------------|
| `join_policy` | Object (single) | Restricts which columns can be used for joins. Fields: `name` (required), `columns` (list of column names) |
| `aggregation_policy` | Object (single) | Enforces aggregation rules (e.g., minimum group size). Fields: `name` (required), `entity_keys` (list of column names) |
| `projection_policies` | Array (multiple) | Controls which columns can appear in results. Each entry: `name` (required), `columns` (list of column names) |
| `masking_policies` | Array (multiple) | Masks column values in query results. Each entry: `name` (required), `columns` (list of column names) |
| `row_access_policy` | Object (single) | Restricts which rows are visible to queries. Fields: `name` (required), `columns` (list of column names) |

**Example with multiple policies:**

```yaml
datasets:
  - alias: customers
    data_object_fqn: MY_DB.ANALYTICS.CUSTOMERS
    allowed_analyses: template_and_freeform_sql
    object_class: custom
    schema_and_template_policies:
      HASHED_EMAIL:
        category: join_standard
        column_type: hashed_email_sha256
    freeform_sql_policies:
      join_policy:
        name: MY_JOIN_POLICY
        columns: ["HASHED_EMAIL"]
      aggregation_policy:
        name: MY_AGG_POLICY
        entity_keys: ["CUSTOMER_ID"]
      projection_policies:
        - name: MY_PROJ_POLICY
          columns: ["REGION", "PURCHASE_COUNT"]
      masking_policies:
        - name: MY_MASKING_POLICY
          columns: ["SSN", "PHONE_NUMBER"]
      row_access_policy:
        name: MY_ROW_ACCESS_POLICY
        columns: ["REGION"]
```

**Example with only aggregation and projection (no join policy):**

```yaml
    freeform_sql_policies:
      aggregation_policy:
        name: EMAIL_AGG_POLICY
        entity_keys: ["HASHED_EMAIL"]
      projection_policies:
        - name: EMAIL_PROJ_POLICY
          columns: ["REGION", "PURCHASE_COUNT"]
```

#### Without Policies (`require_freeform_sql_policy: false`)

To allow freeform SQL **without** requiring policies, set `require_freeform_sql_policy: false`. No `freeform_sql_policies` block is needed:

```yaml
datasets:
  - alias: events
    data_object_fqn: MY_DB.ANALYTICS.EVENTS
    allowed_analyses: template_and_freeform_sql
    object_class: custom
    require_freeform_sql_policy: false
    schema_and_template_policies:
      USER_ID:
        category: join_custom
      EVENT_TYPE:
        category: event_type
      EVENT_TIME:
        category: timestamp
```

### Step 5: Verify Registration

```sql
CALL {DB}.REGISTRY.VIEW_REGISTERED_DATA_OFFERINGS();
```

---

## Workflow B: Register Template

### Step 1: Receive Template Specification

If the user already has a complete template spec, validate it against the rules below and go directly to Step 3 (confirm). If they provide raw SQL, wrap it in the YAML format and proceed to Step 3.

Otherwise, ask the user to describe their use case so you can help build one.

### Step 2: Build Template Specification

```yaml
api_version: 2.0.0
spec_type: template
name: <template_name>
version: <version_string>
type: sql_analysis  # or sql_activation
description: <optional description>
methodology: <optional methodology>

parameters:
  - name: <param_name>
    description: <param_description>
    required: true  # or false
    default: <default_value>  # optional
    type: string  # string | integer | number | boolean | array | object

template: |
  <JinjaSQL template content>
```

### Template Spec Rules

| Field | Constraint |
|-------|-----------|
| `api_version` | Required. String, semver format: `x.y.z` (e.g., `"2.0.0"`) |
| `spec_type` | Required. Must be exactly `template` |
| `name` | Required. Max 75 chars, must start with letter or underscore: `^[A-Za-z_][A-Za-z0-9_]{0,74}$` |
| `version` | Required. String, max 20 chars: `^[A-Za-z0-9_]{1,20}$` |
| `type` | Required. `sql_analysis` or `sql_activation` |
| `template` | Required. JinjaSQL query string (non-empty) |
| `parameters` | Optional. List of parameter objects (each with `name` required, pattern `^[A-Za-z_][A-Za-z0-9_]{0,254}$`) |
| `parameters[].description` | Optional. Max 500 chars |
| `parameters[].type` | Optional. One of: `string`, `integer`, `number`, `boolean`, `array`, `object` |
| `code_specs` | Optional. List of code spec IDs (format: `<name>_<version>`) |
| `description` | Optional. Max 1000 chars |
| `methodology` | Optional. Max 1000 chars |
| No extra fields | `additionalProperties: false` — do NOT add fields not listed above |

### Template Types

| Type | Purpose |
|------|---------|
| `sql_analysis` | Standard SQL analysis - returns query results |
| `sql_activation` | Activation template - sends data to external destinations |

### Template Variables (optional)

Templates **do not have to** use table variables. A template can use only parameters, only `source_table`, only `my_table`, or any combination. Use table variables only when the template needs to reference collaboration data.

**Note:** `source_table` and `my_table` are **built-in Jinja variables** populated automatically via `view_mappings` when the template is run. They don't need to be in `parameters`, but it's not an error if they are. Typically only user-provided arguments (like `join_column`, `threshold`, `segment_name` etc.) go in `parameters`.

| Variable | Description |
|----------|-------------|
| `{{ source_table[0] }}` | Resolves to the fully qualified dataset reference (collaborator alias + offering ID + dataset alias) at index 0 in `view_mappings` |
| `{{ source_table[1] }}` | Resolves to the fully qualified dataset reference at index 1 in `view_mappings` |
| `{{ my_table[0] }}` | Resolves to the locally linked dataset reference at index 0 in `view_mappings` |

The index corresponds to the order data offerings are passed in `view_mappings` when the template is run.

### Table Alias Convention

When a template uses table variables, alias them for readability:

| Alias | Variable | Description |
|-------|----------|-------------|
| `p1` | `source_table[0]` | Shared dataset reference (index 0) |
| `p2` | `source_table[1]` | Shared dataset reference (index 1) |
| `c1` | `my_table[0]` | Locally linked dataset reference (index 0) |

**`source_table` (p1, p2, ...):** Data offerings that were included in the collaboration spec or added via `link_data_offering`. These are visible to all participants and can originate from any collaborator's account. Locally linked offerings (via `link_local_data_offering`) do **not** appear as `source_table`.

**`my_table` (c1):** Datasets linked locally via `link_local_data_offering`. These are **only visible to the account that linked them** — other collaborators cannot see or access these datasets.

Use these aliases consistently when referencing tables (e.g., `p1.HASHED_EMAIL = c1.HASHED_EMAIL`).

### Parameter Types

`string`, `integer`, `number`, `boolean`, `array`, `object`

### Step 3: Confirm with User

**MANDATORY STOPPING POINT**: Display the full template specification to the user.

Ask: "Does this specification look correct? (Yes/No/Modify)"

NEVER proceed to Step 4 without explicit user approval.

### Step 4: Register Template

Disable secondary roles before REGISTER_TEMPLATE and restore after

```sql
USE SECONDARY ROLES NONE;
CALL {DB}.REGISTRY.REGISTER_TEMPLATE($$
api_version: 2.0.0
spec_type: template
name: my_overlap_analysis_v1
version: "2024_01"
type: sql_analysis
description: Count matching records between datasets
methodology: Joins tables on specified columns and counts matches

parameters:
  - name: join_column
    description: Column to join on
    required: true
    type: string

template: |
  SELECT 
    COUNT(*) as match_count
  FROM identifier({{ source_table[0] }}) p1
  JOIN identifier({{ my_table[0] }}) c1
    ON p1.{{ join_column }} = c1.{{ join_column }}
$$);
USE SECONDARY ROLES ALL;
```

**If REGISTER_TEMPLATE is canceled unexpectedly**: Inform the user: "The register template operation was canceled. Please run `USE SECONDARY ROLES ALL` (or start a new session) to restore your secondary roles."

### Activation Template Example

```sql
CALL {DB}.REGISTRY.REGISTER_TEMPLATE($$
api_version: 2.0.0
spec_type: template
name: my_activation_template_v1
version: "2024_01"
type: sql_activation
description: Export matched audience segments

parameters:
  - name: segment_name
    description: Name for the segment
    required: true
    type: string

template: |
  SELECT 
    HASHED_EMAIL,
    '{{ segment_name }}' as segment
  FROM identifier({{ source_table[0] }}) p1
  JOIN identifier({{ my_table[0] }}) c1
    ON p1.HASHED_EMAIL = c1.HASHED_EMAIL
$$);
```

### Step 5: Verify Registration

```sql
CALL {DB}.REGISTRY.VIEW_REGISTERED_TEMPLATES();
```

### Next Step: Add Template to a Collaboration

Registering a template makes it available in the registry, but it must also be added to a specific collaboration before it can be used. Use the `manage-templates` skill to call `COLLABORATION.ADD_TEMPLATE_REQUEST(collab_name, template_id, share_with)`.


## Required Privileges

If operations fail with "Insufficient privileges", see the parent data-cleanrooms SKILL.md "Required Privileges" section for how to grant privileges using `{DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE` or `{DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE`.

| Procedure | Privilege | Scope |
|-----------|-----------|-------|
| `REGISTER_DATA_OFFERING(spec)` | `REGISTER DATA OFFERING` | Account |
| `REGISTER_TEMPLATE(spec)` | `REGISTER TEMPLATE` | Account |
| `VIEW_REGISTERED_DATA_OFFERINGS()` | `VIEW REGISTERED DATA OFFERINGS` | Account |
| `VIEW_REGISTERED_TEMPLATES()` | `VIEW REGISTERED TEMPLATES` | Account |

**Example: Grant REGISTER DATA OFFERING privilege**

```sql
-- Use ACCOUNTADMIN role
USE ROLE ACCOUNTADMIN;

-- Grant privilege to a user role
CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE(
    'REGISTER DATA OFFERING',
    '<user_role>'
);
```

**Example: Grant REGISTER TEMPLATE privilege**

```sql
-- Use ACCOUNTADMIN role
USE ROLE ACCOUNTADMIN;

-- Grant privilege to a user role
CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE(
    'REGISTER TEMPLATE',
    '<user_role>'
);
```

---

## Stopping Points

- Before Step 4 in Workflow A: Confirm data offering specification with user
- Before Step 4 in Workflow B: Confirm template specification with user
**Resume rule:** Upon user approval, proceed directly without re-asking.

## Output

| Operation | Output |
|-----------|--------|
| Register Data Offering | Registration confirmation + verification via VIEW_REGISTERED_DATA_OFFERINGS |
| Register Template | Registration confirmation + verification via VIEW_REGISTERED_TEMPLATES |

## Important Notes

- Data offerings and templates must be registered BEFORE creating a collaboration
- Registered items are not visible to others until you JOIN the collaboration
- Use `| sqlsafe` filter for SQL identifiers in templates
- If you don't have OWNERSHIP on the data, you may need to grant REFERENCE_USAGE

### Handling "Already Exists" Errors

If a registration fails because a data offering or template with the same name already exists:

1. Inform the user that the item is already registered
2. **Primary option**: register a **new version** with a different `version` string (e.g., `"2024_02"` instead of `"2024_01"`)
3. **Alternative**: use the read tool to load `../unregister/SKILL.md` and follow the unregister workflow, then re-register.
4. If the user wants a completely different spec, suggest using a new `name` instead

Do NOT propose `DELETE`, `DROP`, or direct table manipulation — these do not exist as valid APIs.
