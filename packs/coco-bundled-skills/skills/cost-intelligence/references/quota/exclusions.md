# Quota User Exclusions

Methods for excluding specific users from quota enforcement scope.

**Semantic keywords:** exclude users, exempt users, tag exclusion, enforcement exclusion

---

## EXCLUDE_USERS

```sql
CALL {quota_fqn}!EXCLUDE_USERS('{target_type}', {targets});
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.
> **Applicability**: Only applicable when the quota uses `ALL_USERS` scope.

> **This overwrites the quota's whole tag list.** `EXCLUDE_USERS` is a thin wrapper that calls
> `SET_USER_TAGS(targets, 'ALL_USERS')`. Exclusions and user scope are stored in the same field, so
> each call replaces everything set previously by either method. To add an exclusion, pass the
> complete desired set of exclusion pairs — not just the new one. Read the current set from
> `GET_QUOTA_SCOPE` first.

**Parameters:**
- `target_type`: VARCHAR — the type of target for exclusion. Only `'TAG'` is accepted; anything else
  fails with an unsupported-target-type error. `'USER'` is not implemented
- `targets`: ARRAY — an array of `[tag_ref, tag_value]` pairs identifying users to exclude

**Target Types:**
- `'TAG'`: Excludes users matching any of the provided tag reference/value pairs

**Examples:**
```sql
-- Exclude users with the 'exempt' tag value
CALL my_db.my_schema.my_quota!EXCLUDE_USERS(
    'TAG',
    [
        [(SELECT SYSTEM$REFERENCE('TAG', 'my_db.my_schema.exempt_tag', 'SESSION', 'APPLYBUDGET')), 'true']
    ]
);

-- Exclude users matching multiple tags
CALL my_db.my_schema.my_quota!EXCLUDE_USERS(
    'TAG',
    [
        [(SELECT SYSTEM$REFERENCE('TAG', 'my_db.my_schema.exempt_tag', 'SESSION', 'APPLYBUDGET')), 'true'],
        [(SELECT SYSTEM$REFERENCE('TAG', 'my_db.my_schema.admin_tag', 'SESSION', 'APPLYBUDGET')), 'yes']
    ]
);
```

> **Limitations:**
> - Only supported when quota scope is `ALL_USERS`
> - Only `'TAG'` target type is supported today
