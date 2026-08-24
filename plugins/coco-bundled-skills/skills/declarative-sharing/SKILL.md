---
name: declarative-sharing
"description": "Data-as-a-product sharing via APPLICATION PACKAGE with TYPE=DATA (data apps). Bundles data with code objects (notebooks, UDFs, stored procedures, Cortex Agents, semantic views) plus versioning and app roles; the consumer installs once with no setup script. Use when the user explicitly wants declarative sharing or a data app, or to convert/combine existing data shares into a declarative share, or when a consumer migrates from a data share to a declarative app. NOT for open-ended or comparison questions (\"is there an alternative to creating shares\", \"what are my options\", \"which should I use\", \"manifests or native apps\") and NOT for generic 'share data' requests where the construct is unspecified — those go to the sharing router for disambiguation. Triggers: declarative sharing/share, data app, application package TYPE=DATA, convert share to declarative, migrate share to app, generate manifest from share, combine shares into app, versioned share, drop-in replacement for share"
---

# Declarative Sharing (Data Apps)

Share data products with versioning, bundling, and app roles - without the complexity of full native apps.

**"Data app" = declarative share.** When a user says "data app", "data application", "bundle into an app", or "create an app they can install", they mean a declarative share (`TYPE = DATA` application package) — NOT a full native app. Only use the full native app framework if the user explicitly needs a setup script, consumer-side data access, or Snowpark Container Services.

## Intent Detection

Detect user intent and route to the appropriate workflow:

| User Intent | Route |
|-------------|-------|
| **Create/share data from scratch** — share objects, create a data app, build a package, create a listing (no existing data share) | Default workflow (Steps 1-6 below) |
| **Convert or create declarative share from one or more existing data shares** — provider has one or more traditional data shares (secure shares) and wants to migrate or combine them into declarative sharing, or use them as the starting point for a new declarative share | **Load** `workflows/manifest-from-share.md`, then continue with Steps 4-6 below |
| **Consumer migrating from data share to declarative app** — consumer has a database from a traditional data share and the provider has published a new declarative app (listing or package). Consumer wants to switch with zero downtime and no query changes | **Load** `workflows/consumer-share-migration.md` (standalone workflow, does NOT continue with Steps below) |

**Route to `workflows/manifest-from-share.md`** when the user mentions an existing data share (or multiple data shares) they want to convert or base the declarative share on. Common motivations:
- Migrating from traditional sharing to declarative sharing
- Combining multiple data shares into a single declarative share spanning multiple databases
- Adding new capabilities (notebooks, agents, semantic views) to an existing share
- Future-proofing a data share with versioning and app roles
- Getting versioning support for an existing share

After `workflows/manifest-from-share.md` produces the manifest, return here at **Step 4** to create and release the application package.

**Route to `workflows/consumer-share-migration.md`** when the user is a **consumer** (not provider) who already has a database from a traditional data share and wants to switch to a new declarative app. Key signals:
- User mentions having a shared database they want to replace/upgrade
- User mentions a listing name or app package from their provider
- User asks about migrating grants, renaming databases, or zero-downtime share migration
- User is on the **consumer** side (they received a share, not created one)

## When to Use This Skill

**Choose Declarative Sharing when cross-account sharing:**
- Sharing **multiple related objects** (tables + views + agents + semantic views)
- Need **versioning** with automatic consumer updates
- Want **app roles** for granular access control within the share
- Sharing **Cortex Agents** or **semantic views**
- Sharing a **single table** and the user wants versioning or a managed upgrade path

**Use Traditional Data Sharing ONLY when:**
- User **explicitly** asks for a traditional data share (not an application package)
- Sharing a **single table or view** with **no future need** for bundling, versioning, or AI features
- No versioning or bundling needed and user confirms they don't want it

**Use Full Native Apps instead when:**
- Need a **setup script** to create objects in consumer account
- App must **access consumer's data** (with their permission)
- Require **Snowpark Container Services** or custom containers
- Building **Streamlit apps** → Use `apps/deploy-to-spcs` or `apps/build-react-app` skills

**Do NOT use this skill — defer to the `sharing` router — when:**
- The user is **comparing options** or asking for an **alternative** ("is there an alternative to creating shares?", "what are my options", "which should I use", "manifests or native apps?") — the router disambiguates and hands off.
- The user names a **different construct** (org listing / internal marketplace / data product, direct share, clean room). Route to that product's skill, not here.

