
# Streamlit in Snowflake — runtime vs local

Use this guide when the app **runs inside Snowflake** (Streamlit in Snowflake on a warehouse, Snowflake Workspace / container runtime, or similar hosted SiS), or when you are writing code that must work both **locally** and **in Snowflake**. Vanilla `streamlit run` on a laptop assumes a normal filesystem, open PyPI/network access, and `.streamlit/secrets.toml` for credentials—those assumptions often **do not** hold in Snowflake. If you are unsure if an app is standalone or will run in Snowflake, ask the user.

For SQL/session patterns, see [snowflake-connection.md](../../developing-with-streamlit/references/snowflake-connection.md). For `snow` CLI, `snowflake.yml`, and local pre-deploy checks, see [snowflake-deployment.md](snowflake-deployment.md).

---

## Secrets and credentials

### Inside Snowflake (hosted app)

- **Primary Snowflake access:** Use **`st.connection("snowflake")`** (and optionally **`type="snowflake-callers-rights"`** when viewers should execute with their own roles). The platform provides Snowflake session context; you usually **do not** commit or deploy `.streamlit/secrets.toml` **for the Snowflake connection** the way you do on a laptop.
- **Snowflake Workspace / container flows** may document a connection TTL (for example via environment variables). Follow the product or skill guidance for your environment when setting `ttl=` on `st.connection`.
- **Other secrets** (third-party API keys, tokens): Never hard-code. Use the secret or credential mechanisms your Snowflake account and Streamlit product surface support (for example app-level configuration where available). These are **not** interchangeable with “drop a `secrets.toml` in git.”

### Local development of the same app

- Keep **`.streamlit/secrets.toml`** on your machine (and **`.gitignore`** it) so `st.connection("snowflake")` resolves `[connections.snowflake]` while you run `streamlit run` or tests. Derive `account` / `host` from `snow connection list` as in [snowflake-connection.md](../../developing-with-streamlit/references/snowflake-connection.md).

**Summary:** `st.secrets` / `secrets.toml` patterns in this repo mostly describe **local** wiring. In Snowflake, treat the Snowflake connection as **embedded**, and treat non-Snowflake secrets as **platform-managed**.

---

## External access, PyPI, and dependencies

- **Outbound calls** (PyPI, public HTTPS APIs, vendor LLM endpoints) require **external access integrations (EAIs)** and matching **network rules** in Snowflake. Names are **account-specific**; verify with `SHOW EXTERNAL ACCESS INTEGRATIONS` (or your admin) instead of hard-coding a global integration name.
- **Adding packages** (including third-party Streamlit components from PyPI) follows the same rules as any dependency: the runtime must be allowed to reach the index or wheel source. Some Workspace setups use a **fixed pre-installed** dependency set unless `pyproject.toml` is changed **and** PyPI access is configured—changing dependencies without EAI can fail at runtime.
- Do not assume `uv pip install` or unrestricted internet from inside the hosted app; align with [snowflake-deployment.md](snowflake-deployment.md) and your org’s networking policy.

**Docs:** [Streamlit in Snowflake — dependency management](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/dependency-management), [External network access overview](https://docs.snowflake.com/en/developer-guide/external-network-access/external-network-access-overview).

---

## Files, artifacts, and uploads

### Only deployed files exist at runtime

- Any path you open (`open(...)`, `pd.read_csv("data.csv")`, `torch.load("model.pt")`, images, fonts, CCv2 assets, etc.) must refer to files that are actually **shipped with the app**. In Snowflake, that means listing them under **`artifacts`** in `snowflake.yml` (or the equivalent for your deployment path). Laptop-only paths will raise **file not found** in production.

### Durable data belongs in Snowflake

- Prefer **tables, stages, and Snowflake APIs** for durable or large data instead of writing to arbitrary host paths for persistence.

### Upload widgets (`st.file_uploader`, chat file attachments)

- Uploads are handled **in the app process** for the session. Very large files can hit **memory or request limits** in hosted runtimes. Prefer size limits, chunking, or uploading to a **Snowflake stage** / table for large binaries.

### Static assets and `enableStaticServing`

- Theme and static file guidance still applies: files must be **in the deployed bundle** to be served. Local-only static directories are not visible after deploy unless included in artifacts.

---

## Quick checklist (Snowflake-hosted)

1. Snowflake connection via **`st.connection("snowflake")`** — no laptop-only `secrets.toml` requirement for embedded identity.
2. **Artifacts** list every runtime file (Python, config, data, static assets).
3. **Outbound network / PyPI** — EAIs and app settings match what `pyproject.toml` and APIs need.
4. **Secrets** — no credentials in source; use supported Snowflake / app secret patterns for non-Snowflake keys.
