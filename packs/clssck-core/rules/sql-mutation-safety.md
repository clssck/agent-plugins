---
description: Check target, authorization, and recovery before destructive SQL or migration execution
condition:
  - '(?i)\b(?:delete\s+from|update\s+\S+\s+set|merge\s+into|truncate\s+(?:table\s+)?["`\[]?\w+|drop\s+(?:table|schema|database|view|index|sequence|type|function|procedure|materialized\s+view)|alter\s+table\b[^;\n]*\b(?:drop|alter|modify|change)|(?:replace|insert\s+or\s+replace)\s+into)\b'
  - '\b(?:rails|rake)\s+db:(?:drop|reset|rollback|purge|schema:load|migrate:reset)\b'
  - '\b(?:alembic\s+downgrade|prisma\s+(?:migrate\s+reset|db\s+push\b[^\n;&|]*--force-reset)|flyway\s+clean|sequelize\s+db:(?:drop|migrate:undo))\b'
scope: "tool"
interruptMode: tool-only
---

This rule watches every tool argument, including direct SQL and MCP connector calls; tool names and server prefixes vary by installation. Match the SQL operation, not a hard-coded connector name.

Before running SQL that deletes or overwrites persistent data, or drops or narrows a schema, establish target, scope, and recovery.

## Target and authorization

- Establish the target connection, environment, database, and schema without exposing credentials.
- Match the operation and affected data to the user's authorization. Ask only when authorization or consequential scope remains unclear; NEVER demand redundant confirmation.

## UPDATE, DELETE, MERGE

Before UPDATE, DELETE, or MERGE, establish the intended affected rows. Use a read-only preview where practical; a WHERE clause alone does not prove the scope is correct.

```sql
-- Bad: WHERE clause alone, scope unverified
DELETE FROM orders WHERE status = 'stale';

-- Good: preview the affected rows, then mutate
SELECT count(*) FROM orders WHERE status = 'stale';
SELECT id, status, updated_at FROM orders WHERE status = 'stale' LIMIT 20;
DELETE FROM orders WHERE status = 'stale';
```

## DROP, TRUNCATE, destructive ALTER

Before DROP, TRUNCATE, or destructive ALTER, establish an appropriate recovery path or explicitly authorized acceptance of irreversible loss. NEVER assume DDL can be rolled back; transaction behavior varies by database engine and operation.

## Narrowest operation

SHOULD use the narrowest operation that fulfills the request. NEVER replace a targeted repair with a table-wide reset.

```sql
-- Bad: table-wide reset to fix one row
TRUNCATE TABLE users;

-- Good
UPDATE users SET email = 'ada@example.com' WHERE id = 42;
```

## Migrations

Apply the same checks to destructive migration commands. Inspect what the selected downgrade/reset/clean operation will do before running it.

```bash
# Good — inspect current state and target before downgrading
alembic current
alembic history --verbose
alembic downgrade -1
```

## After running

Verify the resulting row changes or schema state; report what was actually checked and any recovery limitations.

## Exceptions

- Disposable databases created solely for this task need no additional confirmation when their ownership and isolation are clear.
- A read-only query or inert example does not become a mutation merely because this reminder matched.
