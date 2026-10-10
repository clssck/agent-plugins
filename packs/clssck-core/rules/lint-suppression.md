---
description: Fix the diagnostic instead of adding lint or type-checker suppressions
condition:
  - '#[ \t]*(?:noqa(?![\w:-])(?![ \t]*:)(?=[ \t\r\n])|(?:ruff|flake8)[ \t]*:[ \t]*noqa\b|(?:type|pyright|ty)[ \t]*:[ \t]*ignore(?![\w-])(?![ \t]*\[)(?=[ \t\r\n])|mypy[ \t]*:[ \t]*ignore-errors\b|pylint[ \t]*:[ \t]*(?:disable[ \t]*=[ \t]*all\b|skip-file\b))'
  - '#!\[allow\(|#\[allow\([^)\]]*\b(?:warnings|clippy::(?:all|pedantic|nursery|restriction|cargo))(?=[,\s)\]])'
  - '(?://|/\*)[ \t]*(?:@ts-(?:ignore|nocheck)\b|(?:eslint|oxlint)-disable(?:-next-line|-line)?(?=[ \t]*(?:\*/|--|\r?\n))|biome-ignore-all\b|biome-ignore(?:-start)?[ \t]+lint[ \t]*:)'
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
- This reminder flags blanket or high-risk suppressions only: bare `# noqa`, `# type: ignore`, `# pyright: ignore`, `# ty: ignore`, file-level `# ruff: noqa`, `# mypy: ignore-errors`, `# pylint: disable=all`, `#![allow(...)]`, `#[allow(warnings)]`/`clippy::all`/`clippy::pedantic`, `@ts-ignore`, `@ts-nocheck`, rule-less `eslint-disable`/`oxlint-disable`, and `biome-ignore-all`. It cannot tell new text from re-pasted text, so a blanket suppression you merely moved still matches.
- Named single-line suppressions never match. Apply the checks above to them anyway: a verified false positive and a stated reason.
