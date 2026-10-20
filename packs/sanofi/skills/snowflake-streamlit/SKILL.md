---
name: snowflake-streamlit
description: "Build, review, deploy, and troubleshoot Streamlit in Snowflake (SiS) apps in Sanofi repos. Use when working with CREATE/ALTER STREAMLIT, warehouse vs container runtime, RUNTIME_NAME, BCR-2342, snowflake.yml and `snow streamlit deploy`, owner-rights roles, secrets/EAI, uv/environment.yml dependencies, or AppTest and deployment contract tests. Not for local or Community Cloud Streamlit; generic review/security → `/review`, `/security`."
---

# Streamlit in Snowflake

Guardrails for Streamlit in Snowflake apps in Sanofi repos: explicit runtime choice, owner-rights least privilege, parameterized read-only queries, viewer-safe caching, source-version and `snow` CLI deployment, contract tests. Work from the repo's existing runtime and deployment contract; never from Snowflake's current default.

Governing hazard: with the 2026_06 behavior bundle (enabled by default since Sept 2026), `CREATE STREAMLIT` without `RUNTIME_NAME` creates a container-runtime app. An unnamed runtime ⇒ silent migration or failed deploy. Local and Community Cloud Streamlit are out of scope. Runtime matrix, deployment mechanics, security constraints, current Snowflake links → [runtime-and-deployment.md](skill://snowflake-streamlit/references/runtime-and-deployment.md).

## Stop rules

- **NEVER silently migrate** between warehouse and container runtimes. Every statement and `snowflake.yml` entity MUST name its runtime explicitly.
- **NEVER act on deployment without explicit request:** execute deployment SQL, upload staged files, change grants, promote a live version.
- **NEVER unasked:** replace legacy deployment syntax, broaden an owner role, publish an app.

## Inspect first

`read`, `grep`, `glob` → locate entrypoint, supporting modules, `environment.yml` or Python dependency file, stage and deployment SQL, query warehouse, owner and viewer roles, CI workflow, app tests. Check the pinned Streamlit version before using an API; prefer repo-native patterns while still valid.

## Application structure

- **Entrypoint:** rendering + widget state.
- **Streamlit-free modules** (when practical): query builders, normalization, security decisions, graph/metric construction.
- **Session:** warehouse runtime → active Snowpark session when deployed. Container runtime → `st.connection("snowflake").session()` only; `get_active_session()`, `_snowflake` unavailable.
- **Local connection path:** only when local development is part of the repo contract; explicit.
- **Queries MUST be fixed or parameterized;** validate identifiers. NEVER turn widget input into arbitrary SQL, role names, stages, object names.
- **Read-only** unless writes are an explicit requirement with authorization, idempotency, auditability, tests.
- **Caching:** only data safe for the runtime's viewer and session semantics. Container-runtime caches shared across all viewers unless `scope="session"`. NEVER cache secrets or authorization decisions across users.

## Security

- **Owner rights by default** on both runtimes; restricted caller's rights (Preview) container-only.
- **Dedicated least-privilege owner role;** reason about viewer context separately. NEVER fix an access error by granting a broad developer or admin role to the app owner.
- **`CURRENT_ROLE()`** = owner role under owner-rights execution. Verify documented requirements before viewer-dependent context or row-access policies.
- **Secrets** MUST stay out of staged plaintext files, source, logs, widget defaults. Use runtime-appropriate Snowflake secrets + external-access controls; a secret needs an external access integration (EAI) attached with it. Container runtime: staged `.streamlit/secrets.toml` overrides Snowflake secrets.
- **Content Security Policy:** external scripts, iframes, fonts, custom components may not load.

## Deployment

- **Stage** entrypoint, dependency file, every imported local module.
- **New work:** source-version deployment — `CREATE STREAMLIT ... FROM '<stage path>'`, then `ALTER STREAMLIT ... ADD LIVE VERSION FROM LAST`. Source location: quoted string literal.
- **`ROOT_LOCATION`:** keep only where the repo deliberately uses that legacy contract.
- **CLI:** `snow streamlit deploy <entity_id> --replace` from a `definition_version: 2` `snowflake.yml`; set `runtime_name` there too; require CLI 3.27.0+; add `--prune` when staged files were removed.
- **Changing `runtime_name`** in an existing project file moves the deployed app on next deploy (CLI 3.27.0+).
- **Install CLI:** `uv tool install snowflake-cli`; NEVER `pip install` into a system or Homebrew Python.

| Bad | Good |
|---|---|
| New `FROM @DB.SCH.STAGE/app` (unquoted) | `FROM '@DB.SCH.STAGE/app'` |
| `CREATE STREAMLIT` and assume live | Follow with `ADD LIVE VERSION FROM LAST` |
| `CREATE STREAMLIT ... FROM '...'` with no `RUNTIME_NAME` | Add `RUNTIME_NAME = 'SYSTEM$WAREHOUSE_RUNTIME'` (or the container name plus `COMPUTE_POOL`) |

```sql
create or replace streamlit DATABASE.SCHEMA.APP_NAME
  from '@DATABASE.SCHEMA.APP_STAGE/app_name'
  main_file = 'APP.py'
  query_warehouse = APP_WH
  runtime_name = 'SYSTEM$WAREHOUSE_RUNTIME';
alter streamlit DATABASE.SCHEMA.APP_NAME add live version from last;
```

## Python dependencies

| Runtime | Rule |
|---|---|
| Container | Snowflake installs with uv from `pyproject.toml` (preferred) or `requirements.txt`. New apps: `uv init --bare`, `uv add "streamlit[snowflake]==<pinned>"`, commit `uv.lock`, stage it with the app. |
| Container | NEVER leave `requirements.txt` beside `pyproject.toml` — takes precedence, bypasses `uv.lock`. |
| Container | Packages need an attached artifact repository (or EAI fallback); owner role without one cannot install them. |
| Warehouse | `environment.yml` from Snowflake Anaconda channel only. uv cannot install it; NEVER convert to `pyproject.toml` unless migrating runtimes. |
| Local dev | Repo already on `requirements.txt` → MAY `uv venv` + `uv pip install -r requirements.txt`; NEVER migrate its tooling unasked. |

## Verification

- **Tests:** pure-module unit tests + Streamlit `AppTest` where the pinned version supports it. Python sources compile; repo linter passes.
- **Deployment SQL:** names every imported supporting file; pins supported dependencies.
- **Container apps:** `uv.lock` committed and staged with `pyproject.toml`; no shadowing `requirements.txt`; package source attached.
- **Contract:** entrypoint name = `MAIN_FILE`; runtime named explicitly and matching dependency file (`environment.yml` vs `pyproject.toml`/`requirements.txt`); target role least privilege; target environment correct.
- **Native smoke test** when owner rights, warehouse packages, staged files, viewer grants, CSP, or networking affect behavior. With the user's go-ahead, run `snow streamlit get-url <DB.SCHEMA.APP>` for the deployed `identifier` using the same Snowflake CLI connection as deployment; the project entity key is not the deployed object name. Open the URL with `browser.open({ name, url, app: { relay: true } })` (omp's own tab in the user's signed-in Chrome). Find the app iframe with `tab.frames()`, then `tab.frame(<that frame's name or url>).count('[data-testid="stException"]')` MUST be 0; inspect `tab.errors()` for failed/CSP-blocked requests, `tab.console()` for application console output, and capture `tab.screenshot()`. No relay → give the user the URL and these checks.
- **No secrets** in staged files; no widget-driven SQL or identifiers.
