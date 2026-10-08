---
name: snowflake-streamlit
description: Guardrails for Streamlit in Snowflake apps in Sanofi repos - explicit runtime choice, owner-rights least privilege, parameterized read-only queries, viewer-safe caching, source-version and snow CLI deployment, contract tests. Use when building, reviewing, deploying, or troubleshooting such apps. Not for Community Cloud or general how-to (developing-with-streamlit-in-snowflake).
---

# Streamlit in Snowflake

Work from the repo's existing runtime and deployment contract. Complements the generic developing-with-streamlit-in-snowflake skill; generic review and security stay with `/review` and `/security`.

## Core Rules

- **NEVER silently migrate** between warehouse and container runtimes. With the 2026_06 behavior bundle (enabled by default since Sept 2026), `CREATE STREAMLIT` without `RUNTIME_NAME` creates a container-runtime app, so every statement and `snowflake.yml` entity MUST name its runtime explicitly.
- **NEVER replace legacy deployment syntax**, broaden an owner role, or publish an app unless the user asks.
- **NEVER execute deployment SQL**, upload staged files, change grants, or promote a live version without an explicit deployment request.
- **Inspect first.** Locate entrypoint, supporting modules, `environment.yml` or Python dependency file, stage and deployment SQL, query warehouse, owner and viewer roles, CI workflow, app tests.
- **Check the pinned Streamlit version** before using an API. Prefer repo-native patterns while they remain valid.
- Runtime selection, deployment mechanics, security constraints, current Snowflake links: [runtime-and-deployment.md](references/runtime-and-deployment.md).

## Application Structure

- Rendering and widget state stay in the entrypoint.
- Query builders, normalization, security decisions, graph/metric construction go in Streamlit-free modules when practical.
- Warehouse runtime: use the active Snowpark session when deployed. Container runtime: `st.connection("snowflake").session()` only; `get_active_session()` and `_snowflake` are unavailable.
- Local connection path only when local development is part of the repo contract; keep it explicit.
- Queries MUST be fixed or parameterized; validate identifiers.
- NEVER turn widget input into arbitrary SQL, role names, stages, or object names.
- Read-only unless writes are an explicit requirement with authorization, idempotency, auditability, tests.
- Cache only data safe for the runtime's viewer and session semantics. Container-runtime caches are shared across all viewers unless `scope="session"`. NEVER cache secrets or authorization decisions across users.

## Security

- Apps on both runtimes execute with owner rights by default; restricted caller's rights (Preview) exist on container runtimes only.
- Use a dedicated least-privilege owner role; reason about viewer context separately.
- NEVER fix an access error by granting a broad developer or admin role to the app owner.
- `CURRENT_ROLE()` is the owner role under owner-rights execution. Verify documented requirements before viewer-dependent context or row-access policies.
- Secrets MUST stay out of staged plaintext files, source, logs, widget defaults. Use runtime-appropriate Snowflake secrets and external-access controls. A secret needs an external access integration (EAI) attached with it. A staged `.streamlit/secrets.toml` overrides Snowflake secrets on container runtimes.
- Respect Content Security Policy; external scripts, iframes, fonts, custom components may not load.

## Deployment

- Stage the entrypoint, dependency file, and every imported local module.
- New work: source-version deployment with `CREATE STREAMLIT ... FROM '<stage path>'`, then `ALTER STREAMLIT ... ADD LIVE VERSION FROM LAST`.
- Source location is a quoted string literal.
- Keep `ROOT_LOCATION` only where the repo deliberately uses that legacy contract.
- CLI deployment: `snow streamlit deploy <entity_id> --replace` from a `definition_version: 2` `snowflake.yml`. Set `runtime_name` there too, require CLI 3.27.0+, and add `--prune` when staged files were removed.
- Changing `runtime_name` in an existing project file moves the deployed app on the next deploy (CLI 3.27.0+).

| Bad | Good |
|---|---|
| `FROM @DB.SCH.STAGE/app` (unquoted) | `FROM '@DB.SCH.STAGE/app'` |
| `CREATE STREAMLIT` and assume live | Follow with `ADD LIVE VERSION FROM LAST` |
| `CREATE STREAMLIT ... FROM '...'` with no `RUNTIME_NAME` | Add `RUNTIME_NAME = 'SYSTEM$WAREHOUSE_RUNTIME'` (or the container name plus `COMPUTE_POOL`) |

## Checklist

- Pure-module unit tests and Streamlit `AppTest` run where the pinned version supports it.
- Python sources compile; repo linter passes.
- Deployment SQL names every imported supporting file and pins supported dependencies.
- Entrypoint name matches `MAIN_FILE`; runtime named explicitly and matching the dependency file (`environment.yml` vs `pyproject.toml`/`requirements.txt`); target role least privilege; target environment correct.
- Native Snowflake smoke test done when owner rights, warehouse packages, staged files, viewer grants, CSP, or networking affect behavior.
- No secrets in staged files; no widget-driven SQL or identifiers.
