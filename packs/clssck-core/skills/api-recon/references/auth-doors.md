# Auth Doors

Detail for api-recon Phase 2. Three independent gates decide whether a stubbed SPA renders its post-login shell. Find each one in the bundles before writing any stub.

## The Three Doors

|Door|Question|Typical evidence|
|---|---|---|
|Render gate|How does the app decide the user is logged in?|`isLogin`, `getToken`, cookie/localStorage reads at startup|
|Interceptor gate|What redirects to /login?|axios/interceptor failure branch on `response_code`/`errno`, 401 handler|
|Content gate|Where do menus and permissions come from?|`menu`, `permission`, `role`, `acl`, `routes` bootstrap calls|

Naming trap: a localStorage key name (e.g. `token`) is NOT proof of the mechanism. Confirm by following the code path — where the value is SET at login and READ at startup.

## Fake-Response Layers

|Layer|Scope|Purpose|
|---|---|---|
|L1 exact|auth/permission/bootstrap endpoints|pass the first screen gate|
|L2 corrective|every JSON response|flip failure codes to the success shape|
|L3 fallback|any other `/api` call|empty success body so the UI keeps mounting|

Shapes matter more than values: keep the envelope (`code`/`data`/`msg` or `errno`), keep types, keep lists empty. Empty tables and placeholder UI are correct outcomes — NEVER "fix" them by logging in for real.

## omp Mapping

- Document-start injection: `browser.open({ init_scripts: [...], allowed_domains: ["app.example.com"] })` — the hook runs before page scripts; the domain fence keeps the session in scope.
- Response mocking: `tab.route(pattern, …)` for per-request fakes; record with `tab.harStart()` / `tab.harStop(path)` and read `tab.requests`.
- Page-world helpers: `tab.run(fn, {args})` executes with full page access for one-off probes.
- Verification: the injected marker exists on `window`; navigate to a business path — the URL MUST NOT end at `/login`.
- SPA routing: `tab.pushState(url)` walks routes without a document load; hash routes change only the fragment.

## Troubleshooting

|Symptom|Meaning|Fix|
|---|---|---|
|Shell renders, sidebar empty|content-gate stub shape incomplete|align envelope and permission codes with a captured response|
|Every route fires the same few bootstrap calls|permission checks failing|Phase 4: rebuild the permission tree, patch stubs, rerun Phase 3|
|Requested business path lands on /login|render or interceptor gate still failing|re-check L1 stubs against the interceptor's failure branch|
|`routes.txt` far smaller than the bundle's route table|route list came from a partial manifest|re-extract from all chunks; check lazy-load manifest coverage|

Reruns are expected: update `config.json`, re-inject, rerun. A stub is wrong until the shell renders on every module path.
