# Create Quota

Step-by-step workflow for creating a new Snowflake Quota — includes lifecycle, user scope, limits, shared resources, and optional block enforcement.

> **See**: Parent `SKILL.md` for routing, guardrails, scope homogeneity rule, and interaction rules.

## Reference Files

- `references/quota/lifecycle.md`
- `references/quota/limits.md`
- `references/quota/shared-resources.md`
- `references/quota/enforcement.md`
- `references/quota/exclusions.md`

---

## Workflow

> **⚠️ Execution order**: All method calls (SET_USER_TAGS, SET_PER_USER_LIMIT, etc.) require the quota to exist first. Always execute `CREATE SNOWFLAKE.CORE.QUOTA` before any method calls — otherwise you'll get "Object does not exist" errors.

### Step 1: Quota Identity

Collect (confirm pre-provided values rather than re-asking):
- **Quota name** — Object name
- **Database.Schema** — Location for the quota instance

Use `CREATE SNOWFLAKE.CORE.QUOTA` from reference file `references/quota/lifecycle.md`.

---

### Step 2: Set User Scope

Users in scope are defined via user tags. This determines which users the quota monitors.

#### Option A: Tag-Based Selection (specific user groups)

Collect tag key/value pairs:
- Resolve any short tag name to its fully qualified form per parent skill rules.
- Ask "Would you like to add another user tag?" and repeat until done.

Then ask for the operator:
```
How should multiple tags be combined?
- UNION (default): Users matching ANY tag are included
- INTERSECTION: Users must match ALL tags
```

Use `SET_USER_TAGS` from reference file `references/quota/lifecycle.md`.

#### Option B: ALL_USERS (account-wide)

Monitors every user in the account.

```
Should this quota apply to ALL users in the account?
```

Use `SET_USER_TAGS` with `ALL_USERS` operator from reference file `references/quota/lifecycle.md`.

---

### Step 3: Set Per-User Limits

The per-user limit is required for the quota to evaluate thresholds.

```
What monthly per-user credit limit would you like to set?
```

Optionally, a daily limit can also be set for enforcement purposes using the 'DAILY' cycle.

Use `SET_PER_USER_LIMIT` from reference file `references/quota/limits.md`.

---

### Step 4: Add Shared Resources

**Do this for every quota.** A quota with no shared resources configured measures **0 credits** —
thresholds never fire and spending methods return nothing. See reference file
`references/quota/shared-resources.md`.

Ask which domains the quota should track, keeping the usage unit homogeneous:
```
Which resources should this quota track?
- Compute: WAREHOUSE
- AI credits: AI FUNCTION, CORTEX AGENT, SNOWFLAKE INTELLIGENCE, CORTEX_CODE
```

AI-credit and compute domains cannot be mixed on one quota — that is rejected at config time. If the
user wants both, create one quota per usage unit.

Use `ADD_SHARED_RESOURCE` from reference file `references/quota/shared-resources.md`.

---

### Step 5: Enable Block Enforcement (Optional)

If the user wants automatic user blocking when limits are breached:

1. Set a daily per-user limit using `SET_PER_USER_LIMIT` with `'DAILY'` cycle from reference file `references/quota/limits.md`
2. Ask whether blocked users should be emailed:
   ```
   Should users receive an email when they are blocked or unblocked?
   ```
3. Enable enforcement with `SET_BLOCK_ENFORCEMENT_ENABLED(enabled, send_emails)` from reference
   file `references/quota/enforcement.md`, always passing both arguments. Omitting the second one
   stops per-user block emails
4. Optionally exclude users using `EXCLUDE_USERS` from reference file `references/quota/exclusions.md` (only when scope is ALL_USERS)

---

### Step 6: Verify

Use `GET_QUOTA_SCOPE` and `GET_CONFIG` from reference file `references/quota/lifecycle.md`.

Present the result to the user.

---

### Step 7: Suggest Next Steps

- Configure notification thresholds (load `notifications/SKILL.md`)
- Configure custom actions — stored procedures on breach (load `custom-actions/SKILL.md`)
- Configure cycle-start reset action (load `cycle-start-actions/SKILL.md`)
