# Step 2 Fallback: `snow stage copy`

Use **only after** primary upload fails in [step_2_publish.md](step_2_publish.md).
Requires `ADD LIVE VERSION` succeeded, shell + Snow CLI, readable source paths.

**Do not use this fallback** when the failure is a **stage limit error** per
[SKILL.md](SKILL.md) § **Stage file size and count limits** — stop and surface
the error to the user instead.

## Destination URI by `<artifact_type>`

### Skill (`<artifact_type> = skill`)

Per file — URI ends with `/`:

```bash
snow stage copy <readable_source_path> \
  'snow://cortex_extension/<DB>.<SCHEMA>.<EXTENSION_NAME>/versions/live/skills/<skill_basename>/<relative_dir>/' \
  --overwrite
```

Example:

```bash
snow stage copy /workspace/SKILL.md \
  'snow://cortex_extension/USER$ALICE.SKILL_SHARING_55A73C8F.SQL_PATTERNS/versions/live/skills/sql-patterns/' \
  --overwrite
```

### Plugin (`<artifact_type> = plugin`)

Flat under `versions/live/`:

```bash
snow stage copy <readable_source_path> \
  'snow://cortex_extension/<DB>.<SCHEMA>.<EXTENSION_NAME>/versions/live/<relative_dir>/' \
  --overwrite
```

Root files: URI ends with `/versions/live/`. `<relative_dir>` empty for root.

Example:

```bash
snow stage copy /workspace/.cortex-plugin/plugin.json \
  'snow://cortex_extension/<DB>.<SCHEMA>.<EXTENSION_NAME>/versions/live/.cortex-plugin/' \
  --overwrite
```

## Commit

After all files copied:

```sql
ALTER CORTEX EXTENSION "<DB>"."<SCHEMA>"."<EXTENSION_NAME>" COMMIT;
```

- `snow://cortex_extension/` uses unquoted `DB.SCHEMA.EXTENSION_NAME`.
- `COMMIT` uses double-quoted `"DB"."SCHEMA"."EXTENSION_NAME"`.

If shell or `snow` is unavailable, surface the original `PUT` / `COPY FILES`
error.

If `snow stage copy` or the post-copy `COMMIT` fails with a **stage limit
error** per [SKILL.md](SKILL.md) § **Stage file size and count limits**, follow
that section and **stop** (do not retry copy or COMMIT).
