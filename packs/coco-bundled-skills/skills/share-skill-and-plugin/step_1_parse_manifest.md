# Step 1 — Parse Metadata

For **share** flows (first-time or re-share) that package files in Step 2.
**Unshare** does not need metadata from disk unless you are resolving an
ambiguous target.

## Skill (`<artifact_type> = skill`)

Parse YAML frontmatter between the first `---` pair in `SKILL.md`; extract
`name`, `description`, `summary`, `info`, `version`. The `name` field is
**required** for first-time share — step 2 derives `<EXTENSION_NAME>` (uppercase,
`_` separators) and `<skill_basename>` (kebab-case folder under `skills/`) from
it. In both paths, parse in your reasoning (line-by-line `key: value`, including
`>`, `>-`, `|`, `|-` block scalars). In non-sandbox mode, do **not** run Python or
`yaml.parse` in a script.

**Load `SKILL.md` text:**

| Path | Method |
| ---- | ------ |
| **Sandbox or CLI (client-local)** | Read `<artifact_dir>/SKILL.md` with file tools, or `cat` in bash. |
| **Non-sandbox (SQL-only)** | After `<artifact_ws>` is set, run via `snowflake_sql_execute`: |

```sql
CREATE OR REPLACE TEMPORARY STAGE share_artifact_md_read;
COPY FILES INTO @share_artifact_md_read/
  FROM '<artifact_ws>'
  FILES = ('SKILL.md');

CREATE OR REPLACE FILE FORMAT share_artifact_raw_txt
  TYPE = CSV
  FIELD_DELIMITER = NONE
  RECORD_DELIMITER = NONE
  COMPRESSION = NONE
  ESCAPE = NONE
  ESCAPE_UNENCLOSED_FIELD = NONE;

SELECT $1 AS content
  FROM @share_artifact_md_read/SKILL.md
  (FILE_FORMAT => 'share_artifact_raw_txt');
```

All six `NONE` / `COMPRESSION = NONE` settings are required so YAML is not
escaped or compressed. Use the `content` column as the frontmatter source.

Build `<artifact_description>` from this fallback chain: (1) `description`,
(2) `summary`, (3) `info`. Collapse `\s+` → single space, trim. Do **not**
truncate here — step 2 composes the final catalog comment interactively and
applies the 1024-char limit at that point. If all three fields are empty,
`<artifact_description>` is empty.

## Plugin (`<artifact_type> = plugin`)

### Locate `<manifest_dir>`

Under `<artifact_dir>` (or `<artifact_ws>`), find every **immediate child**
directory whose name starts with `.` and that contains `plugin.json`. Common
names include `.cortex-plugin` and `.claude-plugin`, but **any** hidden
directory with `plugin.json` counts — do not restrict to those two names.

| Path | Discovery |
| ---- | --------- |
| **Sandbox or CLI (client-local)** | List dot-prefixed subdirectories of `<artifact_dir>`; check each for `plugin.json`. |
| **Non-sandbox (SQL-only)** | `LIST '<artifact_ws>';` then `LIST` each dot-prefixed subdirectory; look for `plugin.json`. |

**Resolution:**

- **One match** → `<manifest_dir>` = that directory name (e.g. `.cortex-plugin`,
  no trailing slash).
- **Multiple matches** → prefer `.cortex-plugin`, then `.claude-plugin`; if
  still ambiguous, ask the user which manifest directory to use.
- **No match** → stop: no `plugin.json` in any hidden directory under the
  plugin root.

The `name` field is **required** for first-time share — step 2 derives
`<EXTENSION_NAME>` (uppercase, `_` separators) from it.

Build `<artifact_description>` from `plugin.json` `description` field (trim
whitespace). Do **not** truncate here — step 2 composes the final catalog
comment interactively and applies the 1024-char limit at that point. If the
field is absent or empty, `<artifact_description>` is empty.

**Load `plugin.json` text:**

| Path | Method |
| ---- | ------ |
| **Sandbox or CLI (client-local)** | Read `<artifact_dir>/<manifest_dir>/plugin.json` with file tools. |
| **Non-sandbox (SQL-only)** | After `<artifact_ws>` and `<manifest_dir>` are set, run via `snowflake_sql_execute`: |

```sql
CREATE OR REPLACE TEMPORARY STAGE share_artifact_json_read;
COPY FILES INTO @share_artifact_json_read/
  FROM '<artifact_ws><manifest_dir>/'
  FILES = ('plugin.json');

CREATE OR REPLACE FILE FORMAT share_artifact_raw_txt
  TYPE = CSV
  FIELD_DELIMITER = NONE
  RECORD_DELIMITER = NONE
  COMPRESSION = NONE
  ESCAPE = NONE
  ESCAPE_UNENCLOSED_FIELD = NONE;

SELECT $1 AS content
  FROM @share_artifact_json_read/plugin.json
  (FILE_FORMAT => 'share_artifact_raw_txt');
```

Parse the `content` column as JSON in your reasoning (extract `name`,
`description`, `version`).
