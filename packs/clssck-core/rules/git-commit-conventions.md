---
description: Guard blanket git staging and direct git commit commands with repository-aware checks
condition:
  - '^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*git\s+(?:(?:(?:-C|-c|--(?:git-dir|work-tree|namespace|config-env|super-prefix|shallow-file|attr-source|date))(?:=|\s+)(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|--exec-path(?:=|\s+)(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:-p|-P|--(?:paginate|no-pager|no-replace-objects|no-lazy-fetch|no-optional-locks|no-advice|bare|literal-pathspecs|glob-pathspecs|noglob-pathspecs|icase-pathspecs)))\s+)*commit(?=\s|$|[;&|)])'
  - '^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*git\s+(?:(?:(?:-C|-c|--(?:git-dir|work-tree|namespace|config-env|super-prefix|shallow-file|attr-source|date))(?:=|\s+)(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|--exec-path(?:=|\s+)(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:-p|-P|--(?:paginate|no-pager|no-replace-objects|no-lazy-fetch|no-optional-locks|no-advice|bare|literal-pathspecs|glob-pathspecs|noglob-pathspecs|icase-pathspecs)))\s+)*add(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|''[^''\n]*''|[^\s;&|()''"#]+))*?[ \t]+(?:-A|--all|-u|--update|\.|:/|-[A-Za-z]*[Au][A-Za-z]*)(?=\s|$|[;&|)])'
scope: 'tool:bash'
---

**Stage and commit only when the user requested it or a repository instruction delegates it.**

1. Read the repository's commit instructions and recent subjects: `git log --pretty=format:'%h %s' -10`.
2. Stage one coherent concern by named paths. `git add -A`/`.`/`-u` and `git commit -a` sweep in every unrelated change, including the user's uncommitted work; check `git status --short` first.
3. Write a concise, specific subject describing the actual change. Use `type(scope): summary` only when the history demonstrably uses it; never generic subjects (`update stuff`, `misc fixes`, `wip`, `address review comments`).
4. Add a body only when it explains rationale, risk, or follow-up.
