---
name: alter-storage-integration
description: >
  Modify properties of an existing storage integration. Change allowed/blocked locations,
  rotate IAM roles, enable/disable, manage tags and comments. Triggers: ALTER STORAGE INTEGRATION,
  modify storage integration, change allowed locations, rotate IAM role, disable integration,
  update storage integration, add tag to integration, UNSET, blocked locations.
---

# Alter Storage Integration

Modify properties of an existing storage integration without breaking stages that reference it.

## When to Use

Use this skill when the user wants to:
- Change allowed or blocked storage locations
- Rotate an IAM role (S3) or update a tenant ID (Azure)
- Enable or disable an integration
- Add, change, or remove tags or comments
- Reset properties to defaults

## Key Guidance

**Always prefer ALTER over CREATE OR REPLACE.** Recreating an integration generates a new hidden ID and breaks all stages that reference it. ALTER preserves the hidden ID.

**SET TAG and SET COMMENT must be in separate ALTER statements** — they cannot be combined in a single SET clause.

## Common Operations

**Change allowed locations:**

```sql
ALTER STORAGE INTEGRATION <name> SET
  STORAGE_ALLOWED_LOCATIONS = ('s3://new-bucket/path/');
```

**Add blocked locations:**

```sql
ALTER STORAGE INTEGRATION <name> SET
  STORAGE_BLOCKED_LOCATIONS = ('s3://sensitive-bucket/');
```

**Rotate IAM role (S3):**

```sql
ALTER STORAGE INTEGRATION [ IF EXISTS ] <name> SET
  STORAGE_AWS_ROLE_ARN = '<new-role-arn>';
```

After rotating, run `DESCRIBE STORAGE INTEGRATION <name>` to get the updated `STORAGE_AWS_IAM_USER_ARN` and `STORAGE_AWS_EXTERNAL_ID` for the new trust policy.

**Update Azure tenant:**

```sql
ALTER STORAGE INTEGRATION [ IF EXISTS ] <name> SET
  AZURE_TENANT_ID = '<new-tenant-id>';
```

**Enable or disable:**

```sql
ALTER STORAGE INTEGRATION <name> SET ENABLED = TRUE;
ALTER STORAGE INTEGRATION <name> SET ENABLED = FALSE;
```

**Add a comment:**

```sql
ALTER STORAGE INTEGRATION <name> SET
  COMMENT = 'Production data lake integration';
```

**Add a tag** (must be a separate ALTER from SET COMMENT):

```sql
ALTER STORAGE INTEGRATION <name> SET TAG
  cost_center = 'analytics-prod';
```

**Remove a tag:**

```sql
ALTER STORAGE INTEGRATION <name> UNSET TAG cost_center;
```

**Enable PrivateLink:**

```sql
ALTER STORAGE INTEGRATION <name> SET
  USE_PRIVATELINK_ENDPOINT = TRUE;
```

**Enable cross-account ACL (S3):**

```sql
ALTER STORAGE INTEGRATION <name> SET
  STORAGE_AWS_OBJECT_ACL = 'bucket-owner-full-control';
```

**Reset properties to defaults** (UNSET):

```sql
ALTER STORAGE INTEGRATION <name> UNSET
  STORAGE_BLOCKED_LOCATIONS, COMMENT;
```

Properties that can be UNSET: `ENABLED`, `STORAGE_BLOCKED_LOCATIONS`, `COMMENT`, `TAG`.

## Access Control

| Privilege | Object | Notes |
|---|---|---|
| OWNERSHIP | Integration | Required to alter. |

## Important Constraints

- `SET TAG` and `SET COMMENT` (or other properties) must be in separate ALTER statements.
- `IF EXISTS` can be used to avoid errors if the integration was already dropped.
- Changing `STORAGE_ALLOWED_LOCATIONS` replaces the entire list — you must include all desired locations, not just new ones.

## Stopping Points

None — ALTER operations are non-destructive and reversible.
