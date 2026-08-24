---
name: find-skill-and-plugin
description: >-
  Find, add, check, or update Cortex Code catalog skills and plugins in CoCo
  Desktop before using them. Use when the user asks to search "the catalog"
  (even without specifying skill or plugin), discover available skills or
  plugins, look up a skill or plugin by name, keyword, or FQN, install a
  catalog skill or plugin, paste a
  `snow://skill_catalog/...` or `snow://cortex_extension/...` URI to install,
  paste a bare Cortex Extension FQN (`<DB>.<SCHEMA>.<NAME>`), make an
  uninstalled `/skill` or `$skill` usable, or browse the skill or plugin
  marketplace/catalog. Discovery happens in-app: it runs
  `SHOW TERSE CORTEX EXTENSIONS IN ACCOUNT` and filters the results by the user's
  keyword or FQN, then always drives toward installation — confirming
  the match (or asking which one, when several match) via ask_user_question and
  emitting a `coco://install_catalog_uri` deep link the user clicks to install
  natively. Do not use this for public Snowflake Marketplace datasets or apps;
  use marketplace-search for third-party data/product listings.
---

# Find Skill and Plugin (Desktop)

Use this skill to discover Cortex Code skills and plugins from the catalog and
install them locally through CoCo Desktop. Discovery happens **in-app**: you run
`SHOW TERSE CORTEX EXTENSIONS IN ACCOUNT` and filter the rows by the user's keyword or
FQN.
Once you've identified the extension (confirming the single match, or asking the
user which one when several match, via `ask_user_question`), you construct its
`snow://skill_catalog/<DB>.<SCHEMA>.<NAME>` URI and install by emitting a
`coco://install_catalog_uri?uri=...` **deep link** — when the user clicks it
in-app, CoCo Desktop's native handler runs a `DESCRIBE` and installs directly
(no confirmation dialog for in-app clicks) using the same backend as the Agent
Settings catalog import. A confirmation prompt only appears when the link is
opened from outside the app.

## Workflow

**Before doing anything**, read the user's request and pick exactly one path:

| What the user said | Path to follow |
|--------------------|----------------|
| Provides / pastes a `snow://skill_catalog/...` or `snow://cortex_extension/...` URI | **Paste URI Workflow** — validate, then emit the install deep link |
| Provides a bare Cortex Extension FQN (`<DB>.<SCHEMA>.<NAME>`, no `snow://` prefix) | **Search Workflow** — search the catalog for that FQN, then confirm and install |
| Wants to find / discover / browse a skill or plugin, or look one up by name, keyword, or FQN (no `snow://` URI in hand) | **Search Workflow** — search the catalog in-app, then confirm and install |

Only an explicit `snow://...` URI goes straight to install. A bare FQN or any
keyword goes through the Search Workflow first, which ends by installing the
chosen extension.

Share URIs use any of these forms. A trailing slash is optional. The version
suffix controls which version installs: **if omitted** the base URI resolves to
the latest certified version automatically (or the default version when none is
certified); **include `/versions/version$N`** and that exact version installs:

- `snow://skill_catalog/<DB>.<SCHEMA>.<NAME>` (version-less → certified/default)
- `snow://skill_catalog/<DB>.<SCHEMA>.<NAME>/` (trailing slash — this is the
  normalized form the share flow hands coworkers, so expect it often)
- `snow://skill_catalog/<DB>.<SCHEMA>.<NAME>/versions/version$N` (pins that exact
  version; a path *beyond* the `version$N` segment is not treated as a pin — it
  re-resolves to certified/default)
- `snow://cortex_extension/<DB>.<SCHEMA>.<NAME>` (the `cortex_extension` scheme,
  version-less → certified/default; a trailing slash is also fine)
- `snow://cortex_extension/<DB>.<SCHEMA>.<NAME>/versions/live/...` (the
  `cortex_extension` form the sharer's stage uses; the FQN is still the first
  path segment)

