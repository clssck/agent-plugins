# Parameter Recon

Cards for `api-recon` Phases 1b and 3b. Paths come from the static harvest; parameter fields are reverse-engineered separately.

## Transport Shapes

**Label every endpoint with its transport before hunting fields.**

|Shape|Where params live|First thing to look for|
|---|---|---|
|REST JSON|body + query|object literal near the path anchor|
|GraphQL|`variables`|gql template, `$page: Int`|
|Form|urlencoded|`<form>`, `FormData`|
|Upload|multipart|`FormData.append`|
|Path params|`/user/:id`|route table, `useParams`/`$route.params`|
|Encrypted/signed|wrapped in `sign`/`data`|hook the encryption function's input|

## Anchor Windowing

**Treat a known path as an anchor and expand a window around it** — with the `grep` tool over the downloaded chunks (NEVER shell `grep`/`rg`/`find`):

- The path literal itself: `"/api/user/list"` over `recon/js/`.
- A windowed capture around a path: `.{0,120}("/api[^"]+").{0,200}`.
- Packer-object leads: `(params|data|body|payload)\s*:\s*\{`.
- Type residue for field hints: `yup`/`zod` schemas, `Form.Item name=`, embedded Swagger.

**Output stays bounded** — matched lines only; page files with the tool's `skip`, and tighten the pattern or window to surface more matches inside one file. NEVER paste bundle fragments into the conversation: record candidates in `recon/param_candidates.json` as `{path, fields[], source, confidence}`.

## Binding Chains

**Walk from the UI control to the payload:** form submit → transform → request builder; table search → `getFieldsValue()`/state → params; route segment/query → loader; interceptors inject global fields (tenant, pagination, signature); enum selects reveal allowed values. The DevTools call stack from the request up to the packer function is the fastest confirmation path.

Three questions per endpoint: how the payload is assembled, what validation exists (required/pattern/enum), and how it travels (path/query/body/multipart/headers).

## Trigger Matrix

**Per module, trigger each action class once and diff the samples.** Outbound bodies under mocks are still real — the request, not the mock, is the truth.

|Action|Fields that usually appear|
|---|---|
|List first load|pagination + default filters|
|Search|keyword, filter|
|Advanced filter|more optional fields|
|Create/edit|full entity|
|Bulk/export/sort|`ids[]`, export type, `sortField`|

Record to `param_samples.json`; required versus optional is decided by multi-sample diffs or validation/error evidence, NEVER by one sample.

## Confidence Tiers

|Tier|Evidence|
|---|---|
|high|observed in ≥2 samples or confirmed by a validation error|
|medium|single observed sample|
|low|static-only candidate (callsite residue)|
|pending|suspected but never triggered — record it as a limitation|

## Error-Based Reverse Check

**Within scope, an intentionally incomplete request may be sent to read the 400/422 body** (`field 'x' is required`, enum violations). That is parameter recon, not exploitation — keep it non-destructive and rate-limited. Watch for wrapped `data`, GraphQL `variables`, and pre-encryption payloads (`bizData`).
