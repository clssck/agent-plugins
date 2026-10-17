# Auth Doors

Cards for the auth-door step in `api-recon`. Three independent gates decide whether a stubbed SPA renders its post-login shell; **find each one in the bundles before writing any stub.**

## The Three Doors

|Door|Question|Typical evidence|
|---|---|---|
|Render gate|How does the app decide the user is logged in?|`isLogin`, `getToken`, cookie/localStorage reads at startup|
|Interceptor gate|What redirects to `/login`?|axios/interceptor failure branch on `response_code`/`errno`, 401 handler|
|Content gate|Where do menus and permissions come from?|`menu`, `permission`, `role`, `acl`, `routes` bootstrap calls|

**Naming trap: a localStorage key name (e.g. `token`) is NOT proof of the mechanism.** Confirm by following the code path — where the value is SET at login and READ at startup.

## Fake-Response Layers

|Layer|Scope|Purpose|
|---|---|---|
|L1 exact|auth/permission/bootstrap endpoints|pass the first screen gate|
|L2 corrective|every JSON response|flip failure codes to the success shape|
|L3 fallback|any other `/api` call|empty success body so the UI keeps mounting|

**Shapes matter more than values:** keep the envelope (`code`/`data`/`msg` or `errno`), keep types, keep lists empty. Empty tables and placeholder UI are correct outcomes — NEVER "fix" them by logging in for real.

## OMP Browser

Read the actual OMP browser tool description first. These names describe the reviewed host contract; use the live schema and backend's reported support when they differ.

- **Tab ownership:** create a named assessment tab. Relay/CDP and adopted Tern targets operate on real user pages; discover and select the intended target before attaching, and never navigate a visible personal tab implicitly.
- **Document start:** `browser.open({ name, url, init_scripts, allowed_domains })` installs early hooks and a host fence. Configure approved hosts before navigation. A fence is a control, not permission to add another host.
- **Interception before interaction:** install `tab.route` handlers and verify a harmless mocked request before clicking. Cover all outbound mutations and local side effects of the chosen action; an unmatched request must not silently reach a real backend. Mocks isolate client behavior, not server access.
- **Capture:** `tab.harStart()` / `tab.harStop({ path })` and `tab.requests()` record supported traffic. Response bodies require `content: "text"` where supported. HAR may contain cookies, credentials, and personal data: avoid collecting them where possible and sanitize before persisting or handing off an export. If the backend cannot provide a safe capture, report that evidence gap rather than claiming a sanitized artifact exists.
- **Execution context:** `tab.evaluate` runs in the page; `tab.run` executes in OMP's host-side tab runtime with broad tool access. Never execute untrusted page text as host code. Re-observe after navigation or re-render before using element IDs.
- **Route coverage:** `tab.pushState` covers SPA route transitions without a document load. Verify the injected marker and final URL; a mounted shell proves only that the mock satisfied the client gates.
- **Backend limits:** Tern recording/interception covers fetch/XHR plus navigation responses, not all subresources or WebSockets; request bodies are document-local. Choose a supported Chromium/CDP backend when the required capture needs more, or record the limitation. Never retry a method the backend explicitly rejects.
- **Release:** stop recording, remove owned route/init hooks, and close the owned tab. Closing an adopted tab releases it; never kill a reused browser process or clear the operator's cookies/storage.

## Troubleshooting

|Symptom|Meaning|Fix|
|---|---|---|
|Shell renders, sidebar empty|content-gate stub shape incomplete|align envelope and permission codes with a captured response|
|Every route fires the same few bootstrap calls|permission checks failing|Rebuild the permission tree, patch stubs, rerun affected runtime routes|
|Requested business path lands on `/login`|render or interceptor gate still failing|re-check L1 stubs against the interceptor's failure branch|
|`routes.txt` far smaller than the bundle's route table|route list came from a partial manifest|re-extract from all chunks; check lazy-load manifest coverage|

Reruns are expected: update `config.json`, re-inject, rerun. A stub is wrong until the shell renders on every module path.
