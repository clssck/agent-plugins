---
name: api-recon
description: Use for authorized discovery of a web app's API surface — static bundle harvesting, runtime enumeration, auth-gate modeling, and parameter reverse-engineering; not for exploitation, fuzzing, or credential attacks.
---

# API Recon

Collect the complete outbound API surface of an authorized web app: backend paths, methods, parameters, response shapes, front-end routes, and the UI actions that trigger them. Methodology adapted from ARTEX's api-recon skill (Hinln/ARTEX, AGPL-3.0); rewritten for omp tools. Recon only — exploitation belongs elsewhere.

## Boundaries

|Area|Allowed|Forbidden|
|---|---|---|
|Target|enumerate paths, methods, params, routes, UI triggers|injection, fuzzing, IDOR/BOLA, any exploit verification|
|Auth|stub or mock client-side gates to reach post-login shells|guessing or brute-forcing credentials; submitting real login forms|
|Runtime|hook interfaces, fake responses, record outbound requests|destructive UI actions, bulk writes, exports of real data|
|Data|empty or mock responses are expected|demanding real data; treating blank pages as blockers|

- Success is measured by what the front end STILL SENDS, not what the backend returns. Mocked bodies are the mechanism, not a compromise.
- Target outside the authorized scope, or scope ambiguous → stop and ask. NEVER proceed on assumption.

## Layers And Modes

|Layer|Output|Limits|
|---|---|---|
|Static (bundles)|full endpoint paths, route drafts, param candidates|no methods; misses runtime-built URLs|
|Runtime (live session)|methods, bodies, responses, WS/SSE, dynamic URLs|pages must render; one sample cannot prove required vs optional|

Modes: `depth` (enumerate known routes and record traffic), `coverage` (drive UI states), `both` (depth then coverage).

## Workflow

Phase 0 — Classify SPA vs MPA; create the task output directory `recon/`. All intermediates go there; the skill directory is read-only.

Phase 1 — Static harvest [GATE]. First productive action: download the entry HTML, enumerate script and chunk URLs (manifest for webpack/Vite), fetch every chunk, extract endpoints and routes. NEVER hand-pick paths out of an unparsed bundle, and NEVER read a bundle larger than ~100KB into context — batch with a throwaway script in `recon/` and bounded `grep` tool calls; verify with `wc -l` counts. Lazy-load discovery works the same for webpack, Vite, and Angular.

Phase 1b — Parameter reverse-engineering. For each important endpoint answer: field names, transport, type, required?, sample value, confidence. Anchors + UI binding chains + multi-sample diffs; recipes in [references/parameter-recon.md](references/parameter-recon.md).

Phase 2 — Auth doors [GATE]. Find the three gates — render gate (how login is judged), interceptor gate (what redirects to /login), content gate (where menus and permissions come from) — and record keys and shapes in `recon/config.json`. NEVER treat a localStorage key name as proof; confirm the code path. Details and stub layers: [references/auth-doors.md](references/auth-doors.md).

Phase 3 — Runtime enumeration [GATE]. Render past login with stubbed gates, then enumerate. omp mapping: `browser.open({init_scripts})` for document-start hooks, `tab.route` for fake responses, `tab.observe`/`tab.id(...)` for clicks, `tab.pushState` for SPA routes, `tab.harStart`/`tab.harStop` plus `tab.requests` for recording. Coverage order: nav/sidebar → tabs → table rows → toolbars (skip irreversible actions) → `pushState` for uncovered routes. Verify: injected marker present; a business path does not land on /login.

Phase 3b — Parameter trigger matrix. Per module, record each action class once — list, search, advanced filter, create/edit, bulk/export/sort — and diff the samples. Outbound bodies under mocks are still real; the request is the truth.

Phase 4 — Permission tree restore, only if module pages render blank or every route shows the same bootstrap calls: extract permission/menu endpoints, rebuild the flat-codes-plus-tree mapping, patch stubs, rerun Phase 3.

Phase 5 — Merge and report. Merge parameters with confidence tiers; emit `api_merged` and `site_map.json`; run error-based reverse checks (in-scope incomplete requests may be sent to read 400 validation text — that is parameter recon, not exploitation). Every discovered service and endpoint MUST be written to the asset library — none dropped.

## Rules

- Big files stay out of context: scripts and bounded searches only.
- Two-strike rule: after two failures of one technique, switch approach or consult [references/parameter-recon.md](references/parameter-recon.md).
- One sample NEVER decides required vs optional; use multi-sample diffs or validation/error evidence.
- Static is the safety net when runtime is blocked; label blind spots (JSVMP, WASM, HMAC/mTLS, gRPC-web) as limitations instead of guessing.
- Recon records requests; before any state-changing click, re-read the Boundaries table.

## Deliverables

|File|Phase|Content|
|---|---|---|
|`recon/js/`, `api_static.txt`, `routes.txt`|1|chunks, static endpoints, routes|
|`param_candidates.json`|1b|static candidates with confidence|
|`config.json`|2|three doors, runtime config|
|`runtime_api.json`, HAR|3|runtime recording incl. WS/SSE|
|`param_samples.json`, `scan_raw.json`|3b|samples, click log|
|`params_merged.json`, `api_merged.txt`, `site_map.json`|5|merged output + limitations|
|asset library|5|all services and endpoints inserted|

## Checklist

- Authorization and scope confirmed before any request; boundaries respected.
- Static harvest completed with counted verification; no giant bundle read into context.
- Three doors recorded in `config.json` with code-path evidence.
- Post-login shell reached; business paths do not redirect to login.
- Trigger matrix covers each module's action classes; samples diffed.
- Params merged with confidence tiers; error-based reverse checks recorded.
- `site_map.json` written with runtime mode, counts, and limitations.
- Every discovered asset inserted; none omitted.
