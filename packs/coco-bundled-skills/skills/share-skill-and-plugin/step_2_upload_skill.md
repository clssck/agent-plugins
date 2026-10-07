# Step 2 — Upload Files: Skill

Upload all skill files into the live version under the `skills/<skill_basename>/`
wrapper. Load this file when `<artifact_type> = skill`.

All paths land files under:

```
snow://cortex_extension/<fqn>/versions/live/skills/<skill_basename>/<relative_dir>/
```

`<skill_basename>` = kebab-case folder from `SKILL.md` `name` (see
[step_2_publish.md](step_2_publish.md) § Derive names).
Shared rules: forward-slash relative paths; reject `..`; empty
`<relative_dir>` → URI ends `…/skills/<skill_basename>/`.

Try **one primary path** (A or B) for the whole share. If upload fails with a
**stage limit error** per [SKILL.md](SKILL.md) § **Stage file size and count
limits**, follow that section and **stop**. Otherwise **load**
[step_2_fallback_stage_copy.md](step_2_fallback_stage_copy.md) when shell + Snow
CLI are available — do not retry the same failing `PUT` / `COPY FILES` in a loop.

## Path A — Sandbox or CLI (client-local upload)

Discover files on disk under `<artifact_dir>`. Build one entry per regular file:
`<absolute_local_path>` and `<relative_path>` under the skill folder.

Upload — one SQL statement per file:

```sql
PUT file://<absolute_local_path>
    $$snow://cortex_extension/<fqn>/versions/live/skills/<skill_basename>/<relative_dir>/$$
  AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
```

Wrap `file://...` in single quotes if the path contains space or `'`
(escape `'` as `''`).

## Path B — Non-sandbox (SQL-only, workspace `COPY FILES`)

Requires `<artifact_ws>` from step 1 (trailing `/`).

Discover files — no bash. Recurse with SQL only:

```sql
LIST '<artifact_ws>';
LIST '<artifact_ws><subdir>/';   -- repeat for each subdirectory
```

Upload — `FILES` lists **only the filename**; directory goes in `FROM` and
`INTO` (trailing `/` on both):

```sql
-- Root file (SKILL.md):
COPY FILES INTO 'snow://cortex_extension/<fqn>/versions/live/skills/<skill_basename>/'
  FROM '<artifact_ws>'
  FILES = ('SKILL.md');

-- Nested file (e.g. references/guide.md):
COPY FILES INTO 'snow://cortex_extension/<fqn>/versions/live/skills/<skill_basename>/references/'
  FROM '<artifact_ws>references/'
  FILES = ('guide.md');
```

`COPY FILES` overwrites same-name objects. Do **not** use `PUT file://` in this
path — it will fail without a client-local filesystem.
