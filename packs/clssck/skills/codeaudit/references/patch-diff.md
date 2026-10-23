# Patch Diff

Recover the bug from the vendor fix that closed it: obtain both builds, align symbols, diff, read the added guards, infer the class, and prove it with a PoC that triggers only the unpatched build.

## Boundaries

- Diff and test builds in your own lab, inside written scope, or in a benchmark range.
- Run a recovered PoC only against builds you own; an advisory covering the bug does not authorize a live target.
- Publish with `{target}`, `{host}`, `{user}` placeholders; keep real hostnames and paths inside the lab.
- If the diff toolchain is missing (`ghidriff`, BinDiff, Diaphora, `radiff2`), report the gap and stop. Never simulate diff output or a clean patched run.

## Workflow

1. **Frame.** Component, affected and fixed versions, advisory bug class; record both build IDs and `sha256`.
2. **Obtain builds.** Windows: update-catalog MSU, `expand`, inner CAB. Linux: `apt download` or distribution pool for both versions, `dpkg-deb -x`, recover `vmlinux` from `vmlinuz` plus dbgsym/System.map. Third party: vendor N-1 and N installers.
3. **Align symbols.** Windows: `symchk /v <module> /s SRV*c:\sym*https://msdl.microsoft.com/download/symbols`. Linux: vmlinux plus `System.map` or dbgsym for both builds. Without symbols annotate by strings, imports, and call shape first.
4. **Diff.** Preferred `ghidriff old new -o out/` (needs Java plus a Ghidra install); BinDiff or Diaphora only where an IDA/Ghidra export already exists. Same compiler and toolchain; compiler churn is noise.
5. **Locate the security change.** Moderate similarity functions (roughly 0.5–0.95); read added conditions, bounds, locks, zeroing, refcounts; deleted blocks are clues.
6. **Infer the class** from the guard table, then read the pre-patch path for reachability and attacker control.
7. **PoC.** Drive boundary values for the class; run the same harness on the patched build and record the clean result.
8. **Record.** Hashes, diff artifacts, guard locations, class, PoC, before/after, residual uncertainty.

## PoC shapes

| Class | PoC shape |
|---|---|
| Integer overflow | `INT_MAX-1`, `0xFFFFFFFF`, arithmetic wrap at the guard |
| Race / TOCTOU | Concurrent threads on open/close plus the ioctl path |
| Use-after-free | Spray, free, reuse in the same allocation class |
| Out-of-bounds | Index or length just past the new guard |
| Missing permission | Same request without the privilege the new check requires |

## Guard to class

| New guard | Likely class |
|---|---|
| `if (a + b < a)`, `__builtin_add_overflow` | Integer overflow |
| Spinlock or mutex added around shared state | Race, TOCTOU, double free |
| `if (idx >= MAX)`, `if (len > buf_size)` | Out-of-bounds read or write |
| `RtlZeroMemory`, `memset(struct, 0, ...)` | Uninitialized-memory info leak |
| Refcount check plus decrement | Use-after-free |
| `ProbeForRead` / `ProbeForWrite` | Unvalidated user pointer |
| Access check or capability test | Missing permission check |
| Removed or narrowed IOCTL/command codes | Attack-surface reduction; study the old path |

## Warnings

- A patch can shrink the surface instead of fixing the bug; re-check alternate paths.
- Mitigations are not fixes and do not establish root cause.
- A fix can be incomplete; retest the original trigger.
- Backports differ; diff the exact builds you claim.

## Deliverables

`builds.json` (versions, sources, hashes), `diff/` (function diff, annotated change), `analysis.md` (class, guards, reachability, alternatives), `poc/` (harness, unpatched result, patched clean result). A PoC without the clean patched comparison proves nothing.
