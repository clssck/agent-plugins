---
description: Delete only the temp paths this session created; never clean /tmp or $TMPDIR by glob, pattern, or time window
condition:
  - '^(?=[\s\S]*(?:/tmp\b|/var/folders|TMPDIR|gettempdir|tmpdir))(?=[\s\S]*(?:\b|\\[nrt])(?:rm(?:Sync)?|rmtree|os\.remove|unlink(?:Sync)?|rmdir(?:Sync)?|delete)\b)'
scope: "tool:bash, tool:eval"
interruptMode: always
---

Delete only the exact temp paths this session created, after their owning process exits. `/tmp` and `$TMPDIR` are shared with every other process, session, and tool on the machine; a glob or a time window also matches their live files.

## Track what you create

Keep the `mktemp -d` path, or name scratch with a unique prefix and record the full paths. Delete exactly those recorded paths, after their owning process exits.

```bash
# Good
scratch=$(mktemp -d)
./run-job --out "$scratch"
rm -rf -- "$scratch"
```

## Never select by pattern

NEVER select deletions by glob, name pattern, or modification time in a shared temp directory, even if the names look like yours. That includes `cd <tmp> && rm <glob>`, `find <tmp> ... -delete`, `find <tmp> ... | xargs rm`, Python `Path("/tmp").glob(...)`/`iterdir()`/`os.listdir` followed by `rmtree` or `unlink`, and JavaScript `fs.readdirSync(os.tmpdir())` followed by `rmSync` or `unlinkSync`.

```bash
# Bad
rm -rf /tmp/myjob-*
find /tmp -name 'myjob-*' -mtime +1 -delete
find "$TMPDIR" -name '*.log' | xargs rm
```

```python
# Bad
for p in Path("/tmp").glob("myjob-*"):
    shutil.rmtree(p)

# Good — remove only the path this session recorded
scratch = tempfile.mkdtemp(prefix="myjob-")
...
shutil.rmtree(scratch)
```

## Untraceable paths

- Can't trace a path to a command you ran? Leave it, and list it in the report.
- Deleted something you can't trace? Say so explicitly: it cannot be recovered.

## Exceptions

A match is a reminder, not a violation: the trigger is only a shared-temp token alongside a deletion token, so it also fires for dry-runs, literal examples, inert text, project-local paths, and cleanup of an exact path this session recorded. None of those need extra permission or correction. Prove exact-path ownership independently of whether a reminder fires.
