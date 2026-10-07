# Agent spec — wiring an agent to a Cortex Sense context

Single contract for the agent object that consumes a built Cortex Sense context. Used by `agent/SKILL.md` for both modes (create a new agent, retrofit an existing one). The generic agent lifecycle — versioning, aliases, profile, deletion — belongs to the `cortex-agent` skill family; this file covers **only** what is specific to Cortex Sense.

Everything below was verified against a live account. Where it contradicts general agent documentation, the verified behaviour wins — note the date of verification when you change it.

## The minimal spec

One flag. That is the whole integration.

```yaml
models:
  orchestration: auto

experimental:
  EnableCortexSense: true

instructions:
  orchestration: '<derived — see agent/SKILL.md §4a>'
  response: '<derived — see agent/SKILL.md §4a>'
```

`EnableCortexSense: true` is the only key required, and the only key this skill ever adds. Do not add `EnableStandaloneExecuteSqlTool`, `FallbackWarehouse`, or any other experimental key — see "Flags you do not need" below for why each is unnecessary.

## Tool inventory

An agent whose spec is the minimal one above — `EnableCortexSense: true`, no `tools[]` at all — has this tool inventory. None of them are declared in the spec.

Attribution is verified by a no-flag control (an agent with no `experimental` block at all), so the two columns are exact:

| Tool | Source | What it does | Notes for the orchestration prompt |
|---|---|---|---|
| `cortex_sense` | **added by the flag** | Retrieves context documents. The reason the flag exists. | The mandatory first call. Parameters in "Calling cortex_sense". |
| `system_execute_sql` | **added by the flag** | Executes SQL against **arbitrary physical tables** — no semantic view or semantic model required. | The answer path. Runs with an empty `execution_environment` by default. |
| `table_details` | platform default | Column-level metadata for named tables. Takes a `tableNames` array. | Present with or without the flag. **Can return fewer tables than requested without erroring** — see the caveat below. |
| `read` | platform default | Reads a file. | Rarely relevant; the prompt does not need to mention it. |
| `server_skill` | platform default | Executes a server-side agent skill. | Only relevant if the agent also has `skills[]`. |

**`EnableCortexSense` adds exactly two tools: `cortex_sense` and `system_execute_sql`.** The control agent had `read`, `server_skill`, and `table_details` but no `cortex_sense` and no `system_execute_sql` — and when asked to run `SELECT 1+1` it replied `CANNOT EXECUTE SQL`, reasoning that "none can run arbitrary SQL". So the flag is genuinely what makes SQL execution available, and it is correct to say so in builder-facing copy.

The practical rule is unchanged: set only this flag, declare none of these five tools, and expect all five.

> **`table_details` omits silently.** Observed: a call for three tables returned two, with `status: success` and no error or warning for the third. The agent reasonably concluded the missing table "wasn't returned (maybe named differently)" — but the table existed and queried fine moments later. A prompt that treats a `table_details` miss as evidence a table is absent will send the agent down a wrong path. If the prompt mentions this tool at all, instruct it to treat absence from the result as *unknown*, not as *does not exist*, and to confirm with a direct query before concluding anything.

**Do not declare `system_execute_sql` in `tools[]`.** It is present without being declared. Declaring it explicitly will create successfully but fail at *runtime* on every turn:

```
Failed to parse tool resources: error unmarshalling tool resources:
agent tool resource value system execute sql is nil: agent tool resource value
generic tool has empty type but non-empty execution environment
```

The same applies to `cortex_sense`, `table_details`, `read`, and `server_skill` — they arrive on their own; the spec must stay silent about them.

Anything the builder genuinely wants **on top** of this set (for example `data_to_chart`, or a `cortex_search` tool) is declared in `tools[]` normally and coexists with the implicit set.

## Flags you do not need

Each of these appears in older hand-written Cortex Sense agents. Adding them is not neutral — the middle column is the cost.

| Flag | What it actually does | Why to omit it |
|---|---|---|
| `EnableStandaloneExecuteSqlTool` | Adds `snowscope_search`, `generic_semantic_context` (deferred, reachable via tool search), and `tool_search_tool_regex`. | It is **not** what makes SQL execution available — a minimal-spec agent already has `system_execute_sql` without it. Its only observed effect is adding competing retrieval tools that the orchestration prompt must then spend instructions suppressing. Omitting it removes the problem instead of managing it. |
| `FallbackWarehouse` | Names a warehouse for tool execution. | `system_execute_sql` succeeds with an empty `execution_environment`. Only add a warehouse if a smoke test actually fails with a missing-warehouse error, and then prefer the manifest's `warehouse` value. |
| `EnableSnowscopeCatalogSearchV2`, `EnableSnowscopeSemanticViewSearch`, `EnableVQRFastPath`, `EnableUnstructuredAnalytics` | Unrelated retrieval/analytics behaviour. | Out of scope for this skill. In retrofit mode, **preserve** them if already present (see "Retrofitting"); never add them. |

