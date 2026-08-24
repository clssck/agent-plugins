---
name: find-skill-and-plugin
description: >-
  Find, add, check, or update Cortex Code catalog skills and plugins
  before using them. Use when the user asks to search "the catalog" (even
  without specifying skill or plugin), discover available skills or
  plugins, install a catalog skill or plugin, try to find a skill or a
  plugin that can help with a task, make an uninstalled `/skill` or
  `$skill` usable, search the skill or plugin marketplace/catalog, check
  whether installed skills or plugins have updates, or update skills and
  plugins from the catalog, stage, GitHub, or tarball sources. ALSO use
  when the user expresses intent to acquire, install, or enable a
  capability, tool, or integration that no already-installed skill covers
  — even without naming a skill, plugin, or catalog, and including
  non-Snowflake developer domains such as infrastructure, CI/CD, and
  third-party SaaS. Do not use this for public Snowflake Marketplace
  datasets or apps; use marketplace-search for third-party data/product
  listings.
---

# Find Skill and Plugin

Use this skill to discover Cortex Code skills and plugins from the catalog and
make them available locally before invoking them.

## Workflow

**Before doing anything**, read the user's request and pick exactly one path:

| What the user said | Path to follow |
|--------------------|----------------|
| Provides `snow://skill_catalog/…` URI | **Share URI Workflow** — skip search, install directly |
| Provides a bare Cortex Extension FQN (no snow URI) | **Bare FQN Workflow** — determine type first, then install with ONE command |
| Mentions "skill" (e.g. "find a skill", "install skill") | **Skill Workflow only** — do NOT run `cortex plugin find` |
| Mentions "plugin" (e.g. "find a plugin", "add plugin") | **Plugin Workflow only** — do NOT run `cortex skill find` |
| Neither "skill" nor "plugin" | **Search Both** — run both commands, let user choose |

Do not deviate from the chosen path. If the user said "skill", skip the plugin
search entirely, even if plugin results might also be relevant.

Share URIs use either form:

- `snow://skill_catalog/<DB>.<SCHEMA>.<CORTEX_EXTENSION>`
- `snow://skill_catalog/<DB>.<SCHEMA>.<CORTEX_EXTENSION>/versions/<version>`

---

### Share URI Workflow

Use this path whenever the user's message contains a `snow://skill_catalog/…`
URI. Skip search entirely and install directly, using the exact URI from the
user's message wrapped in single quotes.

- If the user said **"skill"**:
  ```bash
  cortex skill add 'snow://skill_catalog/<DB>.<SCHEMA>.<CORTEX_EXTENSION>'
  ```
- If the user said **"plugin"**:
  ```bash
  cortex plugin add 'snow://skill_catalog/<DB>.<SCHEMA>.<CORTEX_EXTENSION>'
  ```
- If **neither is stated**, try skill install first:
  ```bash
  cortex skill add 'snow://skill_catalog/<DB>.<SCHEMA>.<CORTEX_EXTENSION>'
  ```
  If it fails with an error indicating the wrong type (e.g. mentions the
  object is not a skill), or mentioning a type mismatch, retry with:
  ```bash
  cortex plugin add 'snow://skill_catalog/<DB>.<SCHEMA>.<CORTEX_EXTENSION>'
  ```
  Only fall back after a type-mismatch error — do not run both proactively,
  and do not retry on unrelated errors (e.g. auth, connection issues).

Then confirm with `cortex skill list` or `cortex plugin list`, matching
whichever command succeeded.

---

### Skill Workflow

1. Search for candidate skills:

```bash
cortex skill find "<query>"
```

Use a short query based on the capability the user needs. If the user named a
specific saved Snowflake connection, pass `--connection <name>`.

If the first query returns no results, retry with 2–3 broader or synonym
queries before giving up. For example, if `"data governance access patterns"`
fails, try `"governance"`, `"access history"`, `"audit"`. Decompose
multi-word phrases into their most distinctive single term. Only move to the
plugin fallback after exhausting reasonable query variations.

