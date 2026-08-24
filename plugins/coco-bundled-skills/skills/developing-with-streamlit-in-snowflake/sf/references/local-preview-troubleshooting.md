
# Local preview troubleshooting (`streamlit run`)

Use this guide when a Snowflake-wired Streamlit app behaves wrongly **on a laptop** (`streamlit run` or `python3 -m streamlit run`). The underlying cause is almost always **connection resolution** — `st.connection("snowflake")` runs through the **snowflake-python-connector**, not the snow CLI, and the two have different defaults. This produces a small set of recurring failure modes that are easy to misdiagnose as "permission errors" or "Snowflake bugs".

For deploy / CI / hosted runtime, see [snowflake-deployment.md](snowflake-deployment.md) and [streamlit-in-snowflake-runtime.md](streamlit-in-snowflake-runtime.md).

## Required env-var form for local launch

```bash
SNOWFLAKE_DEFAULT_CONNECTION_NAME=<entry-from-connections.toml> \
  python3 -m streamlit run /abs/path/streamlit_app.py \
    --server.port 8501 --server.headless true
```

Notes:

- Use **`SNOWFLAKE_DEFAULT_CONNECTION_NAME`**, not `SNOWFLAKE_CONNECTION_NAME`. The latter is the **snow CLI** variable; the python-connector that backs `st.connection` reads the former.
- Use `python3 -m streamlit` (or `uv run streamlit`) rather than bare `streamlit run` — the binary is often not on `PATH`.
- Streamlit auto-increments the port if 8501 is in use. Detect the actual listening port from the dev-server output; do not hardcode 8501. Example:

  ```bash
  lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | grep -i python | awk '{print $2, $9}' | grep ':85'
  ```

- After confirming the server is up, sanity-check it actually serves Streamlit:

  ```bash
  curl -fsS http://localhost:<port>/ | grep -c "<title>Streamlit</title>"
  ```

> **Restart on connection changes.** `st.connection` is cached by name. If you change env vars or `st.connection(...)` kwargs, **kill and relaunch** the dev server (`kill $(lsof -ti:<port>)`) — hot reload alone will reuse the stale connection.

## Diagnostic stub (drop in on first run)

The single most useful debugging tool is to confirm *which* session you are actually on. Add this BEFORE any `USE …` or table read; remove once the wiring is verified:

```python
ctx = session.sql(
    "SELECT CURRENT_ROLE(), CURRENT_USER(), CURRENT_WAREHOUSE(), CURRENT_DATABASE()"
).collect()
st.info(f"role={ctx[0][0]}, user={ctx[0][1]}, wh={ctx[0][2]}, db={ctx[0][3]}")
```

If `role` / `user` / `wh` are not what you expect, you have a connection-resolution bug — fix the env var or the `connections.toml` entry. Do **not** keep adding `USE ROLE`, `USE DATABASE`, etc. statements to paper over it; those mask the real failure (and break entirely on PAT-backed connections, see below).

## Symptom → cause table

| Error you see | Real cause | Fix |
| --- | --- | --- |
| `Database 'X' does not exist or not authorized.` (and `CURRENT_USER()` shows an unexpected user/role) | The connector picked the wrong entry from `~/.snowflake/connections.toml` because no default was set. `default_connection_name` in `connections.toml` is **not always** honored by the python-connector default-resolution. | Launch with `SNOWFLAKE_DEFAULT_CONNECTION_NAME=<entry>` (snippet above). Do NOT use `SNOWFLAKE_CONNECTION_NAME` — that's the snow-CLI variable. |
| `Object does not exist, or operation cannot be performed.` on `session.sql("USE ROLE …")` | The connection is backed by a **PAT (programmatic access token)**, which is scoped to a single role. PATs cannot `USE ROLE` to switch. | Pick a connection whose role already has access to your data; do not rely on `USE ROLE` inside the app. If you need a different role, issue a new PAT bound to it. |
| `command not found: streamlit` | `streamlit` is not on `PATH` (common on system Python). | `python3 -m streamlit run …` or `uv run streamlit run …`. |
| App keeps reporting the *previous* `CURRENT_ROLE()` / `CURRENT_USER()` after a code or env-var change | Streamlit caches `st.connection` by name. Editing kwargs / changing env vars without restarting reuses the stale connection. | Kill and relaunch: `kill $(lsof -ti:<port>)` then re-run with the right env vars. |
| `streamlit.connections.snowflake_connection.SnowflakeConnection() got multiple values for keyword argument 'connection_name'` | The first positional arg to `st.connection(...)` is *already* passed as `connection_name`; passing it again as a kwarg duplicates it. | Pick one — either positional (`st.connection("snowhouse", type="snowflake")`) or kwarg, but not both. (Note: the positional arg is *not* a guaranteed lookup key into `connections.toml`; rely on `SNOWFLAKE_DEFAULT_CONNECTION_NAME`.) |
| Wrong login page / redirect to unexpected account | The `account` value in `secrets.toml` is just the org name (e.g. `MYORG`) instead of the full locator (e.g. `MYORG-MYACCT`). | Run `snow connection list` and copy the exact `account` and `host` values into `secrets.toml`. If the connection config has a `host` field, always include it. |

## Why `USE ROLE` / `USE DATABASE` doesn't fix this

The temptation when the diagnostic stub shows the wrong role is to add `session.sql("USE ROLE my_role").collect()` at the top of the app. Two problems:

1. **It hides the connection-resolution bug.** The next time `st.connection` resolves (different env, different machine, restart), you're back to the wrong session and the `USE` statement will fail or land you somewhere unexpected.
2. **PAT-backed connections fail outright.** A programmatic access token is bound to one role; `USE ROLE` returns `Object does not exist, or operation cannot be performed.` and the app dies.

Fix the connection at the source (env var + `connections.toml` entry), not the session.
