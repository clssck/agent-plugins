---
name: business-ontology-source
description: "Register, list, import from, and manage stage-file sources for Business Ontology domains. Sources are stored as lightweight references in a temporary manifest until native backend storage exists. Triggers: register ontology source, add source to <domain>, add stage file to ontology, track stage prefix for ontology, list ontology sources, import from registered source, pause source, resume source, deprecate source. Also handles legacy 'glossary source' phrasing."
parent_skill: business-ontology-workflow
---

# Source Management

## When to load

The builder wants to:
- Register a stage file or stage prefix as an ontology source
- List or review registered sources for a domain
- Run an import from a registered source
- Update a source's status or monitoring mode

Routed from `../../SKILL.md`. For a single-node creation or a one-shot bulk import, route to `../create/SKILL.md` or `../import/SKILL.md` respectively.

## Setup

Read once:
- `../../reference/API_CONTRACT_CRUD.md` — SYSTEM$ mutation signatures (used for domain creation in Step R2)

Script: `../../scripts/ontology_source_registry.py` — CRUD for the source registry.
Storage: `../../scripts/ontology_sources.yaml` — TEMPORARY schema template / seed. The live registry is stored in a Snowflake internal stage (`@DB.SCHEMA.ONTOLOGY_SOURCES/ontology_sources.yaml`); the script never reads from this local file at runtime. See `../../reference/NOT_IMPLEMENTED_YET.md` item 3.1. All access goes through the script so migration only changes one module.

`<SKILL_DIR>` is a placeholder the agent resolves.

---

## Intent: register source

**Triggers:** "register glossary source", "add stage file to glossary", "add source to <domain>", "track stage prefix for glossary", "add @MY_STAGE to Finance glossary"

### Step R1 — Accept the stage URI

If the builder provided a URI in the trigger, use it. Otherwise ask once:

```
What's the stage URI?
(e.g.  @MY_DB.MY_SCHEMA.MY_STAGE/glossary_terms.csv   ← a specific file
       @MY_DB.MY_SCHEMA.MY_STAGE/business_docs/        ← a folder prefix)
```

Validate shape: must start with `@`, contain at least `DB.SCHEMA.STAGE`, then optionally `/path`.

Infer type automatically:
- `stage_file` — path has a file extension (`.csv`, `.json`, `.pdf`, `.xlsx`, `.yaml`, etc.)
- `stage_prefix` — path ends with `/` or the last segment has no extension

The builder does not need to state the type explicitly.

### Step R2 — Associate with domain(s)

Determine the domain(s) for this source. A source can belong to **multiple domains** or be **generic** (applies to all).

**Detection logic** (do not ask if you can infer):
1. If the builder named domain(s) in the trigger ("add source to Finance", "register for Sales and Marketing") → use those
2. If the file name or path clearly implies a domain ("finance_terms.csv", "@DB.SCHEMA.STAGE/sales/") → suggest it: "This looks like it belongs to `<domain>` — correct? (yes / or type different domain(s))"
3. If unclear → ask once:

```
Is this source for specific domain(s) or generic (applies to all)?
(type domain name(s) comma-separated, or press enter for generic)
```

**Generic** = empty domains array. The source will be visible to Cortex Sense for every use case.

If a named domain does not exist yet, offer to create it:

```
Domain "Finance" does not exist yet. Create it and continue? (yes / no)
```

On **yes**:
```sql
CALL SYSTEM$CREATE_GLOSSARY_DOMAIN('<domain_name>');
```

Surface the feature-gate error once if Business Ontology is not enabled on the account.

### Step R3 — Persist the source reference

Build the domains JSON: `[{"name": "Finance", "id": ""}, {"name": "Sales", "id": ""}]` — or `[]` for generic.

Before writing, confirm with the builder:

```
Register this source?
  URI:      <stage_uri>
  Type:     <inferred type>
  Domains:  <domain list or "generic">
(yes / cancel)
```

On **yes**, run:

```bash
uv run --project <SKILL_DIR>/../.. python <SKILL_DIR>/../../scripts/ontology_source_registry.py \
    --connection <connection> add \
    "<stage_uri>" \
    --domains '<domains_json>' \
    --added-by "<current_user_if_known>"
```

**Error handling:**
- Exit code 1 + `"error"` containing "already registered" → the source exists. Surface: "This source is already registered (source_id: `<id>`). No action needed."
- Exit code 1 + `"error"` containing "Invalid stage URI" → bad format. Surface the error message and ask the builder to correct the URI.
- Any other non-zero exit → surface the error message plainly and stop. Do not retry.

On success, confirm to the builder:

