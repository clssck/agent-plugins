# Migration State File Template

This is the canonical schema for `migration_state.yaml`. The Resume / Pause / Repeat workflows all read and write this file.

## How to use this template

1. **Create**: At the start of a migration (after assessment approval), copy this template into `migration_state.yaml` in the working directory the migration is being run from.
2. **Update**: After each completed phase, set the phase's `status: completed`, fill in `completed_at`, and update the top-level `last_phase_completed` and `next_action`.
3. **Pause**: Before exiting a session that will resume later, also set `paused_at` (ISO timestamp) and `paused_after_phase` (phase name). This is what lets a future "resume my postgres migration" land on the correct phase without re-deriving state from SQL.
4. **Resume**: A new session reads this file FIRST, then runs the diagnostic SQL in `resume/SKILL.md` to confirm what the file claims still matches reality.

## Template

```yaml
# migration_state.yaml
# Canonical state file for a PostgreSQL → Snowflake Postgres migration.
# Update after each phase completes; the resume/pause/repeat workflows depend on it.

migration:
  source:
    host: "<source_host>"
    database: "<database>"
    started: "2026-02-12T10:00:00Z"

  target:
    instance_name: "<snowflake_pg_instance>"
    host: "<target_host>"
    database: "<database>"

  method: "logical_replication | pg_dump | hybrid"
  dump_timing: "now | cutover"  # hybrid only

phases:
  assess:
    status: "not_started | in_progress | completed | skipped"
    completed_at: null
    blockers_found: []
    approval_given: false

  security:
    status: "not_started | in_progress | completed"
    completed_at: null
    roles_exported: false
    roles_imported: false
    grants_applied: false

  schema_ddl:
    status: "not_started | in_progress | completed"
    completed_at: null
    applied_to_target: false

  replicate:
    status: "not_started | in_progress | completed | not_applicable"
    publication_name: "migration_pub"
    subscription_name: "migration_sub"
    slot_name: "migration_sub"
    initial_sync_started: null
    initial_sync_completed: null
    streaming_started: null
    table_count: 0

  pg_dump:
    status: "not_started | in_progress | completed | not_applicable | deferred_to_cutover"
    completed_at: null
    object_count: 0
    deferred: false  # true when dump_timing=cutover

  materialized_views:
    status: "not_started | in_progress | completed | not_applicable"
    completed_at: null
    view_count: 0

  validate:
    status: "not_started | in_progress | completed"
    completed_at: null
    row_counts_match: null
    checksums_match: null
    pgcompare_run: false
    run_count: 0  # incremented each time validation is repeated

  rollback_setup:
    status: "not_started | completed"
    strategy: "reverse_replication | pitr | none"
    reverse_pub_created: false

  cutover:
    status: "not_started | in_progress | completed"
    scheduled_time: null
    actual_start: null
    actual_end: null
    writes_stopped: false
    deferred_dump_completed: false  # hybrid + dump_timing=cutover
    sequences_synced: false
    dns_switched: false
    apps_restarted: false

  cleanup:
    status: "not_started | completed"
    source_slot_dropped: false
    source_publication_dropped: false

paused_at: null           # ISO timestamp when user paused
paused_after_phase: null  # phase name where user paused
notes: |
  Add any migration-specific notes here.

last_updated: "2026-02-12T10:00:00Z"
last_phase_completed: "assess"
next_action: "Create Snowflake Postgres instance"
```

## Field reference

| Field | Required | Notes |
|-------|----------|-------|
| `migration.method` | Yes | One of `logical_replication`, `pg_dump`, `hybrid`. |
| `migration.dump_timing` | hybrid only | `now` runs pg_dump after replication initial sync; `cutover` defers it. |
| `phases.<name>.status` | Yes | Drives the State Decision Tree in `resume/SKILL.md`. |
| `phases.replicate.slot_name` | replication only | Match the source replication slot exactly. |
| `paused_at` / `paused_after_phase` | Pause only | Both required for clean resume. |
| `last_phase_completed` | Yes | Top-level convenience field used by `resume/SKILL.md` for fast-path routing. |
| `next_action` | Yes | Human-readable description of the next step. |
