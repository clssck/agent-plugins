# Sonner API Reference

Exact props, types, and defaults, checked against `sonner` 2.0.8. Types come from `node_modules/sonner/dist/index.d.ts`, but defaults are runtime behavior: read them from the implementation (`dist/index.mjs`: `VIEWPORT_OFFSET`, `TOAST_LIFETIME`, `GAP`, `VISIBLE_TOASTS_AMOUNT`, the `Toaster` destructuring) and confirm in the browser. When the project pins another version, its installed files win over this table. Options passed to `toast()` override the same options set via the Toaster's `toastOptions`.

## `<Toaster />`

| Prop | Type | Default | Description |
| --- | --- | --- | --- |
| `theme` | `string` | `'light'` | `'light'`, `'dark'`, or `'system'`. |
| `richColors` | `boolean` | `false` | Makes error and success states more colorful. |
| `expand` | `boolean` | `false` | Toasts expanded by default (otherwise they expand on hover). |
| `visibleToasts` | `number` | `3` | Amount of visible toasts. |
| `id` | `string` | – | Toaster id, targeted by `toast()`'s `toasterId` option. |
| `position` | `string` | `'bottom-right'` | `top-left`, `top-center`, `top-right`, `bottom-left`, `bottom-center`, `bottom-right`. |
| `closeButton` | `boolean` | `false` | Adds a close button to all toasts. |
| `offset` | `string \| number \| object` | `'24px'` | Offset from screen edges. Object form is per-side: `{ bottom: '24px', right: '16px' }`. |
| `mobileOffset` | `string \| number \| object` | `'16px'` | Offset when screen width < 600px. |
| `swipeDirections` | `array` | based on position | Allowed swipe-to-dismiss directions. |
| `dir` | `string` | document direction | `'ltr'`, `'rtl'`, or `'auto'`; follows the page's `dir` when unset. |
| `duration` | `number` | `4000` | Default auto-close time for every toast; a toast's own `duration` wins. |
| `hotkey` | `string[]` | `['altKey', 'KeyT']` | Keys (event modifier names or `KeyboardEvent.code` values) that focus the toaster area together. |
| `invert` | `boolean` | `false` | Dark toasts in light mode and vice versa. |
| `toastOptions` | `object` | – | Defaults for every toast, limited to: `className`, `descriptionClassName`, `style`, `classNames`, `unstyled`, `closeButton`, `duration`, `actionButtonStyle`, `cancelButtonStyle`, `closeButtonAriaLabel`, `toasterId`. |
| `gap` | `number` | `14` | Gap between toasts when expanded. |
| `icons` | `object` | – | Replace default icons: `{ success, info, warning, error, loading, close }`; `null` removes one. |
| `containerAriaLabel` | `string` | `'Notifications'` | ARIA label for the toast container; the hotkey label is appended. |
| `customAriaLabel` | `string` | – | Replaces the whole container label, hotkey hint included. |

## `toast()` options

`toast(message, options)` — message is a string, JSX, or a function returning JSX. Returns the toast's id.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `description` | `ReactNode` | – | Renders underneath the title; also accepts a function returning JSX. |
| `closeButton` | `boolean` | `false` | Adds a close button. |
| `invert` | `boolean` | `false` | Dark toast in light mode and vice versa. |
| `duration` | `number` | `4000` | Milliseconds before auto-close. `Infinity` persists the toast. |
| `position` | `string` | `'bottom-right'` | Position of this toast. |
| `dismissible` | `boolean` | `true` | If `false`, the user cannot dismiss the toast. |
| `icon` | `ReactNode` | – | Icon in front of the text; `null` removes the default. |
| `action` | `ReactNode \| { label, onClick }` | – | Primary button; clicking closes the toast unless `onClick` calls `event.preventDefault()`. |
| `cancel` | `ReactNode \| { label, onClick }` | – | Secondary button; clicking closes the toast. |
| `actionButtonStyle` | `object` | `{}` | Styles for the action button. |
| `cancelButtonStyle` | `object` | `{}` | Styles for the cancel button. |
| `id` | `string` | – | Custom id; calling `toast()` again with the same id updates the existing toast. |
| `testId` | `string` | – | Rendered as `data-testid` for e2e tests. |
| `toasterId` | `string` | – | Id of the toaster to render this toast in. |
| `style` | `object` | – | Inline styles for the toast. |
| `classNames` | `object` | – | Classes per part: `{ toast, title, description, actionButton, cancelButton, closeButton }`. Needs `!important` unless `unstyled`. |
| `unstyled` | `boolean` | `false` | Removes all default styles. |
| `onDismiss` | `(toast) => void` | – | Fires when the close button is clicked, the toast is swiped away, or it is closed with `toast.dismiss()`. |
| `onAutoClose` | `(toast) => void` | – | Fires when the toast closes automatically after `duration`. |

## Functions

| Function | Purpose |
| --- | --- |
| `toast(message, opts?)` | Render a toast; returns its id. |
| `toast.success / .error / .info / .warning(message, opts?)` | Typed toast with matching icon. |
| `toast.loading(message, opts?)` | Toast with a spinner; update it by id. |
| `toast.promise(promise, { loading, success, error, finally })` | Loading toast that settles with the promise; `success`/`error` accept strings, JSX, functions of the result, or `{ message, ...toastOptions }` (return that object to give the outcome its own `action`, `duration`, `description`). Without the options argument it returns `undefined` and creates no toast. With `loading` it returns the toast id with `.unwrap()` attached; without `loading` no toast shows until it settles and the return value is only `{ unwrap }`. `.unwrap()` resolves or rejects with the promise. A resolved `Error` or non-ok `Response` takes the `error` path; an omitted handler dismisses the toast. |
| `toast.custom((t) => jsx, opts?)` | Headless toast — your JSX, Sonner's behavior. |
| `toast.dismiss(id?)` | Dismiss one toast, or all when called without an id. |
| `toast.getToasts()` | Active toasts, usable outside React. `toast.getHistory()` also includes dismissed ones. `toast.getActiveToasts` does not exist on the `toast` object. |
| `useSonner()` | React hook returning `{ toasts }`. |
