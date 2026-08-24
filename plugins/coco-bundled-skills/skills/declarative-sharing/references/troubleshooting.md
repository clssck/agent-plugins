# Native Apps Troubleshooting

## Declarative Sharing Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `schema shares udfs or stored procedures along with views or tables` | Mixed shared-by-copy and shared-by-reference in same schema | Move agents/UDFs/procedures to one schema, tables/views/semantic views to another |
| Objects work in provider, fail in consumer | Wrong schema layout | Separate shared-by-copy vs shared-by-reference objects into different schemas |
| Version not updating for consumers | Provider hasn't released, or app hasn't been upgraded | Provider: upload updated manifest, then `ALTER APPLICATION PACKAGE <PKG> RELEASE LIVE VERSION`. Then run `ALTER APPLICATION <APP> UPGRADE` on any existing installed app (works for both provider test apps and consumer apps). Do not use `BUILD` alone — it validates but does not publish |
| Consumer can't see shared objects | Objects missing from manifest | Verify all objects are listed in manifest with correct schema paths |
| `CREATE APPLICATION PACKAGE` fails with privilege error | Missing privilege on current role | Run `GRANT CREATE APPLICATION PACKAGE ON ACCOUNT TO ROLE <ROLE>` — check this BEFORE starting the workflow |
| Mixed BUILD and RELEASE commands cause confusion | Using `ALTER ... BUILD` expecting it to publish | `BUILD` only validates the manifest — it does NOT commit or publish. To publish, use `RELEASE LIVE VERSION` after BUILD succeeds |
| `write` tool not available / cannot create manifest | Running CoCo Web outside of Workspaces | Recommend user open a Workspace (Projects > Workspaces in Snowsight). If they decline, use the temporary stage method: `COPY INTO @stage/manifest.yml FROM (SELECT $$<yaml>$$) FILE_FORMAT = (TYPE=CSV COMPRESSION=NONE FIELD_OPTIONALLY_ENCLOSED_BY=NONE ESCAPE=NONE ESCAPE_UNENCLOSED_FIELD=NONE) SINGLE=TRUE OVERWRITE=TRUE`, then `COPY FILES INTO snow://package/.../ FROM @stage FILES=('manifest.yml')` |
| Manifest YAML corrupted with backslashes or quotes | Wrong file format when using stage method | Must set all four params: `COMPRESSION=NONE`, `FIELD_OPTIONALLY_ENCLOSED_BY=NONE`, `ESCAPE=NONE`, `ESCAPE_UNENCLOSED_FIELD=NONE`. Use `$$` dollar-quoting for the YAML string, not single quotes |

## Workspace Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `The field workspaces is currently not supported in the application manifest` | Workspace support is not active on this deployment | Workspace sharing is expected to be available. If you hit this, the deployment is behind — `ACCOUNTADMIN` cannot change it, so contact Snowflake. Do NOT silently fall back to deprecated legacy notebooks |
| Consumer can't access workspace files | Missing roles in manifest | Verify workspace has correct `roles:` list matching defined app roles |
| Workspace not visible after install | Manifest `source` path doesn't match uploaded file paths | Ensure files are uploaded to `snow://package/<PKG>/versions/LIVE/<source_path>/` exactly matching the manifest's `source:` value |
| `source` validation error — does not end with `/` | Source path missing trailing slash | Source MUST end with `/` (e.g., `content/folder/` not `content/folder`) |
| `source` validation error — starts with `/` | Source path has leading slash | Source MUST NOT start with `/` (e.g., `content/folder/` not `/content/folder/`) |
| `source` directory has no files error | Source path uploaded without any files | Upload at least one file to the source path before BUILD/RELEASE |
| Role not defined error | Workspace references a role not in top-level `roles:` | Ensure all roles referenced in workspace are declared in the manifest's top-level `roles:` section |
| Consumer can't modify workspace files | Expected behavior | Shared workspaces are read-only for consumers — they can view/download but not modify, commit, or upload |
| `PUT` to shared workspace fails on consumer | Expected behavior | Consumers cannot write to shared workspaces. This is by design for data integrity |
| Workspace files not appearing after release | Files not uploaded before release | Upload all workspace files to the package version BEFORE running `RELEASE LIVE VERSION`. Verify with `LIST snow://package/<PKG>/versions/LIVE/` |
| .pdf file blocked error | .pdf files are not supported in workspaces | Remove .pdf files; convert to another format if needed |
| Notebook can't access external tables/databases | Notebooks run in Restricted Caller's Rights (RCR) | Notebooks can ONLY access objects shared by the application. Ensure the required tables/views are in the manifest's `shared_content`. Use `SCHEMA.OBJECT` references (the app is the default database) |
| Notebook SQL uses FQN and fails | Application is the default database for notebook sessions | Use `SCHEMA.OBJECT` format (e.g., `DATA_SCHEMA.MY_TABLE`), NOT `DB.SCHEMA.OBJECT`. The app IS the database |
| **`RM` reports `0 rows affected` but the file is still in the package** | **Uppercase `LIVE` in the `RM` path — silently no-ops** | **`RM` requires lowercase `live`: `RM snow://package/<PKG>/versions/live/<file>`. A successful removal returns a row with `result = removed`. Uppercase `LIVE` deletes nothing and raises no error. `PUT`/`GET`/`LIST` are unaffected and accept uppercase.** |
| Duplicate `.ipynb` files after migrating notebooks to a workspace | Notebooks copied into the workspace `source` dir but the originals left at the package root | Remove the root copies with `RM snow://package/<PKG>/versions/live/<file>` (lowercase `live`), then `LIST` to confirm |

## Legacy Notebook Issues (DEPRECATED — use workspaces for next-gen notebooks)

