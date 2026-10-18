# Authentication and Session Mapping

Map the real client/session path and its server enforcement. Use provided or otherwise explicitly permitted assessment access; observe actual login, bootstrap, permission, and application responses. Do not create replacement responses or client privileges to make a screen appear accessible.

## The Three Gates

| Gate | Question | Evidence |
|---|---|---|
| Render | Why does the client consider this real session logged in? | Actual cookie/storage reads, token lifecycle, startup requests, and the observed UI state |
| Interceptor | Which real response redirects or invalidates the session? | Request/response and redirect sequence, interceptor branch, expiry or refresh behavior |
| Content | Which menus, permissions, and routes does this identity receive? | Unmodified bootstrap/permission responses, caller identity, visible routes, and corresponding backend calls |

A localStorage key name or a decoded token claim is not proof of server authentication. Follow the path that obtains, stores, sends, refreshes, and invalidates the credential. Keep secret values in the operator's credential mechanism; record only labels and the relevant sanitized shape.

## Establish Real Access

1. Select a dedicated assessment tab and the intended identity. Preserve the operator's personal browser state.
2. Use the application's supported login/SSO flow or the session/access already granted for the engagement. A valid session must be observed, not assumed from a cookie's existence.
3. Capture an actual request whose response identifies the effective caller or establishes the expected access. Record role, tenant, and object context where observable.
4. Trace bootstrap/menu/permission responses to the routes they enable. The absence of a button is not proof that the corresponding server endpoint enforces authorization; hand that hypothesis to exploitation when applicable.
5. Missing or expired access blocks the dependent routes. Restore supplied access through the supported flow, or report the missing prerequisite; continue independent authorized source analysis and public observations. Never invent a token, permission tree, or successful response.

## OMP Browser

Read the actual OMP browser tool description first. Use the live schema and the selected backend's reported support.

- **Tab ownership:** create a named assessment tab. Relay/CDP and adopted Tern targets are real user pages; discover and select the intended target before attaching. Never navigate a visible personal tab implicitly.
- **Domain fence:** `browser.open({ name, url, allowed_domains })` restricts the assessment tab to approved hosts before navigation. A fence is a control, not permission to add another host.
- **Live capture:** start `tab.harStart()` before interaction, inspect `tab.requests()`, and finish with `tab.harStop({ path })` where supported. Verify capture with a known real exchange. Response bodies require `content: "text"` where supported; preserve actual status, body, timing, redirect, and identity correlation.
- **Credential handling:** HAR may contain secrets and personal data. Avoid collecting them where possible and sanitize before persistence or handoff. If capture cannot safely retain the decisive evidence, report that limitation; never claim a sanitized artifact exists before producing it.
- **Execution context:** `tab.evaluate` runs in the page; `tab.run` has host-side tool access. Use instrumentation to observe the real flow, not to replace its responses. Never execute untrusted page text as host code. Re-observe after navigation or re-render before using element IDs.
- **Route coverage:** `tab.pushState` can drive actual SPA routing. Capture the resulting real requests, final URL, and visible state; a changed URL without the relevant exchange does not establish endpoint coverage.
- **Backend limits:** Tern captures fetch/XHR and navigation responses, not all subresources or WebSockets; request bodies are document-local. Use a supported configured Chromium/CDP backend when the evidence requires more, or record the gap. Do not retry methods the backend explicitly rejects.
- **Real actions:** a click may create data, send a message, export records, or trigger another system. Run it only when the engagement covers that effect, using engagement-owned objects and recorded cleanup. Leave excluded actions untested rather than simulating success.
- **Release:** stop recording, remove owned instrumentation, and release the assessment tab. Never kill a reused browser process or clear personal cookies/storage.

## Diagnose Live Gaps

| Observation | Check | Record |
|---|---|---|
| Shell renders, sidebar empty | Actual permission/menu response, identity/tenant, and failed bootstrap requests | Restriction, missing data, or failing request with its evidence |
| Every route produces bootstrap traffic only | Redirect chain, real session state, client guards, and server responses | Which route was attempted and why its business exchange was not observed |
| Business path redirects to login | Effective credential, expiry/refresh, auth response, and interceptor path | Session failure or missing access; no fabricated route coverage |
| Backend returns 401/403 | Caller, role, object context, and the enforcing response layer | Real denied baseline; bypass validation belongs to the exploitation workflow |
| Route inventory is unexpectedly small | All source/manifests fetched, lazy-load discovery, and actual navigation history | Known denominator and unfetched/unvisited sources |

Update `config.json` with observed session/response shapes and source references. A route stays blocked or untested until the real session and target behavior provide evidence.