## Calling cortex_sense

The parameter list is owned by `CONTEXT_LOOKUP.md` "Priority order → MCP tool". Only the agent-side specifics live here.

```
cortex_sense(
  query: "<the user's question, verbatim>",
  context_names: ["<DB>.<SCHEMA>.<context_name>"]
)
```

- **`context_names`** — always pin it, and always to the full three-part FQN taken verbatim from a `list-contexts` call. All three segments are case-sensitive; Cortex Sense context names are frequently lowercase (`product_data_science_v2_1`) inside an uppercase database and schema. Never uppercase the name to "normalise" it.
- **`datamart_max_results`** — **do not set it.** Earlier agents pass `0` as a workaround for a backend error (`undefined field 'datamart_key'`). That bug is fixed; an unqualified call now succeeds and returns `datamart` documents. Setting `0` today silently suppresses a whole document class. Only set it if the builder explicitly does not want datamart documents.
- **`max_results`** — leave unset for an agent. The per-call caps in `CONTEXT_LOOKUP.md` exist to protect CoCo's context window when a skill fires many calls in sequence; an agent answering one question does not need them.

### Document types — use the real values

The API returns these `doc_type` values. An orchestration prompt that branches on prose labels ("Query pattern", "Domain overview", "Table entity") will never match anything, because those strings do not appear in the response.

| `doc_type` | Content | How the agent should use it |
|---|---|---|
| `table_entity` | Grain, columns, join relationships, default filters, caveats. | The schema for writing SQL. Take the grain so `GROUP BY` is right, and the default filters unless the user overrode them. |
| `qbe` | Real production SQL (`REPRESENTATIVE_SQL`, `METRIC_NAME`, `EXECUTION_COUNT`). Heavily duplicated — one dashboard emits many near-identical rows. | The strongest structural precedent when there is no semantic view. A row whose `METRIC_NAME` matches the question is the highest-priority reference; group by `METRIC_NAME` and read the highest `EXECUTION_COUNT`. |
| `ontology_node` | Business definitions, metric formulas, computation-rule policies. | The only source that defines what a metric *means*. Read before choosing a table. |
| `ontology_edge` | Graph traversal metadata. | Skip silently — no renderable content. |
| `datamart` | Curated datamart documents. | Treat as a table candidate. Returned only when `datamart_max_results` is left unset. |

Each document carries content in `markdown`, in `cam_content`, or both — read whichever is non-empty; they are complementary, not competing. Deduplicate on `entity_key` before use.

`documents` is omitted entirely from the response when empty (`omitempty`), so a missing key means "no results", not an error.

## Preflight — role and privilege

`CREATE AGENT` is evaluated against the **primary role only**; secondary roles do not satisfy it even when `CURRENT_SECONDARY_ROLES()` reports `ALL`. This is the most common failure and it produces a misleading message, so check first:

```sql
SELECT CURRENT_ROLE() AS primary_role, CURRENT_AVAILABLE_ROLES() AS available_roles;
```

If the intended owning role is available but is not the primary role, the fix is to run the create statement under that role (`snow sql --role <ROLE>`, or `USE ROLE <ROLE>` in a session) — not to grant secondary roles. The failure looks like:

```
SQL access control error: Insufficient privileges to operate on schema '<SCHEMA>'.
Your primary role <ROLE> must have CREATE AGENT granted on SCHEMA <DB>.<SCHEMA>.
```

If no available role has the privilege, surface the grant and stop — do not pick a different schema to dodge it:

```sql
GRANT CREATE AGENT ON SCHEMA <DB>.<SCHEMA> TO ROLE <ROLE>;
```

**The agent's own execution role matters more than the creating role.** The agent runs SQL as its caller's primary role, and Cortex Sense retrieval is *not* fully access-filtered — retrieval can legitimately surface tables the caller cannot read. This is a property of the system, not a misconfiguration, and the orchestration prompt must handle it (see `agent/SKILL.md` §4a, "access limits").

## DDL

