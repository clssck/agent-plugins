---
description: Delete only the temp paths this session created; never clean /tmp or $TMPDIR by glob, pattern, or time window
condition:
- '^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*rm(?=[ \t])(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|\''[^\''\n]*\''|[^\s;&|()\''"#]+))*?[ \t]+(?:\\?["\''])?(?:/private)?(?:/tmp/|\$\{?TMPDIR\}?(?:\\?["\''])?/?|/var/folders/)[^\s;&|()\''"#]*[*?\[]'
- '"command"\s*:\s*"(?:(?:\\"(?:[^"\\]|\\[^"])*?\\"|\''(?:[^\''"\\]|\\.)*\''|\\[^"]|[^"\\\''])*?(?:&&|;|\|\|?|\\n|\(|\$\()\s*)?(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*rm(?=[ \t])(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|\''[^\''\n]*\''|[^\s;&|()\''"#]+))*?[ \t]+(?:\\?["\''])?(?:/private)?(?:/tmp/|\$\{?TMPDIR\}?(?:\\?["\''])?/?|/var/folders/)[^\s;&|()\''"#]*[*?\[]'
- '^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*find[ \t]+(?:\\?["\''])?(?:/private)?(?:/tmp|\$\{?TMPDIR\}?|/var/folders)\b[^;&|\n]*?(?:-delete|-exec[ \t]+rm)\b'
- '"command"\s*:\s*"(?:(?:\\"(?:[^"\\]|\\[^"])*?\\"|\''(?:[^\''"\\]|\\.)*\''|\\[^"]|[^"\\\''])*?(?:&&|;|\|\|?|\\n|\(|\$\()\s*)?(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*find[ \t]+(?:\\?["\''])?(?:/private)?(?:/tmp|\$\{?TMPDIR\}?|/var/folders)\b[^;&|\n]*?(?:-delete|-exec[ \t]+rm)\b'
- '(?:listdir|glob\.glob|glob\.iglob|iterdir|scandir|Path\([^)]*\)\.glob)\([^)]*(?:/tmp|TMPDIR|gettempdir|/var/folders)[\s\S]{0,800}?(?:rmtree|os\.remove|os\.unlink|\.unlink)\('
scope:
- tool:bash
- tool:eval
interruptMode: always
---

**`/tmp` and `$TMPDIR` are shared with every other process, session, and tool on the machine.** A glob or a time window also matches their live files.

- Track what you create: keep the `mktemp -d` path, or name scratch with a unique prefix and record the full paths.
- Delete exactly those recorded paths, after their owning process exits.
- NEVER select deletions by glob, name pattern, or modification time in a shared temp directory, even if the names look like yours.
- Can't trace a path to a command you ran? Leave it, and list it in the report.
- Deleted something you can't trace? Say so explicitly: it cannot be recovered.
