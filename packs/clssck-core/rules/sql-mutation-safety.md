---
description: Check target, authorization, and recovery before destructive SQL or migration execution
condition:
  - '(?i)(?:^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*|\bcommand(?:\\?["''])?\s*[:=]\s*(?:\\?["''\x60])(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*)(?:psql|mysql|mariadb|sqlite3|duckdb|snowsql|sqlcmd|snow[ \t]+sql)(?=[ \t])(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|''[^''\n]*''|[^\s;&|()''"#]+))*?[ \t]+(?:(?:--(?:command|execute|query)|-[ceq])(?:=|[ \t]*))?(?:\\?["''\x60])(?:\s|\\[nrt])*(?:(?:[^"''\x60\\\r\n]|\\.)*?;(?:\s|\\[nrt])*)?\b(?:DELETE(?:\s|\\[nrt])+FROM\b|UPDATE(?:\s|\\[nrt])+[^;\r\n]+?(?:\s|\\[nrt])+SET\b|MERGE(?:\s|\\[nrt])+INTO\b|TRUNCATE(?:\s|\\[nrt])+(?:TABLE\b|[\w"\x60\[])|DROP(?:\s|\\[nrt])+(?:TABLE|SCHEMA|DATABASE|VIEW|INDEX|SEQUENCE|TYPE|FUNCTION|PROCEDURE|MATERIALIZED(?:\s|\\[nrt])+VIEW)\b|ALTER(?:\s|\\[nrt])+TABLE\b[^;\r\n]*?(?:\s|\\[nrt])+(?:DROP|ALTER|MODIFY|CHANGE)\b|(?:REPLACE|INSERT(?:\s|\\[nrt])+OR(?:\s|\\[nrt])+REPLACE)(?:\s|\\[nrt])+INTO\b)'
  - '(?i)(?:^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*|\bcommand(?:\\?["''])?\s*[:=]\s*(?:\\?["''\x60])(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*)(?:(?:(?:uv|poetry)[ \t]+run[ \t]+|python3?[ \t]+-m[ \t]+)?alembic(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|''[^''\n]*''|[^\s;&|()''"#]+))*?[ \t]+downgrade(?=\s|$|[;&|)]|\\?["'']\s*[,}])|(?:(?:npx|bunx)(?:[ \t]+(?:-y|--yes))?[ \t]+|pnpm[ \t]+(?:exec[ \t]+)?|npm[ \t]+exec[ \t]+(?:--[ \t]+)?)?prisma(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|''[^''\n]*''|[^\s;&|()''"#]+))*?[ \t]+migrate[ \t]+reset(?=\s|$|[;&|)]|\\?["'']\s*[,}])|flyway(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|''[^''\n]*''|[^\s;&|()''"#]+))*?[ \t]+clean(?=\s|$|[;&|)]|\\?["'']\s*[,}])|(?:bundle[ \t]+exec[ \t]+)?rails(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|''[^''\n]*''|[^\s;&|()''"#]+))*?[ \t]+db:drop(?=\s|$|[;&|)]|\\?["'']\s*[,}])|(?:(?:npx|bunx)(?:[ \t]+(?:-y|--yes))?[ \t]+|pnpm[ \t]+(?:exec[ \t]+)?|npm[ \t]+exec[ \t]+(?:--[ \t]+)?)?sequelize(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|''[^''\n]*''|[^\s;&|()''"#]+))*?[ \t]+db:migrate:undo:all(?=\s|$|[;&|)]|\\?["'']\s*[,}]))'
  - '(?i)(?:\b(?:query|execute|exec|run|prepare|executemany|executescript|raw|sql)|\$(?:queryRawUnsafe|executeRawUnsafe))(?:\s*\(\s*(?:text\(\s*)?[rbuf]{0,2}(?:\\?["''\x60]){1,3}|\x60)(?:\s|\\[nrt])*(?:(?:[^"''\x60\\\r\n]|\\.)*?;(?:\s|\\[nrt])*)?\b(?:DELETE(?:\s|\\[nrt])+FROM\b|UPDATE(?:\s|\\[nrt])+[^;\r\n]+?(?:\s|\\[nrt])+SET\b|MERGE(?:\s|\\[nrt])+INTO\b|TRUNCATE(?:\s|\\[nrt])+(?:TABLE\b|[\w"\x60\[])|DROP(?:\s|\\[nrt])+(?:TABLE|SCHEMA|DATABASE|VIEW|INDEX|SEQUENCE|TYPE|FUNCTION|PROCEDURE|MATERIALIZED(?:\s|\\[nrt])+VIEW)\b|ALTER(?:\s|\\[nrt])+TABLE\b[^;\r\n]*?(?:\s|\\[nrt])+(?:DROP|ALTER|MODIFY|CHANGE)\b|(?:REPLACE|INSERT(?:\s|\\[nrt])+OR(?:\s|\\[nrt])+REPLACE)(?:\s|\\[nrt])+INTO\b)'
scope:
  - tool:bash
  - tool:eval
interruptMode: tool-only
---

# SQL mutation safety

Before executing SQL that deletes or overwrites existing persistent data, or removes or narrows an existing schema:

- Establish the target connection, environment, database, and schema without exposing credentials.
- Match the operation and affected data to the user's authorization. Ask only when authorization or consequential scope remains unclear; do not demand redundant confirmation.
- Before UPDATE, DELETE, or MERGE, establish the intended affected rows. Use a read-only preview where practical; a WHERE clause alone does not prove the scope is correct.
- Before DROP, TRUNCATE, or destructive ALTER, establish an appropriate recovery path or explicitly authorized acceptance of irreversible loss. Do not assume DDL can be rolled back; transaction behavior varies by database engine and operation.
- Prefer the narrowest operation that fulfills the request. Do not replace a targeted repair with a table-wide reset.
- Verify the resulting row changes or schema state; report what was actually checked and any recovery limitations.

Apply the same checks to destructive migration commands. Inspect what the selected downgrade/reset/clean operation will do before running it.

Disposable databases created solely for this task need no additional confirmation when their ownership and isolation are clear. A read-only query or inert example does not become a mutation merely because this reminder matched.

This reminder matches literal command and code text only. Computed queries, SQL from files or heredocs, ORM-generated mutations, and database/MCP tool calls get the same checks even though they never trigger it.
