---
name: openflow-observability-deployment-actions
description: Deployment-level Openflow SQL action templates and preflight (metadata only). Tier 2 -- load only when the Openflow SQL Action Mode has been entered and an allowlisted deployment metadata action candidate exists.
---

<a id="openflow-sql-deployment-actions"></a>
# Openflow SQL Deployment Actions

> Customer-facing name for actions in this file: **Openflow SQL actions for deployments**.

Templates and preflight for the **deployment-level metadata** actions in the MVP allowlist. Every template here assumes [`action-guidelines.md`](action-guidelines.md) is already loaded and all five hard gates from [SKILL.md](../../SKILL.md#openflow-sql-action-mode) will be enforced before the proposed SQL is executed.

## Scope

- Preflight queries shared by deployment metadata actions
- Per-action template: input fields, preflight, exact SQL, expected impact, verification
- Out of scope: deployment lifecycle (`CREATE`, `TERMINATE`, `DROP`, `UPGRADE`), deployment data plane settings, anything privilege-bearing -- all denylisted in [`action-guidelines.md`](action-guidelines.md#action-denylist-mvp)

The MVP only allows two deployment-scoped actions, both metadata-only:

- `deployment.set_display_name`
- `deployment.set_comment`

Both require deployment `OWNERSHIP` on the Snowflake side (per the Openflow privilege model -- `SET` on the deployment is an `OWNERSHIP`-gated operation, not `OPERATE`). If the customer lacks `OWNERSHIP`, fail closed and direct them to the deployment owner. Do not silently fall back to a runtime-scoped action.

---

## Shared Preflight (Deployment Metadata)

Run before any of the per-action templates below. The output of these queries is what fills the **Current state** field in the [Confirmation Preview Format](action-guidelines.md#confirmation-preview-format).

### 1. Resolve the deployment name

`DESCRIBE OPENFLOW DEPLOYMENT` requires the deployment **NAME**, not the UUID. The Snowsight skill context provides `{deployment_id}` as a UUID, so resolve it to a name first:

```sql
SHOW OPENFLOW DEPLOYMENTS;
```

Find the row where the UUID column matches `{deployment_id}` and capture `NAME` as `{deployment_name}`. If zero rows match, **fail closed** -- the UUID is stale or the role cannot see the deployment; fall back to UI guidance.

If the user gave a name directly (no UUID context), accept it but still verify with `SHOW OPENFLOW DEPLOYMENTS LIKE '{deployment_name}'`. Multiple matches -> stop and ask the customer to disambiguate.

> **Quoting rule (BLOCKING).** `SHOW OPENFLOW DEPLOYMENTS` returns the `name` field in the case it was created. Snowflake uppercases bare identifiers in subsequent SQL, so a deployment created lowercase (e.g., `spcs`, `byoc`, `spcs_terraform`) MUST be wrapped in double quotes in every downstream `DESCRIBE` / `ALTER` / `SHOW GRANTS ON` statement: `DESCRIBE OPENFLOW DEPLOYMENT "spcs";`. Without quotes, Snowflake uppercases to `SPCS` and returns `'SPCS' does not exist or not authorized` even though the row is plainly visible in `SHOW OPENFLOW DEPLOYMENTS`. When generating SQL templates below, always quote `{deployment_name}` if it contains any lowercase characters; quoting an already-uppercase name is a no-op and is safe to apply unconditionally.

### 2. Describe the deployment

```sql
DESCRIBE OPENFLOW DEPLOYMENT "{deployment_name}";
```

Capture: `STATUS`, `DISPLAY_NAME`, `COMMENT`, `OWNER`, `DEPLOYMENT_TYPE`.

Validate `STATUS = 'ACTIVE'`. Any other state (`CREATING`, `CREATE_FAILED`, `INACTIVE`, `NOT_REPORTING`, `NOT_HEALTHY`, `DELETING`, `DELETE_FAILED`, `DELETED`, `DEACTIVATION_REQUIRED`, `UPGRADING`, `UPGRADE_FAILED`) -> **fail closed**, do not propose metadata changes against an unhealthy or in-flight deployment.

### 3. Confirm the customer holds OWNERSHIP

```sql
SHOW GRANTS ON OPENFLOW DEPLOYMENT "{deployment_name}";
```

Find a row with `privilege = 'OWNERSHIP'` and `grantee_name` matching the customer's current role (or a role that has been granted to them via role hierarchy, if known). If `OWNERSHIP` is not held, **fail closed**. Surface this as customer-run guidance: tell the customer which role currently owns the deployment and recommend they ask that owner to make the metadata change (or transfer ownership, which is itself out of MVP scope).

If the customer's role identity is not directly known to the agent, present the `OWNERSHIP` row from `SHOW GRANTS` to the customer and ask them to confirm they hold or inherit it before previewing the action. Do not assume.

---

## deployment.set_display_name -- Update the deployment display name

### Inputs

- `deployment_name` (required, the SQL `NAME` of the deployment, not the UUID)
- `display_name` (required, non-empty string; will be quoted as `'...'`)

### Preflight

1. Run [Shared Preflight](#shared-preflight-deployment-metadata) steps 1, 2, and 3.
2. Refuse if `display_name` matches the existing value (no-op stop).
3. Escape single quotes in the input by doubling them (`'` -> `''`).

### Proposed SQL

```sql
ALTER OPENFLOW DEPLOYMENT "{deployment_name}" SET DISPLAY_NAME = '{display_name_escaped}';
```

Do NOT use the SQL `NAME` of the deployment -- that is fixed.

### Expected impact

- Cosmetic only. The Openflow UI label changes; no deployment restart, no data plane impact, no cost impact.
- All runtimes and connectors hosted in the deployment continue to run unchanged.
- Reversible via another `ALTER OPENFLOW DEPLOYMENT ... SET DISPLAY_NAME = '...'` (or `UNSET DISPLAY_NAME`, which is NOT in the MVP allowlist -- treat that as customer-run guidance).

### Verification

```sql
DESCRIBE OPENFLOW DEPLOYMENT "{deployment_name}";
```

Confirm `DISPLAY_NAME` matches the new value.

---

## deployment.set_comment -- Update the deployment comment

### Inputs

- `deployment_name` (required, the SQL `NAME` of the deployment, not the UUID)
- `comment` (required, non-empty string)

### Preflight

1. Run [Shared Preflight](#shared-preflight-deployment-metadata) steps 1, 2, and 3.
2. Refuse if `comment` matches the existing value (no-op stop).
3. Escape single quotes in the input by doubling them (`'` -> `''`).

### Proposed SQL

```sql
ALTER OPENFLOW DEPLOYMENT "{deployment_name}" SET COMMENT = '{comment_escaped}';
```

### Expected impact

- Metadata only. No deployment restart, no data plane impact, no cost impact.
- All runtimes and connectors hosted in the deployment continue to run unchanged.
- Reversible via another `ALTER OPENFLOW DEPLOYMENT ... SET COMMENT = '...'` (or `UNSET COMMENT`, which is NOT in the MVP allowlist -- treat that as customer-run guidance).

### Verification

```sql
DESCRIBE OPENFLOW DEPLOYMENT "{deployment_name}";
```

Confirm `COMMENT` matches the new value.

---

## After Any Successful Action

- Report the before/after values from the verification query in plain language.
- Drop back to diagnostic mode for any further work. Do not chain a second mutation in the same response without a fresh user request and a fresh preview.
- If the customer asks to also change runtime metadata in the same conversation, run a separate preflight + preview for the runtime action -- do not bundle a deployment `ALTER` with a runtime `ALTER` in one preview.
