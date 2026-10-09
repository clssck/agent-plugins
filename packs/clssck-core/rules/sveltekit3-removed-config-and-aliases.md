---
description: SvelteKit 3 removed svelte.config.js, the $lib alias, $app/stores, $app/environment and $service-worker
condition:
- '[''"]\$app/(?:stores|environment)[''"]|[''"]\$lib(?:/[^''"]*)?[''"]|[''"]\$service-worker[''"]|\bkit\s*:\s*\{'
scope:
- tool:edit(**/*.{svelte,ts,js})
- tool:write(**/*.{svelte,ts,js})
- tool:edit(**/svelte.config.{js,ts,mjs})
- tool:write(**/svelte.config.{js,ts,mjs})
interruptMode: never
---

**Check `@sveltejs/kit` in `package.json` first; ignore this for SvelteKit 2.** SvelteKit 3 (October 2026) removed APIs that most examples still use:

| Removed | Use instead |
|---|---|
| `svelte.config.js` with `kit: { ... }` | pass the options to `sveltekit({ ... })` in `vite.config.js`; former `kit.*` keys become top-level plugin options |
| `$lib/...` | `#lib/...` declared in `package.json` `"imports": { "#lib": "./src/lib/index.js", "#lib/*": "./src/lib/*" }`, with file extensions in imports (`#lib/Header.svelte`, `#lib/foo.js`) |
| `$app/stores` (`$page`, `$navigating`) | `$app/state` (`page`, `navigating`, read without the `$` prefix) |
| `$app/environment` | `$app/env` |
| `$service-worker` | `$app/manifest` and `$app/env` |

Codemod for existing apps: `npx sv migrate sveltekit-3`. Source: https://svelte.dev/docs/kit/migrating-to-sveltekit-3
