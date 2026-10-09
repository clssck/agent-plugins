---
description: Check authorization, target, and outgoing commits before git push
condition:
- '^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*git\s+(?:(?:(?:-C|-c|--(?:git-dir|work-tree|namespace|config-env|super-prefix|shallow-file|attr-source|date))(?:=|\s+)(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|--exec-path(?:=|\s+)(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:-p|-P|--(?:paginate|no-pager|no-replace-objects|no-lazy-fetch|no-optional-locks|no-advice|bare|literal-pathspecs|glob-pathspecs|noglob-pathspecs|icase-pathspecs)))\s+)*push(?=\s|$|[;&|)])'
- '"command"\s*:\s*"(?:(?:\\"(?:[^"\\]|\\[^"])*?\\"|\''(?:[^\''"\\]|\\.)*\''|\\[^"]|[^"\\\''])*?(?:&&|;|\|\|?|\\n|\(|\$\()\s*)?(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*git\s+(?:(?:(?:-C|-c|--(?:git-dir|work-tree|namespace|config-env|super-prefix|shallow-file|attr-source|date))(?:=|\s+)(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|--exec-path(?:=|\s+)(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:-p|-P|--(?:paginate|no-pager|no-replace-objects|no-lazy-fetch|no-optional-locks|no-advice|bare|literal-pathspecs|glob-pathspecs|noglob-pathspecs|icase-pathspecs)))\s+)*push(?=\s|$|[;&|)"]|\\n)'
scope: tool:bash
interruptMode: always
---

**A push publishes work to shared, external state.**

- Push only when the user requested it or a repository instruction delegates it.
- Name the remote and destination branch explicitly (`git push <remote> HEAD:<branch>`); never rely on upstream defaults you have not inspected.
- Pushing to a default or protected branch (`main`, `master`, release branches) requires that branch to be the requested target.
- Before pushing, list exactly what will publish: `git log --oneline <remote>/<branch>..HEAD`. Stop if it contains commits you did not create or expect.
- NEVER force-push a shared branch. Rewriting your own feature branch? Use `--force-with-lease=<branch>:<expected-sha>`, not `--force`.
- Deleting remote refs (`--delete`, `:<branch>`) requires an explicit request naming that ref.
