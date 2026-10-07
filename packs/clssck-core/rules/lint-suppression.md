---
description: Fix the diagnostic instead of adding lint or type-checker suppressions
condition:
  - '#[ \t]*(?:noqa\b|type:[ \t]*ignore|pyright:[ \t]*ignore|ty:[ \t]*ignore|mypy:[ \t]*ignore)'
  - '#!?\[allow\('
  - '(?://|/\*)[ \t]*(?:@ts-(?:ignore|expect-error|nocheck)|eslint-disable|biome-ignore|oxlint-disable)'
scope:
  - tool:edit(**/*.{py,pyi,rs,ts,tsx,mts,cts,js,jsx,mjs,cjs})
  - tool:write(**/*.{py,pyi,rs,ts,tsx,mts,cts,js,jsx,mjs,cjs})
interruptMode: never
---

**A suppression hides a diagnostic; it does not fix the code.** Lint and type errors usually point at a real defect, an unsafe call, or a wrong type.

- Fix the cause first: correct the type, narrow the value, restructure the call, or use the safe API the rule points to.
- Keep a suppression only when the diagnostic is a verified false positive or the flagged behaviour is intentional and safe. Then make it as narrow as possible:
  - One line, one named code: `# noqa: S603`, `# type: ignore[arg-type]`, `# ty: ignore[invalid-argument-type]`, `// biome-ignore lint/<group>/<rule>: <reason>`, `// eslint-disable-next-line <rule> -- <reason>`.
  - Rust: `#[expect(<lint>, reason = "...")]` on the smallest item instead of `#[allow]`; `expect` warns once the suppression is no longer needed.
  - TypeScript: `@ts-expect-error <reason>` instead of `@ts-ignore`; never `@ts-nocheck`.
- Always state why the code is correct despite the diagnostic, in the suppression or an adjacent comment.
- NEVER suppress to make a check pass when the project's lint or type check is part of verification; report the remaining diagnostic instead.
- Unchanged suppressions you merely moved or re-pasted are out of scope.
