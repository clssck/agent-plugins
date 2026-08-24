# Versioning with Release Channels (ENABLED)

Use these commands when `DESCRIBE APPLICATION PACKAGE` shows `release_channels = ENABLED`.

## Register a Version

```sql
ALTER APPLICATION PACKAGE <pkg>
  REGISTER VERSION <version_name>
  USING '@<pkg>.<schema>.<stage>';
```

**Important:** `ADD VERSION USING '@stage'` is **NOT supported** when release channels are enabled. Use `REGISTER VERSION`.

## Add a Patch

```sql
ALTER APPLICATION PACKAGE <pkg>
  ADD PATCH FOR VERSION <version_name>
  USING '@<pkg>.<schema>.<stage>';
```

The patch number auto-increments.

## Publish to Consumers

This is a **2-step process**: Add version to channel → Set release directive.

### Add Version to a Release Channel

```sql
ALTER APPLICATION PACKAGE <pkg>
  MODIFY RELEASE CHANNEL <channel>
  ADD VERSION <version_name>;
```

Available channels:

| Channel | Audience | Security Scan | Use Case |
|---------|----------|---------------|----------|
| **QA** | Internal org accounts only | Not required | Internal testing |
| **ALPHA** | External accounts (must be added) | Async - can install while pending | UAT / preview |
| **DEFAULT** | All consumers via listing | Must pass before install | Production |

Max **2 versions per release channel** at a time. If the channel already has 2, drop one first (see Remove a Version below).

### Set the Release Directive

**Default release directive** (applies to all consumers in the channel):
```sql
ALTER APPLICATION PACKAGE <pkg>
  MODIFY RELEASE CHANNEL <channel>
  SET DEFAULT RELEASE DIRECTIVE
  VERSION = <version_name>
  PATCH = <patch_number>;
```

**Custom release directive** (targets specific accounts):
```sql
ALTER APPLICATION PACKAGE <pkg>
  MODIFY RELEASE CHANNEL <channel>
  SET RELEASE DIRECTIVE <directive_name>
  ACCOUNTS = (<org>.<account>)
  VERSION = <version_name>
  PATCH = <patch_number>;
```

**Scheduled upgrade** (delays automatic upgrade):
```sql
ALTER APPLICATION PACKAGE <pkg>
  MODIFY RELEASE CHANNEL <channel>
  SET DEFAULT RELEASE DIRECTIVE
  VERSION = <version_name>
  PATCH = <patch_number>
  UPGRADE_AFTER = '2025-06-01T09:00:00Z';
```

Setting the release directive triggers an **automatic upgrade** of all installed app instances on that channel. Use `UPGRADE_AFTER` to schedule when the upgrade begins.

## Remove a Version

You **cannot** deregister a version that is actively referenced by a release directive or release channel. Follow this order:

**Step 1: Change the release directive** on every channel that references this version:

```sql
ALTER APPLICATION PACKAGE <pkg>
  MODIFY RELEASE CHANNEL <channel>
  SET DEFAULT RELEASE DIRECTIVE
  VERSION = <other_version>
  PATCH = <patch_number>;
```

**Step 2: Remove the version from all release channels:**

```sql
ALTER APPLICATION PACKAGE <pkg>
  MODIFY RELEASE CHANNEL <channel>
  DROP VERSION <version_name>;
```

This is **asynchronous** — the version is only fully removed after all consumers have upgraded off it. Repeat for every channel that has this version.

**Step 3: Deregister the version** (frees up the version slot):

```sql
ALTER APPLICATION PACKAGE <pkg>
  DEREGISTER VERSION <version_name>;
```

This removes the version and all its patches.

## Manage Release Channels

By default, only DEFAULT is active. To use QA or ALPHA, add accounts to them:

```sql
-- Add accounts to a channel
ALTER APPLICATION PACKAGE <pkg>
  MODIFY RELEASE CHANNEL <channel>
  ADD ACCOUNTS = (<org>.<account>);

-- Remove accounts from a channel
ALTER APPLICATION PACKAGE <pkg>
  MODIFY RELEASE CHANNEL <channel>
  REMOVE ACCOUNTS = (<org>.<account>);
```

To install from QA or ALPHA (consumer needs `CREATE PREVIEW APPLICATION` privilege):
```sql
CREATE APPLICATION <app_name>
  FROM APPLICATION PACKAGE <pkg>
  USING RELEASE CHANNEL QA;
```

If no `USING RELEASE CHANNEL` clause is specified, DEFAULT is used.

## Constraints

| Constraint | Limit |
|------------|-------|
| Unassigned versions per package | 2 |
| Versions per release channel | 2 |
| Patches per version | 130 |
| Drop patches individually | Not allowed |
| Disable release channels once enabled | Not allowed |
| `ADD VERSION USING` with release channels | Not supported |
