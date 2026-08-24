---
name: create
parent_skill: data-cleanrooms
description: "Create a new DCR collaboration or clean room - gather collaborators, configure analysis runners, build collaboration spec, and initialize. Triggers: create collaboration, create cleanroom, new collaboration, set up clean room, initiate collaboration, create dcr."
---

# Create Collaboration

Create a new DCR collaboration by building a collaboration specification and calling `{DB}.COLLABORATION.INITIALIZE`.

`INITIALIZE` is the DCR procedure that creates the collaboration and triggers the owner to auto-join. The full qualified name is `{DB}.COLLABORATION.INITIALIZE(COLLABORATION_SPEC)`. The name reflects what it does: setting up the collaboration infrastructure and automatically enrolling the owner as the first participant.

## When to Use

- User wants to create a new collaboration or clean room
- User wants to set up a data clean room (single or multi-party)
- User wants to initiate a collaboration with other parties or within the same account
- User says "create collaboration", "create cleanroom", "new collaboration", "set up clean room", "create dcr"

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Owner** | The current account (creator). ALWAYS automatic — cannot be changed |
| **Collaborator Alias** | Short name (max 25 chars) mapped to a Snowflake account identifier (e.g., `ACME: ORG1.ACCOUNT1`) |
| **Analysis Runner** | A collaborator alias that can run templates on allowed data offerings |
| **Data Provider** | A collaborator alias that provides data offerings to analysis runners |
| **Collaboration Spec** | YAML specification defining the collaboration structure |

## Collaboration Spec Rules

| Field | Constraint |
|-------|-----------|
| `api_version` | Required. String, semver format: `x.y.z` (e.g., `"2.0.0"`). Pattern: `^\d+\.\d+\.\d+$` |
| `spec_type` | Required. Must be exactly `"collaboration"` |
| `name` | Required. Max 75 chars, must start with letter or underscore: `^[A-Za-z_][A-Za-z0-9_]{0,74}$` |
| `version` | Optional. String, max 20 chars: `^[A-Za-z0-9_]{1,20}$` |
| `description` | Optional. Max 1000 chars |
| `collaborator_identifier_aliases` | Required. Object, min 1 entry. Keys are aliases, values are account identifiers |
| `collaborator_identifier_aliases` keys | Max 25 chars, must start with letter or `_`: `^[A-Za-z_][A-Za-z0-9_]{0,24}$` |
| `collaborator_identifier_aliases` values | `ORGNAME.ACCOUNT_NAME` format: `^[A-Za-z][A-Za-z0-9]*\.[A-Za-z][A-Za-z0-9_]*$` (max 255 chars) |
| `owner` | Optional. Must reference a key in `collaborator_identifier_aliases`. Pattern: `^[A-Za-z_][A-Za-z0-9_]{0,254}$` |
| `analysis_runners` | Required. Object, min 1 entry. Keys must be defined collaborator aliases |
| `analysis_runners.<runner>.data_providers` | Required. Object, min 1 entry. Keys must be defined collaborator aliases |
| `analysis_runners.<runner>.data_providers.<alias>.data_offerings` | Required per listed provider. Array of objects, each with `id` |
| `analysis_runners.<runner>.data_providers.<alias>.data_offerings[].id` | Required. Max 255 chars. Valid Snowflake identifier: `^[A-Za-z_][A-Za-z0-9_]{0,254}$` |
| `analysis_runners.<runner>.templates` | Optional. Array of objects with `id`. Can be empty (`[]`) or omitted if no templates |
| `analysis_runners.<runner>.templates[].id` | Required per entry. Max 255 chars. Valid Snowflake identifier: `^[A-Za-z_][A-Za-z0-9_]{0,254}$` |
| `analysis_runners.<runner>.activation_destinations` | Optional. Object with `snowflake_collaborators` and/or `external` arrays |
| `analysis_runners.<runner>.activation_destinations.snowflake_collaborators[]` | Must be a defined collaborator alias: `^[A-Za-z_][A-Za-z0-9_]{0,254}$` |
| `analysis_runners.<runner>.activation_destinations.external[]` | Valid Snowflake identifier: `^[A-Za-z_][A-Za-z0-9_]{0,254}$`. **Not currently supported** — accepted in schema but non-functional |
| No extra fields | `additionalProperties: false` at every level — do NOT add fields not listed above |

### Analysis Runner Fields

