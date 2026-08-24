# Build status (best-effort)

The context-builder API has **no explicit build-state field** (running / done / failed) today. `check build` therefore *infers* status from the signals that do exist: the context's `last_processed_at`, the manifest's `updated_at`, and a context-scoped lookup probe. This is a best-effort read — say so plainly, and never imply a precise progress percentage.

> Field names are confirmed against a live call: `get-context` returns a single context object with `last_processed_at` and `id`. Note that `TRY_PARSE_JSON` yields the numeric `id` / `account_id` in scientific-notation float form (e.g. `4.414318E7`, `172434.0`) — cast/normalize before comparing or displaying.

## Inputs

1. **`get-context`** for the domain — read `last_processed_at` (and the context `id`):

   ```bash
   uv run --project <SKILL_DIR>/.. snow sql --format json -q "
     SELECT SYSTEM\$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER(
       '{\"action\":\"get-context\",\"parameters\":{\"name\":\"<domain>\",\"database_name\":\"<DB>\",\"schema_name\":\"<SCHEMA>\"}}'
     ) AS result;
   "
   ```

   `<domain>`, `<DB>`, `<SCHEMA>` are the same values used elsewhere (see `STORAGE.md`). `get-context` returns a single context object (not a list).

2. **Manifest `updated_at`** — load `scope.yaml` via `get-stage-file` (per `STORAGE.md` "Loading — one call") and read the top-level `updated_at` (the save time).

3. **Context-scoped lookup probe** — run one context lookup (per `CONTEXT_LOOKUP.md`) using a distinctive in-scope query or an in-scope FQN drawn from the manifest, then count how many returned documents actually belong to **this** domain (their `entity_key` / `database.schema.table` fall inside this domain's scope patterns). Documents that match *other* contexts do not count — this is the exact failure mode where a lookup returns docs but none are yours.

## Inference

> **Timestamps are not the whole story.** `last_processed_at` reflects one part of the build; table/catalog and query-history context are produced by a separate path that can lag behind it. So `last_processed_at > updated_at` does **not** guarantee those sources are queryable yet — the **lookup probe** (input 3) is the only reliable readiness signal for them. If the probe is empty right after a save, that is expected for a while; do not conclude the build failed. Never quote a specific cadence or ETA to the builder (no "every hour", no "~2 hours") — say context can take "a few hours" to show up. Timestamps also cannot tell you whether returned context is new vs. from a prior build, so do not infer freshness from them.

| Signal | Verdict | Line to render |
|---|---|---|
| `last_processed_at` is null / epoch, or `<= updated_at` | **building** | `Building — your latest scope is queued and hasn't been processed yet. New context applies automatically when it's ready.` |
| `last_processed_at > updated_at` **and** the probe finds N ≥ 1 results for this domain | **ready** | `Ready — processed <relative time> ago; I can see N items from your <domain> scope.` |
| `last_processed_at > updated_at` **but** the probe finds 0 results for this domain | **processed, empty** | `Processed, but I'm not seeing any context for your scope yet. Table and query-history context can take a few hours to show up after a save — check back a bit later. If it's still empty, the build role may not be able to read your schemas — re-check grants (see the access preflight) and rebuild.` |

Render `last_processed_at` as a relative time ("about 3 hours ago"). Keep the output to the single verdict line plus, for the "processed, empty" case, the pointer to `ACCESS_PREFLIGHT.md` remediation.

> **Customer-friendly wording.** Do not put internal jargon like "in-scope docs", "documents", "index", or "metadata pipeline" in the verdict line the builder sees — say "context for your scope" and, for a count, "I can see N items from your <domain> scope". The `entity_key`/scope-pattern filtering below is an agent-only mechanism; never surface it verbatim.

> **For the "processed, empty" case:** an empty probe right after a save is often just the normal lag before table/query-history context appears — not a failure. Lead with that and suggest checking back later. Only if it stays empty, consider grants: the build runs as the role that owns the context object — the role active when the context was first created, not necessarily the current session role. If the session role has changed since creation, re-check which role owns the context and ensure it has grants on all the domain's schemas.

## Guardrails

- Best-effort only — never claim a running/percentage state the API can't provide.
- Read-only: never force-reprocess, reset the epoch, or re-trigger a build from this verb — it only reports inferred status.
- If `get-context` errors or the context isn't found, say the domain isn't registered yet and route to setup.
- If the lookup probe is unavailable (both MCP and SQL paths down, per `CONTEXT_LOOKUP.md`), report status from `last_processed_at` vs `updated_at` alone and note that you couldn't confirm whether context is showing up this session.
- Do not surface raw `snow sql` output, context ids, or `last_processed_at` epoch values to the builder — translate to plain English.
