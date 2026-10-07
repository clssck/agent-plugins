---
description: Select the pinned Rust toolchain from the correct workspace
condition:
  - '^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:(?!RUSTUP_TOOLCHAIN=)[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command)(?:\s+--)?)\s+)*cargo(?![ \t]+\+\S+)(?=[ \t])(?=(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|''[^''\n]*''|[^\s;&|()''"#]+))*?[ \t]+--manifest-path(?:=|[ \t]+))'
  - '^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:(?!RUSTUP_TOOLCHAIN=)[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command)(?:\s+--)?)\s+)*rustc(?![ \t]+\+\S+)(?=[ \t])(?=(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|''[^''\n]*''|[^\s;&|()''"#]+))*?[ \t]+(?:--crate-name(?:=|[ \t]+)|"[^"\n]+\.rs"|''[^''\n]+\.rs''|[^\s;&|()''"#]+\.rs(?=\s|$|[;&|)])))'
scope: tool:bash
---

**`--manifest-path` selects a Cargo manifest; it does not select a rustup toolchain.**

- Pinned workspace? Set the Bash `cwd` inside the workspace that contains `rust-toolchain` or `rust-toolchain.toml`.
- Cannot use that `cwd`? Select explicitly with `cargo +<channel>` or `RUSTUP_TOOLCHAIN=<channel>`.
- Toolchain identity matters? Run `rustup show active-toolchain` from the same `cwd` before building or testing.
- Keep Cargo, `rustc`, tests, and build scripts in the same toolchain-selecting context.
- NEVER change the global rustup default or install a persistent directory override unless the user requests it.
- No pinned workspace? Proceed with the installed default after observing `rustc --version`.