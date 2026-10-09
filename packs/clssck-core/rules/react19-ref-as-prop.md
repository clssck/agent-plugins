---
description: In React 19-only code, take ref as a prop and render Context directly instead of forwardRef and Context.Provider
condition:
  - '\bforwardRef\s*[<(]'
  - '<\w+\.Provider\b'
scope:
  - tool:edit(**/*.{tsx,jsx})
  - tool:write(**/*.{tsx,jsx})
interruptMode: never
---

**React only; ignore this in Solid, Preact, or Vue JSX.** Check the React version in `package.json` before writing `forwardRef` or `<Ctx.Provider>`.

- **React 19 or later, with no React 18 support needed:**
  - Receive `ref` as a regular prop: `function Input({ ref, ...props }: ComponentPropsWithRef<'input'>)`.
  - Render the context as its own provider: `<Ctx value={value}>`.
  - Both legacy forms still work but are slated for deprecation.
- **React 18 still supported:** keep `forwardRef` and `.Provider`. The React 19 forms don't work there.
- **Migrating a codebase:** use the codemods instead of editing by hand, then review the diff:
  `npx codemod react-19-remove-forward-ref --target src`
  `npx codemod react-19-remove-context-provider --target src`
- Read a child element's ref as `element.props.ref`; `element.ref` is deprecated in React 19.