| Field | Required | When to Include |
|-------|----------|----------------|
| `data_providers` | Yes | Always — list all intended data providers. Offering IDs can be empty (`[]`) if not yet known |
| `templates` | No | Only if the user wants to assign templates now. Can be added later |
| `activation_destinations` | No | Only if the runner will use activation templates (e.g., `standard_audience_overlap_activation`) |

### Alias Reference Rules

All alias references in the spec must point to keys defined in `collaborator_identifier_aliases`:

| Field | Must Reference |
|-------|---------------|
| `owner` | A defined alias key (the current account's alias) |
| `analysis_runners` keys | A defined alias key |
| `data_providers` keys | A defined alias key |
| `activation_destinations.snowflake_collaborators[]` | A defined alias key |

### Activation Destination Types

| Type | Status | Description |
|------|--------|-------------|
| `snowflake_collaborators` | Supported | Collaborator aliases that will receive activated segments |
| `external` | **Not supported** | Accepted in schema but non-functional. Warn user if requested |

---

## Workflow

### Step 1: Get Current Account Identifier

**Option A: Standard SQL (recommended)**
```sql
SELECT CURRENT_ORGANIZATION_NAME(), CURRENT_ACCOUNT_NAME();
```

**Option B: DCR Procedure (for agents)**
```sql
CALL {DB}.AGENTS.DCR$GET_CURRENT_ACCOUNT_IDENTIFIER();
```

Returns: Account identifier in `ORGNAME.ACCOUNT_NAME` format. Store the result — this is the owner's account identifier.

### Step 2: Gather Basic Information

Ask user for:
- **Collaboration name** (valid Snowflake identifier, max 75 characters)
- **Description** (optional, max 1000 characters)

### Step 3: Identify Collaborators

**3a. Ask for the owner's alias first:**

> "What alias would you like for your own account (the owner)?"

This is the short name for the current account. It becomes the `owner` field in the spec.
Example: `OWNER_ACCT`, `MY_COMPANY`, `ACME`

**3b. Ask for other collaborators:**

> "What other parties will participate? For each, provide an alias and their Snowflake account identifier (in `ORGNAME.ACCOUNT_NAME` format)."

**Validate collaborator identifiers:** All account identifiers (including the owner's from Step 1) must be in `ORGNAME.ACCOUNT_NAME` format (e.g., `MYORG.MY_ACCOUNT`). If a user provides an identifier in a different format (e.g., `XYZ12345.us-east-2.aws`, a URL, or a locator), inform them it must be `ORGNAME.ACCOUNT_NAME` and ask them to correct it before proceeding.

### Step 4: Get Current Account's Available Resources

Run both queries and **present the results to the user** so they can see what is available:

```sql
CALL {DB}.REGISTRY.VIEW_REGISTERED_TEMPLATES();
CALL {DB}.REGISTRY.VIEW_REGISTERED_DATA_OFFERINGS();
```

Show the user the list of registered templates and data offerings from these results. Do NOT suggest or fabricate template or data offering names that are not returned by these queries.

**Note:** These resources are ONLY from the current account (owner). Other collaborators' resources are not visible here — include their IDs as provided by the user.

### Step 5: Configure Analysis Runners and Data Providers

Ask both questions explicitly — do not assume roles:

1. **"Which collaborator(s) will run analyses (analysis runners)?"** — each runner must be a defined collaborator alias.
2. **"Which collaborator(s) will provide data, and to which analysis runner(s)?"** — each provider must be a defined collaborator alias.

For each analysis runner, collect:

**Data Providers and Offerings (required — at least 1 provider):**

Ask: **"What are the data offering IDs for each provider?"**

- All intended data providers **must be listed upfront** in the spec, even if their specific data offering IDs are not yet known
- The **owner's** registered data offerings are available from the registry — but registration is not required upfront. Offerings can be registered before or after joining
- For **other collaborators**, include their offering IDs if provided. If offering IDs are not known, still list the collaborator as a data provider with `data_offerings: []` — the offerings can be added after they join

**Templates (optional):**

Ask: **"Would you like to assign any templates to this runner? Here are the registered templates available:"** — then list the templates returned by `VIEW_REGISTERED_TEMPLATES()` in Step 4.

- Templates are **optional** — if the user doesn't want to assign templates now, skip this
- Only present templates that were returned by `VIEW_REGISTERED_TEMPLATES()` — do NOT suggest template names that are not in the registry
- Only the owner's registered templates are available in the create flow

### Step 6: Configure Activation Destinations (Optional)

Activation allows analysis runners to export matched segments to other Snowflake collaborators. If the collaboration will use activation templates (e.g., `standard_audience_overlap_activation`), activation destinations **must** be configured during creation.

Ask the user:
> "Will any analysis runner need to activate (export) segments to other collaborators?"

If **yes**, for each analysis runner that needs activation, collect the `snowflake_collaborators` entries (must reference defined collaborator aliases). If no activation is needed, skip this step entirely.

**Example:**
```yaml
activation_destinations:
  snowflake_collaborators:
    - PARTNER_A          # Must be a defined collaborator alias
  # external:            # Valid in schema but NOT currently supported
  #   - EXTERNAL_PLATFORM
```

### Step 7: Build Collaboration Spec

```yaml
api_version: "2.0.0"
spec_type: collaboration
name: <collaboration_name>
version: <optional_version>            # optional, max 20 chars
description: <optional_description>    # optional, max 1000 chars

collaborator_identifier_aliases:
  <owner_alias>: <current_account_identifier>    # owner's account
  <collaborator_alias>: <account_identifier>     # invited party

owner: <owner_alias>

analysis_runners:
  <runner_alias>:
    data_providers:                   # required (at least 1 provider)
      <provider_alias>:              # list all intended data providers
        data_offerings:
          - id: <data_offering_id>
    templates:                        # optional — omit if none selected
      - id: <template_id>
    activation_destinations:          # optional — if activation needed
      snowflake_collaborators:
        - <collaborator_alias>
      # external:                     # valid in schema but NOT currently supported
      #   - <external_destination>
```

### Step 8: Validate Spec Before Submission

Validate the spec against the Collaboration Spec Rules above. Key checks:
- All alias references resolve to keys in `collaborator_identifier_aliases` (see Alias Reference Rules)
- Template IDs (if included) are from the owner's registered templates
- All intended data providers are listed, even if their offering IDs are not yet known
- Data offering IDs are accepted as provided — registration can happen before or after joining
- No extra fields at any level

If validation fails, explain the issue and fix the spec.

### Step 9: Show Preview and Confirm

⚠️ **MANDATORY STOPPING POINT**

Display the complete collaboration spec YAML in a code block.

Ask: **"Please review the collaboration spec. Would you like to proceed with creating this collaboration? (Yes/No/Modify)"**

- If user says **Modify**: Make changes and show the updated spec again
- If user says **No**: Cancel the operation

**NEVER proceed to INITIALIZE without explicit user approval.**

### Step 10: Create Collaboration

```sql
CALL {DB}.COLLABORATION.INITIALIZE($$
<collaboration_spec_yaml>
$$);
```

- If succeeds: "Collaboration creation triggered. Checking status..."
- If fails: Extract error, explain issue, offer to fix spec and retry

### Step 11: Check Creation Status

```sql
CALL {DB}.COLLABORATION.GET_STATUS('<collaboration_name>');
```

| Status | Action |
|--------|--------|
| `CREATING` | "Creation in progress. Check again in a moment." Do NOT attempt JOIN or any other operation while in this state. If it stays in this state for an extended period, advise the user to contact Snowflake support. |
| `CREATED` | "Success! Invitations sent to collaborators." |
| `CREATE_FAILED` | Show error from DETAILS field, offer to retry with fixed spec. If the error is unclear or persistent, advise the user to contact Snowflake support. |

### Step 12: Post-Creation Guidance

After successful creation:
- **Owner may need to join the collaboration**. If the owner is not yet joined, use the review-join workflow (load `../review-join/SKILL.md`)
- Other collaborators will receive invitations and can review/join from their accounts
- Suggest: "Once all parties have joined, you can run analyses and activations."
- Remind: Can check status anytime using `GET_STATUS`

---

## Required Privileges

If operations fail with "Insufficient privileges", see the parent data-cleanrooms SKILL.md "Required Privileges" section for how to grant privileges using `{DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE` or `{DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE`.

| Procedure | Privilege | Scope |
|-----------|-----------|-------|
| `INITIALIZE(spec)` | `CREATE COLLABORATION` | Account |
| `GET_STATUS(name)` | `GET STATUS` | Collaboration |
| `VIEW_REGISTERED_TEMPLATES()` | `VIEW REGISTERED TEMPLATES` | Account |
| `VIEW_REGISTERED_DATA_OFFERINGS()` | `VIEW REGISTERED DATA OFFERINGS` | Account |

---

## Stopping Points

- Before INITIALIZE: Show complete spec and get explicit user confirmation

**Resume rule:** Upon user approval, proceed directly without re-asking.

## Output

| Operation | Output |
|-----------|--------|
| Create Collaboration | Collaboration spec preview → user approval → initialization confirmation → status check |
