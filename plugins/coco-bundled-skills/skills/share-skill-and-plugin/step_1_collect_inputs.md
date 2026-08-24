# Step 1: Collect Inputs and Detect Intent

Resolve what the user wants: **first-time share**, **re-sharing an already
shared artifact**, or **unshare**; determine `<artifact_type>` ∈ {`skill`,
`plugin`}; capture the right target (local folder vs extension **FQN**); then
(for re-share only) decide content-only vs update share options.

Runtime modes are defined in [SKILL.md](SKILL.md) § Runtime modes. Any step
below that touches disk uses **two paths**: **Sandbox or CLI (client-local)**
vs **Non-sandbox (SQL-only)**.

## CoCo CLI vs what the user copies

- **Tell the user** (when you need a target for re-share / unshare): in
  Snowflake, open **Skill details** or **Plugin details** (under **Skills and
  plugins**) and copy the **catalog URI** — it starts with
  `snow://skill_catalog/`. That is what they should use in the UI.
- **What you usually see in chat**: Cortex Code (**CoCo CLI**) often **intercepts**
  a pasted `snow://skill_catalog/...` URI and turns it into an **install**
  flow, so the **agent** may only see the extension **FQN** — three
  dot-separated Snowflake identifiers, e.g.
  `USER$ALICE.SKILL_SHARING_55A73C8F.MY_SKILL` — **not** the `snow://` string.
  Treat that FQN as **valid input**: parse `<DB>`, `<SCHEMA>`, `<EXTENSION_NAME>`
  and **do not** ask the user to re-type the URI if the FQN is already in the
  thread.

## Detect `<artifact_type>` (do this early)

Before asking for a target or repeating what the user already gave you, set
`<artifact_type>` and `<artifact_noun>` ("skill" or "plugin" for user-facing
copy). **Detection order:**

1. **Explicit words** — user says "skill" or "plugin" (or "skills" / "plugins")
   in the current message → set `<artifact_type>` accordingly.
2. **`SKILL.md` at directory root** — if the user supplied or you can read a
   path whose root contains `SKILL.md` → `skill`.
3. **Dot-prefixed manifest directory** — if the user supplied or you can read
   a path with an immediate child directory whose name starts with `.` and
   contains `plugin.json` → `plugin`. Prefer `.cortex-plugin`, then
   `.claude-plugin`, when multiple match.
4. **Re-share / unshare via FQN or catalog URI** — after parsing the FQN, run
   `DESCRIBE CORTEX EXTENSION` (see § SQL). The `type` column is
   authoritative: `skill` → `<artifact_type> = skill`; `plugin` →
   `<artifact_type> = plugin`.
5. **Ambiguous** — both markers present in the same directory (root `SKILL.md`
   **and** a dot-prefixed dir with `plugin.json`), or neither marker and no
   explicit word → ⚠️ **MANDATORY STOPPING POINT** — call
   `ask_user_question` per
   [share_interactive_prompts.md](../references/share_interactive_prompts.md)
   § **Artifact type** (one picker: skill vs plugin). Set `<artifact_type>`
   from the pick.

Carry `<artifact_type>` forward to every later step. Do **not** re-detect after
it is set unless the user explicitly switches artifact in the same run.

## Detect inputs from the conversation (do this first)

Before asking for a target or repeating what the user already gave you, scan
the **current user message and the visible thread** (same turn / recent
context):

1. **Extension FQN (primary in CoCo chat)** — look for a token matching **three**
   dot-separated segments, each a plausible Snowflake identifier (letters,
   digits, `_`, `$`), e.g. `USER$KAZHANG.SKILL_SHARING_55A73C8F.ACCOUNT_INFO_LOOKUP`.
   - Strip optional surrounding backticks or quotes.
   - Split on `.` into `<DB>`, `<SCHEMA>`, `<EXTENSION_NAME>`.
   - If several candidates appear, prefer the one tied to update/unshare intent;
     if still ambiguous, ask which FQN — **do not** ask for a URI again when a
     single clear FQN is already present.

