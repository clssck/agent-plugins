# Versioning without Release Channels (DISABLED)

Use these commands when `DESCRIBE APPLICATION PACKAGE` shows `release_channels = DISABLED`.

## Add a Version

```sql
ALTER APPLICATION PACKAGE <pkg>
  ADD VERSION <version_name>
  USING '@<pkg>.<schema>.<stage>';
```

Key differences from release channel path:
- `ADD VERSION` instead of `REGISTER VERSION`
- Release directive is set directly on the package (no channel needed)

## Add a Patch

```sql
ALTER APPLICATION PACKAGE <pkg>
  ADD PATCH FOR VERSION <version_name>
  USING '@<pkg>.<schema>.<stage>';
```

The patch number auto-increments.

## Publish / Set Release Directive

Set the release directive directly on the package:

```sql
ALTER APPLICATION PACKAGE <pkg>
  SET DEFAULT RELEASE DIRECTIVE
  VERSION = <version_name>
  PATCH = <patch_number>;
```

## Remove a Version

You **cannot** drop a version that is actively referenced by a release directive. Follow this order:

**Step 1: Change the release directive** to a different version:

```sql
ALTER APPLICATION PACKAGE <pkg>
  SET DEFAULT RELEASE DIRECTIVE
  VERSION = <other_version>
  PATCH = <patch_number>;
```

**Step 2: Drop the version:**

```sql
ALTER APPLICATION PACKAGE <pkg>
  DROP VERSION <version_name>;
```

## View Status

```sql
-- View all versions and patches
SHOW VERSIONS IN APPLICATION PACKAGE <pkg>;

-- View package details including release directive
DESCRIBE APPLICATION PACKAGE <pkg>;
```

## Constraints

| Constraint | Limit |
|------------|-------|
| Versions per package | 2 |
| Patches per version | 130 |
| Drop patches individually | Not allowed |
