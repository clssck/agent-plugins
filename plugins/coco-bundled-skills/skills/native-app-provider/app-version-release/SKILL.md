---
name: app-version-release
description: "Manage versions, patches, and release channels for a Snowflake Native App package. Register versions, add patches, publish to release channels, set release directives, and upgrade consumers. Triggers: version, patch, release channel, publish app, register version, release directive, upgrade consumers, deregister version."
parent_skill: native-app-provider
---

# App Version & Release Management

## When to Load

From the root `native-app-provider` skill when the user wants to create a version, add a patch, or publish to a release channel.

## Guard Rails

- **Do NOT add a version to a release channel or set a release directive unless the user explicitly asks to publish, release, or upgrade consumers.** Creating a version and publishing it are separate actions.
- **Do NOT drop a version from a release channel or application package unless the user explicitly asks for it.**

## Prerequisites

Check whether the current role owns the application package or has `MANAGE VERSIONS` and `MANAGE RELEASES` privileges on it. If either is missing, propose granting them and wait for approval before continuing.

## Step 1: Check Release Channel Status

> **Always run this BEFORE any version or patch command.** The correct SQL syntax differs depending on whether release channels are enabled or disabled. Using the wrong syntax will fail.

```sql
DESCRIBE APPLICATION PACKAGE <app_pkg>;
```

Look for the `release_channels` property in the result:
- **ENABLED** (or TRUE): Release channels are active → use **Modern** syntax below.
- **DISABLED** (or FALSE): Release channels are off → use **Legacy** syntax below.

**You MUST check this for every package** before running any version or release directive commands. Different packages may have different settings.

## Step 2: Ask What the User Wants to Do

**Ask** the user:
```
What would you like to do?

1. View current status — Show versions, patches, and release channels
2. Add a patch to an existing version — For bug fixes or security patches
3. Create a new version — For new features, or major updates
4. Publish to consumers — Add a version to a release channel and set the release directive
```

**STOP**: Wait for user selection. Route to the matching path below.

---

## Path A: View Current Status

```sql
-- View all versions and patches
SHOW VERSIONS IN APPLICATION PACKAGE <pkg>;

-- View release channels and their versions (modern only)
SHOW RELEASE CHANNELS IN APPLICATION PACKAGE <pkg>;

-- View release directives
SHOW RELEASE DIRECTIVES IN APPLICATION PACKAGE <pkg>;
```

For legacy packages, use `DESCRIBE APPLICATION PACKAGE <pkg>` to see the release directive.

---

## Path B: Add a Patch to an Existing Version

### B1: Identify the Target Version

If the user hasn't specified which version to patch, check existing versions:

```sql
SHOW VERSIONS IN APPLICATION PACKAGE <pkg>;
```

**Ask** the user which version to patch if multiple exist.

### B2: Add the Patch

Upload updated files to stage first, then:

```sql
ALTER APPLICATION PACKAGE <pkg>
  ADD PATCH FOR VERSION <version_name>
  USING '@<pkg>.<schema>.<stage>';
```

The patch number auto-increments. Max **130 patches** per version. Patches **cannot be dropped** — the version must be dropped, which drops all patches too.

### After Adding the Patch

If the version is already on a release channel, its patches are **automatically bound** to that channel. You only need to update the release directive to point to the new patch (see Path D).

### Security Scan After Adding a Version or Patch

When you add a new version or patch to an application package, or set the distribution to External, Snowflake automatically runs a security scan. Check the scan status with:

```sql
SHOW VERSIONS IN APPLICATION PACKAGE <package_name>;
```

**Next steps:**
- The automated scan typically completes within a few hours
- If the automated scan fails, Snowflake performs a manual review (additional time required)
- If the status remains `PENDING` for an unexpectedly long time, contact Snowflake Support
- After manual review, status updates to `APPROVED` or `REJECTED`

---

## Path C: Create a New Version

### Modern (Release Channels ENABLED)

**Important:** With release channels enabled, `ADD VERSION` is **NOT supported** and will error. You **must** use `REGISTER VERSION`:

```sql
ALTER APPLICATION PACKAGE <pkg>
  REGISTER VERSION <version_name>
  USING '@<pkg>.<schema>.<stage>';
```

Max **2 unassigned versions** (not added to any channel) at a time. If you already have 2, deregister one first (see `../references/version-with-release-channel.md` → "Remove a Version").

### Legacy (Release Channels DISABLED)

```sql
ALTER APPLICATION PACKAGE <pkg>
  ADD VERSION <version_name>
  USING '@<pkg>.<schema>.<stage>';
```

---

## Path D: Publish to Consumers

