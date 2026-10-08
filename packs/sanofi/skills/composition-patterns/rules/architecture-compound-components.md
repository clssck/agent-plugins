---
title: Use Compound Components
impact: HIGH
impactDescription: enables flexible composition without prop drilling
tags: composition, compound-components, architecture
---

## Use Compound Components

Structure complex components as compound components with a shared context. Each
subcomponent accesses shared state via context, not props. Consumers compose the
pieces they need.

**Incorrect (monolithic component with render props):**

```tsx
function Composer({
  renderHeader,
  renderFooter,
  renderActions,
  showAttachments,
  showFormatting,
  showEmojis,
}: Props) {
  return (
    <form>
      {renderHeader?.()}
      <Input />
      {showAttachments && <Attachments />}
      {renderFooter ? (
        renderFooter()
      ) : (
        <Footer>
          {showFormatting && <Formatting />}
          {showEmojis && <Emojis />}
          {renderActions?.()}
        </Footer>
      )}
    </form>
  )
}
```

**Correct (compound components with shared context):**

`ComposerContextValue` is defined in [state-context-interface.md](state-context-interface.md).
The guarded reader `useComposer()` throws a clear error when a subcomponent is
rendered outside the provider, and returns a non-null value for strict
TypeScript.

```tsx
import { createContext, useContext } from 'react'

const ComposerContext = createContext<ComposerContextValue | null>(null)

function useComposer(): ComposerContextValue {
  const value = useContext(ComposerContext)
  if (!value) {
    throw new Error('Composer components must be rendered inside <Composer.Provider>')
  }
  return value
}

function ComposerProvider({ children, state, actions, meta }: ProviderProps) {
  return (
    <ComposerContext.Provider value={{ state, actions, meta }}>
      {children}
    </ComposerContext.Provider>
  )
}

function ComposerFrame({ children }: { children: React.ReactNode }) {
  return <form>{children}</form>
}

function ComposerInput() {
  const {
    state,
    actions: { update },
    meta: { inputRef },
  } = useComposer()
  return (
    <TextInput
      ref={inputRef}
      value={state.input}
      onChangeText={(text) => update((s) => ({ ...s, input: text }))}
    />
  )
}

function ComposerSubmit() {
  const {
    actions: { submit },
  } = useComposer()
  return <Button onPress={submit}>Send</Button>
}

// Export as compound component
const Composer = {
  Provider: ComposerProvider,
  Frame: ComposerFrame,
  Input: ComposerInput,
  Submit: ComposerSubmit,
  Header: ComposerHeader,
  Footer: ComposerFooter,
  Attachments: ComposerAttachments,
  Formatting: ComposerFormatting,
  Emojis: ComposerEmojis,
}
```

**Usage:**

```tsx
<Composer.Provider state={state} actions={actions} meta={meta}>
  <Composer.Frame>
    <Composer.Header />
    <Composer.Input />
    <Composer.Footer>
      <Composer.Formatting />
      <Composer.Submit />
    </Composer.Footer>
  </Composer.Frame>
</Composer.Provider>
```

Consumers explicitly compose exactly what they need. No hidden conditionals. And the state, actions and meta are dependency-injected by a parent provider, allowing multiple usages of the same component structure.

`<ComposerContext.Provider>` works in React 18 and 19. React 19 also accepts
`<ComposerContext value={...}>`; see [react19-no-forwardref.md](react19-no-forwardref.md).
Memoize the provider `value` per
[state-stable-context-value.md](state-stable-context-value.md). If Server
Components render `Composer.Input`, see
[patterns-polymorphic-parts.md](patterns-polymorphic-parts.md#dot-notation-parts-and-server-components).
