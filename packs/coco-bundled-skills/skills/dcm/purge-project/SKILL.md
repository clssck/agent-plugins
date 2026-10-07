---
name: purge-project
description: "Drops all Snowflake objects managed by a DCM project. DANGEROUS: irreversible data loss. Triggers: purge project, drop all objects in project, user confirms purge after drop-project prompt"
---

# Purge DCM Project

## Overview

`snow dcm purge` drops **every Snowflake object managed by a DCM project** — tables, views, dynamic tables, tasks, warehouses, roles, schemas, and any other object the project owns. The DCM project registration itself **remains** after purge (use `snow dcm drop` afterward if you also want to remove the project metadata).

> **🚨 THIS IS IRREVERSIBLE.** Purging a project drops all managed objects and their data permanently. There is no automatic rollback. This should only be done when intentionally starting over or fully decommissioning a project.

---

## Purge Workflow

### Step 1: Enumerate Managed Objects

Before showing the confirmation, you MUST build a list of all objects that will be destroyed. Try these in order:

**Option A — local project files exist:** Run `raw-analyze` to get the exact set of managed objects:

```bash
snow dcm raw-analyze <identifier> -c <connection> [--target <target>]
```

Parse the JSON output and extract every object definition. Use this list for the warning.

**Option B — no local project files (e.g., `manifest.yml` not found):** Query Snowflake directly for the project's managed objects:

```bash
snow sql -c <connection> -q "SHOW ENTITIES IN DCM PROJECT <DB>.<SCHEMA>.<PROJECT>"
```

Use the results to build the object list.

If all enumeration attempts fail, report the error and do not proceed. The user needs to know what will be destroyed before confirming.

### Step 2: Present Danger Warning and Request Confirmation

Present this warning with the full object list populated:

```
╔══════════════════════════════════════════════════════════════╗
║                🚨 PURGE — POINT OF NO RETURN 🚨              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║ You are about to PERMANENTLY DROP all objects managed by:    ║
║                                                              ║
║   Project:    <DATABASE.SCHEMA.PROJECT_NAME>                 ║
║   Connection: <connection_name>                              ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║ Objects that will be PERMANENTLY DESTROYED:                  ║
║                                                              ║
║   🚨 Tables (and all data):                                  ║
║      • <list each table>                                     ║
║   🚨 Dynamic Tables (and all computed data):                 ║
║      • <list each>                                           ║
║   ⚠️  Views:                                                   ║
║      • <list each>                                           ║
║   ⚠️  Tasks:                                                  ║
║      • <list each>                                           ║
║   ⚠️  Other objects (warehouses, roles, schemas, etc.):      ║
║      • <list each>                                           ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║ ⚠️  DATA LOSS WARNING:                                        ║
║    • All table and dynamic table data will be deleted        ║
║    • This cannot be undone automatically                     ║
║    • Dependent objects outside this project may break        ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║ Type "yes" to confirm purge, or "no" to cancel.              ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

**DO NOT PROCEED unless the user explicitly confirms with "yes" (or "Yes" / "YES").** Any other response cancels the purge.

### Step 3: Execute Purge

Always pass `--force` so the CLI does not re-prompt (you have already obtained confirmation from the user):

```bash
snow dcm purge <identifier> -c <connection> --force [--target <target>]
```

Report success or failure. If the command fails partway through, inform the user that some objects may have already been dropped and they should check Snowflake directly.

---

## When to Use Purge

- Starting over on a project (clean slate)
- Fully decommissioning a project and its data
- Tearing down a dev/test environment

## When NOT to Use Purge

- If the user only wants to remove the DCM project metadata (use `snow dcm drop` instead)
- If the user wants to selectively remove specific objects (modify definitions and deploy)