**Check for a collision first, and never use `CREATE OR REPLACE` in create mode.** The agent name is derived from the domain, so a second create run on the same domain — or any schema that already holds an agent with that name — would silently overwrite an agent someone may already have deployed. That is precisely what the §5 checkpoint exists to prevent, so the DDL must not undo it.

```sql
SHOW AGENTS LIKE '<AGENT_NAME>' IN SCHEMA <DB>.<SCHEMA>;
```

If a row comes back, stop and offer the two real choices — do not auto-rename and do not replace:

```
An agent named <AGENT_NAME> already exists in <DB>.<SCHEMA>
(owner <owner>, created <created_on>).

  type: retrofit it · use a different name · cancel
```

`retrofit it` routes to `agent/SKILL.md` §7 — **a collision on create is the signal the builder wanted retrofit mode.** Only when `SHOW` returns no rows:

```sql
CREATE AGENT <DB>.<SCHEMA>.<AGENT_NAME>
  COMMENT = '<one line: what this agent answers, and which context grounds it>'
  FROM SPECIFICATION $$
<spec YAML>
$$;
```

`CREATE OR REPLACE` is appropriate only when the builder has explicitly asked to overwrite a specific named agent, and even then prefer the retrofit path so existing instructions are merged rather than discarded.

**Use bare `$$` as the dollar-quote tag.** Custom tags (`$spec$`, `$payload$`) are rejected:

```
SQL compilation error: syntax error line <n> at position 0 unexpected '$spec'.
```

Because the tag cannot be customised, the spec body must not contain `$$`. Orchestration instructions are prose and normally will not, but check before submitting — if the text does contain `$$`, rephrase it rather than switching tags.

`PROFILE` is set with a separate `ALTER` (see "CoWork"), not inside the specification.

### Retrofitting an existing agent

Read the current spec, merge, write back. Never compose a fresh spec from scratch — you will silently drop tools, skills, and flags you did not know about.

```sql
DESCRIBE AGENT <DB>.<SCHEMA>.<AGENT_NAME>;
```

Parse the `agent_spec` column (a JSON string). Then:

1. **Merge additively into `experimental`.** Add `EnableCortexSense: true`; preserve every other key exactly as found, including keys this file does not document. Do not remove `EnableStandaloneExecuteSqlTool` from an existing agent without telling the builder what changes — see `agent/SKILL.md` §7.
2. **Leave `tools[]`, `tool_resources{}`, `skills[]`, and `mcp_servers[]` untouched** unless the builder asked for a change. The implicit Cortex Sense tools are additive to whatever is declared.
3. **Write back to the live version:**

```sql
ALTER AGENT <DB>.<SCHEMA>.<AGENT_NAME> MODIFY LIVE VERSION SET SPECIFICATION = $$
<merged spec YAML>
$$;
```

Mutability constraints (which properties are settable at agent level vs. live version vs. a committed version) are owned by `cortex-agent/agent-versioning`. The one consequence worth knowing here: **after any `ALTER AGENT ... COMMIT`, an unversioned run resolves to `DEFAULT`, not `LIVE`** — so a spec change written to LIVE will not be what a plain run executes. If the agent has committed versions, say so and route the builder to that skill rather than guessing.

## CoWork

Agents are discoverable in CoWork (`https://ai.snowflake.com`) without extra registration on most accounts. Two things still matter:

**Display name.** CoWork lists agents by `display_name`; without a profile it shows the raw identifier. Set it:

```sql
ALTER AGENT <DB>.<SCHEMA>.<AGENT_NAME>
  SET PROFILE = '{"display_name": "<Readable Name>", "color": "#29B5E8"}';
```

**Usage grants.** The consuming role needs the agent plus the path to it:

```sql
GRANT USAGE ON AGENT <DB>.<SCHEMA>.<AGENT_NAME> TO ROLE <ROLE>;
GRANT USAGE ON DATABASE <DB> TO ROLE <ROLE>;
GRANT USAGE ON SCHEMA <DB>.<SCHEMA> TO ROLE <ROLE>;
```

Consuming users also need a default role and default warehouse set on their Snowflake user, or CoWork cannot start a session for them.

On accounts that have an explicit Snowflake Intelligence object (older enterprise setups), the agent must also be attached to it. Detect rather than assume, and only run the `ALTER` when `SHOW` returns a row:

```sql
SHOW SNOWFLAKE INTELLIGENCES;
-- only if a row is returned:
ALTER SNOWFLAKE INTELLIGENCE <name> ADD AGENT <DB>.<SCHEMA>.<AGENT_NAME>;
```

There is no `CREATE SNOWFLAKE INTELLIGENCE` command — never attempt to create one.

