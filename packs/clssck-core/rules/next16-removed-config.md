---
description: Next.js 16 removed next lint, eslint/amp/images.domains config, renamed experimental options, and fails next build when a webpack() config exists
condition:
- \bnext\s+lint\b|\beslint\s*:\s*\{|\b(?:dynamicIO|useCache|serverComponentsExternalPackages|bundlePagesExternals|serverRuntimeConfig|publicRuntimeConfig)\s*:|\bexperimental\s*:\s*\{[^}]*\bturbo(?:pack)?\s*:|\bimages\s*:\s*\{[^}]*\bdomains\s*:|\bamp\s*:\s*\{|\bwebpack\s*(?::|\()
scope:
- tool:edit(**/next.config.{js,mjs,cjs,ts,mts})
- tool:write(**/next.config.{js,mjs,cjs,ts,mts})
- tool:edit(**/package.json)
- tool:write(**/package.json)
- tool:edit(**/.github/workflows/*.{yml,yaml})
- tool:write(**/.github/workflows/*.{yml,yaml})
interruptMode: never
---

**Check `next` in `package.json`; this applies to Next.js 16 and later.**

| Don't write | Write instead |
|---|---|
| `webpack(config) { ... }` | `turbopack: { rules: { '*.svg': { loaders: ['@svgr/webpack'], as: '*.js' } }, resolveAlias: { ... } }`. A webpack config makes `next build` fail under the default Turbopack; keep it only with `next build --webpack`. |
| `"lint": "next lint"`, `eslint: { ... }` in next.config | `"lint": "eslint ."` with `eslint.config.mjs` |
| `images: { domains: [...] }` | `images: { remotePatterns: [new URL('https://cdn.example.com/**')] }` |
| `experimental.turbopack` / `turbo` | top-level `turbopack` |
| `experimental.dynamicIO` / `useCache` | `cacheComponents: true` |
| `serverComponentsExternalPackages` | `serverExternalPackages` |
| `serverRuntimeConfig` / `publicRuntimeConfig`, `amp` | environment variables; AMP is removed |

Source: https://nextjs.org/docs/app/guides/upgrading/version-16
