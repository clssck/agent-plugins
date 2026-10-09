---
description: Do not add boolean props that switch a React component's structure or mode; compose variants instead
condition:
  - '\b(?:is|has|show|hide|with|use|as)(?!Child\b)[A-Z]\w*\??\s*:\s*boolean\b'
question: Does this change add a boolean prop to a React component that switches what the component renders or which mode it runs in (for example isThread, isEditing, showFooter, withSidebar, asLink)? Answer no for plain state or accessibility flags such as disabled, open, checked, loading, required, or asChild.
scope:
  - tool:edit(**/*.{tsx,jsx})
  - tool:write(**/*.{tsx,jsx})
interruptMode: never
---

**Each mode boolean doubles the component's possible states.** Once two of them interact, the result is a prop matrix of nested ternaries that nobody can test fully.

- Use one named component per variant (`ThreadComposer`, `EditComposer`), each assembling shared parts (`<Composer.Input />`, `<Composer.Footer>`).
- Put shared state in a provider and let parts read it through a guarded hook (`useComposer()`) that throws outside the provider.
- Pass structure as `children`. Keep render props only for handing data back to the caller (`renderItem`).
- To render a part as a link or custom element, follow the primitive library's convention (`asChild` for Radix, `render` for Base UI), never an `as*` boolean.
- Plain state flags (`disabled`, `open`, `loading`) are fine as booleans.
