# View Quota Exclusions

View which users are excluded from quota enforcement scope.

> **See**: Parent `SKILL.md` for guardrails and interaction rules.

## Reference Files

- `references/quota/exclusions.md`

---

## How to View Exclusions

### GET_QUOTA_SCOPE

Returns the full scope JSON. When the quota uses `ALL_USERS` operator, exclusion tags are stored as the tag array — users matching those tags are excluded from enforcement.

```sql
CALL {quota_fqn}!GET_QUOTA_SCOPE();
```

**Returns** a VARIANT with structure:
```json
{
  "user_tags": {
    "operator": "ALL_USERS",
    "tags": [
      {
        "tagName": "EXEMPT_TAG",
        "tagDatabase": "MY_DB",
        "tagSchema": "MY_SCHEMA",
        "tagValues": ["true"]
      }
    ]
  }
}
```

When `operator` is `ALL_USERS`, the `tags` array represents **exclusion** tags — users matching any of these tags are excluded from the quota.

---

### GET_USERS

Returns the resolved user list with exclusions already applied. Excluded users do not appear in the result.

```sql
CALL {quota_fqn}!GET_USERS();
```

**Returns**: `USER_ID` (NUMBER), `USER_NAME` (VARCHAR) — only users who are currently in scope (after exclusions are filtered out).

---

## Presenting Results

Show the user:
1. The exclusion tags from `GET_QUOTA_SCOPE` (tag name, database, schema, values)
2. Optionally the resolved user list from `GET_USERS` to confirm which users remain in scope