**Documentation**: [Declarative Sharing](https://docs.snowflake.com/en/developer-guide/declarative-sharing/about)

## Prerequisites

- Snowflake account with `CREATE APPLICATION PACKAGE` privilege
- Objects to share already exist (or will be created)

**Pre-flight check** (optional, skip if user says to proceed):
```sql
SHOW GRANTS ON ACCOUNT
  ->> SELECT "privilege", "grantee_name" FROM $1
      WHERE "privilege" = 'CREATE APPLICATION PACKAGE'
        AND "grantee_name" = CURRENT_ROLE();
```
If no rows returned, the current role lacks the privilege — switch to a role that has it or ask an ACCOUNTADMIN to grant it.

## Workflow

### Step 1: Determine What to Share

Ask or infer from context:

1. **What existing objects** need to be shared? (tables, views, functions, procedures)
   - Views MUST be SECURE (`CREATE SECURE VIEW`) — non-secure views will not work
2. **What additional entities** would enhance the data product?
   - **Cortex Agents** — use `agent-optimization` skill to create/optimize agents

**⚠️ AGENT RULES — READ ALL THREE:**

**1. Syntax:** `CREATE AGENT` / `CREATE OR REPLACE AGENT` — NOT `CREATE CORTEX AGENT` (does not exist). Do not analogize from `CREATE CORTEX SEARCH SERVICE`.

**2. execution_environment:** ALL tool types except Cortex Search require this in `tool_resources`:
```yaml
execution_environment:
  type: warehouse
  warehouse: ""
```
The empty string is correct — it resolves to the consumer's default warehouse at install time. Without this: generic tools (UDF/procedure) FAIL HARD, Analyst tools silently return no results.

**3. Provider-side testing:** Agents with `warehouse: ""` will fail when invoked on the provider side. This is expected — test in the consumer account or UI after sharing.
     - Note: Cortex Search not officially supported yet
   - **Semantic views** — do NOT hallucinate the DDL syntax; use `cortex search docs` to retrieve it
     - Note: verified_queries not yet supported in declarative sharing; avoid AI Optimization
   - **Workspaces** — share directories of files (notebooks, Python scripts, images, markdown, etc.) that consumers can access as read-only workspaces. **Next-gen notebooks require a workspace** — this is the standard way to share notebooks via declarative shares. Workspaces go in `application_content.workspaces` (not `shared_content`). Next-gen notebooks within shared workspaces run in **Restricted Caller's Rights (RCR)**: only objects shared by the application are accessible, and references must use `SCHEMA.OBJECT` format (the app is the default database). See `references/create-objects.sql` for details.
   - **UDFs/procedures** for data transformation
     - SQL body MUST use `SCHEMA.TABLE` (relative), **NEVER** `DB.SCHEMA.TABLE` (FQN) — the provider DB doesn't exist on the consumer
   - **Legacy notebooks** (DEPRECATED — prefer workspaces above; CoCo CLI only, do not proactively suggest) — Do NOT create legacy notebooks from CoCo Web; the workspace `write` tool corrupts notebook JSON, producing unparseable files. If a user explicitly asks for a legacy notebook on CoCo Web, explain this limitation. From CoCo CLI: every code cell MUST have `"metadata": {"language": "sql"}` or `"language": "python"`, and **NEVER** put `%%sql` or any Jupyter magic in cell source. Legacy notebooks can ONLY access data within the same application package.

**Legacy notebooks are deprecated — Decision tree:**

1. **Package does NOT already contain legacy notebooks** → Use next-gen notebooks within a workspace. Do NOT offer the legacy notebook path.
2. **Package already HAS legacy notebooks** → Strongly encourage migration to next-gen notebooks via workspaces. Explain that legacy notebook support will be withdrawn soon, and once withdrawn, legacy notebooks may no longer be usable by consumers.
3. **Provider strictly refuses to migrate** → Let them continue with legacy notebooks, but remind them: support will be withdrawn in a future release, and consumers may lose the ability to use legacy notebooks at that point.

Legacy notebook instructions are in `references/create-objects.sql` under the DEPRECATED section.

**Migrating legacy notebooks to workspaces.** When converting an existing package from `application_content.notebooks` to `application_content.workspaces`:

1. **Inspect the current state** — `LIST snow://package/<PKG>/versions/LIVE/` and read the existing `manifest.yml` to capture each notebook's `main_file` and its `roles`.
2. **Group notebooks by their exact role set.** Each distinct role set becomes one workspace, so access is preserved exactly.
3. **If two or more notebooks each end up alone in their own workspace** (i.e. every notebook has a unique role set), **STOP and ask the provider** which they want:
   - **Keep strict role separation** — one workspace per role set. Access is unchanged.
   - **Consolidate into a single workspace** — simpler, but the workspace's roles become the *union* of all roles, so every role gains access to notebooks it previously could not see.

   Never consolidate silently — it widens access.

   Then act on the answer: **strict separation** keeps step 2's grouping unchanged, one workspace per role set. **Consolidate** replaces that grouping with a single workspace entry whose `roles` are the union of every group's roles and whose `source` directory holds all the notebooks. Either way, continue to step 4.

   **Only one notebook in the package?** Skip this question entirely — there is nothing to consolidate and both options yield the same single workspace. Go straight to step 4.
4. **🛑 MANDATORY CHECKPOINT.** Steps 1–3 are read-only; steps 5–7 mutate the live package. Present the plan and get an explicit go-ahead before executing any of them:
   - each workspace, its `source` path, and its `roles`
   - which `.ipynb` file is uploaded to which workspace
   - **which root-level files will be deleted** — this is irreversible
   - that the migration finishes with `RELEASE LIVE VERSION`

   Proceed only once the provider approves. Skip this checkpoint only if they have already told you to run end-to-end without stopping.
5. **Relocate the `.ipynb` files.** Legacy notebooks sit at the package root; workspaces read from the `source` directory. Upload each notebook to its workspace's `source` path (see Step 4.3).
6. **Remove the stale root-level notebooks** so the package doesn't keep duplicate copies:
   ```sql
   RM snow://package/<PKG>/versions/live/<old_notebook>.ipynb;
   ```
   ⚠️ Use lowercase `live` — uppercase `LIVE` silently deletes nothing and reports no error. `LIST` afterwards to confirm. Details in `references/package-release.sql`.
7. **Swap the manifest section** from `notebooks:` to `workspaces:`, then `LIST` to confirm layout and `RELEASE LIVE VERSION`.

**🛑 STOP — BEFORE writing ANY SQL that creates objects (agents, UDFs, procedures, semantic views, notebooks):**
1. **Read `references/create-objects.sql` NOW.** Do not guess syntax from memory.
2. **Copy the exact DDL template** from that file. Do not modify the command keywords.
3. Only skip this if you are sharing exclusively pre-existing tables/views with zero new objects.

### Step 2: Organize Schema Layout

Create all objects in the **source database** (the one the user pointed you to, or a database you already created for this task). **⚠️ NEVER create a database with the same name as the application package** — databases and application packages share the same namespace in Snowflake. If a database `X` exists, `CREATE APPLICATION PACKAGE X TYPE = DATA` will fail.

**Simple case** (only tables, or only views): Use the existing schema where objects already live. Skip schema creation — go straight to Step 3.

**Mixed objects** (agents + data, or UDFs + tables): Create new schemas **in the source database** — shared-by-copy and shared-by-reference objects **cannot be in the same schema**. **⚠️ `RELEASE LIVE VERSION` will fail if you put an agent in the same schema as tables/views.**

| Category | Objects | Schema |
|----------|---------|--------|
| **Shared-by-copy** | Agents, UDFs, procedures | `SHARED_BY_COPY_SCHEMA` |
| **Shared-by-reference** | Tables, views, semantic views, Cortex Search services | `SHARED_BY_REFERENCE_SCHEMA` |

```
SOURCE_DATABASE/          ← the database containing source data (NOT the package name)
├── SHARED_BY_COPY_SCHEMA /
│   ├── my_agent
│   └── my_udf()
└── SHARED_BY_REFERENCE_SCHEMA/
    ├── my_table
    └── my_semantic_view
```

### Step 3: Create Manifest

**🛑 STOP — Read `references/manifest.yml` NOW before writing any manifest YAML.** The format is non-standard and differs from what you expect. Do not guess.

**Minimal example** (sharing one table from scratch — when coming from `manifest-from-share.md`, use the manifest it generated instead):
```yaml
roles:
  - app_user:
      comment: "Read-only access"

shared_content:
  databases:
    - MY_DATABASE:
        schemas:
          - MY_SCHEMA:
              roles: [app_user]
              tables:
                - MY_TABLE:
                    roles: [app_user]
```

**Critical format rules:**
- Do NOT include `manifest_version` — it is auto-added on release
- Do NOT use `app_roles:` — the correct key is `roles:`
- Do NOT use `artifacts:`, `setup_script:`, `privileges:`, or `references:` — those are for native apps, NOT declarative sharing
- **Sharing notebooks? Use `application_content.workspaces`, NOT `application_content.notebooks`.** Next-gen notebooks live inside a workspace. `notebooks:` is deprecated — only use it if the package ALREADY has legacy notebooks and the provider refuses to migrate. Put the `.ipynb` files in the workspace's `source` directory.
- Database and schema names are map keys (with colon), NOT `name:` fields
- Object types are: `tables`, `views`, `semantic_views`, `cortex_agents`, `functions`, `procedures`, `cortex_search_services`
- Per-object `roles` must be a subset of the parent schema's `roles`
- **`required_databases`**: Almost always OMIT this. Only needed when a shared view's expansion references tables in a *different* database that isn't already in `shared_content/databases` — this tells Snowflake to replicate that database in cross-region scenarios. If all your objects live in the same database, do NOT add `required_databases`. It is NOT a place to list the databases you're sharing — that's what `shared_content/databases` is for

### Step 4: Create and Release Package

**🛑 STOP — Read `references/package-release.sql` NOW before running any package commands.** Do not guess syntax.

**⚠️ NEVER do these:**
- `CREATE DATABASE <PACKAGE_NAME>` — databases and app packages share the same namespace; this blocks `CREATE APPLICATION PACKAGE` with that name
- `CREATE CORTEX AGENT` — WRONG; correct is `CREATE AGENT` (no "CORTEX" keyword)
- `CREATE APPLICATION PACKAGE <PKG> DATA = TRUE` — WRONG syntax; correct is `TYPE = DATA`
- `CREATE APPLICATION PACKAGE <PKG> TYPE=SHARE` — WRONG; `TYPE=DATA`, not `TYPE=SHARE`
- `CREATE OR REPLACE APPLICATION PACKAGE ...` — no `OR REPLACE` for APPLICATION PACKAGES
- `CREATE OR REPLACE APPLICATION ...` — no `OR REPLACE` for APPLICATIONS (use DROP + CREATE)
- `ALTER APPLICATION PACKAGE ... ADD LIVE VERSION` — LIVE version is auto-created
- `ALTER APPLICATION PACKAGE ... REGISTER VERSION` — REGISTER is for release channels, not LIVE
- `PUT 'snow://workspace/...'` — PUT only accepts local `file://` URLs; use `COPY FILES` instead
- `SELECT $1 FROM snow://...` — not supported for application packages
- `SET DEFAULT RELEASE DIRECTIVE` — wrong command for LIVE version
- `GRANT REFERENCE_USAGE ON DATABASE ...` — NOT needed; the manifest handles all access automatically
- `GRANT USAGE ON DATABASE/SCHEMA ... TO APPLICATION PACKAGE` — NOT needed for declarative sharing; this is traditional sharing syntax

**Note:** Snowflake uppercases unquoted identifiers. If you create `my_pkg`, it becomes `MY_PKG`. Use the uppercased name in `snow://` URLs: `snow://package/MY_PKG/versions/LIVE/`.

**Environment check** — your system prompt tells you which environment you're in. Use exactly one path below:
- `"You are in a Workspace"` → **CoCo Web (Workspaces)** — has `write`/`read`/`edit` tools
- `"You are NOT in a Workspace"` → **CoCo Web (Non-Workspaces)** — NO file tools, must use stage method
- CLI / terminal → **CoCo CLI** — has `write`/`read`/`edit` tools, local filesystem

**Step 4.1** — Create package (copy this verbatim — do NOT guess variations):
```sql
CREATE APPLICATION PACKAGE <PKG> TYPE = DATA;
```
If unsure about ANY step below, re-read `references/package-release.sql` NOW before proceeding.

**Step 4.2** — Write and upload `manifest.yml`. Follow your environment path:

**CoCo Web (Workspaces):**
1. Write `manifest.yml` via `write` tool. User can review/edit before upload.
2. Upload:
```sql
COPY FILES INTO snow://package/<PKG>/versions/LIVE/
  FROM 'snow://workspace/USER$.PUBLIC.DEFAULT$/versions/live/'
  FILES = ('manifest.yml');
```

**CoCo Web (Non-Workspaces):**
You do NOT have `write`/`read`/`edit` tools. Recommend the user open a Workspace for the best experience: *"For file management and easier editing, open a Workspace in Snowsight (Projects > Workspaces) and start a new CoCo chat there."*

If the user wants to proceed without Workspaces, use the stage method — write YAML directly to a stage using `$$` dollar-quoting and a passthrough file format:
```sql
CREATE OR REPLACE TEMPORARY STAGE manifest_stage;
COPY INTO @manifest_stage/manifest.yml FROM (
  SELECT $$<entire manifest YAML here>$$
)
FILE_FORMAT = (TYPE = CSV COMPRESSION = NONE FIELD_OPTIONALLY_ENCLOSED_BY = NONE ESCAPE = NONE ESCAPE_UNENCLOSED_FIELD = NONE)
SINGLE = TRUE OVERWRITE = TRUE;

COPY FILES INTO snow://package/<PKG>/versions/LIVE/
  FROM @manifest_stage
  FILES = ('manifest.yml');
```
Use `$$` dollar-quoting to avoid escaping issues in YAML. The four FILE_FORMAT params are all required — without them Snowflake adds compression, backslash escaping, or quoting that corrupt the YAML.

**CoCo CLI:**
1. Write `manifest.yml` via `write` tool. User can review/edit before upload.
2. Upload:
```sql
PUT file:///workspace/manifest.yml snow://package/<PKG>/versions/LIVE/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
```

**Step 4.3** (optional) — Upload workspace files.
If the package includes workspaces, upload all files in each workspace's `source` directory to the corresponding path under the package version:

**CoCo CLI:**
```sql
-- Upload each file to its workspace source path
PUT file:///path/to/<source_dir>/<filename> snow://package/<PKG>/versions/LIVE/<source_dir>/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
```

**CoCo Web (Workspaces):**
```sql
COPY FILES INTO snow://package/<PKG>/versions/LIVE/<source_dir>/
  FROM 'snow://workspace/USER$.PUBLIC.DEFAULT$/<source_dir>/'
  FILES = ('<filename>');
```

**CoCo Web (Non-Workspaces):**
Environment detection and the CLI → Workspaces escalation are not specific to declarative packages — follow `apps/native-app-provider/references/native-apps-snowsight.md` (Decision Flow, Shape 1). One override applies to workspace files: its last-resort stage-write loop is **not** available here, because the stage method cannot produce valid notebook JSON and cannot carry binary files such as `.png` at all. There is no best-effort path — **STOP** and have the user open a Workspace (Projects » Workspaces in Snowsight) or switch to CoCo CLI.

The `<source_dir>` must match the `source:` path in the manifest (e.g., `content/analyst_content/`). Repeat for each file in each workspace.

**Step 4.3a** (DEPRECATED, **CoCo CLI only**) — Write legacy notebook `.ipynb` via `write` tool.
Only applies when the manifest uses the deprecated `application_content.notebooks`. Prefer workspaces (Step 4.3).
**⚠️ Do NOT create legacy notebooks on CoCo Web (any tab).** The workspace `write` tool corrupts notebook JSON, and the stage method cannot produce valid notebook JSON. If the user asks for a legacy notebook on CoCo Web, explain this limitation. Do not proactively suggest legacy notebooks.

**Step 4.3b** — **Legacy notebook sanitization** (CoCo CLI only — REQUIRED before uploading ANY `.ipynb`):
After writing the notebook, **re-read** it and verify:
- **No** `%%sql`, `%%sql -r dataframe_N`, or any `%%` magic prefix in any cell `"source"`
- **No** `"resultVariableName"` in cell `"metadata"`
- Every code cell has `"metadata": {"language": "sql"}` or `"metadata": {"language": "python"}`
If any magic is present, `edit` the file to strip it. Then add a second `PUT` for the `.ipynb` file.

**Step 4.4** — Verify upload before releasing:
```sql
LIST snow://package/<PKG>/versions/LIVE/;
```
**If 0 rows: do NOT release.** Debug the upload — the file path or environment may be wrong. Re-check Step 4.2.

**Step 4.5** — Release (MUST be LAST, ONLY after LIST confirms files are present):
```sql
ALTER APPLICATION PACKAGE <PKG> RELEASE LIVE VERSION;
```

**⚠️ STOP**: Confirm package created and LIVE version released before proceeding.

### Step 4A: Modifying an Existing Package

Use this flow when the user wants to **modify** a package that already exists — e.g., update the manifest or add new files. Skip Steps 1-4 above; jump directly here.

**Step 4A.1** — List current files:
```sql
LIST snow://package/<PKG>/versions/LIVE/
```

**Step 4A.2** — Download files for editing:

**CoCo Web (Workspaces):**
```sql
COPY FILES INTO 'snow://workspace/USER$.PUBLIC.DEFAULT$/versions/live/'
  FROM snow://package/<PKG>/versions/LIVE/
  FILES = ('manifest.yml');
```
Then `read`/`edit` the file in the workspace.

**CoCo Web (Non-Workspaces):**
Recommend the user switch to Workspaces for easier editing. If they decline, download to a stage and read:
```sql
CREATE OR REPLACE STAGE download_stage;
COPY FILES INTO @download_stage/
  FROM snow://package/<PKG>/versions/LIVE/
  FILES = ('manifest.yml');

CREATE OR REPLACE FILE FORMAT raw_text_fmt
  TYPE = CSV FIELD_DELIMITER = NONE RECORD_DELIMITER = NONE
  COMPRESSION = NONE ESCAPE = NONE ESCAPE_UNENCLOSED_FIELD = NONE;

SELECT $1 AS content FROM @download_stage/manifest.yml (FILE_FORMAT => 'raw_text_fmt');
```
Edit the YAML, then re-upload using the stage method from Step 4.2.

**CoCo CLI:**
```sql
GET snow://package/<PKG>/versions/LIVE/manifest.yml file:///tmp/;
```
Ask the user where they want files downloaded — `/tmp/` is a safe default.

**Step 4A.3** — Read and edit files (Workspaces/CLI: via `read`/`edit` tools).

**Step 4A.4** — Upload modified files back to package (same upload commands as Step 4.2 for your environment). Verify with `LIST` before releasing.

**Step 4A.5** — Test or release the updated version:

To **iterate without releasing** (provider-side dev/test cycle):
```sql
-- Build to pick up the updated files:
ALTER APPLICATION PACKAGE <PKG> BUILD;

-- Install test app from LIVE version (first time only):
CREATE APPLICATION <APP> FROM APPLICATION PACKAGE <PKG> USING VERSION LIVE;

-- Upgrade test app to latest built LIVE version (subsequent iterations):
ALTER APPLICATION <APP> UPGRADE USING VERSION LIVE;
```

To **release** (MUST be LAST, after testing):
```sql
ALTER APPLICATION PACKAGE <PKG> RELEASE LIVE VERSION;
```

If a released app already exists (provider or consumer), upgrade it after releasing:
```sql
ALTER APPLICATION <APP> UPGRADE;
```

### Step 5: Create Listing (Distribution)

> **Ready to share?** Would you like to:
> 1. **Create a private listing** (share with specific accounts)
> 2. **Use Provider Studio UI** (more options)
>
> For private listing, I'll need:
> - **Target account(s)**: `MYORG.MYACCOUNT` format
> - **Listing title**

**⚠️ MANDATORY**: Listing syntax is in `references/package-release.sql` (already loaded at Step 4). For advanced listing scenarios, invoke the `internal-marketplace-org-listing` skill.

To find organization name: `SELECT CURRENT_ORGANIZATION_NAME();`

**Cross-region sharing** — Ask the user: "Is the target account in a different region or cloud?" If yes:

**⚠️ NEVER run these for cross-region checks (all are hallucinated/wrong):**
- `SYSTEM$SHOW_ACTIVE_REGION_LIST()` — does NOT exist
- `SYSTEM$SHOW_ACTIVE_REGION_GROUP()` — does NOT exist
- `SYSTEM$GLOBAL_ACCOUNT_SET_PARAMETER(...)` — does NOT exist
- `SHOW ORGANIZATION ACCOUNTS` — wrong tool for this job
- `SHOW SHARES` to find consumer region — wrong tool for this job
- `SNOWFLAKE.ORGANIZATION_USAGE.ACCOUNTS` — wrong tool for this job
- Do NOT try to programmatically discover the consumer's region — just ask the user

**The ONLY command needed** — check if auto-fulfillment is enabled for the provider account:
```sql
SELECT SYSTEM$IS_GLOBAL_DATA_SHARING_ENABLED_FOR_ACCOUNT('<PROVIDER_ACCOUNT_NAME>');
```
- Returns `TRUE` → proceed to create cross-region listing with `auto_fulfillment` in YAML
- Returns `FALSE` → tell user ORGADMIN must enable it first:
  ```sql
  SELECT SYSTEM$ENABLE_GLOBAL_DATA_SHARING_FOR_ACCOUNT('<PROVIDER_ACCOUNT_NAME>');
  ```
- These functions require `ORGADMIN` role. If the current role can't run them, tell the user to ask their ORGADMIN.

Then add `auto_fulfillment` to the listing YAML — see `references/package-release.sql` for the exact cross-region listing template.

### Step 6: Consumer-Side Verification

> **If you're a consumer**, skip directly to this step.

**⚠️ NEVER do these:**
- `CREATE OR REPLACE APPLICATION ...` — does NOT exist. Must `DROP APPLICATION IF EXISTS` first, then `CREATE APPLICATION`

**Install commands** (copy verbatim — do NOT guess):
```sql
-- Same-account install (from package):
CREATE APPLICATION <APP> FROM APPLICATION PACKAGE <PKG>;

-- Cross-account install (from listing):
CREATE APPLICATION <APP> FROM LISTING '<LISTING_ID>';

-- Reinstall (must drop first):
DROP APPLICATION IF EXISTS <APP>;
CREATE APPLICATION <APP> FROM APPLICATION PACKAGE <PKG>;

-- Upgrade existing app to latest released version (no reinstall needed):
ALTER APPLICATION <APP> UPGRADE;
```

**Test in UI first**: Snowflake Intelligence → select the agent.

**Troubleshooting**: See `references/troubleshooting.md`.

---

## Key Concepts

### Constraints & Limits

- **1,000 object limit** in `shared_content` per application package — plan schema layout accordingly
- **No wildcard/regex** for object names in the manifest — every object must be listed explicitly
- **Semantic view verified_queries**: Do NOT use FQN — use table alias only (e.g. `SELECT * FROM COMPANIES`), or you get INTERNAL_ERROR 370001
- **Workspace `source` format**: MUST end with `/`, MUST NOT start with `/`. Directory must contain at least one file.
- **Workspaces are read-only for consumers** — consumers can view/download files but cannot modify, commit, or upload to shared workspaces
- **Workspace notebooks are executable** — `.ipynb` notebooks within shared workspaces are executable (but not editable) by consumers. They run in Restricted Caller's Rights (RCR).
- **Notebook RCR scope** — Notebooks can ONLY access objects shared by the application. Use `SCHEMA.OBJECT` references (the app is the default database). No external databases or consumer-owned tables are accessible.
- **Blocked file types in workspaces** — `.pdf` files are explicitly blocked
- **Legacy notebooks can only access data within the same application package** (deprecated path) — they cannot query external databases or the provider's source data directly
- **No REFERENCE_USAGE grants** — manifest handles access automatically
- **App name becomes the database** — `SELECT * FROM <app_name>.<schema>.<table>`

---

## Stopping Points

**Skip all stopping points when the user says to proceed end-to-end or skip confirmations.** Execute the full workflow without pausing.

When interactive:
- ✋ After Step 2: Confirm schema layout before creating manifest
- ✋ After Step 4 or 4A: Confirm package created/updated and version released
- ✋ After Step 5: Ask whether user wants a listing
- ✋ After Step 6: Confirm consumer can access data

**Resume rule:** Upon user approval, proceed directly to next step without re-asking.

**Iteration rule:** When user asks to redo or fix a step, skip confirmations for previously approved steps. Go directly to the step that needs fixing without re-asking about earlier decisions.

## Output

- Application package (`TYPE=DATA`) with manifest
- Consumer-installable data app
- Private listing (if requested)
