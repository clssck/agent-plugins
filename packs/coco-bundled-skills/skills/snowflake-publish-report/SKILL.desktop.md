---
name: snowflake-publish-report
description: >
  Publish a local HTML report file as a shareable Snowflake Intelligence (Cowork)
  report artifact from Cortex Code. Copies the HTML into the user's workspace (an
  editable copy) and creates the report artifact linked back to it, so the "edit"
  button opens the workspace copy. Use after authoring an HTML report, or whenever
  the user asks to publish or share one.
  Triggers: publish report, publish the html, publish this report, share report,
  publish to snowflake intelligence, publish to cowork, share to cowork, publish
  as a snowflake intelligence / cowork report.
allowed-tools: publish_report
---

# Publish an HTML report to Snowflake Intelligence (Cowork)

When the user asks to publish or share an HTML report you authored (or that
already exists in the workspace) — whether they call it "Snowflake Intelligence",
"SI", or "Cowork" — publish it as a report artifact using the `publish_report`
tool. Do not hand-roll a stage upload.

## Before publishing: confirm who to share with

Sharing is grant-based (link sharing is off) and **at least one role is required** — publishing with no roles is rejected. The grant *is* the entire access decision, so who you share with matters.

- **If the user already stated who to share with** (a specific role, or explicitly "everyone"/"the whole account"), use exactly that.
- **Otherwise you must ask first and wait for their answer** — do not publish until they tell you.
- **Never default to `PUBLIC`.** `PUBLIC` grants READ to *everyone in the account*; use it **only** when the user explicitly asked for account-wide/everyone access. If the request is vague, ask — do not assume `PUBLIC`.

Word the question the way Snowsight's own publish flow does, so the two surfaces
read the same. Snowsight's dialog uses "Who has access", "Add roles to the
artifact", "Give roles view-only access in Snowsight and CoWork", and "Artifact
view only". Ask:

> Who has access? Give roles view-only access to this report in Snowsight and CoWork.

with one option per role, phrased `<ROLE> — <who that is>`:

> - `PUBLIC — everyone in the account`
> - `SYSADMIN — only the SYSADMIN role`

Do **not** say "grant role", "the publish command", or mention a title — the user
is choosing who gets access, not reading about the implementation. Say "view-only
access", not "can view the report", to match Snowsight.

## Tool call

Invoke `publish_report` with:

- `file_path` — path to the `.html`/`.htm` file (workspace-relative, e.g. `reports/q2.html`, or absolute). Must be inside the open workspace folder.
- `title` — human-readable title shown in Snowflake Intelligence / Cowork.
- `grant_roles` — array of role names to grant READ. **Required, at least one.** Use `["PUBLIC"]` only when the user explicitly asked for account-wide access.
- `connection` — optional; omit to use the active connection.

## What it does

1. Copies the HTML into your workspace at `<workspace>/reports/<file>` — an editable copy.
2. Publishes it as a report artifact with lineage back to that copy, so the "edit" button opens it.
3. Re-running with the same file updates the same artifact (no duplicates).

## After publishing

The tool returns the artifact id, the workspace path, the granted roles, and a
shareable URL. Report it back as a markdown list, in exactly this order:

- Shareable link: <the URL from the tool result, character-for-character>
- Shared with: <the roles>
- Title: <report title>
- Artifact ID: <artifact id>
- Workspace copy: <workspace path>

Use a list, never an indented block: indenting these lines makes the chat render
them as a code block, where the URL is neither clickable nor selectable — so the
user cannot open or copy the link the feature exists to produce.

Copy the link verbatim — never construct, guess, shorten, or re-case a URL. Do
not omit "Shared with"; the user needs to know who can open the report. If the
tool reported a republish, say so.
