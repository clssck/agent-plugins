# Step 2 — Upload Files: Plugin

Upload all plugin files into the live version preserving the local directory
structure exactly at the live root — no `skills/<basename>/` wrapper.
Load this file when `<artifact_type> = plugin`.

Target base URI:

```
snow://cortex_extension/<fqn>/versions/live/
```

Each file `<relative_path>` (forward-slash; reject `..`) maps to:

```
snow://cortex_extension/<fqn>/versions/live/<relative_path>
```

Example mappings for a typical Cortex plugin layout (`<manifest_dir>` =
`.cortex-plugin`):

| Local file | Stage URI |
|---|---|
| `<manifest_dir>/plugin.json` | `snow://…/versions/live/<manifest_dir>/plugin.json` |
| `agents/my-agent.md` | `snow://…/versions/live/agents/my-agent.md` |
| `commands/my-command.md` | `snow://…/versions/live/commands/my-command.md` |
| `hooks/on-load.sh` | `snow://…/versions/live/hooks/on-load.sh` |
| `.mcp.json` | `snow://…/versions/live/.mcp.json` |
| `settings.json` | `snow://…/versions/live/settings.json` |
| `LICENSE` | `snow://…/versions/live/LICENSE` |

**Exclude** when scanning: `.git/`, `.git` (file), `node_modules/`,
`.env`, `.env.*`, `.aws/`, `.ssh/`.

Try **one primary path** (A or B) for the whole share. If upload fails with a
**stage limit error** per [SKILL.md](SKILL.md) § **Stage file size and count
limits**, follow that section and **stop**. Otherwise **load**
[step_2_fallback_stage_copy.md](step_2_fallback_stage_copy.md) when shell + Snow
CLI are available.

## Path A — Sandbox or CLI (client-local upload)

Discover files on disk under `<artifact_dir>`. Build one entry per regular file:
`<absolute_local_path>` and `<relative_path>` under the plugin root.

Upload — one SQL statement per file:

```sql
PUT file://<absolute_local_path>
    $$snow://cortex_extension/<fqn>/versions/live/<relative_dir>/$$
  AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
```

`<relative_dir>` is the directory portion of `<relative_path>` (empty string
if the file is at the root — URI ends with `…/live/`). Wrap `file://...` in
single quotes if the path contains a space or `'` (escape `'` as `''`).

## Path B — Non-sandbox (SQL-only, workspace `COPY FILES`)

Requires `<artifact_ws>` from step 1 (trailing `/`).

```sql
LIST '<artifact_ws>';
LIST '<artifact_ws><subdir>/';   -- repeat for each subdirectory
```

```sql
-- Root file (e.g. settings.json):
COPY FILES INTO 'snow://cortex_extension/<fqn>/versions/live/'
  FROM '<artifact_ws>'
  FILES = ('settings.json');

-- Nested file (e.g. <manifest_dir>/plugin.json):
COPY FILES INTO 'snow://cortex_extension/<fqn>/versions/live/<manifest_dir>/'
  FROM '<artifact_ws><manifest_dir>/'
  FILES = ('plugin.json');

-- Nested file (e.g. agents/my-agent.md):
COPY FILES INTO 'snow://cortex_extension/<fqn>/versions/live/agents/'
  FROM '<artifact_ws>agents/'
  FILES = ('my-agent.md');
```

`COPY FILES` overwrites same-name objects. Do **not** use `PUT file://` in
this path.
