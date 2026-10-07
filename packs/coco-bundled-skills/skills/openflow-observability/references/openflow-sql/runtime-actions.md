---
name: openflow-observability-runtime-actions
description: Runtime / EAI Openflow SQL action templates and preflight checks. Tier 2 -- load only when the Openflow SQL Action Mode has been entered and an allowlisted runtime action candidate exists.
---

<a id="openflow-sql-runtime-actions"></a>
# Openflow SQL Runtime Actions

> Customer-facing name for actions in this file: **Openflow SQL actions for runtimes**. Use "SQL-managed runtime" / "Openflow SQL action" when speaking to the customer.

Templates and preflight for the runtime / EAI actions in the MVP allowlist. Every template here assumes `references/openflow-sql/action-guidelines.md` is already loaded and all five hard gates from [SKILL.md](../../SKILL.md#openflow-sql-action-mode) will be enforced before the proposed SQL is executed.

## Scope

- Preflight queries shared by all runtime actions
- Per-action template: input fields, preflight, exact SQL, expected impact, verification
- Out of scope: connector mutations, deployment mutations, admin DDL (`GRANT`, `CREATE NETWORK RULE`, `CREATE EXTERNAL ACCESS INTEGRATION`)
- Out of scope: runtime resize / "make it bigger" requests. NODE_TYPE is create-time-only and node-count changes are not allowlisted -- see the node-size denylist entry in [action-guidelines.md](action-guidelines.md#action-denylist-mvp).

---

## Shared Preflight

Run before any of the per-action templates below. The output of these queries is what fills the **Current state** field in the [Confirmation Preview Format](action-guidelines.md#confirmation-preview-format).

### 1. Resolve runtime FQN

If the user gave only a short name:

```sql
SHOW OPENFLOW RUNTIMES LIKE '{runtime_name_or_pattern}';
```

- Clean zero rows (the query ran and returned no matching runtime) -> **fail closed**, fall back to UI guidance (the runtime is legacy or not visible to this role).
- Multiple rows -> **stop and ask** the customer to choose the FQN. Quote `NAME`, `DISPLAY_NAME`, `DEPLOYMENT`, `DATABASE_NAME`, `SCHEMA_NAME` for each row.
- One row -> capture `NAME`, `DATABASE_NAME`, `SCHEMA_NAME`, build `runtime_fqn = "<DATABASE_NAME>.<SCHEMA_NAME>.<NAME>"`.
- **Errors** (`unsupported` / `syntax error near OPENFLOW` / `feature ... disabled` / `does not exist or not authorized`) are NOT a clean zero-row result. They mean this account may not be Openflow-SQL-enabled, not that the runtime is invisible. Do not fail closed here: construct the best-known `runtime_fqn` from the inputs (`<database>.<schema>.<runtime_name>`) and still run step 2's `DESCRIBE` so the customer sees the verbatim result of the actual read. `SHOW` is only a name-resolution helper; it never returns `EXTERNAL_ACCESS_INTEGRATIONS`, so it cannot substitute for the `DESCRIBE`.

### 2. Describe the runtime

```sql
DESCRIBE OPENFLOW RUNTIME {runtime_fqn};
```

**Mandatory for every runtime / EAI action -- always execute it, never skip or substitute it.** This is the canonical runtime read and the only query that returns the live `EXTERNAL_ACCESS_INTEGRATIONS` list that `runtime.attach_eai` unions against. Run it even when step 1's `SHOW` errored or you expect the account to reject Openflow SQL: attempt it against the best-known `runtime_fqn`, surface any error verbatim, then proceed to the Confirmation Preview. A `SHOW OPENFLOW RUNTIMES` result alone is never sufficient to skip this step.

Capture: `STATUS`, `MIN_NODES`, `MAX_NODES`, `NODE_TYPE`, `EXTERNAL_ACCESS_INTEGRATIONS` (raw string list), `DEPLOYMENT`, `DISPLAY_NAME`, `OWNER`, `SERVER_URL`.

Validate `STATUS` against the action eligibility table in `references/openflow-sql/action-guidelines.md`. Stop if the action is not allowed for the current state.

### 3. (Conditional) Describe the parent deployment

Required for `runtime.attach_eai` on SPCS deployments and any time the user is unsure whether the runtime is SPCS or BYOC.

`DESCRIBE OPENFLOW DEPLOYMENT` requires the deployment NAME, not the UUID. The Snowsight skill context provides `{deployment_id}` as a UUID, so resolve it to a name first:

```sql
SHOW OPENFLOW DEPLOYMENTS;
```

Find the row where the UUID column matches `{deployment_id}` and capture `NAME` as `{deployment_name}`. If zero rows match, **fail closed** -- the UUID is stale or the role cannot see that deployment; fall back to UI guidance. Then run:

```sql
DESCRIBE OPENFLOW DEPLOYMENT "{deployment_name}";
```

Wrap `{deployment_name}` in double quotes (deployment names are case-sensitive when created lowercase, e.g. `spcs`; bare identifiers get uppercased and fail with `does not exist or not authorized`). See [deployment-actions.md > Quoting rule](deployment-actions.md#1-resolve-the-deployment-name).

- `DEPLOYMENT_TYPE = 'SNOWFLAKE'` -> SPCS, EAI is meaningful.
- `DEPLOYMENT_TYPE = 'BYOC'` -> EAI is NOT applicable. Stop the EAI action and explain that BYOC outbound network access is governed by the customer's cloud network configuration.

---

<a id="shared-verification"></a>
## Shared Verification (after any mutating action)

Every per-action **Verification** section below runs a single `DESCRIBE OPENFLOW RUNTIME` (or equivalent) and inspects the post-action state. Two cross-action rules apply to that step:

- **Do not promise completion.** Openflow SQL mutations are asynchronous and dispatched through a FIFO queue (2 concurrent tasks per account). The agent does not poll for action completion. Whatever the post-action `DESCRIBE` returns is a single point-in-time read -- the action may still be queued, in flight, or transitioning. Report the observed state, never assert "the action is done" unless `DESCRIBE` shows the expected terminal `STATUS`.
- **Surface queued / in-flight responses verbatim.** If Snowflake's `ALTER` response includes "Task queued for execution", "concurrent task", "FIFO order", "queued", or "pending", OR if the immediate `DESCRIBE` still shows the pre-action `STATUS`, surface that queued / in-flight wording in the agent's response, tell the customer to check back later, and stop. **Do not poll-and-retry the `DESCRIBE` from inside the same response.** See [Failure Handling > Async work](action-guidelines.md#failure-handling) for the canonical rule and the [Pending Action Tracker](action-guidelines.md#pending-action-tracker) for the no-chained-mutations consequence.

---

## runtime.attach_eai -- Attach an existing EAI to a SQL-managed runtime

### Inputs

- `runtime_fqn` (required)
- `eai_name` (required, must be the existing EAI name as it appears in `SHOW EXTERNAL ACCESS INTEGRATIONS`)

### Preflight

1. Run [Shared Preflight](#shared-preflight) steps 1, 2, and 3.
2. Confirm the deployment is SPCS (`DEPLOYMENT_TYPE = 'SNOWFLAKE'`). EAI does not apply to BYOC.
3. Confirm the EAI exists and is enabled:

```sql
SHOW EXTERNAL ACCESS INTEGRATIONS LIKE '{eai_name}';
```

   - Zero rows -> **fail closed**: the EAI does not exist (or is not visible to this role). Load `admin-ddl-assist.md` for customer-run guidance -- creating a new EAI is NOT in MVP.
   - One row with the `enabled` column equal to `true` -> proceed. Snowflake `SHOW` commands return column headers in uppercase and values as lowercase booleans; read the value case-insensitively (`ENABLED = TRUE` and `enabled = true` are the same field) and do not depend on the client's display casing.
   - `enabled = false` -> stop and tell the customer the EAI is disabled. Do not attempt to enable it.

4. Confirm the EAI is granted to the runtime role. The runtime execution role MUST be confirmed from one of: (a) customer-provided input, (b) an explicit column on `DESCRIBE OPENFLOW RUNTIME` that names the execution role, or (c) the connector configuration if it records the runtime role. **`OWNER` from `DESCRIBE OPENFLOW RUNTIME` is NOT the runtime execution role -- do not substitute it.** If the execution role cannot be confirmed from (a), (b), or (c), **stop** and ask the customer directly. Do not guess, and do not run `SHOW GRANTS` against an assumed role.

```sql
SHOW GRANTS ON INTEGRATION {eai_name};
```

   - If `USAGE` is not granted to the runtime role, **fail closed**. Surface this as customer-run admin DDL guidance, not as an agent action.

   4b. Inspect the network rules the EAI references and verify the runtime role can reach them. Run `DESCRIBE INTEGRATION {eai_name}` and read the `ALLOWED_NETWORK_RULES` property. For each FQN listed there (e.g. `DB.SCHEMA.RULE_NAME`) the runtime execution role needs ANY ONE of: (a) OWNERSHIP on the rule, (b) USAGE on the rule, OR (c) effective access via OWNERSHIP/USAGE on the rule's parent schema. Run `SHOW GRANTS ON NETWORK RULE {rule_fqn}` and `SHOW GRANTS ON SCHEMA {db}.{schema}` to enumerate what the role has. If NONE of (a)/(b)/(c) is present, **fail closed** -- the `ALTER` will succeed against the EAI grant check but fail with `Insufficient privileges to operate on network_rule '...'` at execution time. Surface this as customer-run admin DDL guidance via `admin-ddl-assist.md` rather than attempting the `ALTER`.

5. Read the existing EAI list from the `EXTERNAL_ACCESS_INTEGRATIONS` column of step 2's `DESCRIBE`. Parse using the canonical parser in [Raw `EXTERNAL_ACCESS_INTEGRATIONS` format](action-guidelines.md#raw-external_access_integrations-format) (do NOT improvise: preserve each existing `raw_token` for SQL rendering and derive a separate comparison key for deduplication). Build three ordered token lists:
   - `{current_tokens}` -- existing entries with their exact raw SQL token as Snowflake returned it.
   - `{proposed_tokens}` -- `{current_tokens}` plus the new EAI token returned by `SHOW EXTERNAL ACCESS INTEGRATIONS`, unless its comparison key is already present.
   - `{removed_tokens}` -- entries in `{current_tokens}` that are NOT in `{proposed_tokens}`. For `runtime.attach_eai` this MUST be empty.

   If `{eai_name}` is already in `{current_tokens}` by comparison key, **stop and report** -- no action needed.

   If `{removed_tokens}` is non-empty (would only happen if the parser dropped or re-cased an entry), **fail closed** and surface the discrepancy. Never proceed with an `ALTER` that loses an existing EAI.

   The Confirmation Preview MUST render all three lines verbatim per gate 5 in [Hard Gates Recap](action-guidelines.md#hard-gates-recap):

   ```
   Current EAI list:  [<rendered current_tokens>]
   Proposed EAI list: [<rendered proposed_tokens>]
   Removed:           []   (must be empty for attach)
   ```

### Proposed SQL

```sql
ALTER OPENFLOW RUNTIME {runtime_fqn}
  SET EXTERNAL_ACCESS_INTEGRATIONS = ({comma_separated_full_list});
```

The full list MUST include every previously-attached EAI using its preserved raw token, plus the validated new EAI token. Never replace the list with just `{eai_name}`.

### Expected impact

- Current EAI list: `[{comma_separated_current_list}]` (preserved raw tokens from step 2 `DESCRIBE`).
- Proposed EAI list: `[{comma_separated_full_list}]` (preserved existing tokens plus the validated new token).
- `STATUS` stays `ACTIVE` throughout. The runtime does NOT restart and does NOT pass through `RESTARTING` or `UPDATING`. The new EAI is in effect on the next processor scheduling tick. CDC connectors are not paused; non-CDC scheduled connectors are not interrupted.
- No data loss.
- No CDC retention risk -- there is no pause, so the [CDC Retention Warning](action-guidelines.md#cdc-retention-warning-cross-cutting) does NOT apply to this action.
- Cost impact: none.
- Reversible: yes, by another `ALTER OPENFLOW RUNTIME ... SET EXTERNAL_ACCESS_INTEGRATIONS = (...)` that omits the EAI.

### Verification

```sql
DESCRIBE OPENFLOW RUNTIME {runtime_fqn};
```

Confirm `EXTERNAL_ACCESS_INTEGRATIONS` contains both the prior list and the new EAI. Optional: re-run the network entry-point query from `references/troubleshoot-network.md` filtered to the runtime namespace; the `UnknownHostException` pattern should stop appearing within a few minutes.

---

## runtime.restart -- Restart a SQL-managed runtime (no recovery mode)

### Inputs

- `runtime_fqn` (required)
- `reason` (required free text used in the preview, e.g. "stale TLS certs on otherwise stable runtime")

### Preflight

1. Run [Shared Preflight](#shared-preflight) steps 1 and 2.
2. Require `STATUS = 'ACTIVE'`. Stop on any other state.
3. If the diagnostic finding is "stuck upgrading", "OOM crash loop with no resize headroom", or any case marked support-only in `references/troubleshoot-runtime.md`, **stop**. Restart is not the right action for those.
4. Refuse `RESTART RECOVERY`. The Openflow SQL action surface supports the `[RECOVERY]` modifier (it brings the runtime back up with all processors stopped), but the agent does not propose it in MVP -- recovery mode is reserved for break-glass investigation by the customer in the Openflow UI.
5. Enumerate connectors so the preview's `Current state` shows the blast radius (restart stops every connector on the runtime):

```sql
SHOW OPENFLOW CONNECTORS IN ACCOUNT;
-- then filter rows where the `runtime` column matches the short runtime name from `{runtime_fqn}`. (`IN OPENFLOW RUNTIME ...` is not a valid SHOW scope.)
```

   Surface connector names and statuses in the preview. If any connector is a CDC source, add the CDC retention caveat from **Expected impact** below.

### Proposed SQL

```sql
ALTER OPENFLOW RUNTIME {runtime_fqn} RESTART;
```

### Expected impact

- The runtime will become unavailable while restarting (typically a few minutes for SPCS Small/Medium, longer for Large).
- All running connectors stop and restart. CDC connectors resume from last committed offset; non-CDC scheduled connectors resume on next interval.
- **CDC retention risk:** when any CDC connector is present on the runtime, include the [CDC Retention Warning](action-guidelines.md#cdc-retention-warning-cross-cutting). For `runtime.restart` use the **Standard** tier by default; escalate only if the customer's `reason` mentions a multi-hour window or a known stuck-restart history. Cross-reference `references/troubleshoot-runtime.md` (Connector Resume After Runtime Recovery) for the table-restart procedure.
- Reversible: not directly; once restarted, the only "undo" is to wait for it to come back up and inspect.
- Cost impact: minimal (brief downtime).

### Verification

```sql
DESCRIBE OPENFLOW RUNTIME {runtime_fqn};
```

Watch `STATUS` move from `RESTARTING` back to `ACTIVE`. If it lands in `RESTART_FAILED`, do NOT retry from the agent. Surface the failure and pivot to diagnosis.

Apply the [Shared Verification](#shared-verification) rules: **do not promise completion**, and surface a "Task queued" / FIFO response verbatim when Snowflake returns one.

---

## runtime.resume -- Resume a SUSPENDED SQL-managed runtime

### Inputs

- `runtime_fqn` (required)

### Preflight

1. Run [Shared Preflight](#shared-preflight) steps 1 and 2.
2. Require `STATUS = 'SUSPENDED'`. Stop otherwise (no need to "resume" an `ACTIVE` runtime).
3. Refuse `RESUME RECOVERY`. The Openflow SQL action surface supports the `[RECOVERY]` modifier (it resumes the runtime with all processors stopped), but the agent does not propose it in MVP -- recovery mode is reserved for break-glass investigation by the customer in the Openflow UI.

### Proposed SQL

```sql
ALTER OPENFLOW RUNTIME {runtime_fqn} RESUME;
```

### Expected impact

- Runtime spins back up; pods are scheduled again. Cost meter for the runtime resumes.
- Connectors resume per their previously configured state.
- Reversible: yes, via `runtime.suspend` after it reaches `ACTIVE`.

### Verification

```sql
DESCRIBE OPENFLOW RUNTIME {runtime_fqn};
```

Watch `STATUS` move through `ACTIVATING` to `ACTIVE`. `ACTIVATE_FAILED` -> stop and surface the error.

---

## runtime.suspend -- Suspend an ACTIVE SQL-managed runtime

### Inputs

- `runtime_fqn` (required)
- `reason` (required free text, e.g. "pause for cost", "freeze during source DB maintenance window")

### Preflight

1. Run [Shared Preflight](#shared-preflight) steps 1 and 2.
2. If `STATUS = 'SUSPENDED'`, **stop and report** -- the runtime is already suspended. Do not issue a second `ALTER ... SUSPEND`; Snowflake will error on the illegal state transition and the agent has no structured recovery for it.
3. Require `STATUS = 'ACTIVE'` for all other cases. Any non-`ACTIVE`, non-`SUSPENDED` state -> stop.
4. List active connectors so the user knows what stops:

```sql
SHOW OPENFLOW CONNECTORS IN ACCOUNT;
-- then filter rows where the `runtime` column matches the short runtime name from `{runtime_fqn}`. (`IN OPENFLOW RUNTIME ...` is not a valid SHOW scope.)
```

   Surface connector names and statuses in the preview's `Current state` so the user knows the blast radius.

### Proposed SQL

```sql
ALTER OPENFLOW RUNTIME {runtime_fqn} SUSPEND;
```

### Expected impact

- The runtime stops; pods are torn down. No data is lost; CDC connectors will resume from last committed offset on the next `RESUME`.
- **CDC retention risk:** when any CDC connector is present on the runtime, include the [CDC Retention Warning](action-guidelines.md#cdc-retention-warning-cross-cutting). For `runtime.suspend`, ask the mandatory duration prompt from that section before rendering the preview and use the tier selected by the customer's `(a)/(b)/(c)` reply. Do not infer a tier from prose such as "maintenance window" or "over the weekend". Cross-reference `references/troubleshoot-runtime.md` (Connector Resume After Runtime Recovery) for the table-restart procedure.
- Cost impact: runtime cost stops accruing. Parent deployment continues to incur baseline cost.
- Reversible: yes, via `runtime.resume`.

### Verification

```sql
DESCRIBE OPENFLOW RUNTIME {runtime_fqn};
```

Watch `STATUS` transition through `SUSPENDING` to `SUSPENDED`. `SUSPEND_FAILED` -> stop and surface the error.

---

## runtime.set_display_name -- Update the runtime display name

### Inputs

- `runtime_fqn` (required)
- `display_name` (required, non-empty string; will be quoted as `'...'`)

### Preflight

1. Run [Shared Preflight](#shared-preflight) steps 1 and 2.
2. Require `STATUS = 'ACTIVE'` (`DISPLAY_NAME` alter requires the runtime to be active).
3. Refuse if `display_name` matches the existing value (no-op stop).

### Proposed SQL

```sql
ALTER OPENFLOW RUNTIME {runtime_fqn} SET DISPLAY_NAME = '{display_name_escaped}';
```

Escape single quotes in `{display_name_escaped}` by doubling them (`'` -> `''`). Do NOT use the SQL `NAME` -- that is fixed.

### Expected impact

- Cosmetic only. UI label changes; no runtime restart, no data impact, no cost impact.
- Reversible.

### Verification

```sql
DESCRIBE OPENFLOW RUNTIME {runtime_fqn};
```

Confirm `DISPLAY_NAME`.

---

## runtime.set_comment -- Update the runtime comment

### Inputs

- `runtime_fqn` (required)
- `comment` (required, non-empty string)

### Preflight

1. Run [Shared Preflight](#shared-preflight) steps 1 and 2.
2. Validate `STATUS` against the row for `Update comment (ALTER ... SET COMMENT)` in the action eligibility table in `references/openflow-sql/action-guidelines.md`. Allowed states: `ACTIVE`, `SUSPENDED`. Refuse on any other state. Do not restate the fail-closed list here -- the eligibility table is the single source of truth.

### Proposed SQL

```sql
ALTER OPENFLOW RUNTIME {runtime_fqn} SET COMMENT = '{comment_escaped}';
```

Escape single quotes in `{comment_escaped}` by doubling them (`'` -> `''`), matching the rule used for `set_display_name`.

### Expected impact

- Metadata only. No restart, no data impact.
- Reversible via another `ALTER ... SET COMMENT` or `ALTER ... UNSET COMMENT`.

### Verification

```sql
DESCRIBE OPENFLOW RUNTIME {runtime_fqn};
```

Confirm `COMMENT`.

---

## runtime.unset_display_name -- Clear the runtime display name

### Inputs

- `runtime_fqn` (required)

### Preflight

1. Run [Shared Preflight](#shared-preflight) steps 1 and 2.
2. Require `STATUS = 'ACTIVE'` (`DISPLAY_NAME` alter requires the runtime to be active, per the action eligibility table in `references/openflow-sql/action-guidelines.md`).
3. If `DISPLAY_NAME` is already unset (NULL or empty in the `DESCRIBE` output), **stop and report** -- no action needed.

### Proposed SQL

```sql
ALTER OPENFLOW RUNTIME {runtime_fqn} UNSET DISPLAY_NAME;
```

### Expected impact

- Cosmetic only. The UI label reverts to the SQL `NAME`. No runtime restart, no data impact, no cost impact.
- Reversible by `ALTER OPENFLOW RUNTIME ... SET DISPLAY_NAME = '...'` (the previous display name is not preserved -- the customer must supply it again if they want to restore).

### Verification

```sql
DESCRIBE OPENFLOW RUNTIME {runtime_fqn};
```

Confirm `DISPLAY_NAME` is NULL or empty.

---

## runtime.unset_comment -- Clear the runtime comment

### Inputs

- `runtime_fqn` (required)

### Preflight

1. Run [Shared Preflight](#shared-preflight) steps 1 and 2.
2. Validate `STATUS` against the row for `Update comment (ALTER ... SET COMMENT)` in the action eligibility table in `references/openflow-sql/action-guidelines.md`. Allowed states: `ACTIVE`, `SUSPENDED`. Refuse on any other state.
3. If `COMMENT` is already unset (NULL or empty in the `DESCRIBE` output), **stop and report** -- no action needed.

### Proposed SQL

```sql
ALTER OPENFLOW RUNTIME {runtime_fqn} UNSET COMMENT;
```

### Expected impact

- Metadata only. No runtime restart, no data impact, no cost impact.
- Reversible by `ALTER OPENFLOW RUNTIME ... SET COMMENT = '...'` (the previous comment is not preserved -- the customer must supply it again if they want to restore).

### Verification

```sql
DESCRIBE OPENFLOW RUNTIME {runtime_fqn};
```

Confirm `COMMENT` is NULL or empty.

---

## After Any Successful Action

- Report the before/after values from the verification query in plain language.
- If the action was triggered from a diagnostic finding, run the original confirmatory query (e.g. the network entry-point query from `references/troubleshoot-network.md`) bounded to the post-action window so the customer can see the error pattern stop.
- Drop back to diagnostic mode for any further work. Do not chain a second mutation in the same response without a fresh user request and a fresh preview.