2. **Full skill catalog URI** — if the raw text still contains
   `snow://skill_catalog/` (case-sensitive), parse it too:
   - Take the first well-formed URI (from `snow://` through the next
     whitespace, newline, closing `)`, `]`, `>`, or end of message).
   - Store the **verbatim** string as `<existing_catalog_uri_verbatim>` when you
     have it (including any `/versions/version$N/...` suffix).
   - Derive the same three-part FQN from the first path segment after
     `snow://skill_catalog/` (stop at `/`, `?`, or end), split on `.`.

3. **If both URI and FQN appear** — they must refer to the same extension; if
   they disagree, ask which is correct. If they agree, keep the verbatim URI when
   present and still carry the parsed FQN for SQL.

4. **Intent hints** — phrases such as “update my skill/plugin”, “re-share”,
   “refresh”, “new version”, or “change who can see it” together with **either**
   a catalog URI **or** an extension FQN imply **Updating an already shared
   artifact** (§1 option 2). “Unshare”, “stop sharing”, “revoke access” + FQN/URI
   imply **Unshare** (§1 option 3). If the user only supplied FQN/URI and said
   “update” / “change” without choosing (1)(2)(3), default to **(2)** and proceed —
   **do not** demand they repeat the target.

   **Ambiguous share intent** — if the message says “share this”, “publish”,
   “make this available”, or similar generic phrases **without** an explicit
   “first-time” or “re-share” qualifier, **do not ask** — auto-detect via
   `DESCRIBE` probe (see §1 in **What to Ask** below).

Only **after** this pass should you ask for anything still missing.

## What to Ask

For each subsection below, **skip** questions whose answers you already inferred
from the user’s message or thread (see **Detect inputs from the conversation**
and **Detect `<artifact_type>`**). If anything is still missing or ambiguous,
ask in order:

### 1. Intent

**If intent is explicit** from the user's message, map it directly — do not
ask or probe:

- "first-time share", "new share", "share for the first time" → `share-first-time`
- "re-share", "reshare", "update my skill/plugin", "refresh", "new version",
  "change who can see it" → `share-resync` or `share-resync-and-update-share-options`
  (resolved in §3 after `DESCRIBE`)
- "unshare", "stop sharing", "revoke access" → `unshare`

