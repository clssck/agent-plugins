---
title: Keep the Context Value Stable
impact: MEDIUM
impactDescription: prevents every compound part re-rendering on each provider render
tags: context, performance, memoization, react-compiler
---

## Keep the Context Value Stable

React re-renders every consumer when the provider's `value` changes by
`Object.is`. `memo` on a part does not stop it. A provider that builds
`{ state, actions, meta }` inline creates a new object, and new action
functions, on every render, so every `useComposer()` caller re-renders even when
nothing it reads changed.

First check whether React Compiler is on: `babel-plugin-react-compiler` in
`package.json`, `reactCompiler` in `next.config.*`, or an Expo SDK 54+ app
(compiler on by default for new apps).

**Incorrect (no compiler, new value every render):**

```tsx
function ForwardMessageProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState(initialState)
  const inputRef = useRef<TextInput>(null)
  const forwardMessage = useForwardMessage()

  return (
    <ComposerContext.Provider
      value={{
        state,
        actions: { update: setState, submit: () => forwardMessage(state) },
        meta: { inputRef },
      }}
    >
      {children}
    </ComposerContext.Provider>
  )
}
```

**Correct (no compiler, memoize the value and its callbacks):**

```tsx
function ForwardMessageProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState(initialState)
  const inputRef = useRef<TextInput>(null)
  const forwardMessage = useForwardMessage()

  const submit = useCallback(() => forwardMessage(state), [forwardMessage, state])
  const value = useMemo<ComposerContextValue>(
    () => ({ state, actions: { update: setState, submit }, meta: { inputRef } }),
    [state, submit],
  )

  return <ComposerContext.Provider value={value}>{children}</ComposerContext.Provider>
}
```

**With React Compiler:**

- New code: write the inline value; the compiler memoizes it, including after
  early returns where `useMemo` cannot run.
- Keep `useMemo`/`useCallback` only as an escape hatch for precise control,
  e.g. a value used as an Effect dependency.
- Existing code: leave current `useMemo`/`useCallback` in place; removing it
  can change compilation output. Remove only with tests.
- The compiler needs code that follows the Rules of React; enable the
  `recommended` preset of `eslint-plugin-react-hooks` (it replaces
  `eslint-plugin-react-compiler`) to surface violations.

## Sources

- useContext: Optimizing re-renders when passing objects and functions — <https://react.dev/reference/react/useContext#optimizing-re-renders-when-passing-objects-and-functions>
- React Compiler v1.0 (Oct 2025) — <https://react.dev/blog/2025/10/07/react-compiler-1>