In every form the extension **FQN** is the first path segment after the scheme
prefix: split it on `.` into `<DB>`, `<SCHEMA>`, `<NAME>`.

**Bare FQN (no `snow://` prefix).** If the user hands you just a Cortex Extension
FQN — e.g. `USER$ALICE.SKILL_SHARING.MY_SKILL` — do not treat it as an install
URI. Route it to the **Search Workflow** and use its `<DB>`, `<SCHEMA>`, `<NAME>`
parts to filter the `SHOW TERSE CORTEX EXTENSIONS IN ACCOUNT` results (see below). A
well-formed FQN splits into exactly three non-empty identifiers
(`<DB>.<SCHEMA>.<NAME>`) and should match exactly one row; the Search Workflow
then confirms and installs it. Searching (rather than blindly normalizing to a
URI) verifies the extension actually exists and is readable before you offer to
install it. If the input does *not* split into exactly three non-empty
identifiers, treat it as a free-text keyword and run the Search Workflow on it as
a keyword instead.

---

## Paste URI Workflow (install)

Use this whenever the user's message contains a `snow://skill_catalog/...` (or
`snow://cortex_extension/...`) URI, **or** when the Search Workflow has
identified an extension and constructed its
`snow://skill_catalog/<DB>.<SCHEMA>.<NAME>` URI for you. This is the install
step. Skip search entirely when the user pasted a full `snow://` URI.

1. **Validate and parse the URI locally.** It must start with
   `snow://skill_catalog/` or `snow://cortex_extension/` and match one of the
   accepted forms above. Reject anything containing `%`, `;`, backticks, or `..`
   path segments — do not "fix" a malformed URI; ask the user to re-paste it. A
   single trailing slash and any `/versions/...` (for the `cortex_extension`
   form, `/versions/live/...`) tail are allowed, not errors.

   **Parse the FQN** from the first path segment after the scheme prefix: read
   from the end of `skill_catalog/` (or `cortex_extension/`) up to the next `/`,
   `?`, or end of string, then split that segment on `.` into exactly three
   parts — `<DB>`, `<SCHEMA>`, `<NAME>`. Ignore everything after that first
   segment (trailing slash, `versions/...`, etc.). If it does not split into
   exactly three non-empty identifiers, treat the URI as malformed and ask the
   user to re-paste. Use these three parts only for the advisory `DESCRIBE`
   below; the deep link in step 3 carries the **exact URI you were given** — the
   one the user pasted, or the one the Search Workflow constructed (either scheme
   prefix is valid) — not the reparsed FQN.

   When you arrived here from the Search Workflow, the URI you constructed is
   already validated and you know the type from `SHOW`, so you may skip the
   advisory `DESCRIBE` in step 2 and go straight to emitting the deep link.

2. **Preflight `DESCRIBE` (advisory)** — confirm the extension exists, is
   readable by the active role, and learn its type so you can tell the user what
   they're installing. Run through `snowflake_sql_execute` on the active
   connection:

   ```sql
   DESCRIBE CORTEX EXTENSION "<DB>"."<SCHEMA>"."<NAME>";
   ```

   Read the `type` column, comparing **case-insensitively** — `DESCRIBE` returns
   lowercase values: `plugin` → plugin; `skill` or empty → skill. If
   `DESCRIBE` fails:
   - **Does not exist or not authorized** — Snowflake returns a single combined
     message for both causes (e.g. `Cortex Extension '<DB>.<SCHEMA>.<NAME>' does
     not exist or not authorized.`, or `Database '<DB>' does not exist or not
     authorized.`), so you cannot tell them apart from the error text. Either the
     URI is wrong / the extension was dropped, **or** the active role lacks
     `READ` on it. Show the error and ask the user to double-check the URI and
     confirm the correct role is active in the desktop and that the publisher has
     granted access; do not emit a link until it resolves.
   - **Cortex Extensions feature not enabled** — a parse-level or
     unsupported-feature error (e.g. `syntax error` near `CORTEX`/`EXTENSION`,
     `unsupported feature` referencing `CORTEX EXTENSION`, or `object type
     'cortex extension' is not supported`). This means catalog skills/plugins are
     not enabled on this account. Tell the user the catalog feature is not
     enabled here and to contact Snowflake support; do not emit a link.
   - Any other failure — report it and stop.

   This preflight is advisory only. The deep-link handler runs its own
   authoritative `DESCRIBE` when the user clicks, so never rely on the type you
   read here to be trusted downstream.