**If intent is ambiguous** (e.g. "share this", "publish this", "make this
available" — no first-time / re-share qualifier), **do not ask the user**.
Auto-detect by probing for the extension's existence:

1. Read the manifest (see §2 and § **Parse Metadata**). Extract `name`; derive
   `<EXTENSION_NAME>` (uppercase, `-` and whitespace → `_`). Resolve
   `<personal_db>` via `SELECT CURRENT_USER()` if not yet known.
2. Find candidate schemas — run **once**:
   ```sql
   SHOW SCHEMAS LIKE 'SKILL_SHARING%' IN DATABASE "<personal_db>";
   ```
   **Carry `<schema_discovery_result>` forward** to step 2's §2A.Discover so
   step 2 does **not** re-run this query.
3. For each candidate schema in ladder order, run:
   ```sql
   DESCRIBE CORTEX EXTENSION "<personal_db>"."<candidate_schema>"."<EXTENSION_NAME>";
   ```
   Collect every candidate where `DESCRIBE` succeeds **and** `type` matches
   `<artifact_type>` (`type = 'skill'` when `<artifact_type> = skill`;
   `type = 'plugin'` when `<artifact_type> = plugin`) into `<extension_matches>`
   (each entry: `<candidate_schema>` + DESCRIBE result). Track the first
   successful `DESCRIBE` whose `type` does not match `<artifact_type>` as
   `<type_mismatch>` (if any).
   - **Exactly one** entry in `<extension_matches>` → set `<DB>` =
     `<personal_db>`, `<SCHEMA>` = that schema. See §3 below for the combined
     reshare confirmation + share options stop.
   - **More than one** entry in `<extension_matches>` → ⚠️ **MANDATORY
     STOPPING POINT** — list each match in chat, then call
     `ask_user_question` per [share_interactive_prompts.md](../references/share_interactive_prompts.md)
     § **Multiple schema matches** (one option per FQN + Cancel). Set
     `<DB>` / `<SCHEMA>` from the pick, then see §3 below.
   - **Zero** entries in `<extension_matches>` and **all** candidates return
     "does not exist" (or no schemas found) → set `<intent>` =
     `share-first-time`. Proceed silently; no stop needed.
   - **Zero** entries in `<extension_matches>` but `<type_mismatch>` is set →
     **stop** — surface the type-mismatch error (see § SQL).
   - **Any other error** → stop; surface the error; do **not** proceed.

Map to `<intent>` after later steps: `share-first-time`, `share-resync`, or
`share-resync-and-update-share-options` (see §3); `unshare`.

### 2. Target (depends on §1)

- **First-time share** — local directory for the artifact:

  | `<artifact_type>` | Required layout |
  | ----------------- | ---------------- |
  | `skill` | Root contains `SKILL.md`. Extension object name from frontmatter **`name`** (uppercase, `-` and whitespace → `_`; see step 2), not from the folder name unless `name` is missing. |
  | `plugin` | Hidden manifest folder (dot-prefixed name) with `plugin.json` — e.g. `.cortex-plugin/`. Extension object name from `plugin.json` `name` (same transform; see step 2), not from the folder name. |

  **`<skill_basename>`** *(skill only)* — same rule in both runtime modes. In
  sandbox and non-sandbox alike, derive it from `SKILL.md` `name` in step 2
  (kebab-case: lowercase, `_` and whitespace → `-`). It becomes the folder
  segment `snow://cortex_extension/…/versions/live/skills/<skill_basename>/`.
  When `name` is set, do **not** use the host path folder name or the workspace
  `<folder>` name as `<skill_basename>` — only the transformed `name` (e.g.
  `name: sql-patterns` → `sql-patterns`, not `SQL_PATTERNS` and not whatever
  the directory is called on disk).

  **`<manifest_dir>`** *(plugin only)* — dot-prefixed directory name under the
  plugin root that contains `plugin.json` (e.g. `.cortex-plugin`; discovered in
  § **Parse Metadata**).

  What **differs** by mode is only **where you read** the artifact files from
  before upload:

  | Path | Source location |
  | ---- | ---------------- |
  | **Sandbox or CLI (client-local)** | `<artifact_dir>` — absolute or mounted path (e.g. `/Users/…/my-skill`, `/workspace/my-plugin`). |
  | **Non-sandbox (SQL-only)** | `<artifact_ws>` — `snow://workspace/…/versions/live/<folder>/` under the default workspace (resolve base via `DESCRIBE WORKSPACE` in [SKILL.md](SKILL.md) § Runtime modes). Skill workspace hints: `.snowflake/cortex/skills/<name>/` or `.snowflake/si/skills/<name>/` under `live/`. If files exist only on a host path outside the workspace, stop and have the user copy the artifact into the workspace before continuing — SQL-only mode cannot read laptop disk. |

- **Re-sharing** or **Unshare**: you need the extension’s **FQN** for SQL
  (`DESCRIBE`, `REVOKE`, etc.). **Prefer what is already in the conversation**
  (see **Detect inputs from the conversation**): usually the **FQN** in CoCo
  chat; sometimes the full **`snow://skill_catalog/...`** string if the client
  did not strip it.

  **When you still need input after the scan**, ask the user to open
  **Snowflake → Skill details** or **Plugin details** and copy the **catalog
  URI** (starts with `snow://skill_catalog/`, then
  `<DB>.<SCHEMA>.<CORTEX_EXTENSION_OBJECT_NAME>`, optional
  `/versions/version$N/...`). **Also tell them:** if CoCo only leaves
  `DB.SCHEMA.NAME` visible in chat after they paste, **that three-part line is
  enough** — they do not need to fight the client for the `snow://` prefix.

  **Parsing** (URI → FQN): take the path segment immediately after
  `snow://skill_catalog/` (stop at `/`, `?`, or end). Split on `.` into **three**
  parts — same split as for a bare FQN token.

  **Canonical catalog URI for handoff** (coworkers still install with
  `snow://skill_catalog/...`): if you only received the FQN, set
  `<existing_catalog_uri>` =
  `snow://skill_catalog/<DB>.<SCHEMA>.<EXTENSION_NAME>/` (normalized). If you
  received a full URI from the user, keep that verbatim in
  `<existing_catalog_uri_verbatim>` when useful; `<existing_catalog_uri>` should
  still be at least the normalized base URI for consistency.

  Use `"<DB>"."<SCHEMA>"."<EXTENSION_NAME>"` in all SQL.

- **Re-sharing** (continued): Step 2 still needs the artifact tree to upload on
  the next live version. If missing, ask after you have the URI/FQN:

  | Path | Source location |
  | ---- | ---------------- |
  | **Sandbox or CLI (client-local)** | `<artifact_dir>` — local path with the manifest (`SKILL.md` or dot-dir + `plugin.json`). |
  | **Non-sandbox (SQL-only)** | `<artifact_ws>` — workspace `snow://` folder (see first-time share table). |

**Do not ask “whom to share with” in Step 1.** Do not list PUBLIC, share-link,
catalog, or role choices here. **Whom to share with** is asked **only** in
[step_3_apply_share_options.md](step_3_apply_share_options.md) (or collected
before plugin Option A CLI in step 2), using **exactly** the three numbered
options defined there — every time that step runs.

## SQL

`SELECT CURRENT_USER();` → personal DB = `USER$` + the returned
identifier (opaque); quoted later as `"USER$<USER>"`. Then probe
extension existence:

For **re-share**, **unshare**, or **ambiguous share intent** (auto-detect
path in §1), a `DESCRIBE` is needed. For re-share and unshare, `<DB>`,
`<SCHEMA>`, and `<EXTENSION_NAME>` come from the FQN/URI already in the
thread. For **ambiguous intent**, the schema is not yet known — the probe
in §1 runs `SHOW SCHEMAS` first (see §1) and iterates over candidates;
the `<SCHEMA>` is resolved there before `DESCRIBE` is attempted. For
**explicit first-time share**, skip `DESCRIBE` (proceed directly to Step 2).

**Before running `DESCRIBE`** (re-share / unshare / ambiguous-intent probe),
surface [SKILL.md](SKILL.md) § **Cortex Extension — user-facing one-liner**
once per run so the user knows what the `CORTEX EXTENSION` keyword in the
next SQL refers to. Skip on subsequent statements in the same run.

```sql
DESCRIBE CORTEX EXTENSION "<DB>"."<SCHEMA>"."<EXTENSION_NAME>";
```

- **success** → the extension exists. Check `type` column against
  `<artifact_type>`:
  - If `type` does not match `<artifact_type>` (e.g. sharing a skill into a
    plugin extension or vice versa): **stop**. Surface the error:
    - When `<artifact_type> = skill`:
      > The Cortex Extension `<DB>.<SCHEMA>.<EXTENSION_NAME>` exists but its
      > type is `<type>`, not `skill`. Cannot reshare a skill into a non-skill
      > extension. Please provide a different FQN.
    - When `<artifact_type> = plugin`:
      > The Cortex Extension `<DB>.<SCHEMA>.<EXTENSION_NAME>` exists but its
      > type is `<type>`, not `plugin`. Cannot share a plugin into a non-plugin
      > extension. Please provide a different FQN.
  - If `type` matches `<artifact_type>`:
    - **Ambiguous share intent** → set `<intent>` = `share-resync`; present
      the combined reshare confirmation + share options stop (§3 ambiguous
      reshare).
    - **Re-share** → capture `default_version_location_uri`, `comment`,
      `discoverable`, then **Parse Metadata** and § **Re-share: renamed
      artifact?** below — **not** §3 yet.
    - **Unshare** → continue.
    - **Explicit first-time share** → stop and clarify: they may mean
      **re-share** instead.
- **error** whose message (case-insensitive) contains any of `does not exist`,
  `object does not exist`, `unknown cortex extension`:
  - **Ambiguous share intent** → set `<intent>` = `share-first-time`; proceed
    silently (no question needed). If iterating over multiple candidate schemas,
    continue to the next candidate before treating as not-found.
  - **Explicit first-time share** → expected; proceed as `share-first-time`.
  - **Re-share** or **unshare** → surface the error; do **not** pretend the
    extension exists.
- **error** whose message (case-insensitive) signals the **Cortex Extensions
  feature is not enabled** on this account — any of: `syntax error` near
  `CORTEX`/`EXTENSION`, `unsupported feature` referencing `CORTEX EXTENSION`,
  or `object type 'cortex extension' is not supported`. This is the **first**
  statement that exercises Cortex Extension syntax, so a parse-level failure
  here means the feature is gated off. **Stop** the entire pipeline
  (re-share / unshare alike — first-time share never runs this `DESCRIBE`,
  so the gate fires in step 2 instead) and follow
  [SKILL.md](SKILL.md) § **Cortex Extensions feature not enabled on this
  account**.
- **any other error** → stop; surface the error; do **not** proceed.

## Parse Metadata

Load and follow [step_1_parse_manifest.md](step_1_parse_manifest.md), then
return here for § Re-share: renamed artifact?

### Re-share: renamed artifact? *(mandatory — before §3)*

When the user chose **Updating an already shared artifact** (§1 option 2) and
`DESCRIBE` succeeded for their FQN/URI, compare the extension object they
referenced with the name implied by the **current** local manifest:

1. `<catalog_extension_name>` — third segment from their FQN / catalog URI (what
   `DESCRIBE` targeted). Keep this as `<superseded_extension_name>` for reporting.
2. `<name_implied_extension>` — apply the same name resolution as step 2 § Derive
   names:
   - **Skill:** trimmed `name` from `SKILL.md` when present; otherwise folder
     fallback from `<artifact_dir>` or `<artifact_ws>`; then uppercase; every `-`
     → `_`; every whitespace → `_`.
   - **Plugin:** from `plugin.json` `name`: uppercase; every `-` → `_`; every
     whitespace → `_`.

If the two strings differ **case-insensitively**, the artifact was **renamed**.
**This check overrides re-share wording** — phrases like “update the existing
share”, “push latest content”, or an old FQN in the message do **not** authorize
`ALTER` / upload / `COMMIT` on the old extension.

**Do not** ask the user to confirm whether to update the old FQN vs create a new
share. **Do not** run §3 (A)/(B). Tell the user and pivot immediately:

> The **`name`** in your current manifest (`<name>` → extension
> **`<name_implied_extension>`**) does not match the shared `<artifact_noun>` you
> pointed at (**`<DB>.<SCHEMA>.<catalog_extension_name>`**). A shared
> `<artifact_noun>` is **uniquely identified by that extension name**, so we will
> **create a new share** (first-time share flow) as **`<name_implied_extension>`**,
> not update the old catalog entry. The previous entry (**`<existing_catalog_uri>`**
> or FQN) stays unchanged — unshare it separately if you no longer want it.

Then:

- Set `<intent>` = `share-first-time`.
- Set `<EXTENSION_NAME>` = `<name_implied_extension>` (publish target).
- Carry `<superseded_extension_name>` and `<existing_catalog_uri>` only for the
  final report — **never** use them as `<id>` / upload / `COMMIT` targets in
  step 2.

If they match, continue as **re-share** and complete §3.

### 3. Re-share only — share options

**Only when** § **Re-share: renamed artifact?** did **not** pivot to
`share-first-time`.

#### Ambiguous reshare (extension found by auto-detect probe)

⚠️ **MANDATORY STOPPING POINT** — show the existing FQN and catalog URI in
chat, then call `ask_user_question` per
[share_interactive_prompts.md](../references/share_interactive_prompts.md)
§ **Reshare combined stop** (use "Different skill/plugin…" label with
**`<artifact_noun>`**). **Do not** paste the option list as markdown.

**After the picker** — collect any remaining free-text in **one** chat
message (never split across turns): the local artifact folder if
`<artifact_dir>` / `<artifact_ws>` is still unknown, and comma-separated role
names if the user picked **To a specific ROLE…**. If neither is outstanding,
ask nothing.

**Map picker labels to intent and audience state:**

| Picker label | `<intent>` | `<share_choice>` | `<share_roles>` | `<discoverable_value>` |
| ------------ | ---------- | ---------------- | --------------- | ---------------------- |
| **Everyone…** | `share-resync-and-update-share-options` | 1 | `[PUBLIC]` | TRUE |
| **Privately via a share link…** | `share-resync-and-update-share-options` | 2 | `[PUBLIC]` | FALSE |
| **To a specific ROLE…** | `share-resync-and-update-share-options` | 3 | user-supplied (uppercase) | TRUE |
| **Keep current share options…** | `share-resync` | — | — | — |

- Set `<artifact_dir>` / `<artifact_ws>` whenever the path follow-up provides
  them. Step 3 **skips its audience question** when `<share_choice>` is set.
- **Don't reshare** → **stop; done.**
- **Different skill/plugin already uses this name** → explain and **stop**:

    > Each `<artifact_noun>` you share is uniquely identified by the `name` in
    > its manifest (which maps directly to the Cortex Extension name
    > **`<EXTENSION_NAME>`**). A different `<artifact_noun>` has already been
    > shared under that same name as **`<DB>.<SCHEMA>.<EXTENSION_NAME>`**. To
    > share your `<artifact_noun>` you must either:
    >
    > 1. Drop the existing Cortex Extension:
    >    `DROP CORTEX EXTENSION "<DB>"."<SCHEMA>"."<EXTENSION_NAME>";`
    > 2. Or change the `name` field in your manifest to a unique name and share
    >    again.
    >
    > I have not created, altered, or uploaded anything.

    **Done — do not proceed further.**

#### Explicit reshare (user stated "reshare", "update my skill/plugin", etc.)

After `DESCRIBE CORTEX EXTENSION` succeeds (§ SQL) and § **Re-share: renamed
artifact?** kept re-share intent, call `ask_user_question` per
[share_interactive_prompts.md](../references/share_interactive_prompts.md)
§ **Explicit reshare mode (A / B)**.

- **Content-only — keep current share options** → `share-resync` (step 3
  skipped).
- **Update content and change share options** →
  `share-resync-and-update-share-options` (step 3 runs unless audience
  collected later).
- **Cancel** → **stop; done.**

If `<artifact_dir>` / `<artifact_ws>` is still unknown, ask once in chat for the
path after the picker. Name-conflict replies use the same DROP-or-rename
message as §3 ambiguous reshare.

## Output

Carry forward:

- `<artifact_type>` ∈ {`skill`, `plugin`}
- `<artifact_noun>` — "skill" or "plugin" for user-facing copy
- `<intent>` ∈ {share-first-time, share-resync,
  share-resync-and-update-share-options, unshare}
- `<artifact_dir>` *(share flows, Sandbox or CLI)* — folder with the manifest
  (`SKILL.md` or dot-dir + `plugin.json`)
- `<artifact_ws>` *(share flows, non-sandbox only)* — workspace
  `snow://workspace/…/versions/live/…/` URI for the artifact folder
- `<manifest_dir>` *(plugin only)* — dot-prefixed directory name under the
  plugin root that contains `plugin.json` (e.g. `.cortex-plugin`)
- `<skill_basename>` *(skill only)* — kebab-case stage folder from `name`
  (step 2); used in `…/skills/<skill_basename>/…` on upload
- `<DB>`, `<SCHEMA>`, `<EXTENSION_NAME>` — from parsed **FQN** for **unshare**
  and for **re-share** when the catalog extension still matches manifest
  `name`. For **`share-first-time`** (including a re-share that pivoted because
  `name` changed), `<EXTENSION_NAME>` is from **current** manifest, not the old
  FQN.
- `<superseded_extension_name>` *(optional)* — old FQN extension segment when a
  re-share pivoted to `share-first-time`; report only, not a publish target.
- `<existing_catalog_uri>` *(re-share / unshare)* — normalized
  `snow://skill_catalog/<DB>.<SCHEMA>.<EXTENSION_NAME>/` at minimum; use the
  user’s verbatim catalog URI when they supplied one (may include version path).
- `<existing_catalog_uri_verbatim>` *(optional)* — only when the raw message
  contained a full `snow://skill_catalog/...` string; otherwise empty.
- `<artifact_description>` *(share only)* — raw description from manifest;
  step 2 turns this into the final `<comment>`
- `<existing_comment>` *(re-share only)* — the `comment` column from the
  DESCRIBE above (may be empty)
- `<schema_discovery_result>` *(ambiguous-intent probe only)* — the result of
  `SHOW SCHEMAS LIKE 'SKILL_SHARING%'`; passed to step 2 so it is **not** re-run
- `<share_choice>` *(ambiguous reshare, options 1–3 only)* — audience choice
  (1, 2, or 3) collected during §3 ambiguous reshare combined stop; step 3
  skips its audience question when this is set
- `<share_roles>` — role list (e.g. `[PUBLIC]` for choices 1 & 2; user-supplied
  for choice 3); empty when not applicable
- `<discoverable_value>` — TRUE or FALSE per the mapping above; empty when not
  applicable

## ⚠️ MANDATORY STOPPING POINT

**Intent gate** (applies only when a stop is needed):

- **Explicit intent** (user clearly stated first-time share, re-share, or
  unshare) → no intent stop needed; confirm only **target**.
- **Ambiguous share + auto-detected first-time** (all DESCRIBE probes returned
  “does not exist”, or no `SKILL_SHARING%` schemas found) → no intent stop;
  confirm only **target** (`<artifact_dir>` or `<artifact_ws>`).
- **Ambiguous share + auto-detected re-share** (DESCRIBE succeeded) → one
  `ask_user_question` **Reshare** picker (§3); path/roles only as single chat
  follow-ups if still missing. Do **not** issue a second A/B stop.
- **Explicit reshare** → one `ask_user_question` **Reshare mode** picker (§3)
  after DESCRIBE succeeds and rename check passes.
- **Ambiguous artifact type** (both markers or neither) → one **Artifact type**
  picker before intent probing.

In all cases, do **not** treat an **FQN or URI already present** in the thread
as “missing”; re-asking for the same target is wrong.

## ⚠️ MANDATORY STOPPING POINT — Pre-flight summary

**Always run** after intent, target, artifact type, and (for re-share) §3
choices are resolved — and **before** loading the next step. Show the gathered
details using
[share_interactive_prompts.md](../references/share_interactive_prompts.md)
§ **Pre-flight summary** (use the template matching `<artifact_type>`). Then
call `ask_user_question` § **Confirm gathered details**. Do **not** proceed to
step 2 or step 4 until the user picks **Yes, proceed**.

## Next

- share-* → `step_2_publish.md` *(only after pre-flight confirm)*
- unshare → `step_4_unshare.md` *(only after pre-flight confirm)*
