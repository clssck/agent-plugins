---
description: A React context provider given an inline object value re-renders every consumer on each render unless React Compiler is on
condition:
  - '<[\w.]*(?:Context|Provider)\b[^>]*?\bvalue=\{\{'
scope:
  - tool:edit(**/*.{tsx,jsx})
  - tool:write(**/*.{tsx,jsx})
interruptMode: never
---

**`<Ctx.Provider value={{ ... }}>` creates a new object, and new functions, on every render.** Every consumer re-renders even when nothing it reads changed, and wrapping a consumer in `memo` doesn't stop it.

First check whether React Compiler is on: `babel-plugin-react-compiler` in `package.json`, `reactCompiler` in `next.config.*`, or `experiments.reactCompiler` in an Expo `app.json`.

- **Compiler off:** wrap the callbacks in `useCallback` and the value in `useMemo`, then pass the memoized value.
- **Compiler on:** leave the inline value in new code, because the compiler memoizes it. Don't remove existing `useMemo`/`useCallback` without tests.