**Legacy notebooks are deprecated.** They still work today but will be removed in a future release. For new work, use workspaces instead. The issues below apply to existing packages using `application_content.notebooks`.

| Issue | Cause | Fix |
|-------|-------|-----|
| **SQL cells show syntax errors / interpreted as Python (MOST COMMON)** | **Missing `"metadata": {"language": "sql"}` on code cells** | **Every code cell MUST have `"metadata": {"language": "sql"}` or `"metadata": {"language": "python"}`. Without this, cells default to Python and SQL will not execute. Verify EVERY cell after generating a notebook.** |
| **Cell shows raw `%%sql -r dataframe_1` text instead of executing** | **Jupyter magic `%%sql` in cell source** | **Shared app notebooks do NOT run in a Workspace Jupyter kernel. Remove ALL `%%sql`, `%%sql -r dataframe_N`, and other magic prefixes from cell source. Set language via `"metadata": {"language": "sql"}` instead.** |
| Notebook can't access provider's source data | Notebooks can only access data within the same app package | This is expected — notebooks are scoped to the application. Use `SCHEMA.TABLE` references (no database prefix) |
| Notebook shows "connecting" but never loads | Missing EAI or warehouse configuration | Consumer needs an active warehouse; verify notebook runtime settings |

## Cortex Agent Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| **`CREATE CORTEX AGENT` fails with syntax error** | **Wrong DDL command (MOST COMMON)** | **Correct syntax is `CREATE AGENT` — the word CORTEX is NOT part of the command. Do not analogize from `CREATE CORTEX SEARCH SERVICE`.** |
| **Agent tools fail / no results / "empty execution environment"** | **`execution_environment` missing or wrong (MOST COMMON)** | **ALL tool types that run queries (Analyst, UDF, procedure) require `execution_environment: {type: "warehouse", warehouse: ""}`. The empty string is correct — the consumer's default warehouse resolves at runtime. Generic tools (UDF/procedure) FAIL HARD without it; Analyst tools silently return no results. Cortex Search is the only tool type that does NOT need execution_environment (uses max_results instead).** |
| Agent works at creation but fails when invoked provider-side | `warehouse: ""` can't resolve on provider | This is expected — `warehouse: ""` resolves to the consumer's default warehouse at install time. Provider-side testing requires setting a real warehouse. Test in consumer account or UI after sharing. |
| `Unknown user-defined function` on consumer | Using FQN with database prefix (`DB.SCHEMA.OBJECT`) in agent tool_resources | UDFs/procedures MUST use relative identifier: `SCHEMA.OBJECT` (NEVER include the database). Snowflake resolves the database automatically in the installed app context |
| **UDF/procedure "object does not exist" on consumer** | **FQN (DB.SCHEMA.TABLE) inside the UDF/procedure body** | **The SQL body of UDFs and procedures MUST use relative references (`SCHEMA.TABLE`), NEVER FQN (`MY_DB.SCHEMA.TABLE`). The provider's database name does not exist on the consumer — the app name IS the database.** |
| Tool call error 370001 | Nested objects in input_schema | Flatten to primitive types only (string, number, boolean) |
| Tool call error 370001 with semantic view | Semantic view has verified_queries with FQN references | Remove verified_queries or use table aliases only (no FQN) |
| Consumer 404 on agent REST API | Wrong database in URL | Use APPLICATION NAME as database, not source database |
| Search tool not working | Limited declarative sharing support | Cortex Search has limited support in declarative shares |
| Agent can't be granted to share | Agent has tools in different database | All agent tool_resources must be in same database as agent |

## Manifest Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Function not found in consumer | Missing parameter types | Include types in manifest: `my_func(VARCHAR, NUMBER):` |
| Semantic view not accessible | Missing from manifest | Include ALL dependencies the agent references |

## Diagnostic Commands

```sql
-- Check package grants
SHOW GRANTS TO APPLICATION PACKAGE <PKG>;

-- Check what's in the share
DESCRIBE APPLICATION PACKAGE <PKG>;

-- Verify manifest uploaded
LIST snow://package/<PKG>/versions/LIVE/;

-- Check versions
SHOW VERSIONS IN APPLICATION PACKAGE <PKG>;
```

## Consumer-Side Troubleshooting

### REST API Testing

**Recommended: Always try the Snowflake UI first** before resorting to REST API. The UI provides better error messages and is easier to debug.

If you need REST API testing, common issues include:

| Issue | Cause | Fix |
|-------|-------|-----|
| 401 Unauthorized | Invalid or expired PAT | Generate new PAT, verify token type header |
| 404 Not Found | Wrong endpoint or object path | Verify application name, schema, and object name |
| 390142 Invalid payload (REST API) | Wrong message format | REST API Agent: `"content": "string"`. REST API Analyst: `"content": [{"type": "text", "text": "..."}]` |
| `Request is malformed` (SQL `DATA_AGENT_RUN`) | Wrong content format in SQL function | `DATA_AGENT_RUN` requires array format: `"content": [{"type": "text", "text": "..."}]` — plain string `"content": "string"` FAILS (unlike REST API which accepts strings) |
| Response has warnings about verified_queries | FQN references in verified_queries | Expected behavior - Analyst removes problematic queries but continues |

### REST API Debugging

For REST API endpoint URLs and curl examples, see:
- Agent API: `POST /api/v2/cortex/agent:run` — content is a plain string
- Analyst API: `POST /api/v2/cortex/analyst/message` — content must be `[{"type": "text", "text": "..."}]`
- Auth: use PAT with `X-Snowflake-Authorization-Token-Type: PROGRAMMATIC_ACCESS_TOKEN`
- Host: check `~/.snowflake/connections.toml` or `SELECT CURRENT_ACCOUNT_URL();`
