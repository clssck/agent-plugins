---
title: React 19 Refs and Context Reads
impact: MEDIUM
impactDescription: cleaner component definitions and context usage
tags: react19, refs, context, hooks
---

## React 19 Refs, Context Reads, and Actions

> **React 19+ only.** Skip this if you're on React 18 or earlier. All other
> rules in this skill work on React 18 and 19.

In React 19, `ref` can be received as a regular prop, so new React 19-only
components usually do not need a `forwardRef` wrapper. `useContext()` remains a
supported context API. Choose `use(Context)` only when its ability to read a
context conditionally or in a loop is needed.

If a library must support React 18 as well as React 19, retain a compatible
`forwardRef` boundary until React 18 support is removed.

**React 19-only (receive `ref` as a prop):**

```tsx
import type { ComponentPropsWithRef } from 'react'

type ComposerInputProps = ComponentPropsWithRef<'input'>

function ComposerInput({ ref, ...props }: ComposerInputProps) {
  return <input ref={ref} {...props} />
}
```

## Context Providers

React 19 lets a context render as its own provider. React 18 requires
`.Provider`.

```tsx
// React 19 only
<ComposerContext value={value}>{children}</ComposerContext>

// React 18 and 19
<ComposerContext.Provider value={value}>{children}</ComposerContext.Provider>
```

## Choose the Context Reader Intentionally

Use `useContext()` for an unconditional context read at the top level of a
component. It remains supported in React 19. This skill's shared guarded reader
`useComposer()` ([state-context-interface.md](state-context-interface.md))
wraps it; read `actions.submit` through that reader, not from the raw context.

```tsx
function SubmitButton() {
  const {
    actions: { submit },
  } = useComposer()
  return <button onClick={submit}>Submit</button>
}
```

Use `use(Context)` in a Client Component when the context read must occur inside
a conditional or loop. It is not a wholesale replacement for `useContext()`.

```tsx
import { use } from 'react'

function ThemedRule({ show }: { show: boolean }) {
  if (!show) return null

  const theme = use(ThemeContext)
  return <hr className={theme} />
}
```

Do not use `use(Context)` in a Server Component; reading context with that form
is unsupported there. Put the context-consuming UI behind a Client Component
boundary instead.

## Ref Callbacks Are Cleanup-Aware

React 19 calls a cleanup function returned from a `ref` callback instead of
calling the callback with `null`. With React 19 typings, TypeScript rejects any
other return value, so implicit returns fail type-checking.

```tsx
// Incorrect: implicit return of the element
<input ref={(node) => (inputRefs.current[id] = node)} />

// Correct: block body, optional cleanup
<input
  ref={(node) => {
    inputRefs.current[id] = node
    return () => {
      delete inputRefs.current[id]
    }
  }}
/>
```

Read a child's ref as `element.props.ref`. `element.ref` is deprecated and
warns. Prefer composing with children over `cloneElement`; React documents it
as fragile because it hides data flow.

## Migrating Existing Code

Do not hand-edit across a codebase. Run the codemods, then review the diff:

```bash
npx codemod react-19-remove-forward-ref --target src
npx codemod react-19-remove-context-provider --target src
```

`forwardRef` and `<Context.Provider>` still work in React 19 and are slated for
deprecation in future versions. Do not run these codemods while React 18 is
supported.

## Actions Inside a Provider

When the provider's `actions.submit` wraps `useActionState`, the returned
`dispatchAction` MUST run inside an Action: pass it to a `<form action>` /
`formAction` or an Action prop, or wrap it in `startTransition`. Calling it from
a bare `onClick` logs an error and `isPending` does not update. Likewise the
`useOptimistic` setter MUST be called inside an Action, or the optimistic value
flashes then reverts.

```tsx
// Incorrect: dispatch outside a Transition
<button onClick={() => dispatchAction()}>Send</button>

// Correct: form action (React wraps it in a Transition)
<form action={dispatchAction}>
  <ComposerSubmit />
</form>
```

A leaf part inside the `<form>` can read `pending` with `useFormStatus()` from
`react-dom` instead of a context field. It reports only a parent `<form>`;
called in the component that renders the form, `pending` is always `false`.
Expose `isPending` through `state` (for example `state.isSubmitting`) when
parts live outside the form.

## Sources

- React v19 release post (ref as prop, `<Context>` provider, ref cleanup, `useFormStatus`) — <https://react.dev/blog/2024/12/05/react-19>
- React 19 Upgrade Guide (`element.ref` deprecation, ref callback return types) — <https://react.dev/blog/2024/04/25/react-19-upgrade-guide>
- `use` — <https://react.dev/reference/react/use>
- `createContext` (`.Provider` is legacy) — <https://react.dev/reference/react/createContext>
- `forwardRef` (deprecated in a future release) — <https://react.dev/reference/react/forwardRef>
- `useActionState` (dispatch must run in an Action) — <https://react.dev/reference/react/useActionState>
- `useOptimistic` (setter must run in an Action) — <https://react.dev/reference/react/useOptimistic>
- `useFormStatus` — <https://react.dev/reference/react-dom/hooks/useFormStatus>
- `cloneElement` (alternatives) — <https://react.dev/reference/react/cloneElement>
- React codemods — <https://github.com/codemod/react-codemod>