## Smoke test

Verify the wiring end-to-end before reporting success. Run the agent and confirm it (a) calls `cortex_sense`, (b) gets documents, (c) executes SQL, (d) returns a number.

```sql
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
  '<DB>.<SCHEMA>.<AGENT_NAME>',
  $${"messages":[{"role":"user","content":[{"type":"text","text":"<question>"}]}]}$$
) AS r;
```

- Omit `thread_id` / `parent_message_id`. Passing `"thread_id": 0` fails with `Thread 0 does not exist or not authorized for this user`.
- The payload is JSON inside a SQL string. Dollar-quote it with `$$`; a single-quoted literal will have its backslash escapes consumed by Snowflake and arrive as malformed JSON (`Request is malformed`).
- Read the response `content[]` array: `tool_use` entries name the tools actually called, `tool_result` entries carry `status`, and `text` entries hold the answer. A run that answers without a `cortex_sense` `tool_use` means the retrieval gate in the orchestration instructions is not binding.
- **The answer may arrive as several `text` entries**, not one — a multi-paragraph answer is commonly split across consecutive blocks. Concatenate every `text` entry in order before judging the answer; reading only the first will truncate it and can make a complete answer look partial.
- `thinking` entries are present too and are useful when diagnosing: they show which table the agent considered and rejected, which is how you tell a retrieval problem from a reasoning problem.

## Verification status

Verified against a live account on 2026-08-11:

- The tool inventory of a minimal-spec agent (`EnableCortexSense` only, empty `tools[]`): `cortex_sense`, `system_execute_sql`, `table_details`, `read`, `server_skill`.
- **Attribution, via a no-flag control.** An agent with no `experimental` block has only `read`, `server_skill`, `table_details` — and answered `CANNOT EXECUTE SQL` when asked to run `SELECT 1+1`. So `EnableCortexSense` adds exactly `cortex_sense` and `system_execute_sql`; the other three are platform defaults.
- `system_execute_sql` running arbitrary-table SQL — no semantic view, empty `execution_environment`, no `FallbackWarehouse`.
- `cortex_sense` succeeding **without** `datamart_max_results`, returning 19 documents including 2 `datamart` docs.
- The five real `doc_type` values.
- Bare `$$` accepted as the only dollar-quote tag; `$spec$` and `$payload$` rejected at compile time.
- The runtime failure from declaring `system_execute_sql` in `tools[]`.
- `CREATE AGENT` requiring the primary role while `CURRENT_SECONDARY_ROLES()` reported `ALL`.
- `DATA_AGENT_RUN` rejecting `"thread_id": 0`, and mangling single-quoted JSON payloads.

**End-to-end run** (agent built by `agent/SKILL.md` against the `product_data_science` context, question: *"how is CoCo doing in the past month"*):

- The agent called `cortex_sense` first, pinned to the correct three-part FQN, expanded the colloquial name to "CoCo (Cortex Code)", and omitted `datamart_max_results`. Retrieval returned all five `doc_type`s.
- It then ran three `system_execute_sql` calls against arbitrary `SNOWSCIENCE.LLM.*` tables — each with `execution_environment: {"warehouse": ""}` — and answered with real figures. **The manifest's `warehouse` (SNOWHOUSE) was never needed**, further confirming `FallbackWarehouse` is unnecessary.
- Behaviours traceable to specific instruction items: it resolved "the past month" against `MAX(DS)` rather than `CURRENT_DATE` and confirmed neither period was partial (item 6); it stated *"this is my own composition, not a blessed metric definition"* (the honesty clause); and it volunteered that it had **not** applied an account-type filter it saw in a `qbe` pattern.
- Two rough edges found and documented: `table_details` returned two of three requested tables with `status: success` (see "Tool inventory"), and the answer arrived split across three `text` blocks (see "Smoke test").

**Not verified — open items:**

- **Warehouse-less sessions.** The empty `execution_environment` succeeded in sessions that had an active warehouse. Whether it still succeeds when the caller has none is untested — this is the most likely reason a `FallbackWarehouse` would turn out to be necessary after all.
- **CoWork surfacing.** `PROFILE` is settable and round-trips, but the agent was not opened in the CoWork UI, and the grant path was not exercised with a second role.
- **Retrofit mode.** The create path is verified end-to-end; §7's merge, tool-delta, and `MODIFY LIVE VERSION` write-back have not been run against a real agent.

Re-verify the tool inventory when the preview moves forward — it is the item most likely to change, and the orchestration prompt in `agent/SKILL.md` §4a depends on it being accurate.
