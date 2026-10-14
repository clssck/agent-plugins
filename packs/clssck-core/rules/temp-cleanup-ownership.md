---
description: Delete only the temp paths this session created; never clean /tmp or $TMPDIR by glob, pattern, or time window
condition:
  - '\brm\b[^\n;&|]*\s["'']?(?:(?:/private)?/tmp|/var/folders|\$\{?TMPDIR\}?)/[^\s;&|]*[*?\[]'
  - '\bfind\s+["'']?(?:(?:/private)?/tmp|/var/folders|\$\{?TMPDIR\}?)\b[^\n;&|]*(?:-delete\b|-exec\s+rm\b|\|\s*xargs\b[^\n;&|]*\brm\b)'
  - '(?:listdir|glob\.i?glob|iterdir|scandir|\.r?glob)\([^)]*(?:/tmp|TMPDIR|gettempdir|/var/folders)[\s\S]{0,800}?(?:rmtree|os\.remove|os\.unlink|\.unlink)\('
  - 'Path\([^)]*(?:/tmp|TMPDIR|gettempdir|/var/folders)[^)]*\)\s*\.\s*(?:r?glob|iterdir)\([\s\S]{0,800}?(?:rmtree|os\.remove|os\.unlink|\.unlink)\('
scope: "tool:bash, tool:eval"
interruptMode: always
---

`/tmp` and `$TMPDIR` are shared with every other process, session, and tool on the machine. A glob or a time window also matches their live files.

- Track what you create: keep the `mktemp -d` path, or name scratch with a unique prefix and record the full paths.
- Delete exactly those recorded paths, after their owning process exits.
- NEVER select deletions by glob, name pattern, or modification time in a shared temp directory, even if the names look like yours. That includes `find <tmp> ... -delete`, `find <tmp> ... | xargs rm`, and Python `Path("/tmp").glob(...)`/`iterdir()`/`os.listdir` followed by `rmtree` or `unlink`.
- Can't trace a path to a command you ran? Leave it, and list it in the report.
- Deleted something you can't trace? Say so explicitly: it cannot be recovered.
