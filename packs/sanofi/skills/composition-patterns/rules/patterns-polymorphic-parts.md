---
title: Let Consumers Swap the Rendered Element, and Compose Library Parts Correctly
impact: MEDIUM
impactDescription: avoids boolean `as*` props and broken Radix/Base UI triggers
tags: composition, asChild, render-prop, radix, base-ui, rsc
---

## Let Consumers Swap the Rendered Element

When a part must render as a different element or your own component (a trigger
as a link, a menu item as `<a>`), do not add a boolean or an `as` string prop per
case. Use the convention of the primitive library already in the project.

| Library | Prop | Example |
|---|---|---|
| Radix (`radix-ui`) | `asChild` | `<Tooltip.Trigger asChild><a href="/x">Docs</a></Tooltip.Trigger>` |
| Base UI (`@base-ui/react`, formerly `@base-ui-components/react`) | `render` (element, or function `(props, state) => ...` for hot paths) | `<Menu.Item render={<a href="/x" />}>Docs</Menu.Item>` |

NEVER mix the two in one component tree. Check `package.json` first; shadcn/ui
components follow whichever primitive they wrap.

Base UI `render` is not the `renderHeader`-style render prop that
[patterns-children-over-render-props](patterns-children-over-render-props.md)
rejects: it replaces the rendered element, not a slot of children.

## The Consumer Component Contract

The component passed to `asChild` / `render` receives the primitive's props and
event handlers. It MUST spread all props onto its DOM node and MUST accept
`ref`. If it does not, the trigger silently loses behavior or positioning.

**Incorrect (drops props and ref):**

```tsx
const MyButton = ({ children }: { children: React.ReactNode }) => <button>{children}</button>
```

**Correct (React 19):**

```tsx
function MyButton({ ref, ...props }: React.ComponentPropsWithRef<'button'>) {
  return <button ref={ref} {...props} />
}
```

On React 18, wrap with `forwardRef` as in Radix's guide. When changing the
element type, you own accessibility: a `Tooltip.Trigger` must stay a focusable
element that handles pointer and keyboard events.

Nested parts compose by nesting `asChild` or `render`; the same two requirements
apply to each layer.

## Dot-Notation Parts and Server Components

A `Composer.Input` style object defined inside a `'use client'` file breaks when a
Server Component imports it: the import is an opaque client reference, so
accessing a property on it throws ("You cannot dot into a client module from a
server component") or yields `undefined`. Fixes, in order of preference:

1. Put `'use client'` on each part's file, not on the file that builds the
   namespace. Re-export with `export * as Composer from './parts'`; each member
   is then its own client reference. Radix puts the directive in each
   primitive package's `index.ts` and Base UI in each part file; the file doing
   `export * as ...` has none.
2. Import parts by name (`ComposerFrame`, `ComposerInput`) in Server Components.
3. Compose the compound tree inside one Client Component and render that from the
   Server Component.

AVOID `Object.assign(Composer, { Input })` or `Composer.Input = ...` in a
`'use client'` file consumed from Server Components.

## Sources

- Radix Primitives, Composition (`asChild`) — <https://www.radix-ui.com/primitives/docs/guides/composition>
- Base UI, Composition (`render` prop; package renamed to `@base-ui/react`) — <https://base-ui.com/react/handbook/composition>
- shadcn/ui, Tailwind v4 + React 19 (forwardRef removed, `data-slot`) — <https://ui.shadcn.com/docs/tailwind-v4>
- React, `'use client'` directive (server imports from client modules) — <https://react.dev/reference/rsc/use-client>
- Next.js issue #75192, namespace/compound components in RSC (maintainer explanation) — <https://github.com/vercel/next.js/issues/75192>
- Radix `export * as` namespacing — <https://github.com/radix-ui/primitives/blob/main/packages/react/radix-ui/src/index.ts>