3. **Emit the install deep link — make it stand out.** Percent-encode the exact
   `snow://` URI (`encodeURIComponent`) — this turns `:` into `%3A`, `/` into
   `%2F`, and `$` into `%24` (so a `USER$ALICE` database becomes `USER%24ALICE`),
   while `.`, `_`, and `-` pass through unchanged. Run the **whole** URI through
   `encodeURIComponent`; do not hand-encode only `:` and `/` and leave a raw `$`
   — the `USER$<name>` databases that most shared skills live under all contain
   one. Then present the link as the visual centerpiece of your reply, not a
   throwaway sentence. Use this exact layout:

   - A short lead-in naming the artifact and what it does (one line).
   - The call to action on its **own line** as an `H2` heading link that leads
     with a 📖 book emoji and a bold, imperative label, so it reads as a big
     clickable button without looking like spam:

   ```
   ## 📖 [**Install <name> now**](coco://install_catalog_uri?uri=<ENCODED_SNOW_URI>)
   ```

   - A one-line italic caption underneath explaining what clicking does.

   For `snow://skill_catalog/DB.SCHEMA.MY_SKILL`, the whole block looks like:

   ```
   **MY_SKILL** — <one-line summary of what the skill does>.

   ## 📖 [**Install MY_SKILL now**](coco://install_catalog_uri?uri=snow%3A%2F%2Fskill_catalog%2FDB.SCHEMA.MY_SKILL)

   *Clicking installs it directly through CoCo Desktop's catalog importer (no SQL); if you open the link from outside the app you'll get a confirmation prompt first.*
   ```

   A `USER$`-scoped FQN must have its `$` encoded the same way. For
   `snow://skill_catalog/USER$ALICE.SKILL_SHARING.MY_SKILL` — where `USER$ALICE`
   becomes `USER%24ALICE` — the block is:

   ```
   **MY_SKILL** — <one-line summary of what the skill does>.

   ## 📖 [**Install MY_SKILL now**](coco://install_catalog_uri?uri=snow%3A%2F%2Fskill_catalog%2FUSER%24ALICE.SKILL_SHARING.MY_SKILL)

   *Clicking installs it directly through CoCo Desktop's catalog importer (no SQL); if you open the link from outside the app you'll get a confirmation prompt first.*
   ```

   Keep the heading link on its own line (blank line above and below) so it
   renders as a large, prominent button. Do not paste raw SQL install commands;
   the deep link is the install mechanism on Desktop.

4. **Confirm** — after they click, the skill appears under the
   **Skills** tab (or as a **CATALOG** plugin card) in Agent Settings. Use the
   installed name for future `$skill` / `/skill` references. A running agent may
   not auto-load a skill installed mid-turn, so do not assume `$skill` or
   `/skill` will resolve until a later turn.

