---
name: custom-incrementalization
description: "Recommend and create custom incremental dynamic tables (CI DTs). Use when: stream-static joins, shape-of-changes logic (different handling for inserts/updates/deletes), append-only audit logs, state reuse/memoization for incremental speedups, schema evolution without reinit, migrating MERGE-based streams+tasks pipelines, DT with only inserts from base table. Triggers: custom incrementalization, CI DT, REFRESH USING, MERGE DT, INSERT INTO SELF, stream-static join, append-only log, audit trail DT, shape of changes, imperative DT refresh, DT only inserts."
parent_skill: dynamic-tables
---

# Custom Incremental Dynamic Tables (CI DTs)

Guidance for recommending and creating dynamic tables with custom incrementalization — imperative DML refresh logic using `REFRESH USING` instead of a declarative SELECT.

**Terminology note:** Use "custom incrementalization" (lowercase) for the feature and "custom incremental dynamic table" for the object. `CUSTOM_INCREMENTAL` (uppercase) only appears as the SQL `REFRESH_MODE` parameter value.

## When to Load

**Use custom incrementalization only when standard dynamic tables don't meet requirements.** Standard DTs are simpler and automatically managed — prefer them when possible.

Main skill routes here when user needs:
- Stream-static join patterns in a dynamic table
- Different logic for inserts vs updates vs deletes (shape-of-changes)
- Append-only log / audit trail accumulating over time
- MERGE logic that leverages existing table state (SELF) for performance
- Schema evolution without reinitialization
- Migration from streams+tasks using MERGE/INSERT that can't be expressed as SELECT

---

## Prerequisites

**Load** [references/custom-incrementalization.md](../references/custom-incrementalization.md) for full syntax, semantics, and limitations.

---

## Workflow

**If arriving from task-to-dt** (user was redirected here because their pipeline uses MERGE with conditional change logic or stream-static join): Skip Step 1 questions and Step 2c (migration checks already done). Proceed directly to Step 2a.

### Step 1: Identify the Use Case

**Goal:** Determine which CI DT pattern fits the user's scenario.

**Decision matrix:**

| Scenario | Pattern | DML Type | Notes |
|----------|---------|----------|-------|
| Enrich incremental changes with static dimension lookups | Stream-static join | INSERT INTO SELF (if source is insert-only) or MERGE INTO SELF (if source has updates/deletes) | Use MERGE when source stream has updates/deletes |
| DT should only capture inserts from base table | Append-only from insert stream | INSERT INTO SELF with CHANGES(INFORMATION => APPEND_ONLY) | Filters to only inserts, ignoring updates/deletes |
| Different actions for INSERT/UPDATE/DELETE | Shape-of-changes | MERGE INTO SELF (with METADATA$ACTION filtering) | |
| Accumulate history / audit trail (never update/delete) | Append-only log | INSERT INTO SELF | |
| Use existing table state to limit work (e.g., top-k) | Stateful MERGE | MERGE INTO SELF (with SELF in USING) | State reuse/memoization for speedup |
| Time-window processing without CHANGES() | Window-based append | INSERT INTO SELF (with NOT EXISTS against SELF) | |
| Schema evolution without full reinit | Any CI DT | Either (use CREATE OR ALTER to add columns) | |

**Ask user:**
1. What is the source data? (fact table, event stream, etc.)
2. What transformation do you need? (enrich, filter, merge, accumulate)
3. Do you care about the *type* of change (insert vs delete vs update)?
4. Is this replacing an existing streams+tasks pipeline?

Confirm use case and pattern with the user before proceeding.

---

### Step 2: Assess Feasibility

**Goal:** Verify CI DT is the right choice and check prerequisites.

#### 2a. Confirm CI DT is Needed (Not Standard DT)

Standard DTs are simpler. Only use CI DT when standard DTs **cannot** express the logic:

