# Running snowflake-postgres on Windows

Cortex Code is GA on native Windows. Everything in `snowflake-postgres/` runs
there without WSL, but a few things differ from macOS / Linux. This reference
is the canonical place to look up what changes. Individual SKILL.md files link
here.

## What's actually different on Windows

The only meaningful runtime difference is **where libpq stores credentials**.
On macOS / Linux the canonical paths are `~/.pgpass` and `~/.pg_service.conf`.
On native Windows libpq uses `%APPDATA%\postgresql\` and the filenames lose
their leading dot.

| OS                       | pgpass                                          | pg_service                                           |
|--------------------------|-------------------------------------------------|------------------------------------------------------|
| macOS / Linux / WSL      | `~/.pgpass`                                     | `~/.pg_service.conf`                                 |
| Native Windows           | `%APPDATA%\postgresql\pgpass.conf`              | `%APPDATA%\postgresql\pg_service.conf`               |

There is no translation layer. The files genuinely live in different places
depending on the OS.

### How the skill handles this

- **Python scripts (`pg_common.py`, `pg_connect.py`, `filter_vendor_dump.py`,
  the migration tooling, etc.) compute the right path themselves** via
  `os.name`. They never use `~/.pgpass` literally on Windows; they read and
  write `%APPDATA%\postgresql\pgpass.conf` directly. Resolution order on
  Windows is: `%APPDATA%\postgresql\` → `%USERPROFILE%\AppData\Roaming\postgresql\`
  → `RuntimeError`. Matches libpq's own fallback chain.
- **SKILL.md and reference doc prose still says `~/.pgpass`** as shorthand.
  When the agent walks a Windows user through anything that touches that
  file by hand (e.g. `cat ~/.pgpass`), the agent should substitute the
  Windows path. Each SKILL.md has a Windows-note callout at the top to keep
  this in attention.

`~/.snowflake/` is **not** remapped — Snowflake CLI handles its own config
directory and uses `%USERPROFILE%\.snowflake\` on Windows automatically.

## WSL vs native — pick once

Both work. Pick once and stick with it:

- **WSL** behaves identically to Linux. `os.name == 'posix'` inside WSL so
  the scripts take the POSIX branch (correct — WSL has a Linux filesystem
  view and must not write to `%APPDATA%`). All `~/.pgpass` guidance in the
  skill applies as-is.
- **Native Windows** gets `%APPDATA%\postgresql\` automatically via the
  scripts. Use this when you don't have WSL set up.

If you're operating from PowerShell, the Python invocations all still work;
just substitute PowerShell's `Get-Content`, `Out-File`, and `$env:VAR` for
`cat`, `>`, and `$VAR` in any handcrafted snippets.

## Driver behavior on Windows-on-ARM

`psycopg2-binary` does not publish a wheel for `win_arm64`. On native Windows
ARM64 (e.g. Surface Pro with Snapdragon, Parallels on Apple Silicon), `uv sync`
skips `psycopg2-binary` via a PEP 508 environment marker and the scripts fall
back to `pg8000` — a pure-Python PostgreSQL driver that is already a declared
dependency.

The fallback is transparent: scripts connect via `pg_common.connect()`, which
dispatches to whichever driver loaded, and catch the driver-agnostic
`pg_common.PgError` / `pg_common.PgOperationalError` aliases.

### What differs on the pg8000 path

| Aspect | psycopg2 (common path) | pg8000 (WoA fallback) |
|--------|----------------------|----------------------|
| Performance | C extension, fast bulk reads | Pure Python, slower on large result sets |
| `options=` GUC string | Forwarded to libpq | Silently dropped — no equivalent |
| `hostaddr=` DNS bypass | Forwarded to libpq | Silently dropped — uses `host` |
| SQLSTATE access | `e.pgcode` attribute | `e.args[0]["C"]` dict key |
| SSL | libpq-native | `ssl.SSLContext` wrapper |

`pg_doctor.py` is the only script affected by the `options=` gap. On WoA it
runs in best-effort mode: no DB-level `default_transaction_read_only` or
`statement_timeout` enforcement. The script's queries are all SELECTs (no
DDL/DML), so practical impact is low.

### Snowflake-side operations on WoA

`snowflake-connector-python` has the same `win_arm64` wheel gap. All
Snowflake-side entry points still work on WoA: operations that need a
Snowflake call fall back to the `snow` CLI, which reads the same
`~/.snowflake/connections.toml`.

The one exception is **direct-args / env-var auth** (`SNOWFLAKE_ACCOUNT` +
`SNOWFLAKE_USER` + `SNOWFLAKE_PASSWORD`): that's a connector-specific flow with
no `snow sql` equivalent, so it still requires the connector. On WoA, use a
saved connection in `~/.snowflake/connections.toml` instead.

### Invoking `snow sql` safely from scripts / agent shells

When the agent falls back to `snow sql` directly on WoA, two gotchas come
up reliably:

1. **Use `--connection NAME`, not `-c NAME`.** At the top-level `snow`
   command, `-c` resolves to `--config-file` (path to the config TOML),
   not connection. At the `sql` subcommand `-c` *is* `--connection` — but
   depending on snow's version and argument-parser quirks the short form
   can mis-route and you'll see errors like `Try '-c sql --help' for help`.
   The long `--connection my_conn` form is unambiguous in every version.

2. **Prefer `-f file.sql` over `-q "..."` on Windows.** cmd.exe and
   PowerShell handle nested quoting differently from bash. SQL containing
   single quotes (e.g. `COMPUTE_FAMILY = 'STANDARD_M'`) inside an outer
   `-q "..."` argument often gets mangled, or whitespace causes the
   argument to split into multiple tokens. Write the SQL to a temp file
   and pass `-f`. This also makes the command auditable: the file persists
   the exact text that was sent.

PowerShell example for a hand-run `CREATE POSTGRES INSTANCE`:

```powershell
@"
CREATE POSTGRES INSTANCE PG_WIN_TEST
  COMPUTE_FAMILY = 'STANDARD_M'
  STORAGE_SIZE_GB = 100;
