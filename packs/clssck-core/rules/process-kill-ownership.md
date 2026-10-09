---
description: Kill only processes this session started; never by port or broad pattern without identifying them
condition:
- '^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*(?:pkill|killall)(?=[ \t])'
- '"command"\s*:\s*"(?:(?:\\"(?:[^"\\]|\\[^"])*?\\"|\''(?:[^\''"\\]|\\.)*\''|\\[^"]|[^"\\\''])*?(?:&&|;|\|\|?|\\n|\(|\$\()\s*)?(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*(?:pkill|killall)(?=[ \t])'
- '^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*(?:lsof|pgrep)\b[^\n;&|]*\|[ \t]*xargs(?:[ \t]+-[^\s;&|]+)*[ \t]+kill(?=\s|$|[;&|)])'
- '"command"\s*:\s*"(?:(?:\\"(?:[^"\\]|\\[^"])*?\\"|\''(?:[^\''"\\]|\\.)*\''|\\[^"]|[^"\\\''])*?(?:&&|;|\|\|?|\\n|\(|\$\()\s*)?(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*(?:lsof|pgrep)\b[^\n;&|]*\|[ \t]*xargs(?:[ \t]+-[^\s;&|]+)*[ \t]+kill(?=\s|$|[;&|)"]|\\n)'
- '^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*kill(?:[ \t]+-[^\s;&|]+)*[ \t]+"?\$\((?:lsof|pgrep)\b'
- '"command"\s*:\s*"(?:(?:\\"(?:[^"\\]|\\[^"])*?\\"|\''(?:[^\''"\\]|\\.)*\''|\\[^"]|[^"\\\''])*?(?:&&|;|\|\|?|\\n|\(|\$\()\s*)?(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*kill(?:[ \t]+-[^\s;&|]+)*[ \t]+"?\$\((?:lsof|pgrep)\b'
- '^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*fuser(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|''[^''\n]*''|[^\s;&|()''"#]+))*?[ \t]+-[A-Za-z]*k'
- '"command"\s*:\s*"(?:(?:\\"(?:[^"\\]|\\[^"])*?\\"|\''(?:[^\''"\\]|\\.)*\''|\\[^"]|[^"\\\''])*?(?:&&|;|\|\|?|\\n|\(|\$\()\s*)?(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*fuser(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|''[^''\n]*''|[^\s;&|()''"#]+))*?[ \t]+-[A-Za-z]*k'
scope: tool:bash
interruptMode: always
---

**A port, name, or `-f` pattern does not prove which process you are killing.** Servers, apps, and daemons the user started (dev servers, trading services, editors, system agents) look the same to `lsof`, `pgrep`, and `pkill`.

- Kill processes this session started, by the PID you recorded or through the managed job/service (`proc://<id>/kill`).
- Anything else: identify every target first (`ps -p <pid> -o pid,etime,command=`), and kill only those you can show this session started.
- A pre-existing process occupying a needed port? Use another port, or ask before stopping it. NEVER restart or stop user services as troubleshooting.
- NEVER `killall`/`pkill` system or GUI processes (`sharingd`, `Dock`, `Finder`, terminal emulators, IDEs) unless the user asked for that exact restart.
- Prefer `SIGTERM`; use `-9` only after a graceful stop of your own process failed.
