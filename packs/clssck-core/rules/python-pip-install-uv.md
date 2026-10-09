---
description: Install Python packages with uv, not pip into a system or user Python
condition:
- '^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*(?:python(?:3(?:\.\d+)?)?[ \t]+-m[ \t]+)?pip3?[ \t]+install(?=\s|$|[;&|)])'
- '"command"\s*:\s*"(?:(?:\\"(?:[^"\\]|\\[^"])*?\\"|\''(?:[^\''"\\]|\\.)*\''|\\[^"]|[^"\\\''])*?(?:&&|;|\|\|?|\\n|\(|\$\()\s*)?(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*(?:python(?:3(?:\.\d+)?)?[ \t]+-m[ \t]+)?pip3?[ \t]+install(?=\s|$|[;&|)"]|\\n)'
scope: tool:bash
interruptMode: always
---

**`pip install` outside an activated virtualenv mutates the system or `--user` Python.** On Homebrew or system Python it is blocked by PEP 668, and `--break-system-packages` or `--user` leaves packages behind that outlive the task.

|Need|Use|
|---|---|
|Run a script needing a package|`uv run --with <pkg> python script.py`, or PEP 723 inline deps + `uv run script.py`|
|One-off CLI|`uvx <tool>` / `uvx --from <pkg> <cmd>`|
|Persistent CLI the user asked for|`uv tool install <pkg>`|
|Project dependency|`uv add <pkg>` (or `uv pip install -r requirements.txt` in a `uv venv`)|
|Remote host or container|whatever that environment uses; this applies to the local machine|

An activated project venv (`.venv/bin/pip install`) is fine; NEVER pass `--break-system-packages`.