> **Only do this when the user explicitly asks to publish, release, or make a version available to consumers.** Do not proceed automatically after creating a version or patch.

### Modern (Release Channels ENABLED)

This is a **2-step process**. You must do both steps in order:

**Step 1: Add the version to a release channel:**

```sql
ALTER APPLICATION PACKAGE <pkg>
  MODIFY RELEASE CHANNEL <channel>
  ADD VERSION <version_name>;
```

**Step 2: Set the release directive on that channel:**

```sql
ALTER APPLICATION PACKAGE <pkg>
  MODIFY RELEASE CHANNEL <channel>
  SET DEFAULT RELEASE DIRECTIVE
  VERSION = <version_name>
  PATCH = <patch_number>;
```

For custom directives, scheduled upgrades, or managing channel accounts, see `../references/version-with-release-channel.md` → "Set the Release Directive" and "Manage Release Channels".

**STOP — MANDATORY CHECKPOINT**: Before setting the release directive, present the version and target channel to the user and confirm they want to publish. Setting a release directive triggers automatic upgrades for all consumers on the channel.

### Legacy (Release Channels DISABLED)

Set the release directive directly on the package (no channels):

```sql
ALTER APPLICATION PACKAGE <pkg>
  SET DEFAULT RELEASE DIRECTIVE
  VERSION = <version_name>
  PATCH = <patch_number>;
```

---

## Manage Release Channels

By default, only DEFAULT is active. To manage QA or ALPHA channels (add/remove accounts, install from non-default channels), see `../references/version-with-release-channel.md` → "Manage Release Channels".

---

## Version Lifecycle Management

For removing versions and deregistering, see `../references/version-with-release-channel.md` → "Remove a Version" (modern) or `../references/version-without-release-channel.md` → "Remove a Version" (legacy).

Key constraints: max 2 unassigned versions per package, max 2 versions per release channel, max 130 patches per version, patches cannot be dropped individually, release channels cannot be disabled once enabled.

#### Version Stuck in "Dropping" State

A version can only be dropped when no release directives reference it and no app is currently using it (including apps mid-upgrade). Check for blocking applications:

```sql
SELECT *
FROM snowflake.data_sharing_usage.application_state_view
WHERE package_name = '<pkg>'
  AND upgrade_state != 'DISABLED'
  AND (
      version = '<version_name>'
      OR (previous_version = '<version_name>' AND upgrade_state = 'FINALIZING')
  );
```

If applications are still on the version or finalizing an upgrade from it, wait for them to complete. Disabled applications do not block a version drop.

For packages with **Listing Auto-Refresh enabled** (the default for most packages), drops typically complete quickly. If the drop is still pending after a few minutes, verify it is enabled:

```sql
DESCRIBE APPLICATION PACKAGE <pkg>;
```

Look for `LISTING_AUTO_REFRESH`. If it is `FALSE`, you can enable it or manually trigger a replication refresh:

See [Upgrade an installed app across multiple regions](https://docs.snowflake.com/en/developer-guide/native-apps/versioning#upgrade-an-installed-app-across-multiple-regions) for replication scheduling options.

If the version remains `Dropping` after a full refresh cycle, contact Snowflake Support.

---

## Prepare for Listing

If the user wants to create a listing for the application package, the following prerequisites must be met **before** running `CREATE EXTERNAL LISTING`:

1. **At least one version must be registered** in the package (see Path C above)
2. **The version must be added to the DEFAULT release channel** (modern packages):

```sql
ALTER APPLICATION PACKAGE <pkg>
  MODIFY RELEASE CHANNEL DEFAULT
  ADD VERSION <version_name>;
```

3. **A default release directive must be set** on the DEFAULT channel:

```sql
ALTER APPLICATION PACKAGE <pkg>
  MODIFY RELEASE CHANNEL DEFAULT
  SET DEFAULT RELEASE DIRECTIVE
  VERSION = <version_name>
  PATCH = <patch_number>;
```

Without these steps, `CREATE EXTERNAL LISTING` will fail with: *"No default release directive is found for application package"*.

For legacy packages (release channels DISABLED), set the release directive directly on the package instead (see Path D Legacy syntax).

> **Troubleshooting**: If you see `"The Release Directive of this application package contains invalid patch to share to external account"` when creating a listing, the release directive has not been set. Run the `SET DEFAULT RELEASE DIRECTIVE` command above before creating the listing.

**Once prerequisites are met**, load `../references/publish-listing.md` for the full `CREATE EXTERNAL LISTING` syntax, manifest format, and examples.

## Output

- Version registered/added or patch added in application package
- Version added to target release channel (only when user asks to publish)
- Release directive set, triggering consumer upgrades