| Need | Standard DT? | CI DT? |
|------|-------------|--------|
| Simple SELECT transformation | ✅ Use standard | Overkill |
| GROUP BY aggregation | ✅ Use standard | Overkill |
| JOIN where both sides trigger refresh | ✅ Use standard | Overkill |
| Stream-static join (only one side incremental) | ❌ Full recompute | ✅ |
| Conditional INSERT/UPDATE/DELETE by change type | ❌ Not expressible | ✅ |
| Append-only accumulation (never delete old rows) | ❌ DT replaces content | ✅ |
| MERGE using existing state for optimization | ❌ Not expressible | ✅ |

#### 2b. Check Prerequisites and Evaluate Against Known Limitations

1. **Change tracking** on source tables:
   ```sql
   SHOW TABLES LIKE '<source_table>';
   -- Verify change_tracking = TRUE
   ```

2. **Source compatibility**: CI DTs can read from:
   - Base tables with change tracking (via CHANGES() clause)
   - Other dynamic tables (via CHANGES() clause)
   - Static tables (read in full, no CHANGES())
   - SELF (the CI DT's own current state)

3. **Evaluate user's scenario against known limitations:**

   Review the full limitations table in the loaded reference document. For each limitation, check whether the user's scenario would violate it. Key questions to ask:

   - Does the user need multiple DML statements in one refresh? → Cannot use CI DT
   - Does the logic require IF/ELSE branching or loops? → Cannot use CI DT
   - Does it need to call external APIs or stored procedures? → Cannot use CI DT
   - Does one refresh need to write to multiple target tables? → Split into multiple CI DTs
   - Does the user need `CHANGES()` on SELF (the DT's own history)? → Not allowed
   - Does the user expect view semantics (DT always reflects latest SELECT result)? → CI DTs are imperative, not view-like. Rows persist unless explicitly deleted via MERGE. If user needs view semantics, recommend standard DTs instead.
   - Does the user need to clone or replicate the DT? → Not supported for CI DTs

   **⚠️ MANDATORY STOPPING POINT if any limitation is triggered**: Present the conflict to the user and discuss alternatives (standard DT, hybrid task+DT, or staying on streams+tasks).

#### 2c. Migration from Streams+Tasks — Pre-Requisite Checks

**If migrating from an existing pipeline:**

1. **Check for stored procedures in tasks:**
   ```sql
   SHOW TASKS IN SCHEMA <schema>;
   -- Look at 'definition' column for CALL statements
   ```

2. **If stored procs are used, inspect their bodies:**
   ```sql
   SELECT GET_DDL('PROCEDURE', '<proc_name>(arg_types)');
   ```

   **Critical check**: Look for multi-statement transactions that do work *beyond* consuming the stream. CI DTs execute a single DML statement — they cannot:
   - Update multiple target tables in one refresh
   - Perform conditional branching (IF stream has data THEN X ELSE Y)
   - Call external APIs or send notifications
   - Execute DDL as part of the refresh
   - Maintain counters or state in variables across refreshes

   **If any of these patterns exist**: The pipeline cannot be fully expressed as a CI DT. Consider:
   - Splitting into multiple CI DTs (one per target)
   - Keeping the non-DML side effects in a lightweight task triggered by the DT
   - Hybrid approach: CI DT for the core MERGE + task for side effects

3. **Map components:**

   | Streams+Tasks | CI DT Equivalent |
   |--------------|-----------------|
   | `CREATE STREAM ... ON TABLE x` | `FROM x CHANGES()` in REFRESH USING |
   | Stream offset (position) | `START AT (STREAM => '<stream_name>')` to carry over offset (requires BACKFILL FROM) |
   | `SYSTEM$STREAM_HAS_DATA()` | No direct equivalent. CI DT refresh runs even when CHANGES() returns 0 rows (no-op DML still consumes warehouse credits). |
   | Task SCHEDULE / CRON | TARGET_LAG |
   | Task AFTER (predecessors) | Automatic DAG from table references |
   | MERGE INTO target USING stream | MERGE INTO SELF USING (... FROM source CHANGES()) |
   | INSERT INTO target SELECT FROM stream | INSERT INTO SELF SELECT FROM source CHANGES() |

4. **Seamless pipeline continuation with BACKFILL FROM and START AT:**

   To continue processing from where the stream left off without data loss or duplication, use BACKFILL FROM with START AT:

   ```sql
   CREATE OR REPLACE DYNAMIC TABLE my_ci_dt (...)
     TARGET_LAG = DOWNSTREAM
     WAREHOUSE = my_wh
     BACKFILL FROM my_database.my_schema.existing_target_table
     START AT (STREAM => 'my_database.my_schema.my_existing_stream')
     REFRESH USING (
       MERGE INTO SELF USING ...
     );
   ```

   **Notes:**
    - START AT requires BACKFILL FROM — you cannot use START AT alone.
    - The stream name in START AT must be a quoted string.
    - BACKFILL FROM Iceberg sources is NOT supported. If the existing target is an Iceberg table, you must manually copy the data or use a different approach.

Present feasibility assessment to the user. If blockers exist, discuss alternatives.

---

### Step 3: Design the CI DT

**Goal:** Write the CREATE DYNAMIC TABLE ... REFRESH USING statement.

**Template:**

```sql
CREATE OR REPLACE DYNAMIC TABLE <name> (
  <column_list>
)
  TARGET_LAG = { '<time>' | DOWNSTREAM }
  WAREHOUSE = <warehouse>
  REFRESH USING (
    { MERGE INTO SELF AS tgt USING (...) AS src ON ... WHEN ... }
    |
    { INSERT INTO SELF SELECT ... FROM <source> CHANGES(...) ... }
  );
```

**Key decisions:**

1. **INSERT INTO SELF vs MERGE INTO SELF:**
   - INSERT: Append-only patterns (logs, audit trails, event accumulation)
   - MERGE: Need to update/delete existing rows based on incoming changes

2. **CHANGES() clause options:**
   - `CHANGES()` — all change types (DEFAULT information)
   - `CHANGES(INFORMATION => APPEND_ONLY)` — only inserts (more efficient if source is append-only)

3. **Column list**: CI DTs require explicit column definitions in the CREATE statement.

4. **SELF references**: Use `SELF` (not the table name) to reference the CI DT's own current state.

Present the CREATE statement to the user for approval before executing.

---

### Step 4: Execute and Verify

**Goal:** Create the CI DT and confirm it works.

**Actions:**

1. **Enable change tracking** if needed:
   ```sql
   ALTER TABLE <source> SET CHANGE_TRACKING = TRUE;
   ```

2. **Execute** the approved CREATE statement.

3. **Verify creation:**
   ```sql
   SHOW DYNAMIC TABLES LIKE '<name>';
   ```

4. **Verify data** after first refresh:
   ```sql
   SELECT * FROM <name> LIMIT 10;
   ```

5. **Test incremental behavior** — insert/update/delete rows in source, wait for refresh, verify CI DT reflects changes correctly.

Present results to the user. Confirm correct behavior.

---

### Step 5: Decommission Old Pipeline (if migrating)

**Only if replacing streams+tasks:**

1. **Run in parallel** for a monitoring period (CI DT + old pipeline both active)
2. **Compare outputs** between old target table and new CI DT
3. **Suspend** tasks after validation:
   ```sql
   ALTER TASK <task_name> SUSPEND;
   ```
4. **Drop** after confidence period:
   ```sql
   DROP TASK IF EXISTS <task_name>;
   DROP STREAM IF EXISTS <stream_name>;
   ```

---

## Scenario Examples

### Scenario 1: Stream-Static Join

**Problem:** Enrich clickstream events with page metadata. Only new clicks should trigger processing; page dimension changes shouldn't reprocess all clicks.

```sql
CREATE OR REPLACE DYNAMIC TABLE enriched_clicks (
  click_id INT, user_id INT, page_title STRING,
  section STRING, click_ts TIMESTAMP
)
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = my_wh
  REFRESH USING (
    INSERT INTO SELF
    SELECT c.click_id, c.user_id, p.page_title, p.section, c.click_ts
    FROM clicks CHANGES(INFORMATION => APPEND_ONLY) AS c
    LEFT OUTER JOIN pages AS p ON c.page_id = p.page_id
  );
```

**Note:** If the static side has one-to-many cardinality, use MERGE with deduplication instead.

### Scenario 2: Audit Deletes Log (Shape-of-Changes)

**Problem:** Maintain a permanent log of every deleted row from a source table.

```sql
CREATE OR REPLACE DYNAMIC TABLE dt_deletions_log (id INT, name STRING, email STRING)
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = my_wh
  REFRESH USING (
    INSERT INTO SELF
    SELECT * EXCLUDE (METADATA$ISUPDATE, METADATA$ACTION)
    FROM users CHANGES()
    WHERE NOT METADATA$ISUPDATE AND METADATA$ACTION = 'DELETE'
  );
```

### Scenario 3: Top-K Leaderboard (Stateful MERGE)

**Problem:** Maintain a top-3 leaderboard, re-ranking only changed entries against current leaders — never scanning full population.

```sql
CREATE OR REPLACE DYNAMIC TABLE leaderboard (player_id INT, total_score INT, rank INT)
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = my_wh
  REFRESH USING (
    MERGE INTO SELF AS tgt
    USING (
      WITH candidates AS (
        SELECT
          COALESCE(ch.player_id, cur.player_id) AS player_id,
          COALESCE(ch.total_score, cur.total_score) AS total_score
        FROM SELF AS cur
        FULL OUTER JOIN (
          SELECT player_id, total_score
          FROM player_scores CHANGES()
          WHERE METADATA$ACTION = 'INSERT'
        ) AS ch ON cur.player_id = ch.player_id
      ),
      ranked AS (
        SELECT *, ROW_NUMBER() OVER (
          ORDER BY total_score DESC, player_id ASC
        ) AS new_rank
        FROM candidates
      )
      SELECT player_id, total_score, new_rank FROM ranked
    ) AS src
    ON tgt.player_id = src.player_id
    WHEN MATCHED AND src.new_rank <= 3 THEN
      UPDATE SET tgt.total_score = src.total_score, tgt.rank = src.new_rank
    WHEN MATCHED AND src.new_rank > 3 THEN
      DELETE
    WHEN NOT MATCHED AND src.new_rank <= 3 THEN
      INSERT (player_id, total_score, rank)
      VALUES (src.player_id, src.total_score, src.new_rank)
  );
```

### Scenario 4: Time-Window Refresh Without CHANGES()

**Problem:** Append recent events using a time filter, deduplicating against existing rows.

```sql
CREATE OR REPLACE DYNAMIC TABLE recent_events (
  id INT, event_ts TIMESTAMP, payload VARIANT
)
  TARGET_LAG = '1 hour'
  WAREHOUSE = my_wh
  REFRESH USING (
    INSERT INTO SELF
    SELECT r.id, r.event_ts, r.payload
    FROM raw_events r
    WHERE r.event_ts >= DATEADD('hour', -1, CURRENT_TIMESTAMP())
      AND NOT EXISTS (
        SELECT 1 FROM SELF s WHERE s.id = r.id
      )
  );
```

**Warnings:**
- The time window should be **at least as large as TARGET_LAG** to avoid missing rows between refreshes.
- `NOT EXISTS` against SELF scans all existing rows each refresh — performance degrades linearly as the table grows. Consider periodic purging or partitioning strategies for long-lived tables.
- Rows accumulate indefinitely. If the table grows unbounded, add a separate cleanup mechanism (e.g., a scheduled task that deletes old rows, or a MERGE-based CI DT that expires entries).

---

## Stopping Points Summary

1. ✋ Step 1: After identifying use case and pattern
2. ✋ Step 2: After feasibility assessment (especially for migrations)
3. ✋ Step 3: After designing CREATE statement (before execution)
4. ✋ Step 4: After execution (verify correctness)

---

## Output

- CI DT created with appropriate REFRESH USING logic
- Verified refresh mode is CUSTOM_INCREMENTAL
- Old pipeline decommissioned (if migration)
