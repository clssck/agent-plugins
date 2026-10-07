---
name: create-template
parent_skill: data-cleanrooms
description: "Create DCR SQL Jinja template specs for the Collaboration API.
  Triggers: create template, write template, build template, template spec,
  audience overlap, activation template, incrementality, attribution,
  convert PnC template, migrate template, template for clean room,
  measure, query, analyze, compare audiences, match, segment, export."
allowed-tools:
  - snowflake_sql_execute
  - ask_user_question
---

# Create Template and Logic

Generate valid SQL Jinja **template specs** for the Snowflake DCR **Collaboration API only**.

## When to Use

User wants to:
- Create a new SQL Jinja template spec for a clean room collaboration
- Build an audience overlap, activation, reach, incrementality, attribution, or crosswalk template
- Measure, query, or analyze data across organizations in a clean room
- Convert/migrate a Provider-and-Consumer (PnC) template to Collab API format
- Understand template_spec structure or fix a rejected template

## Provider-and-Consumer Guardrail

This skill creates and converts Collaboration API templates.

**If the user wants to call PnC write APIs** (`add_custom_sql_template()`, `provider.add_*`, `consumer.add_*`): these are legacy APIs. If they want a new template, continue to Step 1.

**If the user wants to migrate a single PnC template** (reuse SQL logic in a new Collab API collaboration): route to Step 4C.