"@ | Out-File -Encoding ascii create_instance.sql

snow sql --connection my_conn -f create_instance.sql
```

Bash / Git Bash example (heredoc):

```bash
cat > create_instance.sql <<'EOF'
CREATE POSTGRES INSTANCE PG_WIN_TEST
  COMPUTE_FAMILY = 'STANDARD_M'
  STORAGE_SIZE_GB = 100;
EOF

snow sql --connection my_conn -f create_instance.sql
```

Inline `-q "..."` is fine for trivial queries (`-q "SELECT CURRENT_VERSION()"`)
in bash, but not for anything containing single quotes, multi-line text,
or shell metacharacters — especially in cmd.exe / PowerShell.

### Writing ad-hoc Python on WoA

When the agent needs to write a quick Python script to interact with Postgres on
WoA (e.g. inserting test data, running a one-off query), it should use `pg8000`
directly — not `psycopg2` (unavailable) or `psql` (may not be installed). Example:

```python
import pg8000
conn = pg8000.connect(host="...", port=5432, database="...", user="...", password="...", ssl_context=None)
cur = conn.cursor()
cur.execute("INSERT INTO test (id, name) VALUES (1, 'hello')")
conn.commit()
conn.close()
```

Or route through the skill's own `pg_common.connect()` which handles SSL and
driver dispatch automatically. `psycopg2` and `snowflake-connector-python` are
not available on WoA — any script that imports them will fail at import time.

## Prereqs (same as macOS / Linux + one Windows-specific install)

The skill assumes the same prereqs on every OS:

- **Cortex Code CLI** — installed per the
  [official Snowflake docs](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-cli).
  On Windows that's `irm https://ai.snowflake.com/static/cc-scripts/install.ps1 | iex`.
- **Snowflake CLI (`snow`)** — **required**, not just recommended. On WoA the
  `snowflake-connector-python` wheel is unavailable, so the skill falls back
  to `snow sql` for Snowflake-side operations. On
  mac/linux/x64-Windows it's still required for saved-connection setup
  (`pg_connect --create` writes to `~/.snowflake/connections.toml`). Install
  per the official docs — `winget install Snowflake.SnowflakeCLI` on Windows,
  `brew install snowflake-cli` on macOS, `pip install snowflake-cli` anywhere.
  Cortex Code shares the same `~/.snowflake/connections.toml`.
- **Python 3.11+ and uv** — required to run the skill's scripts on every
  platform (the skill invokes `uv run --project <SKILL_DIR> python ...`
  everywhere). Same prereq as on macOS / Linux. If you don't have them,
  install whichever way works for your environment (e.g.
  `winget install Python.Python.3.12` + `winget install astral-sh.uv`).

The one install step that genuinely differs on Windows is **the PostgreSQL
client tooling** (`psql`, `pg_dump`, `pg_dumpall`, `pg_restore`). macOS users
typically have these via Homebrew already; Windows users usually don't:

```powershell
winget install PostgreSQL.PostgreSQL
```

Verify the bin directory is on PATH with `where.exe psql` after install.

## Shell support

Per the Cortex Code CLI docs, supported shells are **`bash`, `zsh`, and
`fish`**. PowerShell and `cmd.exe` are not on that list. On native Windows
the typical paths are:

- **Git Bash** (bundled with Git for Windows) — `bash`, works directly.
- **WSL** — full Linux shell.
- **PowerShell / cmd.exe** — Cortex Code itself runs there since it's a
  native binary, but skill scripts that pipe to `bash` (e.g. anything the
  agent suggests with a `| bash` or backticks) won't work the same way.
  Most `snowflake-postgres/` scripts are pure Python invoked via
  `uv run python`, which is shell-neutral, so this usually doesn't bite —
  but worth knowing if you hit a snippet that assumes bash semantics.

## What this doc does not cover

- Full Cortex Code or Snowflake CLI install — see the official Snowflake
  docs linked above.