```
Source registered:
  URI:     @MY_DB.MY_SCHEMA.MY_STAGE/glossary_terms.csv
  Type:    stage_file
  Domain:  Finance

Want to import nodes from it now? (yes / later)
```

On **yes** → jump to "Intent: import from registered source" (Step I2, skipping I1).

---

## Intent: import from registered source

**Triggers:** "import from registered source", "import from source", "run import for <domain>", or builder replies "yes" after registering a source

### Step I1 — Identify the source

Look up registered active sources for the named domain:

```bash
uv run --project <SKILL_DIR>/../.. python <SKILL_DIR>/../../scripts/ontology_source_registry.py \
    --connection <connection> get_by_domain "<domain_name>"
```

If multiple active sources exist, render a short list and ask which one to import:

```
Active sources for Finance:
  1  @MY_DB.MY_SCHEMA.MY_STAGE/glossary_terms.csv    (stage_file)  last imported: 2026-06-10
  2  @MY_DB.MY_SCHEMA.MY_STAGE/policies/              (stage_prefix) last imported: —

Which source? (number)
```

### Step I2 — Preview the file contents

```sql
-- CSV
SELECT $1 AS raw FROM <stage_uri>
  (FILE_FORMAT => (TYPE = CSV SKIP_HEADER = 1)) LIMIT 10;

-- JSON
SELECT PARSE_JSON($1) AS raw FROM <stage_uri>
  (FILE_FORMAT => (TYPE = JSON)) LIMIT 10;
```

Render up to 5 rows. Confirm: "Looks like N columns. Proceed with import? (yes / cancel)"

### Step I3 — Route to the import workflow

Pass the stage URI as the source and proceed through `../import/SKILL.md` from **Step 2A** onward (AI extraction → candidate review → draft/approve cycle). Skip `../import/SKILL.md` Step 1 — the source is already identified.

After a successful import, stamp the source:

```bash
uv run --project <SKILL_DIR>/../.. python <SKILL_DIR>/../../scripts/ontology_source_registry.py \
    --connection <connection> update "<source_id>" \
    --last-imported-at "<iso_timestamp>"
```

---

## Intent: list sources

**Triggers:** "list glossary sources", "what sources are registered", "show sources for <domain>"

```bash
uv run --project <SKILL_DIR>/../.. python <SKILL_DIR>/../../scripts/ontology_source_registry.py \
    --connection <connection> list [--domain "<domain_name>"] [--status active]
```

Render a compact table:

```
Registered sources:

  #   URI                                            Type          Domain     Status      Last imported
  1   @MY_DB.SCHEMA.STAGE/terms.csv                 stage_file    Finance    active      2026-06-10
  2   @MY_DB.DOCS.STAGE/business_rules/             stage_prefix  Sales      active      —
  3   @MY_DB.ARCHIVE.STAGE/old_terms.csv            stage_file    Finance    paused      2026-01-15

Commands: import #N · pause #N · resume #N · deprecate #N
```

---

## Intent: update source

**Triggers:** "pause source #N", "resume source", "deprecate source", numbers from the list above

Resolve the source_id from the row number shown in the list.

**pause / resume / deprecate:**

```bash
uv run --project <SKILL_DIR>/../.. python <SKILL_DIR>/../../scripts/ontology_source_registry.py \
    --connection <connection> update "<source_id>" --status <active|paused|deprecated>
```

**enable Cortex Sense scheduled enrichment:**

```bash
uv run --project <SKILL_DIR>/../.. python <SKILL_DIR>/../../scripts/ontology_source_registry.py \
    --connection <connection> update "<source_id>" --monitoring-mode sense_scheduled
```

`sense_scheduled` is a forward-looking marker for the automated ontology↔Cortex Sense
enrichment job (`../../reference/NOT_IMPLEMENTED_YET.md` Gap #4, owned by the Cortex Sense team). Until that
lands, the steward-driven enrichment path is `../phase-2-enrich/SKILL.md`.

Confirm the change, then re-render the list.

### Binding a node to a Semantic View

This is **not** a source-registry operation. A node↔Semantic View binding is a catalog
association created through `../phase-3-generate/SKILL.md` (`SYSTEM$DRAFT_GLOSSARY_ASSET`
with `refType=SEMANTIC_VIEW`, role `RELATED_SEMANTIC_VIEW`). If the builder asks to attach a
Semantic View, route there — the registry deliberately stores no `semantic_view_fqn`.

---

## What this skill never does

- Copy or cache file bytes into the registry or any local state file
- Validate the semantic content of a stage file before registering it (that happens at import time)
- Delete source entries — use `deprecated` status instead; the registry is an append-only audit trail
- Ask for Snowflake credentials — source URIs use the current session context
- Block or prompt the builder with storage-layer details (YAML path, backend storage status, etc.)
