# Security Checklist

Review-time checks for web application changes. Full exploit analysis → omp `/security` or the `security-reviewer` agent.

## Contents

- [Diff-Based Pass](#diff-based-pass)
- [Secrets](#secrets)
- [Authentication](#authentication)
- [Authorization](#authorization)
- [Input Validation](#input-validation)
- [Security Headers](#security-headers)
- [CORS](#cors)
- [Data Protection](#data-protection)
- [Dependency Security](#dependency-security)
- [Lockfile and Config Red Flags](#lockfile-and-config-red-flags)
- [Error Handling](#error-handling)
- [OWASP Top 10:2025](#owasp-top-102025)
- [CWE Top 25 (2025) Diff Patterns](#cwe-top-25-2025-diff-patterns)
- [Sources](#sources)

## Diff-Based Pass

Run first; the per-area checklists below then apply to what changed (OWASP Secure Code Review, diff-based reviews).

- [ ] What control did this diff touch or bypass? Check deleted and moved lines for removed guards, validation, escaping, logging.
- [ ] New trust boundary or integration (route, webhook, queue consumer, third-party API, file or URL input)? Trace source → processing → sink and confirm validation at the boundary.
- [ ] Highest-risk files first: auth/session, access checks, query construction, file and process calls, crypto, config and CI.
- [ ] Business logic: step order enforced server-side, race on check-then-act, limits on the new flow.
- [ ] Security-sensitive area you cannot judge (crypto, complex authz, concurrency)? Say so and recommend `/security` or a qualified reviewer; NEVER approve it by silence.

## Secrets

- [ ] No secrets in the diff
- [ ] `.gitignore` covers `.env`, `.env.local`, `*.pem`, `*.key`
- [ ] `.env.example` holds placeholders only

Search changed content with the omp `grep` tool (case-insensitive `password|secret|api[_-]?key|token|BEGIN .*PRIVATE KEY`) over the changed files. Searching the diff text itself:

```bash
# bash / zsh
git diff --cached -U0 | grep -iE 'password|secret|api[_-]?key|token'
```

```powershell
# PowerShell (Select-String is case-insensitive by default)
git diff --cached -U0 | Select-String -Pattern 'password|secret|api[_-]?key|token'
```

Staged diff only; repeat without `--cached` for unstaged changes. A hit is a lead, not a finding: confirm it is a real value.

## Authentication

- [ ] Passwords hashed with argon2id, scrypt, or bcrypt (≥12 rounds)
- [ ] Session cookies: `httpOnly`, `secure`, `sameSite: 'lax'` or stricter
- [ ] Session expiry configured
- [ ] Login rate limited
- [ ] Reset tokens time-limited and single-use
- [ ] MFA on sensitive operations (recommended)

## Authorization

- [ ] Every protected endpoint checks authentication
- [ ] Every resource access checks ownership or role (IDOR)
- [ ] Admin endpoints verify admin role
- [ ] API keys scoped to minimum permissions
- [ ] JWT validated: signature, expiry, issuer, audience

## Input Validation

- [ ] Validation at system boundaries (API routes, form handlers)
- [ ] Allowlists, not denylists
- [ ] String lengths and numeric ranges constrained
- [ ] Email, URL, date parsed by proper libraries
- [ ] File uploads: type restricted, size limited, content verified
- [ ] SQL parameterized, no string concatenation
- [ ] HTML output encoded via framework auto-escaping
- [ ] Redirect targets validated (open redirect)
- [ ] Server-side fetches of user-supplied URLs allowlisted (SSRF)

## Security Headers

```
Content-Security-Policy: default-src 'self'; script-src 'self'
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

- `X-XSS-Protection`: omit or `0`; rely on CSP.
- `frame-ancestors` in CSP supersedes `X-Frame-Options` where both are supported.
- Tune CSP per app; this is a starting point, not a mandate.

## CORS

|Resource|Required|
|---|---|
|Private, cookie/credentialed, or user-specific|Explicit origin allowlist; `credentials: true` only with an allowlist|
|Intentionally public, no credentials (public data, CDN assets)|`Access-Control-Allow-Origin: *` acceptable|

```typescript
// Private API
cors({
  origin: ['https://app.example.com'],
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
  allowedHeaders: ['Content-Type', 'Authorization'],
})

// Bad: wildcard on a credentialed or private API
cors({ origin: '*', credentials: true })
```

- Browsers reject `*` with credentials; flag the attempt as a misconfiguration.
- Reflecting the request `Origin` without an allowlist = same risk as `*` plus credentials.
- NEVER flag `*` on a resource documented as public.

## Data Protection

- [ ] Sensitive fields excluded from API responses (`passwordHash`, `resetToken`)
- [ ] Passwords, tokens, card numbers absent from logs
- [ ] PII encrypted at rest where regulation requires
- [ ] TLS for all external communication
- [ ] Database backups encrypted

## Dependency Security

Read-only evidence commands; identical in bash, zsh, and PowerShell:

```bash
npm audit --json
npm audit --audit-level=critical
npm outdated
```

- NEVER run `npm audit fix`, `npm update`, or `npx npm-check-updates -u` during review; they change the tree.
- Report vulnerable package, advisory, and fixed version; recommend the upgrade as a finding.
- pnpm/yarn projects: `pnpm audit --json` / `yarn npm audit --json`.
- `npm audit` needs a lockfile; `--no-package-lock` re-resolves the tree and results vary per run. `--audit-level` only changes the exit code, not the report.
- `npm audit signatures` (read-only) verifies registry signatures and provenance attestations of installed packages; use the latest npm CLI.
- An advisory hit proves nothing about packages with no advisory yet. Known-bad lists lag malicious publishes; judge new or bumped packages with the signals in [SKILL.md](../SKILL.md#dependency-review).
- New dependency added? Also apply the dependency questions in [SKILL.md](../SKILL.md#dependency-review).

## Lockfile and Config Red Flags

Read lockfile and install-policy diffs line by line; reviewers skip them and attackers rely on it.

|Signal in the diff|Why it matters|
|---|---|
|Lockfile entry changed with no matching `package.json` change|Possible injected or substituted package|
|Same `name@version` with a different `integrity` hash, or a new `resolved` host/URL|Tampered tarball or registry substitution|
|New `git+ssh://`, `github:`, or `https://…tgz` dependency sources|Bypasses registry controls; mutable refs. pnpm `blockExoticSubdeps` (default `true`) blocks these for transitive deps; npm `allow-git=none\|root` limits git deps|
|New `preinstall`/`install`/`postinstall` on a dependency|Execution vector of the 2025 Shai-Hulud npm worm; pnpm and npm now gate install scripts by allowlist|
|`ignore-scripts=true` removed, `dangerouslyAllowAllBuilds: true` (pnpm), `dangerously-allow-all-scripts` (npm), or broad `allowBuilds`/`allowScripts` entries|Disables the install-script gate. Prefer explicit per-package allow entries|
|`strictDepBuilds: false` (pnpm)|Unreviewed build scripts stop failing the install|
|`minimumReleaseAge: 0`, removed, or widened `minimumReleaseAgeExclude` (pnpm); `min-release-age` removed (npm)|Drops the cooldown that lets malicious versions get detected and pulled. Units differ: pnpm minutes (default `1440`), npm days|
|`trustPolicy: no-downgrade` removed or `trustPolicyExclude` grown (pnpm)|Re-allows packages whose publish trust (trusted publisher, provenance) decreased|
|`trustLockfile: true` (pnpm)|Skips re-verification of lockfile entries; a poisoned lockfile from an outside contributor slips through|
|New `registry=` or scoped registry, or `strict-ssl=false`|Dependency-confusion or MITM path; internal scopes MUST resolve to the internal registry|
|Workflow `uses: owner/action@v1` (tag or branch) instead of a full-length commit SHA|Tags are mutable; a SHA is the only immutable pin. Verify the SHA belongs to the action repo, not a fork|
|Floating ranges (`latest`, `*`) or CI switched from `npm ci` / `--frozen-lockfile` to a resolving install|Unreviewed versions reach production|

- pnpm settings live in `pnpm-workspace.yaml`; `.npmrc` is read only for auth and registry settings, so a pnpm policy added to `.npmrc` is silently inert.
- A changed policy file without a stated reason → ask the author; an unexplained weakening is Important at minimum.

## Error Handling

```typescript
// Good: generic message, details logged server-side
res.status(500).json({
  error: { code: 'INTERNAL_ERROR', message: 'Something went wrong' },
});

// Bad: leaks internals
res.status(500).json({
  error: err.message,
  stack: err.stack,
  query: err.sql,
});
```

- [ ] Failures fail closed: an exception in an auth or validation path denies access
- [ ] No empty `catch` that swallows errors in security-relevant paths
- [ ] Resource cleanup on error paths (connections, locks, temp files)

## OWASP Top 10:2025

Source: <https://owasp.org/Top10/2025/>. Category names and order verified against that page.

|#|Category|Review prevention|
|---|---|---|
|A01|Broken Access Control (includes SSRF, CSRF, IDOR)|Server-side authz on every endpoint; ownership checks; allowlist outbound URLs; CSRF protection|
|A02|Security Misconfiguration|Security headers; least privilege; no default credentials; debug off in production|
|A03|Software Supply Chain Failures|`npm audit --json`; lockfile committed and reviewed; pinned dependencies; trusted registries; install scripts allowlisted; CI/CD at least as hardened as what it deploys; no single person writes and promotes code to production without a second reviewer|
|A04|Cryptographic Failures|TLS; strong password hashing; vetted libraries; no secrets in code|
|A05|Injection|Parameterized queries; context-aware output encoding; allowlist validation|
|A06|Insecure Design|Threat model; abuse cases; limits on sensitive flows|
|A07|Authentication Failures|Rate limiting; session management; MFA; secure credential recovery|
|A08|Software or Data Integrity Failures|Signed artifacts; verified updates; no insecure deserialization of untrusted data|
|A09|Security Logging and Alerting Failures|Log auth and access events; alert on anomalies; never log secrets|
|A10|Mishandling of Exceptional Conditions|Fail closed; handle every error path; no information leaks in errors; no unchecked exceptions in auth|

## CWE Top 25 (2025) Diff Patterns

Weaknesses from the 2025 CWE Top 25 that a web or Node diff most often introduces. Map a finding to its CWE ID in the report when it fits.

|CWE (2025 rank)|Look for in the diff|
|---|---|
|CWE-79 XSS (1)|`dangerouslySetInnerHTML`, `innerHTML`, unescaped template output, user data in `href`/`src`|
|CWE-89 SQL injection (2)|Template-literal or concatenated SQL, raw-query escape hatches in ORMs|
|CWE-352 CSRF (3)|State-changing GET; cookie-authenticated mutation without token or `SameSite`; CORS loosened|
|CWE-862 Missing Authorization (4), CWE-863 Incorrect Authorization (17), CWE-284 Improper Access Control (19), CWE-639 user-controlled key (24)|New route/server function with no authz check; ownership taken from the request body; ID lookups without owner filter|
|CWE-22 Path Traversal (6)|User input in `path.join`/`fs.*` without resolving and checking the base directory|
|CWE-78 OS Command Injection (9), CWE-94 Code Injection (10), CWE-77 Command Injection (23)|`exec`/`execSync` with interpolated strings, `shell: true`, `eval`, `new Function`, dynamic `import()` of user input|
|CWE-434 Unrestricted Upload (12)|Upload handler trusting client MIME type or filename; files stored under web root|
|CWE-502 Deserialization of Untrusted Data (15)|`yaml.load` / unsafe loaders, `pickle`, `node-serialize`-style revival of request data|
|CWE-20 Improper Input Validation (18)|New boundary (route, form, message consumer) with no schema validation|
|CWE-200 Information Exposure (20)|Whole DB rows returned to the client; stack traces or tokens in responses and logs|
|CWE-306 Missing Authentication for Critical Function (21)|Admin, export, or webhook endpoint reachable without session or signature check|
|CWE-918 SSRF (22)|Server-side `fetch` of a user-supplied URL without an allowlist; webhook or import-by-URL features|
|CWE-770 Resources Without Limits (25)|Unbounded list endpoints, uploads, loops over request-sized input, missing rate limits or timeouts|
|CWE-476 NULL Pointer Dereference (13); memory safety: CWE-787 (5), 416 (7), 125 (8), 120 (11), 121 (14), 122 (16)|Native, C/C++, Rust `unsafe`, or WASM code: unchecked length, unchecked null return. Rare in TypeScript apps; escalate to `/security`|

Ranks and IDs verified against the 2025 list (page updated 2025-12-15); re-check there before citing a rank in a report.

## Sources

- OWASP Top 10:2025, <https://owasp.org/Top10/2025/>; A03 Software Supply Chain Failures, <https://owasp.org/Top10/2025/A03_2025-Software_Supply_Chain_Failures/>
- 2025 CWE Top 25 Most Dangerous Software Weaknesses, <https://cwe.mitre.org/top25/archive/2025/2025_cwe_top25.html>
- OWASP Secure Code Review Cheat Sheet, <https://cheatsheetseries.owasp.org/cheatsheets/Secure_Code_Review_Cheat_Sheet.html>
- Google eng-practices, What to look for in a code review, <https://google.github.io/eng-practices/review/reviewer/looking-for.html>
- npm Docs, `npm audit`, <https://docs.npmjs.com/cli/v11/commands/npm-audit>
- npm Docs, config (`min-release-age`, `allow-git`, `allow-scripts`, `strict-allow-scripts`, `ignore-scripts`), <https://docs.npmjs.com/cli/v11/using-npm/config>
- pnpm, Mitigating supply chain attacks, <https://pnpm.io/supply-chain-security>
- pnpm, Dependency Resolution Settings (`minimumReleaseAge`, `trustPolicy`, `trustLockfile`, `blockExoticSubdeps`), <https://pnpm.io/settings/dependency-resolution>
- pnpm, Build settings (`allowBuilds`, `strictDepBuilds`, `dangerouslyAllowAllBuilds`), <https://pnpm.io/settings/build>
- OpenSSF, Concise Guide for Evaluating Open Source Software, <https://best.openssf.org/Concise-Guide-for-Evaluating-Open-Source-Software>
- GitHub Docs, Secure use reference (pin actions to a full-length commit SHA), <https://docs.github.com/en/actions/reference/security/secure-use>
