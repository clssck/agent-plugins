# Cleanup Command

One autonomous cleanup pass over the current repository: discover ONE target → execute completely → verify → report. Stateless: derive everything from the current tree; assume prior passes left it consistent.

## Arguments

`$ARGUMENTS` optional: paths, packages, or modules to focus on, and/or a smell class (`dead`, `dup`, `split`, `move`). Empty → whole repository, any class. Treat arguments as scope hints only; never as shell input.

<critical>
- Behavior-preserving ONLY: public API, CLI, wire/RPC/file formats, and rendered output NEVER change.
- Every pass MUST yield a named, concrete quality win: duplicate implementation gone, responsibility extracted, dead cluster removed, guard clutter deleted. Deletion favored: net-negative LOC is the expectation and the tie-breaker; a net-neutral/positive split or move needs a real win. Report LOC delta either way.
- Fix root causes: wrong type upstream, wrong module home, wrong ownership. NEVER paper over with downstream guards, casts, or wrappers.
- Complete cutover this pass: migrate every copy and callsite; delete originals. NEVER half-migrate or leave re-export shims, aliases, or deprecated paths.
- NEVER commit; NEVER touch generated, vendored, or third-party code.
- No target clears the bar → output exactly `CLEAN: no target above threshold` and stop.
</critical>

## 0. Learn the repository

Before scanning, use the repository instructions already supplied by the host. Read the repository's contributor/development docs, manifests, and scoped configuration; never search for alternate agent-instruction files.

- **Languages**: from manifests (`package.json`, `Cargo.toml`, `pyproject.toml`, `go.mod`, `*.csproj`, `Gemfile`, …) and file extensions actually present. Clean only languages the repo authors.
- **Exclusions**: `.gitignore`, `.gitattributes` (`linguist-generated`, `linguist-vendored`), formatter/linter ignore files, codegen config, and header markers (`@generated`, `DO NOT EDIT`). Always exclude lockfiles, snapshots/fixtures, build output, vendored trees, and declaration/bindings output.
- **Package boundaries**: workspace definitions (workspace globs, Cargo workspace members, Go modules, multi-project build files). Public surface = explicit exports maps, public barrels/entry points, `pub` crate API, documented CLI. Wildcard subpath exports expose files mechanically, not contractually.
- **Checks and formatter**: the commands the repo documents or wires into manifests/task runners (`scripts`, `Makefile`, `justfile`, `Taskfile`, release/build automation). Record the exact type-check, lint, test, and format commands; prefer the narrowest documented scope (per package/file).

Instructions conflict with this command → repository instructions win. No documented check exists for a language → state that in the report instead of inventing one.

## 1. Discover

Use LSP (references, diagnostics, unused-symbol hints), compiler/linter warnings from documented checks, and targeted `grep`/`find`. Read every candidate before judging it; tool output is evidence, not verdict.

**Dead weight** — highest value/risk
- Exported symbols with zero in-repo references. Symbols reachable from the public surface are PROTECTED: external consumers are invisible.
- Unpassed options/parameters; unreachable branches; unused config keys.
- Compatibility shims, deprecated aliases, re-export indirection left by past refactors.
- Runtime checks duplicating type-system or boundary-validation guarantees.

**Duplication**
- Helper reimplemented in 2+ files; copies differing only by a literal/flag.
- Inline reimplementation of an existing central utility (paths, truncation, process spawning, stream reading, caching, retries).
- Parallel switch/if chains dispatching on the same discriminant in multiple places.
- Literal-heavy tables/descriptors repeat intentionally; extract only when one helper genuinely simplifies every site.

**God objects**
- File dwarfs its siblings AND mixes responsibilities (state + IO + rendering + parsing), or a type's methods span domains. Large coherent files are fine.

