---
description: React ref callbacks must use a block body; an assignment expression body returns a value React 19 treats as cleanup
condition:
  - 'ref=\{\s*(?:\([^()]*\)|\w+)(?:\s*:\s*[^=]+?)?\s*=>\s*\(?\s*[\w$.\[\]]+\s*=(?![=>])'
scope:
  - tool:edit(**/*.{tsx,jsx})
  - tool:write(**/*.{tsx,jsx})
interruptMode: never
---

**`ref={(node) => (refs.current[id] = node)}` returns the node.** React 19 treats a ref callback's return value as its cleanup function, and its TypeScript types reject anything except a function or `undefined`.

- Use a block body: `ref={(node) => { refs.current[id] = node }}`.
- Clean up by returning a function rather than relying on a `null` call:
  `ref={(node) => { refs.current[id] = node; return () => { delete refs.current[id] } }}`.
- The block body also works on React 18, so there's no reason to keep the expression form.
