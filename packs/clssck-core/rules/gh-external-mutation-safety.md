---
description: Check authorization and target before gh commands that change GitHub state
condition:
- '^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*gh[ \t]+(?:pr[ \t]+(?:create|merge|close|reopen|comment|review|edit|ready)|issue[ \t]+(?:create|close|reopen|comment|edit|delete|transfer|lock)|repo[ \t]+(?:create|delete|edit|rename|archive|unarchive|fork|sync)|release[ \t]+(?:create|delete|edit|upload)|workflow[ \t]+(?:run|enable|disable)|run[ \t]+(?:rerun|cancel|delete)|secret[ \t]+(?:set|delete)|variable[ \t]+(?:set|delete)|label[ \t]+(?:create|delete|edit|clone)|gist[ \t]+(?:create|delete|edit)|cache[ \t]+delete)(?=\s|$|[;&|)])'
- '"command"\s*:\s*"(?:(?:\\"(?:[^"\\]|\\[^"])*?\\"|\''(?:[^\''"\\]|\\.)*\''|\\[^"]|[^"\\\''])*?(?:&&|;|\|\|?|\\n|\(|\$\()\s*)?(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*gh[ \t]+(?:pr[ \t]+(?:create|merge|close|reopen|comment|review|edit|ready)|issue[ \t]+(?:create|close|reopen|comment|edit|delete|transfer|lock)|repo[ \t]+(?:create|delete|edit|rename|archive|unarchive|fork|sync)|release[ \t]+(?:create|delete|edit|upload)|workflow[ \t]+(?:run|enable|disable)|run[ \t]+(?:rerun|cancel|delete)|secret[ \t]+(?:set|delete)|variable[ \t]+(?:set|delete)|label[ \t]+(?:create|delete|edit|clone)|gist[ \t]+(?:create|delete|edit)|cache[ \t]+delete)(?=\s|$|[;&|)"]|\\n)'
- '^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*gh[ \t]+api\b(?![^;&|\n]*(?:-X|--method)[ \t=]*GET\b)(?=[^;&|\n]*?(?:(?:-X|--method)[ \t=]*(?:POST|PUT|PATCH|DELETE)\b|[ \t](?:-f|-F|--field|--raw-field|--input)(?=[ \t=])))'
- '"command"\s*:\s*"(?:(?:\\"(?:[^"\\]|\\[^"])*?\\"|\''(?:[^\''"\\]|\\.)*\''|\\[^"]|[^"\\\''])*?(?:&&|;|\|\|?|\\n|\(|\$\()\s*)?(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*gh[ \t]+api\b(?![^;&|\n]*(?:-X|--method)[ \t=]*GET\b)(?=[^;&|\n]*?(?:(?:-X|--method)[ \t=]*(?:POST|PUT|PATCH|DELETE)\b|[ \t](?:-f|-F|--field|--raw-field|--input)(?=[ \t=])))'
scope: tool:bash
interruptMode: always
---

**`gh` mutations publish to shared, external state: PRs, issues, repos, releases, workflows, secrets.**

- Run them only when the user requested that action on that target, or a repository instruction delegates it.
- Name the repo explicitly (`--repo owner/name` or `repos/owner/name/...`); NEVER rely on the inferred remote of an unfamiliar checkout.
- `gh api` with `-f`/`-F`/`--field`/`--input` sends a **POST** unless you pass `-X GET`. Reading with fields? Add `-X GET`.
- Destructive targets (`repo delete`, `release delete`, `secret delete`, `run delete`, `cache delete`, DELETE requests) need an explicit request naming that target.
- Prefer a reversible form: draft PRs/releases, `--dry-run` where `gh` supports it.
- After the call, report the URL or ID it created or changed.
