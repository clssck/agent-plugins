---
description: Protect reusable build and dependency caches from destructive cleanup
condition:
  - '\brm\b[^\n;&|]*(?:node_modules|\btarget\b|\bdist\b|\bbuild\b|bazel-|\.cache|\.venv|\.gradle|\.pnpm-store|pnpm/store|\.npm|\.bun/install/cache|\.cargo|go-build|go/pkg/mod|Library/Caches)'
  - '\b(?:cargo|bazel|bazelisk)\s+clean\b'
  - '\b(?:npm|yarn|pnpm|bun|uv|pip3?)\s+(?:cache\s+(?:clean|clear|prune|purge|rm|remove)|store\s+prune|pm\s+cache\s+rm)\b'
  - '\bgo\s+clean\s+-(?:cache|modcache|testcache|fuzzcache)\b'
scope: "tool:bash"
interruptMode: always
---

Build outputs and dependency caches are reusable user data; broad deletion is destructive. Delete or clean only when the user explicitly requested this exact target; otherwise ask first.

A match is a reminder, not a violation: dry-runs, literal examples, and cleanups the user already requested for this exact target need no extra permission or correction.

## Before deleting

- Resolve the real path and inspect its size before mutation; prove it is the intended cache, not source, a symlink escape, or a shared canonical target.
- Verify no active build, test, server, or package process owns the path. If another process owns it, defer cleanup; stop that process only when its shutdown is explicitly authorized.

```bash
# Good — resolve, size, and check owners before removing
dir=$(realpath target)
du -sh "$dir"
lsof +D "$dir"
```

## Use instead

```bash
# Bad — discards the whole store
rm -rf ~/.pnpm-store

# Good — the tool's documented prune removes only unreferenced packages
pnpm store prune
```

## Not troubleshooting

- NEVER use `chmod`, `chown`, `bazel clean`, `cargo clean`, or recursive removal as default troubleshooting.
- NEVER delete shared Cargo, Bazel, Gradle, Go, Bun, npm, pnpm, uv, pip, or macOS `~/Library/Caches` caches to fix an unrelated failure.

```bash
# Bad — wiping shared caches to chase an unrelated build error
rm -rf ~/.cargo/registry ~/Library/Caches
go clean -modcache
npm cache clean --force
```

## Exceptions

Command-owned temporary directories may be removed after their owner exits.

## Prefer

Prefer the tool's narrow, documented prune operation when it preserves reusable artifacts.
