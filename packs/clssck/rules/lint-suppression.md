---
description: Fix the diagnostic instead of adding lint or type-checker suppressions
condition:
  - '#\s*noqa(?!:)'
  - '#\s*(?:type|pyright|ty):\s*ignore(?!\[)'
  - '#\s*(?:ruff|flake8):\s*noqa|mypy:\s*ignore-errors|pylint:\s*(?:disable=all|skip-file)'
  - '#!\[allow\(|#\[allow\((?:warnings|clippy::(?:all|pedantic|nursery|restriction|cargo))\b'
  - '@ts-(?:ignore|nocheck)|biome-ignore-all'
  - '(?:eslint|oxlint)-disable(?:-next-line|-line)?\s*(?:\*/|--|\n|$)'
scope: "tool:edit(**/*.{py,pyi,rs,ts,tsx,mts,cts,js,jsx,mjs,cjs}), tool:write(**/*.{py,pyi,rs,ts,tsx,mts,cts,js,jsx,mjs,cjs})"
interruptMode: never
---

A suppression hides a diagnostic; it does not fix the code. Lint and type errors usually point at a real defect, an unsafe call, or a wrong type.

## Fix the cause first

Correct the type, narrow the value, restructure the call, or use the safe API the rule points to.

```python
# Bad
port = int(os.environ.get("PORT"))  # type: ignore

# Good
port = int(os.environ.get("PORT", "8080"))
```

## When a suppression is justified

Keep a suppression only when the diagnostic is a verified false positive or the flagged behaviour is intentional and safe. Then make it as narrow as possible: one line, one named code. MUST state why the code is correct despite the diagnostic, in the suppression or an adjacent comment.

|Language|Blanket (Bad)|Narrow form (Good)|
|---|---|---|
|Python|bare `# noqa`, `# type: ignore`, `# pyright: ignore`, `# ty: ignore`; file-level `# ruff: noqa`, `# mypy: ignore-errors`, `# pylint: disable=all`|`# noqa: S603`, `# type: ignore[arg-type]`, `# ty: ignore[invalid-argument-type]`|
|Rust|`#![allow(...)]`, `#[allow(warnings)]`, `#[allow(clippy::all)]`/`clippy::pedantic`|`#[expect(<lint>, reason = "...")]` on the smallest item instead of `#[allow]`; `expect` warns once the suppression is no longer needed|
|TypeScript|`@ts-ignore`; NEVER `@ts-nocheck`|`@ts-expect-error <reason>`|
|Biome|`biome-ignore-all`|`// biome-ignore lint/<group>/<rule>: <reason>`|
|ESLint / Oxlint|rule-less `eslint-disable` / `oxlint-disable`|`// eslint-disable-next-line <rule> -- <reason>`|

```python
# Bad
subprocess.run(cmd)  # noqa

# Good
# cmd is a fixed argv list built above; no shell, no user input.
subprocess.run(cmd)  # noqa: S603
```

```rust
// Bad
#![allow(clippy::all)]

// Good
#[expect(clippy::too_many_arguments, reason = "mirrors the C ABI signature")]
fn ffi_init(a: u32, b: u32, c: u32, d: u32, e: u32, f: u32, g: u32, h: u32) {}
```

## Verification

NEVER suppress to make a check pass when the project's lint or type check is part of verification; report the remaining diagnostic instead.

## What this reminder matches

This reminder matches only the blanket forms in the Bad column. It cannot tell new text from re-pasted text, so a blanket suppression you merely moved still matches. Named single-line suppressions never match; apply the checks above to them anyway: a verified false positive and a stated reason.
