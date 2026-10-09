---
name: composition-patterns
description: "React component API composition: compound components, lifted state, context interfaces, stable provider values, explicit variants, children vs render props, asChild/render parts, React 19 refs and Actions. Use when refactoring boolean-prop-heavy components, designing component libraries or context providers, or reviewing React component APIs. Not for general PR review."
---

# React Composition Patterns

Replace boolean-prop proliferation with compound components, lifted state, and composed internals. Works on React 18 and 19; only the `react19-` rule needs React 19.

## Rules

Load the rule file before applying it; each holds Incorrect/Correct examples.

|Priority|Category|Impact|Rule|Summary|
|---|---|---|---|---|
|1|Architecture|CRITICAL|[architecture-avoid-boolean-props](rules/architecture-avoid-boolean-props.md)|NEVER add boolean props to switch behavior; compose|
|1|Architecture|HIGH|[architecture-compound-components](rules/architecture-compound-components.md)|Shared context + subcomponents; consumers assemble pieces|
|2|State|HIGH|[state-context-interface](rules/state-context-interface.md)|Context contract: `state`, `actions`, `meta`; guarded reader|
|2|State|HIGH|[state-lift-state](rules/state-lift-state.md)|Provider owns state; siblings outside the frame read it|
|2|State|MEDIUM|[state-decouple-implementation](rules/state-decouple-implementation.md)|Only the provider knows how state is stored|
|2|State|MEDIUM|[state-stable-context-value](rules/state-stable-context-value.md)|Memoize provider value unless React Compiler is on|
|3|Patterns|MEDIUM|[patterns-explicit-variants](rules/patterns-explicit-variants.md)|One named component per variant, not boolean modes|
|3|Patterns|MEDIUM|[patterns-children-over-render-props](rules/patterns-children-over-render-props.md)|`children` for structure; render props only to pass data back|
|3|Patterns|MEDIUM|[patterns-polymorphic-parts](rules/patterns-polymorphic-parts.md)|`asChild`/`render` contract; dot-notation parts in Server Components|
|4|React 19|MEDIUM|[react19-no-forwardref](rules/react19-no-forwardref.md)|`ref` as prop; ref cleanup; `useContext` vs `use`; Actions in providers; codemods|

## Workflow

1. `read` `package.json`: React version, primitive library (`radix-ui` or `@base-ui/react`), React Compiler signals.
2. `grep` target components for boolean mode props (`is*`, `show*`), `render*` props, `forwardRef`, `.Provider`.
3. Load the matching rule files above; apply the Decision Rules below.
4. React 19-only codebase? Run the codemods in [react19-no-forwardref](rules/react19-no-forwardref.md) via `bash`; review the diff.
5. Run the project's typecheck and tests via `bash`; walk the Checklist.

## Decision Rules

- Boolean prop selects structure? Replace with a variant component or children.
- Two or more booleans interact? Variants; NEVER a prop matrix.
- Siblings outside the component need its state? Lift to a provider.
- UI imports a concrete store hook? Move it into the provider; UI reads the context interface.
- Render prop passes data to the child (`renderItem`)? Keep it. Static structure? Use `children`.
- Compound child rendered outside its provider? Guarded reader MUST throw a clear error.
- React 18 supported? Keep `forwardRef` and `<Context.Provider>`; NEVER use `<Context value>` or `use(Context)`.
- Provider builds `{ state, actions, meta }` inline and React Compiler is off? Memoize it; with the compiler on, leave it inline.
- Part must render as a link or custom component? Use the project's primitive convention (`asChild` for Radix, `render` for Base UI); NEVER add `as*` booleans.
- Compound parts imported by a Server Component? NEVER define the dot-notation object in a `'use client'` file; namespace-export per-part client files.
- Provider wraps `useActionState`/`useOptimistic`? Dispatch and setter MUST run inside an Action or Transition.

## Conventions

- Context shape: `{ state, actions, meta }`; type `meta.inputRef` as `RefObject<T | null>`.
- Read context through one guarded `useComposer()`-style hook returning a non-null value.
- General examples use `useContext` and `<Context.Provider>`; React 19 shorthand appears only in the `react19-` rule.
- Examples build provider values inline for brevity; memoize per [state-stable-context-value](rules/state-stable-context-value.md) when the compiler is off.
- Examples use a messaging composer with React Native primitives (`TextInput`, `onPress`); adapt names and DOM equivalents, keep structure.

## References

- <https://react.dev/learn/passing-data-deeply-with-context>
- <https://react.dev/reference/react/use>
- <https://react.dev/blog/2024/04/25/react-19-upgrade-guide>
- <https://react.dev/blog/2025/10/07/react-compiler-1>
- Per-rule `## Sources` lists in the `react19-`, `state-stable-` and `patterns-polymorphic-` rule files.

## Checklist

- No boolean prop switches layout or behavior.
- Variants are named components, not prop combinations.
- Only the provider imports state implementation.
- Consumers read context via a guarded hook; no raw nullable context.
- Ref types match the React version's typings; ref callbacks use block bodies.
- React 19-only syntax absent unless the project targets React 19+.
- Provider value is stable (memoized, or React Compiler enabled).
- Part components spread props and accept `ref` so `asChild`/`render` works.