**If the user wants to migrate their entire PnC cleanroom** (data offerings, roles, and templates together): recommend the [DCR Migration Tool](https://docs.snowflake.com/en/user-guide/cleanrooms/migration-tool) — a dedicated Clean Room Migration skill is on the roadmap but not yet available. If the user insists on proceeding with the agent anyway, you can try to help, but warn them that the agent does not have full context over the entire cleanroom structure and the result will likely be incomplete — they proceed at their own risk.

> **Note on terminology:** "provider" and "consumer" are general terms and also legacy PnC concepts. In PnC SQL being converted (Step 4C), `provider.TABLE` and `consumer.TABLE` are table aliases — they do NOT map directly to Collab API `data_provider`/`analysis_runner` roles. This distinction matters when assigning `source_table` vs `my_table` during conversion.

## Prerequisites

The parent skill (`data-cleanrooms`) passes `{DB}` from database discovery.
If not available, run:

```sql
SHOW DATABASES LIKE 'SAMOOHA_BY_SNOWFLAKE_LOCAL_DB%';
```

Set `{DB}` to the result. All procedure calls use `{DB}` prefix.

## Common Template Catalog

Present this catalog to the user so they can confirm the outcome they want.

| # | Use Case | Outcome | v1 | Type |
|---|----------|---------|----|------|
| 1 | **Audience Overlap** | Measure how many users exist in both datasets, expressed as a count or percentage. E.g., "80% of your customers also appear in the publisher's dataset." | Full | sql_analysis |
| 2 | **Audience Activation** | Export a list of matched user identifiers to a collaborator for targeting — e.g., deliver a segment of overlapping users to an ad platform for campaign delivery. | Full | sql_activation |
| 3 | Reach & Frequency | Count how many unique users saw an ad and how many times on average. E.g., "Campaign X reached 50K unique users with an average frequency of 3.2 impressions." | Outline | sql_analysis |
| 4 | Incrementality / Lift | Compare conversion rates between exposed (test) and unexposed (control) groups to measure the incremental impact of a campaign. | Outline | sql_analysis |
| 5 | Multi-Touch Attribution | Assign credit for conversions across multiple ad touchpoints (e.g., display, social, search) to understand which channels drive the most value. | Outline | sql_analysis |
| 6 | Lookalike / Propensity | Build an ML model to find publisher users who look most like the advertiser's best customers. **Requires code spec** — produce a handoff brief (plain markdown, no YAML). | -> handoff brief | ML |

For #1-#2, load the full reference pattern. For #3-#5, load outline. For #6, produce a **handoff brief** (see Code Spec Handoff section) — no template_spec YAML.

**If the user's use case doesn't match any catalog entry:**
> I don't have a pre-built pattern for that use case yet, but I can help you build a custom template. Can you describe the business problem you're trying to solve — what outcome are you looking for? For example: "I want to know how many of my customers also appear in my partner's dataset" or "I want to measure whether my ad campaign drove more purchases."

If the user describes a clear outcome, build a custom template using the appropriate reference patterns as a starting point.

**Freeform SQL use:** If the user wants to write arbitrary SQL against clean room data without a template structure, recommend they use `template_and_freeform_sql` on their data offering's `allowed_analyses` field instead. Templates are best for reusable, parameterized queries; freeform SQL is better for one-off exploration. If they want freeform SQL access, route them to the **Register Data Offering** skill to set up `allowed_analyses: template_and_freeform_sql` on their offering.

### Confirm Outcome

Before proceeding, confirm the user's desired outcome in plain language:
> Based on your request, it sounds like you want to **[outcome description]**. Is that right?

Accept and proceed, or adjust based on their response.

## Workflow

### Step 1: Detect Context and Gather Information

Check what context the user provides:

**Mode A — With clean room:**
User references a collaboration. Before calling any APIs, check if the following context is already present in the prompt (e.g. passed by CoCo UI integration or prior conversation):
- Collaboration name (`{COLLAB_NAME}`)
- Data offering schemas (column names, categories, join columns)
- Existing templates

If all of this context is already available, skip the API calls below and proceed directly to Step 2. Only call these APIs for information that is genuinely missing:
```sql
CALL {DB}.COLLABORATION.VIEW_DATA_OFFERINGS('{COLLAB_NAME}');
CALL {DB}.COLLABORATION.VIEW_TEMPLATES('{COLLAB_NAME}');
CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS();
```
Extract:
- Data offerings: table schemas, column categories, join columns
- Existing templates: what's already registered (avoid duplicates)
- Collaborators: who the other participants are
- Configuration: single-account vs multi-account, activation destinations

**Single-account detection:** If collaboration shows all aliases map to the same account:
> This is a single-account clean room (common for testing/onboarding). The template will work the same way — `source_table` and `my_table` just happen to be in the same account. In production multi-party scenarios, these would reference different organizations' data.

**If any call fails:**
- Permission error → user needs at least VIEW privilege on the collaboration
- Collaboration not found → confirm the collaboration name with the user
- Empty results → collaboration may have no offerings yet. Ask the user to describe their table schemas (column names, which are join keys, which are passthrough) and proceed with that user-provided context, or route them to the create skill (`../../data-cleanrooms/create/SKILL.md`) to set up their collaboration first.

**No collaboration referenced:**
If the user does not mention a specific collaboration name and indicates they want a standalone/portable template (e.g., "I'm not in a clean room yet," "I want to create a template for later"), skip all API calls. Build a fully parameterized template using `source_table[0]`/`my_table[0]` as generic table references wrapped in `identifier()`. The template will be portable — register it via `{DB}.REGISTRY.REGISTER_TEMPLATE()` and add to any collaboration later via `ADD_TEMPLATE_REQUEST`. Proceed directly to Step 2.

> **Always produce a complete template_spec in this mode.** Designing the template first — before the collaboration and data offerings are set up — is a valid and common workflow. It lets users work backwards: write the query they want, then figure out what columns and offerings they need to support it. If the user describes the business outcome they want, that is enough to produce a spec. Never withhold a spec because there is no active collaboration.

### Step 2: Detect Intent

Infer which flow from context or ask:

- **Flow A** — "create from data offerings" -> Step 4A
- **Flow B** — "audience overlap / activation / measure / query / ..." -> Step 4B
- **Flow C** — "convert Provider-and-Consumer template" or PnC syntax detected -> Step 4C (migration tool referral)

### Step 3: Naming & Description

Auto-generate a name and description based on the detected use case. Assign the name directly — asking the user adds an unnecessary round-trip and typically yields generic names like `test1`.

**Naming rules:**
- Max 75 chars, pattern: `^[A-Za-z_][A-Za-z0-9_]{0,74}$`
- Convention: `{usecase}_{variant}_{version}` e.g. `audience_overlap_email_v1`
- **Every template spec in your output requires a globally unique `name`.** Differentiate by use case, variant, or context — e.g. `audience_overlap_email_v1`, `single_account_overlap_v1`, `three_party_overlap_email_v1`.

**Description rules:**
- Max 1000 chars, explain what the template measures/produces

**Version rules:**
- Max 20 chars, pattern: `^[A-Za-z0-9_]{1,20}$`
- Convention: `YYYY_MM` or `v1`, `v2`

**If user provides their own poor name** (e.g. `test1`), push back once:
> `test1` won't help collaborators understand what this template does. The person running this template is usually different from the person who created it. How about `audience_overlap_email_v1` instead?

Accept if user insists after one pushback.

Load -> `references/naming-conventions.md`

### Step 4A: Create from Data Offerings

**Narrate each decision.**

1. List available offerings and their column categories
2. Identify join columns (join_standard / join_custom)
3. Identify passthrough, timestamp, event_type columns
4. Select template type (sql_analysis or sql_activation)
5. Determine the correct table variable for each party — **this is the most common template bug**:
   - **`LINK_DATA_OFFERING`** (shared external offering) → `source_table[N]`. Both parties providing offerings use `source_table[0]` and `source_table[1]`. Reserve `my_table` for `LINK_LOCAL_DATA_OFFERING` only.
   - **`LINK_LOCAL_DATA_OFFERING`** (runner's own private data, not visible to other party) → `my_table[0]`. Only use `my_table` when a party has explicitly linked local/private data.
   - Check `VIEW_DATA_OFFERINGS` output: if you see `LINK_DATA_OFFERING` for both sides, use `source_table[0]`/`source_table[1]`. If you see `LINK_LOCAL_DATA_OFFERING` for the runner's data, use `my_table[0]` for that side.
6. Build the SQL body using `identifier()` wrappers. **The canonical table reference syntax is `identifier({{ source_table[0] }})` and `identifier({{ source_table[1] }})` (or `identifier({{ my_table[0] }})` for local data). There is no `data_offering()` function in the DCR Jinja engine — do not use it.** **Apply policy filters and aliases — this step is mandatory when offerings declare column categories:**
   - **Table aliases:** `source_table[0]` → alias `p1`, `source_table[1]` → alias `p2`, `my_table[0]` → alias `c1`. Always use these exact lowercase aliases — policy filter enforcement depends on them.
   - **Join columns** (`join_standard` / `join_custom`): apply `| join_policy` → `{{ col | join_policy }}`
   - **Passthrough / analysis columns**: apply `| column_policy` → `{{ col | column_policy }}`
   - **Activation column** (in `sql_activation` templates): apply `| activation_policy` → `{{ col | activation_policy }}`
   - See `references/jinja-filters.md` for full syntax and the known limitation with alias-prefixed columns.

Narration example:
> I found `HASHED_EMAIL` marked as `join_standard` in both offerings — I'll use this as the primary join key. I also see `HASHED_PHONE` as a secondary join option. This will be a "waterfall" join: first it will match on email, then try phone for unmatched records.

Load reference pattern from `references/` matching the use case.

### Step 4B: Create from Use Case Pattern

1. Match user request to catalog (#1-#6)
2. For #1-#2: Load full reference -> `references/audience-overlap.md` or `references/activation.md`
3. For #3-#5: Load outline reference
4. For #6: Produce a **handoff brief** (plain markdown) and skip Steps 5-6 entirely — go straight to the Code Spec Handoff section
5. Adapt the reference pattern to the user's specific analytical need — the reference is a structural starting point, not a fixed query. If the user's described outcome differs from the reference (e.g., different join strategy, additional GROUP BY dimensions, filtered subsets, custom aggregation), modify the template SQL accordingly rather than copying the reference verbatim.

**If no catalog match:**
> I don't have a pre-built pattern for that yet. Can you tell me more about the business problem you're trying to solve — what outcome are you hoping to get from the clean room? I can build a custom template based on that.

If the user describes a clear outcome, build a custom template. Also suggest:
> If you think this should be a standard pattern, you can request it on the [Snowflake Community Ideas portal](https://community.snowflake.com/s/ideas). Please describe the use case in your own words there — Snowflake respects customer privacy and cannot read your conversation history.

Narration:
> I'm using the standard Audience Overlap pattern. This counts the number of matching identifiers between the two datasets, grouped by dimensions you choose.

### Step 4C: Convert a PnC Template to Collab API

Scope: single-template SQL conversion only. Full cleanroom migration → recommend the [DCR Migration Tool](https://docs.snowflake.com/en/user-guide/cleanrooms/migration-tool) first.

#### Sub-step 1: Obtain the PnC template SQL

Ask the user:
> "Do you have the PnC template SQL to convert? You can paste it directly, or I can fetch it from your P&C clean room — just give me the clean room name."

**Path A — User pastes the SQL:** Accept it and proceed to Sub-step 2.

**Path B — CoCo fetches it (API):**
1. Ask for the clean room name.
2. `CALL {DB}.PROVIDER.VIEW_CLEANROOMS();` — confirm the cleanroom is accessible.
3. `CALL {DB}.PROVIDER.DESCRIBE_CLEANROOM('{cleanroom_name}');` — locate the "Templates in cleanroom:" section to get template names.
4. Present the template list; user selects which one to migrate.
5. `CALL {DB}.PROVIDER.VIEW_TEMPLATE_DEFINITION('{cleanroom_name}', '{template_name}');` — extract the `TEMPLATE` column (full Jinja SQL body). Show it to the user for confirmation.

**Webapp fallback:** If the API calls above fail (cleanroom disabled, access denied, or the cleanroom no longer exists), direct the user to: Snowsight → Data Clean Rooms → [cleanroom name] → Templates tab → copy the SQL from there.

Load `references/pnc-migration-guide.md`.

#### Sub-step 2: Scrub and convert

**⚠️ Before converting anything:** scan the SQL for PnC-internal variables and functions that have no equivalent in the Collab API. For each one found, surface it explicitly to the user and require acknowledgment before proceeding:

> "This template uses `{{ app_instance | sqlsafe }}.cleanroom.addNoise()` for differential privacy noise injection. The Collaboration API handles differential privacy at the platform level — there is no equivalent for injecting custom noise in template SQL. If you proceed, this will be removed from the converted template. Do you want to continue?"

**PnC features that require user acknowledgment:**

| PnC feature | Status in Collab API | What to remove |
|---|---|---|
| `{{ app_instance \| sqlsafe }}.cleanroom.addNoise(...)` | Not supported in template SQL — platform handles privacy | Remove the entire addNoise() expression |
| `{{ privacy.epsilon \| default(...) }}` | Not user-configurable in template SQL | Remove with addNoise() |
| `{{ request_id \| sqlsafe }}` | Internal context var, not exposed in Collab API | Remove |
| `{{ join_columns_check }}` | PnC join enforcement variable | Replace with an explicit join column parameter |
| `{{ at_timestamp }}` | PnC time-travel variable | Remove or ask user for intent |

**⚠️ On "provider" and "consumer" in the SQL:** These are PnC table path aliases, not Collab API roles. When converting:
- `samooha_by_snowflake_local_db.provider.TABLE` → `identifier({{ source_table[0] }})` aliased `p1`
- `samooha_by_snowflake_local_db.consumer.TABLE` → the consumer pattern: `{% set consumer_table = my_table[0] if my_table and my_table|length > 0 else source_table[1] %}` aliased `c1`

**For activation templates specifically:**
- The activation column is exported from the **consumer side** (`my_table[0]`, alias `c1`) — not the provider side
- Spec type must be `sql_activation`, not `sql_analysis`
- Verify: `SELECT DISTINCT c1.{{ activation_column | sqlsafe }} AS activation_id`

**Remaining conversions** (see `references/pnc-migration-guide.md`):
- `{{ source_table[0] | sqlsafe }}` → `identifier({{ source_table[0] }})` (drop `| sqlsafe`, wrap in `identifier()`)
- Extract implicit Jinja variables → explicit `parameters` list
- Add required YAML fields: `api_version: "2.0.0"`, `spec_type: template`, `name`, `version`
- Infer `type`: `sql_activation` if selecting identifiers for export, `sql_analysis` otherwise — ask user to confirm

Narrate each conversion decision. Then proceed to **Step 5** (validate and present) and **Step 6** (handoff to register).


### Step 5: Validate, Present, Explain

**MANDATORY STOPPING POINT — Present Template for Review**

**ML/code use cases (catalog #6) skip this step entirely** — they produce a handoff brief only (see Code Spec Handoff section). Step 5 applies only to SQL Jinja template cases (#1-#5 and custom).

1. Validate the generated spec against these rules (confirmed against `snowflake_product_docs`: `https://docs.snowflake.com/en/user-guide/cleanrooms/v2/spec-reference`):
   - `api_version`: **Required**, string `"2.0.0"`
   - `spec_type`: Must be `"template"`
   - `name`: **Required**, max 75 chars, valid Snowflake identifier — must be unique across all specs in your output
   - `version`: **Required**, max 20 chars, valid Snowflake identifier
   - `type`: `sql_analysis` or `sql_activation`
   - `description`: Optional, max 1000 chars
   - `methodology`: Optional, max 1000 chars
   - `template`: **Required** — always include a non-empty JinjaSQL string with real, executable SQL
   - `parameters[].name`: Valid Snowflake identifier
   - `parameters[].description`: Optional, max 500 chars
   - `parameters[].type`: Optional, one of: `string`, `integer`, `number`, `boolean`, `array`, `object`
   - No reserved parameter names — see `references/reserved-names.md` for the complete list (8 protected names)

   **Pre-emit checklist — verify before presenting ANY spec:**
   - [ ] `template` field is present and non-empty (real SQL, not a placeholder like `<your SQL here>`)
   - [ ] `name` is unique across ALL specs in this entire output — scan every `$$` block you have written so far and confirm no other spec shares this name
   - [ ] `api_version` is `"2.0.0"`
   - [ ] `type` is `sql_analysis` or `sql_activation`
   - [ ] **If type is `sql_activation`:** template body MUST use `BEGIN / CREATE OR REPLACE TABLE cleanroom.{{ result_table | sqlsafe }} AS ... / RETURN 'analysis_results'; / END;`. A plain SELECT body will be rejected. `result_table` is a reserved DCR variable — do not declare it as a parameter. See `references/activation.md` for the canonical pattern.
   - [ ] No reserved parameter names used
   - [ ] All table references in `template` use `identifier()` — no hardcoded database/schema/table paths
   - [ ] Template SQL references the exact join columns and tables the user specified — re-read the user's request and verify column names match
   - [ ] If this case is about fixing a rejected spec (e.g. "already exists"), present only the corrected version — omit the original failing spec from `$$` delimiters
   - [ ] **Optional parameters with defaults:** if a parameter declares `default: N` in YAML, the template body MUST also use `{{ param | default(N) }}` — the YAML `default:` field is documentation only and Jinja does NOT fall back to it at runtime. Without the Jinja filter, an omitted parameter will raise an error instead of using the declared default.
   - [ ] **code_specs field:** if the template SQL calls a function from a registered code spec (syntax: `codeSpecName$functionName(...)`), include a `code_specs` list in the spec YAML. Entries must be bare ID strings — not objects. Correct: `code_specs: [normalize_score_v1]`. Wrong: `code_specs: [{id: normalize_score_v1}]`.
   - [ ] **Table aliases in FROM/JOIN:** always alias `source_table[0]` as `p1` and `source_table[1]` as `p2` — not descriptive names like `publisher` or `advertiser`. The exact alias `p1`/`p2`/`c1` is required for policy filter enforcement to work correctly.
   - [ ] **String parameters in WHERE predicates:** string values in WHERE/HAVING clauses must be surrounded by single quotes. Correct: `WHERE col = '{{ param | sqlsafe }}'`. Wrong: `WHERE col = {{ param | sqlsafe }}` (renders as `WHERE col = myvalue` — invalid SQL).

2. Present the complete template_spec YAML in a `$$` block
3. Explain what the template does and key design choices. Do **not** show the registration CALL command yet — wait for user approval first.
4. If Mode A (with clean room): Note whether other collaborators have auto-approve enabled
5. Ask: "Does this look correct? Once you confirm, I'd recommend a quick dry run before we register it."

   **Only after the user confirms:** provide the registration command. Default registry: `CALL {DB}.REGISTRY.REGISTER_TEMPLATE($$<spec>$$)`. Custom registry: `CALL {DB}.REGISTRY.REGISTER_TEMPLATE($$<spec>$$, '<registry_name>')` — spec first, registry name second.

### Step 5.5: Optional Dry Run (Recommended)

**Strongly recommend this step** before handoff to register. Templates that look syntactically valid can still fail inside a collaboration due to Jinja rendering issues, column reference mismatches, or join logic errors. A local dry run catches these before registration, when fixes are cheap.

After the user approves the spec in Step 5, ask:

> Before we register, I'd recommend a quick **dry run** to make sure the Jinja SQL renders and executes correctly. This catches issues like missing column references, malformed joins, or parameter substitution bugs before they fail inside the collaboration. Want to do a dry run? (Strongly recommended.)

If user declines, skip to Step 6.

If user accepts, load the dry-run workflow: `references/dry-run.md`

### Step 6: Hand Off to Register Skill

When user approves, hand off to the register skill for submission:

> Your template spec is ready. I'm handing off to the register skill to register it and (if applicable) add it to your collaboration.

Load the register skill: `../../data-cleanrooms/register/SKILL.md`

Pass the complete, approved template_spec YAML. The register skill handles:
- `{DB}.REGISTRY.REGISTER_TEMPLATE()` — registers the spec in the account registry
- Verification via `{DB}.REGISTRY.VIEW_REGISTERED_TEMPLATES()`

After registration, adding the template to a specific collaboration requires a separate step:
- `{DB}.COLLABORATION.ADD_TEMPLATE_REQUEST(COLLABORATION_NAME, TEMPLATE_ID, SHARE_WITH)` (Mode A only) — handled by the **manage-templates skill** (`../../data-cleanrooms/manage-templates/SKILL.md`), not the register skill. `SHARE_WITH` is an array of analysis runner aliases (e.g. `['PARTNER_A', 'PARTNER_B']`) — pass these along with the collaboration name and template ID.

**Context to pass along:**
- The approved template_spec YAML (the `$$` block from Step 5)
- The collaboration name (if Mode A)
- The collaborator aliases who should be analysis runners (if Mode A)
- The registry name (if the user has specified a custom registry — see Registry Name section below)

### Registry Name

By default, `REGISTER_TEMPLATE` registers into the account's default registry (`{DB}.REGISTRY`). Customers with multiple teams, environments, or ISV setups may maintain **named/custom registries** — separate registry schemas within the DCR database. Common reasons:

- **Environment separation**: different registries for dev/staging/prod templates so test templates never appear alongside production ones
- **Team governance**: separate template libraries per business unit (e.g., marketing vs. data science), each with its own access grants
- **ISV / Native App builds**: partners embedding DCR functionality need their templates isolated from the customer's own template library

If the user mentions a custom registry name (e.g., "register this to our `MARKETING_REGISTRY`"), include `registry_name` in the context passed to the register skill. The correct call syntax is: `CALL {DB}.REGISTRY.REGISTER_TEMPLATE($$<spec>$$, '<registry_name>')` — spec first, registry name second. Reversing the order causes a type error.

### Step 7: Handle Rejection

> **Re-entry path only.** This step applies when the user has already attempted registration (via the register skill) and returned with an error. During initial spec creation (Steps 1–6), skip this section.

If the register skill reports a failure, diagnose and fix the spec here:

| Error | Fix |
|-------|-----|
| "already exists" | Bump version string (e.g. `2024_02`), or unregister then re-register (see below) |
| "invalid name" | Fix name characters/length |
| "invalid type" | Correct to `sql_analysis` or `sql_activation` |
| "empty template" | Add SQL content |
| "invalid parameter" | Rename the reserved/invalid parameter |
| "insufficient privileges" | ACCOUNTADMIN grants via `{DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE` |

**For "already exists" errors:** Offer two paths:

1. **Bump `version`** and re-register — usually simplest (e.g., `"2024_02"`).
2. **Unregister then re-register** if they need the same name+version:
   - `CALL {DB}.REGISTRY.VIEW_REGISTERED_TEMPLATES()` → get the `TEMPLATE_ID` for the conflicting entry.
   - `CALL {DB}.REGISTRY.UNREGISTER_TEMPLATE('<TEMPLATE_ID>')` → removes the registry entry.
     If the template is still linked to collaborations, this call will fail and name each collaboration in the error. Call `COLLABORATION.REMOVE_TEMPLATE` on each before retrying `UNREGISTER_TEMPLATE`.
   - Re-register with the original name+version.

Note: `REMOVE_TEMPLATE` on a collaboration only unshares the template from that collaboration; it doesn't delete the registry entry. Use `UNREGISTER_TEMPLATE` to fully remove it.

Show the corrected field values in inline text or a non-`$$` code block (e.g., `version: "2024_02"`). Only emit a full `$$` spec block when the `template` field contains complete, executable SQL — a `$$` block with placeholder text like `[your SQL here]` will fail validation.

**⚠️ MANDATORY STOPPING POINT** — Present updated spec and wait for re-approval before handing back to the register skill.

## Reserved Names and Aliases

See `references/reserved-names.md` for the full list of protected Jinja variables and table alias conventions.

## Jinja Filter Reference

See `references/jinja-filters.md` for the complete filter table, auto-binding rules, policy filter syntax, and known limitations.

## Code Spec Handoff

If the user needs ML model training, Python UDFs, custom Python logic, or containerized workloads, **produce a handoff brief instead of a template_spec.** This skill only creates SQL Jinja templates; ML/code workloads require a `code_spec`, which is a different artifact managed by the Code Spec skill.

**For ML/code cases, always produce a handoff brief** — a plain-text markdown summary with no YAML block, no `$$` delimiters, and no `spec_type: template`. The handoff brief is the only artifact for this case.

Handoff brief format (use exactly this structure):

> **Handoff Brief — Code Spec Required**
>
> - **Use case:** [describe the ML/code task]
> - **Provider table:** `source_table[0]` ([what it contains])
> - **Consumer table:** `my_table[0]` ([what it contains])
> - **Join key:** [e.g. `HASHED_EMAIL`]
> - **Model output:** [what the model produces]
> - **Artifact needed:** `code_spec` (this cannot be expressed as a SQL Jinja `template_spec`)
>
> To create the code spec, use the DCR Code Spec skill (when available) or register it manually.

Route to handoff brief for: lookalike modeling, propensity scoring, any Python UDF creation, statistical significance testing, custom ML pipelines.

## Dual-Audience Note

Templates may be used by:
- **Data engineers** in notebooks (comfortable with Jinja, SQL, parameters)
- **Business users** in Streamlit apps (need clear parameter names + descriptions)

Write parameter descriptions that make sense to non-technical users:
- Good: `join_column: "Column used to match records between datasets (e.g., HASHED_EMAIL)"`
- Bad: `join_column: "Jinja var for equi-join predicate"`

## Reference Patterns

Load on demand based on use case. Also consult `snowflake_product_docs`: `https://docs.snowflake.com/en/user-guide/cleanrooms/v2/spec-reference` for the latest spec schema.

- `references/audience-overlap.md` — Full pattern + narration
- `references/activation.md` — Full pattern + narration
- `references/reach-frequency.md` — Outline
- `references/incrementality.md` — Outline
- `references/multi-touch-attribution.md` — Outline
- `references/pnc-migration-guide.md` — Full migration mapping
- `references/naming-conventions.md` — Name/description examples

## Stopping Points

| Point | When | What to Do |
|-------|------|------------|
| Step 5 | After generation | Present complete template_spec, explain, wait for approval |
| Step 5.5 | After approval | Offer dry run (recommended); if accepted, run and re-confirm updated spec |
| Step 7 | After rejection fix | Present updated spec, wait for re-approval |

**Register only after the user explicitly approves the spec at Step 5 (or Step 7 for re-submissions).**

### Final Review Sweep

Before writing the final output, scan all `$$` spec blocks and verify:
1. Every `name` field is unique across the entire document — no two specs share the same name
2. Every `template` field contains real SQL (not placeholder text)
3. Every spec has `api_version: "2.0.0"` and a valid `type`
4. Every spec block appears exactly once — if you wrote the same spec earlier while explaining design choices, remove that earlier copy and keep only the final deliverable block

If a duplicate name is found, differentiate it — e.g. append the case context: `audience_overlap_email_v1` vs `audience_overlap_email_v2` (for the version-bumped fix).

## Output

The skill produces one of:
1. **Template spec** — a complete, valid `template_spec` YAML ready for `REGISTER_TEMPLATE()`, with narrated explanation and automatic handoff to the register skill on approval
2. **Handoff brief** — a plain-text markdown summary for ML/code use cases (catalog #6), containing DCR-specific context for the code-spec skill. A handoff brief contains no YAML, no `$$` block, and no `spec_type` field.