For full documentation, see
[Import a skill from the catalog](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-desktop/skills#import-a-skill-from-the-catalog).

---

## Search Workflow (in-app)

Use this when the user wants to **find, discover, or browse** a skill or plugin
— including looking one up **by name, keyword, or FQN** (e.g. "find the
`data-quality` skill", "any plugins for dbt?", "search for cost skills",
`USER$ALICE.SKILL_SHARING.MY_SKILL`) — and does not already have a full
`snow://skill_catalog/...` URI. Discovery is done **in-app with SQL**: enumerate the
catalog with `SHOW TERSE CORTEX EXTENSIONS IN ACCOUNT`, filter the rows client-side by
the user's query, then drive the user to install the match. Do **not** use the
`snowflake_object_search` tool for this — it cannot return Cortex Extensions
(it only indexes tables, views, databases, schemas, functions, semantic views,
agents, streamlit apps, streams, stages, tasks, and pipes), so it will never
find a skill or plugin.

1. **Enumerate the catalog.** Run this through `snowflake_sql_execute` on the
   active connection:

   ```sql
   SHOW TERSE CORTEX EXTENSIONS IN ACCOUNT;
   ```

   The result is RBAC-filtered server-side (you only see extensions the active
   role can read). Each `TERSE` row has these columns: `name`, `database_name`,
   `schema_name`, `created_on`, `updated_on`, `comment`, `security_scan_status`,
   `created_by`, `type` (`skill` or `plugin`), `discoverable`,
   `latest_certified_version`. (`TERSE` still returns `comment`, `created_by`,
   and `type`, which the keyword/type filter below needs; it just omits the
   `owner` and `certification_status` columns that full `SHOW` includes.)

   If the statement fails:
   - **Cortex Extensions feature not enabled** — a parse-level /
     unsupported-feature error (`syntax error` near `CORTEX`/`EXTENSION`,
     `unsupported feature` referencing `CORTEX EXTENSION`, or `object type
     'cortex extension' is not supported`). Tell the user the catalog feature is
     not enabled on this account and to contact Snowflake support; stop.
   - **Insufficient privileges / any other failure** — report the error and, as
     a fallback, offer the browser catalog page (see
     [Browser fallback](#browser-fallback) below). Do not fabricate results.

2. **Filter the rows client-side to match the user's query** — mirror the CLI's
   substring behavior:

   - **Keyword query** (name, topic, or free text): keep rows where the query,
     compared **case-insensitively**, is a substring of the `name`, `comment`
     (description), or `created_by` (author) column. Split a multi-word query on
     whitespace and prefer rows matching all words, but fall back to
     any-word matches if nothing matches all.
   - **FQN query** (`<DB>.<SCHEMA>.<NAME>`): match rows where `database_name`,
     `schema_name`, and `name` equal the three parts (case-insensitive). This
     should normally yield exactly one row.
   - **Type filter**: if the user explicitly asked for a *skill* or a *plugin*,
     additionally keep only rows whose `type` matches. (`SHOW TERSE` always
     populates `type` as `skill` or `plugin`, so no empty-type fallback is
     needed here — that empty-`type` mapping applies only to the `DESCRIBE`
     path.) If the user did not specify, include both types.

   Rank the surviving rows so the strongest matches come first: exact `name`
   match, then name-substring match, then description/author match.

3. **Resolve to a single extension to install** using `ask_user_question` — the
   Search Workflow always ends in an install decision:

   - **No matches after filtering** — tell the user nothing in the catalog
     matched their query, suggest a broader keyword, and optionally offer the
     [Browser fallback](#browser-fallback). Stop; do not emit an install link.
   - **`SHOW` returned zero rows at all** (the unfiltered catalog came back
     empty, before you applied any keyword/FQN filter) — this usually means the
     **active role has no visibility** into any Cortex Extensions (the result
     is RBAC-filtered server-side), not that the catalog is truly empty. Tell
     the user the empty result likely reflects their current role's
     permissions, and ask them to confirm the correct role is active in the
     desktop (and that a publisher has granted them access) before retrying. A
     broader keyword will not help here. Optionally offer the
     [Browser fallback](#browser-fallback).
   - **Exactly one match** — do not silently install. Present the match
     (`name`, `type`, FQN, and a one-line summary from `comment`) and use
     `ask_user_question` to confirm the user wants to install it (e.g. options
     "Install it" / "No, don't install"). Only proceed on confirmation. **If the
     user declines**, do not install; ask whether they want to refine the
     search (re-run `SHOW TERSE` with a different keyword) or stop, and follow
     their choice.
   - **Multiple matches** — use `ask_user_question` to ask **which one** to
     install. Provide one option per match, each labeled with the extension
     `name` and its `type`, with the FQN and a short `comment` snippet in the
     option description (cap at the top ~5–6 ranked matches; if more remain,
     say so and invite a narrower keyword). Include a way to decline (e.g. a
     "None of these" choice). Only proceed once the user picks one. **If the
     user declines / picks "None of these"**, do not install; ask whether they
     want to refine the search (re-run `SHOW TERSE` with a different keyword) or
     stop, and follow their choice.

   Never surface the `security_scan_status` column to the user (see Guardrails);
   use it for nothing here.

4. **Construct the install URI from the chosen row.** Build the version-less
   share URI from that row's FQN:

   ```
   snow://skill_catalog/<database_name>.<schema_name>.<name>
   ```

   The version-less form resolves to the certified/default version on the
   handler side — the same default the CLI uses.

5. **Install** by handing that URI to the
   [Paste URI Workflow](#paste-uri-workflow-install): run its advisory
   `DESCRIBE` preflight (optional, since `SHOW` already told you the type) and
   emit the `coco://install_catalog_uri` deep link. That deep link is the
   install mechanism — the Search Workflow's job is only to identify the right
   extension and construct its URI.

### Browser fallback

Only when `SHOW TERSE CORTEX EXTENSIONS IN ACCOUNT` fails (feature disabled or
insufficient privileges) and you cannot enumerate the catalog, fall back to
pointing the user at the Snowsight catalog page so they can find the extension
and copy its `snow://skill_catalog/...` link to paste back:

1. Resolve the host/org/account:

   ```sql
   SELECT CURRENT_ORGANIZATION_NAME() AS ORG,
          CURRENT_ACCOUNT_NAME()      AS ACCOUNT,
          SYSTEM$NA_SECURITY_URL('')  AS HOST_URL;
   ```

2. Build `{host}/{org}/{account}/#/skills`, where `{host}` is the origin
   (`<scheme>://<host>`, no path) of `HOST_URL` (fall back to
   `https://app.snowflake.com` if empty/unparseable) and `{org}`/`{account}` are
   URL-encoded. Example: `https://app.snowflake.com/MYORG/MYACCT/#/skills`.

3. Present it as a prominent CTA, then install whatever `snow://` URI they paste
   via the [Paste URI Workflow](#paste-uri-workflow-install):

   ```
   Catalog search isn't available on this connection — here's your account's catalog page:

   ## 🌐 [**Browse Shared Skills & Plugins on Snowsight**](https://app.snowflake.com/MYORG/MYACCT/#/skills)

   *Find the skill or plugin you want, copy its `snow://skill_catalog/...` link, and paste it back here to install.*
   ```

   Both skills and plugins live on the same `#/skills` page, so one link serves
   either type. If the host/org/account SQL also fails, just point the user to
   `https://app.snowflake.com` and tell them to open **Skills & Plugins**.

For full documentation, see
[Import a skill from the catalog](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-desktop/skills#import-a-skill-from-the-catalog)
and
[Import a plugin from the catalog](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-desktop/plugins#import-a-plugin-from-the-catalog).

---

## Determining artifact type from a URI

You do **not** need to determine the type before installing — the
`coco://install_catalog_uri` handler runs its own authoritative `DESCRIBE` on
click and routes to the skill or plugin installer accordingly. A single deep
link works for either type.

Run `DESCRIBE` yourself only as an optional preflight, to confirm the extension
exists / is readable and to tell the user what they're installing:

```sql
DESCRIBE CORTEX EXTENSION "DB"."SCHEMA"."NAME";
```

Read the `type` column, comparing **case-insensitively** — `DESCRIBE` returns
lowercase values: `plugin` → plugin; `skill` or empty → skill. Treat this
value as advisory only; never pass it into the deep link (the link carries just
the `uri`, and the handler re-verifies the type).

If `DESCRIBE` fails:
- **Does not exist or not authorized** — Snowflake returns one combined message
  for both causes (e.g. `Cortex Extension '<DB>.<SCHEMA>.<NAME>' does not exist
  or not authorized.`, or `Database '<DB>' does not exist or not authorized.`),
  so you cannot distinguish them from the error text. Either the URI is wrong /
  the extension was dropped, **or** the active role lacks `READ` on it. Show the
  error, ask the user to double-check the URI and confirm the correct role is
  active and that the publisher has granted access; do not emit a link until it
  resolves.
- **Cortex Extensions feature not enabled** — a parse-level / unsupported-feature
  error (`syntax error` near `CORTEX`/`EXTENSION`, `unsupported feature`
  referencing `CORTEX EXTENSION`, or `object type 'cortex extension' is not
  supported`) means the catalog feature is off on this account. Tell the user and
  point them to Snowflake support; do not emit a link.
- Any other failure — report it and stop; do not emit a link.

---

## Guardrails

- Do not run `cortex skill find`, `cortex plugin find`, `cortex skill add`, or
  `cortex plugin add` CLI commands — these use the CLI connection, not the
  desktop's active connection. On Desktop, discovery runs in-app via
  `SHOW TERSE CORTEX EXTENSIONS IN ACCOUNT` on the active connection, and install goes
  through the `coco://install_catalog_uri` deep link (also the active
  connection).
- Do **not** use the `snowflake_object_search` tool to find skills or plugins —
  it cannot return Cortex Extensions (its corpus covers only tables, views,
  databases, schemas, functions, semantic views, agents, streamlit apps,
  streams, stages, tasks, and pipes). Search the catalog with
  `SHOW TERSE CORTEX EXTENSIONS IN ACCOUNT` and filter the rows client-side instead.
- The Search Workflow must always end in an install decision: once a match is
  identified, use `ask_user_question` to confirm the single match (or ask which
  one when several match) and then emit the install deep link. Do not just list
  results and stop.
- The deep link is the install mechanism on Desktop: emit
  `coco://install_catalog_uri?uri=<percent-encoded snow:// URI>` and let the user
  click it. Do not paste raw install SQL or write directly to
  `~/.snowflake/cortex/skills.json`, the plugin registry, or the stage cache —
  the native handler resolves the version, downloads, and registers the entry.
- Construct the install URI from a searched row as the version-less
  `snow://skill_catalog/<database_name>.<schema_name>.<name>` (certified/default
  version), matching the CLI default. Always percent-encode the `snow://` URI in
  the deep link (`encodeURIComponent`) so characters like `/`, `:`, and `$`
  survive (e.g. `:`→`%3A`, `/`→`%2F`, `$`→`%24`).
- Never trust a preflight `DESCRIBE` type as the install decision; the handler
  re-checks type on click. Do not put a `type` parameter in the deep link.
- Always recommend the user visit the relevant documentation link when guiding
  them through the install — include it in your response, not just on failure.
- Do not tell the user to use an uninstalled catalog skill with `$skill` or
  `/skill`; install it first.
- Do not assume the catalog SQL object name equals the installed skill name; use
  the actual installed name shown under Agent Settings.
- Do not use this skill for public Snowflake Marketplace datasets, Native Apps,
  or connectors; use `marketplace-search`.
- `SHOW TERSE CORTEX EXTENSIONS IN ACCOUNT` lists both skills and plugins in one result
  (distinguished by the `type` column), and the Snowsight `#/skills` browser
  fallback page shows both too, so you do not need separate flows per type.
- Do not surface or report a Cortex Extension's security or certification status
  (e.g. the `security_scan_status` column returned by
  `SHOW TERSE CORTEX EXTENSIONS`, or `security_scan_status` /
  `certification_status` from `DESCRIBE CORTEX EXTENSION`). These are not a
  signal you should relay to the user.