**Hierarchy rot**
- Domainless junk drawers (`utils`, `helpers`, `misc`, `common`) holding unrelated accretions.
- Deep relative imports signalling a wrong module home.
- Directories grouped by kind (`types/`, `constants/`, `interfaces/`) instead of domain.
- Unused barrels, single-file directories, names that no longer describe contents.

## 2. Select

Score `(quality win × confidence) / blast radius`. Pick exactly ONE cluster small enough to migrate completely and review in one sitting. Tie-break: deletion > dedup > split > move; equal → larger LOC reduction.

Bar: the win fits in one sentence and is substantial for this codebase — an entire duplicate implementation or dead cluster removed, a multi-responsibility file split on real seams, a junk drawer or guard-clutter hotspot eliminated, a module cluster moved so the tree reads designed, not accreted. Cosmetic churn never clears it.

## 3. Execute

**Dead weight / redundant checks**
- Delete dead symbols and tests that only mirror them. Deletion requires BOTH: LSP references (or exhaustive grep where no LSP exists) show no callsites — a missed callsite is a bug; and the symbol is not reachable from the public surface. Either fails → keep.
- Narrow once at the IO boundary; internal code receives the narrowed type. Delete downstream null-propagation on non-nullable values, fallbacks on non-optional values, re-narrowing, and casts papering over flow.
- Genuinely sometimes-absent value → fix the TYPE upstream; NEVER add downstream guards.
- Swallow-and-limp error handling → delete or propagate. Catch only precise, expected errors.

**Dedup**
- 2+ copies → one function in the nearest common domain module; cross-package → the repo's existing shared package. NEVER create a junk drawer.
- Literal/flag variants → one function with a named-options parameter; NEVER boolean positionals.
- Keep the hardened copy (timeouts, caps, sanitization, error context), not a fresh copy lacking it.

**God objects**
- Split along existing seams into domain-named, single-responsibility modules.
- Extraction = MOVEMENT: code verbatim except imports/visibility; rewriting while moving hides regressions.
- Update every importer; NEVER keep a re-export shim. A split that introduces an interface, base class, event bus, or DI where a direct call existed has failed.

**Hierarchy**
- Move files with LSP rename/move support where available so imports update everywhere; otherwise update every importer explicitly.
- Group by domain, not kind; collapse single-file directories; delete empty barrels. The result MUST read as always designed.

**Perf** — opportunistic, only in code already touched
- Hoist loop invariants, precompile patterns, single pass instead of chained transforms on hot paths, drop intermediate copies. NEVER trade cold-path clarity for micro-perf; NEVER add caching layers.

## 4. Prohibitions

- NEVER add dependencies, config/options, feature flags, wrapper layers, single-implementation abstractions, or "future-proofing".
- NEVER rename or alter the public surface.
- NEVER reformat/restyle outside the touched cluster; NEVER sweep comments/docs; comment only new non-obvious code.
- NEVER add tests for moved-but-unchanged code; keep passing tests, relocating them with their subject.

## 5. Verify

1. Run the repository's documented formatter on edited files only, then its type-check/lint for affected packages: clean.
2. Run tests scoped to affected packages/files using the documented test command.
3. Rendering/output code touched → confirm every output path still goes through the same escaping/sanitization as before.
4. Grep for every deleted/moved symbol and old path: zero stale references, including docs and config.

Any check fails and the fix is not a straightforward completion of this cutover → stop and report the failing state. NEVER discard the working tree or overwrite pre-existing edits; undo only hunks proven to belong to this pass and only when safe.

## 6. Report

- Target: chosen cluster and smell class.
- Actions: deleted/merged/split/moved; named quality win; LOC delta.
- Verification: exact commands run and their results; checks unavailable in this repo.
- Risk: what a reviewer should check.

<critical>
One target per pass; complete migration; originals deleted; documented checks clean. Named quality win; identical behavior; no new abstractions or shims. Deletion-leaning: justify a net-positive delta. Nothing clears the bar → `CLEAN: no target above threshold`.
</critical>
