---
name: cld-setup-prerequisites
description: "Gather configuration options for catalog-linked database setup"
parent_skill: catalog-linked-database
---

# CLD Configuration Gathering

Collect configuration options to create a catalog-linked database.

## When to Load

From main skill Create Workflow → Step 2: After prerequisite checks (catalog integration and external volume) are verified.

## Prerequisites (Already Verified)

From main skill Step 1, you should already have:
- ✓ Catalog integration name (verified, REST-based)
- ✓ External volume name (if not using vended credentials)

---

## Workflow

> Note: Step numbers continue from main skill's Step 1 (Prerequisites).

**IMPORTANT**: Ask each question explicitly and wait for user response before proceeding to the next step. Do not skip any steps.

---

### Step 2.1: Database Name

**Ask**:
```
What would you like to name your catalog-linked database?

Guidelines:
- Alphanumeric characters and underscores
- Must be unique in your account
```

**Record**: Database name

---

### Step 2.2: Namespace Filtering

**Ask**:
```
Would you like to filter which namespaces are synced?

A: Sync all namespaces (default)

B: Allow specific namespaces only (ALLOWED_NAMESPACES)
   → Only syncs the specified namespaces and their nested content
   
C: Block specific namespaces (BLOCKED_NAMESPACES)
   → Syncs all namespaces EXCEPT those specified

Note: You can use both ALLOWED and BLOCKED together.
      BLOCKED takes precedence (e.g., if ns1.ns2 is allowed but ns1 is blocked, ns1.ns2 won't sync).

Would you like me to list the available namespaces from your catalog first?
```

**If user wants to list namespaces**:
```sql
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<catalog_integration>');
```

**If A** → No filtering, continue

**If B** → **Ask**: "Which namespaces should be allowed? (comma-separated)"
- Record: ALLOWED_NAMESPACES list

**If C** → **Ask**: "Which namespaces should be blocked? (comma-separated)"
- Record: BLOCKED_NAMESPACES list

---

### Step 2.3: Case Sensitivity (for Namespaces/Schemas and Tables)

**Ask**:
```
What case sensitivity does your external catalog use for identifiers?

A: Case-insensitive (Unity Catalog, AWS Glue) [Default]
   → For querying: No double quotes needed, case doesn't matter
   → For DDL (CREATE/ALTER): Must use double-quoted identifiers

B: Case-sensitive (OpenCatalog/Polaris)
   → For querying: Use double quotes to match exact case from catalog
   → Unquoted identifiers are auto-converted to uppercase by Snowflake
```

**Record**: CATALOG_CASE_SENSITIVITY = CASE_INSENSITIVE (default) or CASE_SENSITIVE

**Note to user**:
```
Case sensitivity affects how you interact with tables in Snowflake:

CASE_INSENSITIVE (default - Glue, Unity):
  Querying:
    SELECT * FROM mytable;        -- Works
    SELECT * FROM MYTABLE;        -- Works (same table)
  DDL commands (CREATE ICEBERG TABLE, ALTER, etc.):
    Must use double-quoted identifiers

CASE_SENSITIVE (OpenCatalog/Polaris):
  Querying:
    SELECT * FROM "MyTable";      -- Use double quotes to match exact case
    SELECT * FROM mytable;        -- Converted to MYTABLE, may not match catalog
  If your catalog has lowercase names, you must use double quotes:
    SELECT * FROM "mytable";
```

---

### Step 2.4: Nested Namespaces

**Ask**:
```
Does your catalog have nested namespaces?

A: No / Ignore nested namespaces (default)
B: Yes, flatten nested namespaces

Note: Nested namespaces appear as: ns1.ns2.ns3
```

**If A** → Record: NAMESPACE_MODE = IGNORE_NESTED_NAMESPACE

**If B** → **Ask**: "What delimiter should separate flattened namespace levels? (e.g., / or _)"
- Record: NAMESPACE_MODE = FLATTEN_NESTED_NAMESPACE
- Record: NAMESPACE_FLATTEN_DELIMITER = '<delimiter>'

**Note**: The delimiter character cannot appear in your namespace names.

---

### Step 2.5: Write Mode

**Ask**:
```
Should the catalog-linked database be writable?

A: Writable (ALLOWED_WRITE_OPERATIONS = ALL) [Default]
   → Can create/drop tables from Snowflake.
   ⚠️ WARNING: DROP TABLE in Snowflake propagates to remote catalog,
      removing the table AND data from both systems.

B: Read-only (ALLOWED_WRITE_OPERATIONS = NONE)
   → Safer. Cannot create, update, or drop tables from Snowflake.
```

**Record**: ALLOWED_WRITE_OPERATIONS = ALL (default) or NONE

---

### Step 2.6: Sync Interval

**Ask**:
```
How often should Snowflake check for new/dropped tables in the remote catalog?

This controls namespace and table DISCOVERY, not data refresh frequency.
(Data refresh is controlled by REFRESH_INTERVAL_SECONDS on the catalog integration.)

Default: 30 seconds
Range: 30 to 86400 (1 day)

Enter seconds, or press Enter for default (30):
```

**Record**: SYNC_INTERVAL_SECONDS (default 30)

---

### Step 2.7: Configuration Summary

**Present checklist**:

```
CLD Configuration Summary
═══════════════════════════════════════════════════════════

From Prerequisites:
✓ Catalog Integration: <integration_name>
✓ External Volume: <volume_name|Not required (vended credentials)>

CLD Settings:
✓ Database Name: <database_name>
✓ Namespace Filtering: <All|ALLOWED: x,y|BLOCKED: x,y>
✓ Case Sensitivity (namespaces/tables): <CASE_INSENSITIVE|CASE_SENSITIVE>
✓ Nested Namespaces: <IGNORE_NESTED_NAMESPACE|FLATTEN_NESTED_NAMESPACE>
✓ Namespace Flatten Delimiter: <Not applicable|'X'>
✓ Write Mode: <NONE (Read-only)|ALL (Writable)>
✓ Sync Interval: <X> seconds

═══════════════════════════════════════════════════════════
```

**⚠️ MANDATORY STOPPING POINT**: "Does everything look correct? Ready to create the catalog-linked database?"

- If yes → **Continue** to `../SKILL.md` Step 3 → **Load** `create/SKILL.md`
- If changes needed → Ask what to update

---

## Output

Validated configuration ready for database creation.

## Next Steps

After user confirms:
→ **Continue** to `../SKILL.md` Step 3: Create Database
→ **Load** `create/SKILL.md`