1a. **If no skills are found after trying multiple queries**, run the plugin search as a fallback:

```bash
cortex plugin find "<query>"
```

If the plugin results look relevant, present the top plugin results and ask
the user before proceeding:
> "I didn't find any skills matching that query, but I found these plugins —
> would you like to install one of them instead?"
Only continue if the user picks one. If the plugin search also returns nothing,
report that no results were found for either type.

2. **⚠️ MANDATORY STOPPING POINT** — present the top search results and ask
which one (if any) to install. Do **not** pick or install a skill yourself.

Show a short numbered list (typically the top 3–5) using each result's name and
one-line description. Do not rely on the catalog object's SQL name alone; a
Cortex Extension object name can differ from the actual `name` in `SKILL.md`.

Example:

```
I found these skills matching your request:

1. **good-morning** — Daily AE morning briefing with account health, product adoption, …
2. **daily-digest** — Summarized overnight alerts and open tasks
3. **standup-prep** — Prep notes for daily standup from recent activity

Which one would you like to install? (or say none / try a different search)
```

Wait for the user to choose. If nothing fits, offer to refine the query. Resume
only after they pick a result (or explicitly ask you to install one by name).

3. Install **only** the skill the user selected. Prefer the exact command
printed by `cortex skill find`; it preserves important options such as
`--connection`. Some catalog **skills** are delivered by a backing Cortex
Extension, in which case the install command carries the extension FQN via
`--plugin-fqn`:

```bash
cortex skill add <catalog-name> --plugin-fqn '<DB.SCHEMA.CORTEX_EXTENSION>'
```

