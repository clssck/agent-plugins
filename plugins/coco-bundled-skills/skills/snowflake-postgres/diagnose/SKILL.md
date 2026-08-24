---
name: snowflake-postgres-diagnose
description: "Run Postgres health diagnostics via pg_doctor.py. Triggers: 'health check', 'diagnose', 'diagnostics', 'insights', 'pg_doctor', 'cache hit', 'bloat', 'vacuum', 'dead rows', 'autovacuum', 'locks', 'blocking queries', 'blocked', 'waiting', 'long running', 'slow queries', 'query performance', 'outliers', 'unused indexes', 'table sizes', 'disk usage', 'storage', 'connections', 'connection count', 'how many connections', 'what's running', 'active queries'."
parent_skill: snowflake-postgres
---

# Snowflake Postgres - Diagnose

## When to Load

From `snowflake-postgres/SKILL.md` when intent is DIAGNOSE.

**Note:** All `<SKILL_DIR>` placeholders must be absolute paths.

## Prerequisites

- A saved Postgres connection (via `connect/SKILL.md` workflow)
- SSL required (`sslmode=require`)

## CRITICAL: Diagnose Only — Never Prescribe

**Read this before running any checks.** The agent MUST NOT recommend, suggest, or offer to run any write operations. This includes:

- NEVER say "Run VACUUM FULL", "Run REINDEX", "Let me run VACUUM", "Want me to vacuum that?"
- NEVER say "Recommendation: Run ...", "You should run ...", "Consider running ..."
- NEVER offer to execute `pg_terminate_backend`, `pg_cancel_backend`, `DROP INDEX`, or any DDL/DML
- NEVER ask "Want me to run a vacuum on these tables?" or similar
- NEVER run raw SQL via psql for diagnostics — always use `pg_doctor.py` which enforces readonly + timeout

**What to do instead:**
- Present the data: "3 tables have significant bloat" 
- Offer to investigate: "Want me to show which tables are most affected?"
- Offer to explain: "I can explain what bloat means and why it happens"
- If the user asks "what should I do?": explain the options and trade-offs, then say "check with your DBA or team before making changes — I may not have full context about your workload"

**Stats caveat:** `pg_stat_user_indexes` counters reset on instance restart. Mention this when discussing unused indexes.

## Workflow

### Step 1: Verify Connection Exists

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_connect.py --list
```

If the target instance isn't saved, route to `connect/SKILL.md` first.

### Step 2: Run Health Check

**Always use pg_doctor.py with `--json` mode.** Never run raw SQL via psql or any other method for diagnostics — pg_doctor.py enforces readonly mode, statement timeout, and structured output. Even for single check drill-downs, use `pg_doctor.py --check <name> --json`.

#### Full Health Check (default)

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_doctor.py \
  --connection-name <NAME> --json
```

#### Single Check (drill-down)

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/pg_doctor.py \
  --connection-name <NAME> --check <CHECK_NAME> --json
```

### Available Checks

| Check | Description | Thresholds |
|-------|-------------|------------|
| `cache_hit` | Index and table cache hit rate | ✅ ≥99%, ⚠️ 95-99%, ❌ <95% |
| `bloat` | Table and index bloat | ✅ <30%, ⚠️ 30-50%, ❌ >50% |
| `vacuum_stats` | Dead rows and autovacuum status | ⚠️ if tables need vacuum |
| `connections` | Connection counts per role | Informational |
| `locks` | Exclusive locks held | ⚠️ if locks present |
| `blocking` | Blocked queries | ❌ if queries blocked |
| `long_running` | Queries > 5 minutes | ⚠️ if found |
| `outliers` | Top slow queries (requires pg_stat_statements) | Informational |
| `unused_indexes` | Indexes never scanned (wasting space) | ⚠️ if any found |
| `table_sizes` | Table size breakdown (total, index, toast) | Informational |

### Step 3: Format Results as Markdown

Parse the JSON output and present results as formatted markdown. **Do not paste raw JSON or tabulate output into chat.**

#### Summary View (full health check)

Format the results as a markdown table with status icons:

```markdown
## Health Check — <connection_name>

| Status | Check | Summary |
|--------|-------|---------|
| ✅ | Cache hit | table hit rate: 99.8% |
| ⚠️ | Bloat | Max bloat: 1.4x |
| ✅ | Vacuum stats | Vacuum status healthy |
| ✅ | Connections | 12 active connections |
| ✅ | Locks | No exclusive locks |
| ✅ | Blocking | No blocking queries |
| ✅ | Long running | No long-running queries |
| ✅ | Outliers | Top 10 query outliers |
| ⚠️ | Unused indexes | 3 unused indexes (wasting space) |
| ✅ | Table sizes | 7 tables |

**2 items need attention.** Want me to dig into bloat or unused indexes?
I can also explain what any of these checks measure.
```

#### Drill-Down View (single check with rows)

When the user asks to see detail on a specific check, run that check with `--json` and format the `rows` array as a markdown table using the `columns` array as headers.

```markdown
## Bloat Detail

| Type | Schema | Object | Bloat | Waste |
|------|--------|--------|-------|-------|
| table | public | orders | 1.4x | 64 kB |
| index | public | orders::idx_created | 1.2x | 16 kB |
```

### Step 4: Offer Next Steps

**The user makes the decisions — the agent provides the data.** Offer to investigate further or explain concepts. Refer to `references/thresholds.md` for threshold context.

### Issue-Specific Guidance

| Issue | Context | What to Offer |
|-------|---------|---------------|
| Low cache hit (new instance) | Normal for new instances | Explain it will improve as cache warms up |
| Low cache hit (established) | Queries reading from disk | Offer to run outliers check to find top resource consumers |
| High bloat | From writes/updates | Offer to show which tables are most affected |
| Blocking queries | Causing timeouts | Offer to show the blocking/blocked PIDs and queries |
| Long-running queries | May need optimization | Offer to show the queries and their durations |
| Vacuum needed | Dead rows building up | Offer to show which tables have the most dead rows |
| Unused indexes | Wasting disk and slowing writes | Offer to list them with sizes |

## Safety

All diagnostics run in **readonly mode** (`default_transaction_read_only=on`) with a 30-second statement timeout. No data can be modified by pg_doctor.

## References

- `references/thresholds.md` — Detailed threshold documentation and recommended actions
