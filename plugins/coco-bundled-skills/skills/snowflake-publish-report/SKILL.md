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
allowed-tools: Bash
---

# Publish an HTML report to Snowflake Intelligence (Cowork)

When the user asks to publish or share an HTML report you authored (or that
already exists locally) — whether they call it "Snowflake Intelligence", "SI", or
"Cowork" — publish it as a report artifact by running the Cortex CLI below. Do not
hand-roll a stage upload.

## Before publishing: confirm who to share with

Sharing is grant-based (link sharing is off) and **at least one role is required** — publishing with no roles is rejected. The grant *is* the entire access decision, so who you share with matters.

- **If the user already stated who to share with** (a specific role, or explicitly "everyone"/"the whole account"), use exactly that.
- **Otherwise you must ask first and wait for their answer** — do not publish until they tell you. Ask whether to share with a specific Snowflake role or with everyone in the account.
- **Never default to `PUBLIC`.** `PUBLIC` grants READ to *everyone in the account*; use it **only** when the user explicitly asked for account-wide/everyone access. If the request is vague, ask — do not assume `PUBLIC`.

Pass each chosen role as a `--grant-role`.

## Command

    cortex artifact publish-report <file.html> --title "<Report Title>" --grant-role <ROLE> [--grant-role <ROLE> ...] [--connection <name>]

- `<file.html>` — the HTML report to publish (an `.html`/`.htm` file in the current working directory).
- `--title` — human-readable title shown in Snowflake Intelligence / Cowork.
- `--connection` — optional; omit to use the active connection.
- `--grant-role` — **required**, repeatable; the role(s) to grant READ. A report must be shared with someone (link sharing is always off). `PUBLIC` shares with **everyone in the account** — use it only when the user explicitly asked for that, never as a default (see "confirm who to share with" above).

## What it does

1. Copies the HTML into your workspace at `<workspace>/reports/<file>` — an editable copy.
2. Publishes it as a report artifact with lineage back to that copy, so the "edit" button opens it.
3. Re-running with the same file updates the same artifact (no duplicates).

## After publishing

The command prints one line containing the artifact id, the workspace path, the
granted roles, and a `Shareable link:` URL. Report it back in exactly this
format and order, one field per line:

    Shareable link: <the URL the command printed, character-for-character>
    Shared with: <the roles from "Granted READ to">
    Title: <report title>
    Artifact ID: <artifact id>
    Workspace copy: <workspace path>

Copy the link verbatim — never construct, guess, shorten, or re-case a URL. Do
not omit "Shared with"; the user needs to know who can open the report. If the
command reported a republish, say so.
