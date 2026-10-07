---
name: cld-create-database
description: "Create and execute catalog-linked database SQL"
parent_skill: catalog-linked-database
---

# Create Catalog-Linked Database

Generate and execute SQL to create the catalog-linked database.

## When to Load

From main skill Step 3: After configuration gathered and approved in `setup/SKILL.md`.

## Prerequisites

Must have from setup phase:
- Catalog integration name (verified, REST-based)
- Database name
- External volume (if not vended credentials)
- Namespace filtering (ALLOWED_NAMESPACES/BLOCKED_NAMESPACES lists, if any)
- Case sensitivity setting (CASE_INSENSITIVE or CASE_SENSITIVE)
- Nested namespace mode (IGNORE_NESTED_NAMESPACE or FLATTEN_NESTED_NAMESPACE)
- Namespace flatten delimiter (if FLATTEN_NESTED_NAMESPACE mode selected)
- Write mode (NONE or ALL)
- Sync interval (seconds)

---

## Workflow

### Step 2.1: Generate SQL

Build the CREATE DATABASE statement based on collected prerequisites.

**Base SQL (vended credentials)**:
```sql
CREATE DATABASE <database_name>
  LINKED_CATALOG = (
    CATALOG = '<catalog_integration>'
  );
```

**With external volume**:
```sql
CREATE DATABASE <database_name>
  LINKED_CATALOG = (
    CATALOG = '<catalog_integration>'
  )
  EXTERNAL_VOLUME = '<external_volume>';
```

**Full options template**:
```sql
CREATE DATABASE <database_name>
  LINKED_CATALOG = (
    CATALOG = '<catalog_integration>'
    [ALLOWED_NAMESPACES = (<comma-separated list>)]
    [BLOCKED_NAMESPACES = (<comma-separated list>)]
    [ALLOWED_WRITE_OPERATIONS = {NONE | ALL}]
    [NAMESPACE_MODE = {IGNORE_NESTED_NAMESPACE | FLATTEN_NESTED_NAMESPACE}]
    [NAMESPACE_FLATTEN_DELIMITER = '<delimiter>']
    [SYNC_INTERVAL_SECONDS = <value>]
  )
  [EXTERNAL_VOLUME = '<external_volume>']
  [CATALOG_CASE_SENSITIVITY = {CASE_SENSITIVE | CASE_INSENSITIVE}];
```

---

### Step 2.2: Review & Approval

**Present generated SQL**:

```
Generated CREATE DATABASE SQL:
═══════════════════════════════════════════════════════════
<complete SQL statement with actual values>
═══════════════════════════════════════════════════════════

This will create a catalog-linked database:
- Database: <database_name>
- Catalog Integration: <catalog_integration>
- External Volume: <volume_name|Not required (vended credentials)>
- Namespace Filtering: <All|ALLOWED: x,y|BLOCKED: x,y>
- Case Sensitivity (namespaces/tables): <CASE_INSENSITIVE|CASE_SENSITIVE>
- Nested Namespaces: <IGNORE_NESTED_NAMESPACE|FLATTEN_NESTED_NAMESPACE>
- Namespace Flatten Delimiter: <Not applicable|'X'>
- Write Mode: <Read-only (NONE)|Writable (ALL)>
- Sync Interval: <X> seconds
```

**⚠️ MANDATORY STOPPING POINT**:

"Please review the SQL above. Ready to execute and create the catalog-linked database?"

**Wait for explicit approval**:
- "Yes" / "Approved" / "Looks good" → Continue to Step 2.3
- "No" / "Wait" → Ask: "What changes would you like to make?"
- "Edit" → Ask for specific modifications

---

### Step 2.3: Execute Creation

**Execute approved SQL**:
```sql
<approved CREATE DATABASE statement>
```

**Expected Success**:
```
Database <database_name> successfully created.
```

**If Success** → Continue to Step 2.4

**If Error** → Present error, load `references/troubleshooting.md`

---

### Step 2.4: Initial Sync Check

**Wait a few seconds for initial sync**, then check status:

```sql
SELECT SYSTEM$CATALOG_LINK_STATUS('<database_name>');
```

**Parse response** (JSON):
- `executionState`: `RUNNING` (next sync scheduled/executing) or `FAILED` (error occurred)
- `failureDetails`: Array of entity sync failures - **empty array means healthy**

**Present initial status**:
```
Initial Sync Status:
═══════════════════════════════════════════════════════════
Database: <database_name>
Execution State: <RUNNING|FAILED>
Failure Details: <None|List of failures>
═══════════════════════════════════════════════════════════
```

**If executionState is RUNNING and failureDetails is empty**: "Sync is healthy. Tables will appear as they are discovered."

**If FAILED or failureDetails has entries**: Present failure details, recommend troubleshooting.

---

## Output

Successfully created catalog-linked database, ready for verification.

## Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Catalog integration not found` | Invalid integration name | Verify name with `SHOW CATALOG INTEGRATIONS` |
| `Insufficient privileges` | Missing CREATE DATABASE | Grant privilege to role |
| `External volume required` | Catalog doesn't support vended credentials | Provide external volume |
| `Invalid namespace` | Namespace doesn't exist in catalog | Check namespace names in remote catalog |

## Next Steps

After successful creation:
→ **Continue** to `../SKILL.md` Step 4: Verification
→ **Load** `verify/SKILL.md`
