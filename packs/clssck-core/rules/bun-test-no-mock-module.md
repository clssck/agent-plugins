---
description: Ban Bun module mocks in tests
astCondition:
- mock.module($$$ARGS)
scope:
- tool:edit(**/*{.test,.spec,_test,_spec}.{ts,tsx,js,jsx,mts,cts,mjs,cjs})
- tool:write(**/*{.test,.spec,_test,_spec}.{ts,tsx,js,jsx,mts,cts,mjs,cjs})
- tool:edit(**/{test,tests,__tests__}/**/*.{ts,tsx,js,jsx,mts,cts,mjs,cjs})
- tool:write(**/{test,tests,__tests__}/**/*.{ts,tsx,js,jsx,mts,cts,mjs,cjs})
- tool:edit(**/*{preload,setup}*.{ts,tsx,js,jsx,mts,cts,mjs,cjs})
- tool:write(**/*{preload,setup}*.{ts,tsx,js,jsx,mts,cts,mjs,cjs})
interruptMode: never
---

**NEVER use `mock.module()` in tests.**

`mock.module()` mutates Bun's process-global module registry, can leak across test files, and is not reset by `mock.restore()`.

- Namespace-import the dependency and use the test runner's `spyOn()` on the exported function.
- Restore spies in `afterEach`.
- NEVER treat `--isolate`, `--parallel`, or preload ordering as exceptions; tests must remain safe under the repository's normal full-suite runner.
- Import-time behavior? Refactor behind an explicit dependency seam instead of overriding the module registry.
