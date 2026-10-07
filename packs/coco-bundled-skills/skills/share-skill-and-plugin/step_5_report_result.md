# Step 5: Report the Result

Use `<artifact_noun>` ("skill" or "plugin") in user-facing copy.

## Share Success

Tell the user the `<artifact_noun>` was **shared** successfully (avoid
**published**). Include name + FQN, audience, DISCOVERABLE, and share URI.
On content-only re-share, say "share options were preserved".

When step 1 pivoted to first-time share because manifest `name` changed, say
this is a **new** catalog entry and the **superseded** FQN is **unchanged**.

URI: prefer versioned form from post-share `DESCRIBE`
(`snow://skill_catalog/…/versions/version$<N>/`), else bare catalog URI.

**Coworker handoff:**

Share this URI with coworkers — they can paste it into **Cortex Code** to
install the `<artifact_noun>`:

`<snow://skill_catalog/...>`

Paste the **exact** URI string. Do **not** tell them to browse the catalog or
run install CLI commands unless they explicitly ask.

For skills only: do not default to `cortex skill add … --catalog`.

## Unshare Success

Tell the user the `<artifact_noun>` name + FQN, count of READ grants revoked,
and any leftover grantees after partial failure (verbatim message from step 4).
If `<total> == 0`, say "`<FQN>` had no active READ grants; nothing to revoke".

## Failure

Surface Snowflake error + failing statement. No partial success claims on
failed COMMIT. For partial unshare REVOKE, use step 4 verbatim message.

### Stage file size or count limit

When step 2 stopped on a **stage limit error** per
[SKILL.md](SKILL.md) § **Stage file size and count limits**:

1. Say sharing **failed** because the `<artifact_noun>` exceeds Cortex
   Extension stage limits.
2. Include the **verbatim** server or CLI error.
3. Name the violated limit when the error fragment makes it clear (file count,
   total size, or per-file size).
4. Tell the user to **reduce files or file sizes** in their local
   `<artifact_noun>` and try again, or **contact Snowflake support** to raise
   the account limit.
5. Do **not** claim partial success or suggest retrying via a different upload
   path.

## Decision Rules

- Reflect **final** audience and DISCOVERABLE.
- Do not collapse audience and discoverability into one sentence.
