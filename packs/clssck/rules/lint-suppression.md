---
description: Fix the diagnostic instead of adding lint or type-checker suppressions
condition:
  - '#\s*noqa(?!:)'
  - '#\s*(?:type|pyright|ty)\s*:\s*ignore(?!\[)'
  - '#\s*(?:(?:ruff|flake8)\s*:\s*noqa|mypy\s*:\s*ignore-errors|pylint\s*:\s*(?:disable\s*=\s*all|skip-file))'
  - '#\s*!\s*\[\s*allow\s*\(|#\s*\[\s*allow\s*\(\s*(?:warnings|clippy\s*::\s*(?:all|pedantic|nursery|restriction|cargo))\b'
  - '(?://|/\*|\*)\s*(?:@ts-(?:ignore|nocheck)|biome-ignore-all)'
  - '(?:eslint|oxlint)-disable(?:-next-line|-line)?\s*(?:\*/|--|\n|$)'
question: "Decide whether the source contains a real blanket lint or type-check suppression. Step 1, real syntax only: a directive counts only when it is an actual comment (after a `#`, `//` or `/*`, or on a `*` line inside a block comment) or an actual Rust attribute line starting with `#[` or `#![`, with that `#`, `//`, `/*` or attribute outside any quotes. Anything between quotes (single, double, backtick or triple-quoted strings, template literals, docstrings, regexes) is data even when it contains `#`, `//`, `noqa`, `@ts-ignore` or `#![allow(...)]`, and prose that merely mentions a directive is not one; if every candidate is such text, answer NO. Step 2, classify each real directive. YES for file-wide or whole-check forms even when they carry a code, rule name or reason: `# ruff: noqa` and `# flake8: noqa` (the `ruff:` or `flake8:` prefix makes them file-wide even as `# ruff: noqa: F401`), `# mypy: ignore-errors`, `# pylint: disable=all`, `# pylint: skip-file`, `@ts-nocheck`, `biome-ignore-all` and any Rust inner attribute `#![allow(...)]`. YES for any `@ts-ignore`. YES for line forms that name nothing: `# noqa`, `# type: ignore`, `# pyright: ignore` or `# ty: ignore` with no code, and `eslint-disable`, `eslint-disable-line`, `eslint-disable-next-line` or their `oxlint-` equivalents with no rule name, even at end of input. YES for an outer `#[allow(...)]` naming `warnings` or exactly one of `clippy::all`, `clippy::pedantic`, `clippy::nursery`, `clippy::restriction`, `clippy::cargo`; a specific lint that only starts with such a word is narrow. NO for narrow forms: `# noqa: CODE` without a `ruff:` or `flake8:` prefix, coded Python ignores like `# type: ignore[arg-type]`, `@ts-expect-error`, single-line `biome-ignore` naming a rule, ESLint or Oxlint disables naming a rule, and outer Rust `#[allow]` or `#[expect]` naming specific lints. A narrow suppression does not cancel a blanket one elsewhere in the same source."
scope: "tool:edit(**/*.{py,pyi,rs,ts,tsx,mts,cts,js,jsx,mjs,cjs}), tool:write(**/*.{py,pyi,rs,ts,tsx,mts,cts,js,jsx,mjs,cjs})"
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

This reminder is judged, not deterministic. A regex only decides whether the judge is asked about a completed edit or write; the judge then separates real blanket suppressions from strings, ordinary comments and named suppressions. It never interrupts and never fires while a call is still streaming. It runs only when `ttsr.judge` enables judging (`auto` needs the host's native judge, `off` disables it), so with judging off these checks are not applied. It cannot tell new text from re-pasted text, so a blanket suppression you merely moved still counts. File-level and whole-check forms (`# ruff: noqa: F401`, `biome-ignore-all`, `#![allow(dead_code)]`) and `@ts-ignore` count even with a code or reason. Named single-line suppressions and outer attributes naming one lint are not flagged; apply the checks above to them anyway: a verified false positive and a stated reason.