⚠️ `--plugin-fqn` does **not** mean "install a plugin." It is only correct when
the catalog object is a **skill** (Cortex Extension `type = SKILL`). A genuine
**plugin** (`type = PLUGIN`) must be installed through the **Plugin Workflow**
with `cortex plugin add '<FQN>'` — never `cortex skill add`. A plugin FQN such
as `USER$SHSEN.SKILL_SHARING.COCO_JIRA` looks identical to a skill's backing
extension FQN, so if you reached this step from a `cortex plugin find` result,
or you are not certain the object is a skill, first confirm the type — see
[Determining artifact type from an FQN or URI](#determining-artifact-type-from-an-fqn-or-uri).

Always wrap the FQN in single quotes. FQNs can contain `$` (e.g.
`USER$ALICE.SKILL_SHARING.MY_SKILL`) which the shell interprets as a variable
without quoting.

4. Confirm the installed skill name:

```bash
cortex skill list
```

Use the installed skill's real `SKILL.md` name for future `$skill` or `/skill`
references. The install output and `cortex skill list` are authoritative.

5. If the user needs the newly installed skill used in the same turn, inspect
the installed skill's `SKILL.md` from the listed path and follow its
instructions directly. A running agent may not auto-load a skill that was
installed after the prompt was parsed, so do not assume `$skill` or `/skill`
will resolve until a later turn.

If the user is testing from a source checkout and provides a CLI prefix such as
`bun run dev --`, use that prefix consistently in place of `cortex`.

---

### Plugin Workflow

1. Search for candidate plugins:

```bash
cortex plugin find "<query>"
```

1a. **If no plugins are found**, run the skill search as a fallback:

```bash
cortex skill find "<query>"
```

If the skill results look relevant, present the top skill results and ask
the user before proceeding:
> "I didn't find any plugins matching that query, but I found these skills —
> would you like to install one of them instead?"
Only continue if the user picks one. If the skill search also returns nothing,
report that no results were found for either type.

2. **⚠️ MANDATORY STOPPING POINT** — present the top search results and ask
which one (if any) to install. Do **not** pick or install a plugin yourself.

Show a short numbered list (typically the top 3–5) using each result's name,
one-line description, and FQN (e.g. `MISSION_CONTROL.APPS.AGENT_MODE`).

Example:

```
I found these plugins matching your request:

1. **agent-mode** (`MISSION_CONTROL.APPS.AGENT_MODE`) — Enables agent mode workflows
2. **release-ops** (`…RELEASE_OPS`) — Release automation helpers

Which one would you like to install? (or say none / try a different search)
```

Wait for the user to choose. If nothing fits, offer to refine the query. Resume
only after they pick a result (or explicitly ask you to install one by name/FQN).

3. Install **only** the plugin the user selected, by FQN wrapped in single quotes:

```bash
cortex plugin add 'MISSION_CONTROL.APPS.AGENT_MODE'
```

Always wrap the FQN in single quotes. FQNs can contain `$` (e.g.
`USER$ALICE.SKILL_SHARING.NOVA`) which the shell interprets as a variable
without quoting.

4. Confirm the installed plugin:

```bash
cortex plugin list
```

5. Check a specific plugin by name:

```bash
cortex plugin check agent-mode
```

---

### Bare FQN Workflow

Use this path when the user provides a bare Cortex Extension FQN
(e.g. `USER$ALICE.SKILL_SHARING.COST_ADVISOR`) without a `snow://skill_catalog/…`
URI. If they pasted a share URI instead, use the **Share URI Workflow** above.
The FQN shape is identical for skills and plugins — do not guess.

1. **Determine the type** by describing the extension:

```bash
cortex sql -q "DESCRIBE CORTEX EXTENSION <DB>.<SCHEMA>.<NAME>"
```

Read the `type` column in the output.

If `DESCRIBE` is unavailable or fails, fall back to searching both catalogs and
matching the FQN against the results:

```bash
cortex skill find "<name>"
cortex plugin find "<name>"
```

Whichever search returns a result whose FQN matches → that is the type.

If `DESCRIBE` fails **and** neither catalog search returns a result matching the
FQN, the object cannot be found. **Stop and tell the user** the artifact was not
found — do not attempt to install it. Never try both install commands as a
fallback when the type cannot be determined.

2. **Install using exactly one command** based on the resolved type:

- `type = SKILL` → install via catalog name and backing extension FQN:
  ```bash
  cortex skill add <catalog-name> --plugin-fqn '<DB.SCHEMA.NAME>'
  ```

- `type = PLUGIN` → install by FQN:
  ```bash
  cortex plugin add '<DB.SCHEMA.NAME>'
  ```

⚠️ **Never run both `cortex skill add` and `cortex plugin add` on the same
FQN.** Once you have determined the type, commit to exactly one install command
and stop. Trying both is incorrect regardless of which one succeeds.

---

### Search Both (default)

Only use this path when the user's request mentions neither "skill" nor "plugin"
and did not provide a share URI or bare FQN.

Run both searches, then **⚠️ MANDATORY STOPPING POINT** — present results
clearly labelled by type and ask which one (if any) to install. Do not install
until the user chooses:

```bash
cortex skill find "<query>"
cortex plugin find "<query>"
```

Show top skills and top plugins in separate numbered lists (name + one-line
description). After the user picks one, follow the appropriate Skill Workflow
or Plugin Workflow install step above.

---

## Determining artifact type from an FQN or URI

When the user hands you a `snow://skill_catalog/…` URI, follow the
**Share URI Workflow** — install directly (by stated type, or try skill then
plugin on a type-mismatch error). Do not search the catalog and do not run
`DESCRIBE` for a share URI.

When the user hands you a bare Cortex Extension FQN (no share URI, and no
"skill"/"plugin" stated), follow the **Bare FQN Workflow**, which uses
`DESCRIBE CORTEX EXTENSION` to resolve the type before installing. The FQN
shape is identical for skills and plugins, so you cannot tell from the name
alone — an object in `SKILL_SHARING` is not necessarily a skill.

Describe the extension over the connection and read the `type` column:

```bash
cortex sql -q "DESCRIBE CORTEX EXTENSION <DB>.<SCHEMA>.<NAME>"
```

(Or run the SQL through whatever connection the user is using; pass
`--connection <name>` if they named a saved connection.)

- `type = SKILL` → use the **Skill Workflow**
  (`cortex skill add … [--plugin-fqn '<FQN>']`).
- `type = PLUGIN` → use the **Plugin Workflow**
  (`cortex plugin add '<FQN>'`).

If `DESCRIBE` is unavailable on a bare FQN, try installing it as a skill first
using the **Skill Workflow**. 
If it fails with an error indicating the wrong type (e.g. mentions the object 
is not a skill), or mentioning a type mismatch, retry with the **Plugin Workflow**

---

## Updates

### Skills

Check installed remote, stage, tarball, and catalog skills:

```bash
cortex skill check
```

Check one source or skill:

```bash
cortex skill check <skill-or-source>
```

Update an installed skill with the command shown by `check`, or use the
appropriate source form:

```bash
cortex skill update <skill-or-source>
cortex skill update <skill-name> --plugin-fqn <DB.SCHEMA.CORTEX_EXTENSION>
```

### Plugins

Check a specific installed plugin:

```bash
cortex plugin check <plugin-name>
```

## Snowsight Sandbox

In a Snowsight sandbox session, export both env vars once per session
before running any `cortex skill` command, so installed skills and
`skills.json` persist in the workspace volume instead of the ephemeral
home directory:

```bash
export CORTEX_HOME=/workspace/.snowflake
export SKILL_DIR=/workspace/.snowflake/cortex/skills
```

### Troubleshooting

If `cortex skill add` reports success but the new skill is missing from
`cortex skill list` or absent from `skills.json`, the env vars are set in
only one of the two processes (the CoCo UI vs. the spawned subprocess).
Confirm both are exported in both environments, then re-run.

## Guardrails

- Do not tell the user to use an uninstalled catalog skill with `$skill` or
  `/skill`; install it first.
- After `cortex skill find` or `cortex plugin find`, always show the top results
  and wait for the user to choose before running `cortex skill add` or
  `cortex plugin add`. Never auto-install the "best match" from search results.
  (Share URI and bare-FQN workflows still install the artifact the user named.)
- Do not assume the catalog SQL object name equals the installed skill name.
- Do not edit `SKILL.md` metadata to force a name match during install; preserve
  the publisher's bundle and use the actual installed skill name.
- Do not use this skill for public Snowflake Marketplace datasets, Native Apps,
  or connectors; use `marketplace-search`.
- When the user explicitly says "skill", use only `cortex skill find` / `cortex skill add`; do not search plugins.
- When the user explicitly says "plugin", use only `cortex plugin find` / `cortex plugin add`; do not search skills.
- When neither is specified, always run both `cortex skill find` and `cortex plugin find` and present combined results before installing.
- Never install a plugin with `cortex skill add`. A result from `cortex plugin find`, or any Cortex Extension with `type = PLUGIN`, is installed with `cortex plugin add '<FQN>'`. The `--plugin-fqn` flag on `cortex skill add` is only for skills backed by an extension (`type = SKILL`), not for plugins.
- When the user provides a `snow://skill_catalog/...` URI, do not run `cortex skill find` or `cortex plugin find`; install directly per the stated type, or try `cortex skill add '<URI>'` first and fall back to `cortex plugin add '<URI>'` only on a type-mismatch error (see [Share URI Workflow](#share-uri-workflow)).
- When given a bare FQN whose type is unknown, determine the type first via `DESCRIBE CORTEX EXTENSION` (see [Determining artifact type from an FQN or URI](#determining-artifact-type-from-an-fqn-or-uri)) instead of assuming skill or trying both install commands.
- For a bare FQN, never run both `cortex skill add` and `cortex plugin add`. Resolve the type via `DESCRIBE` first, then use exactly one command. (For a share URI, trying skill then plugin after a type-mismatch error is expected — see Share URI Workflow.)
