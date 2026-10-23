# Binary and Package Surface

Static analysis answers a specific question about a build: which secrets and endpoints it embeds, which libraries it links, how managed or wasm structure is organized, and which exact build it is. Work from primitives — identify, unpack, extract, disassemble — and choose the engine you already have. OMP's IDA integration is preferred when available; Ghidra headless, `objdump`, or a helper the agent writes are equal alternatives.

## Boundaries

- Analyze artifacts from authorized targets or the operator's own builds.
- Static reads only. The target is never executed by this path.
- Every artifact records path, `sha256`, size, and source; extracted output stays in the task output directory.
- Strings, symbols, and decompiler output are candidates, never confirmed secrets or vulnerabilities; verify against configuration or a live response.
- A missing toolchain is not a blocker: switch primitive, use an available engine, or write a bounded helper. Record which path and version produced the evidence.
- Do not install third-party packages or MCP servers into the host without explicit authorization.

## Artifact classes

ELF, PE, Mach-O, APK, IPA, HAP, WASM, ZIP/JAR, Electron archives, and obfuscated JavaScript bundles. Save downloads under `assessment/`, hash them, and retain the raw file only when the engagement permits.

## Primitives

| Question | Primitive | Example |
|---|---|---|
| What is this? | Magic and hash | `file`, `sha256sum`, manifest read |
| What is inside the container? | Archive listing and extraction | `unzip -l`, `jar tf`, `tar tf`, `7z l` |
| What constants and strings? | String sweep | `strings -a -n 6`, `grep -E` |
| What libraries and imports? | ELF/PE/Mach-O headers | `readelf -d`, `objdump -p`, `otool -L` |
| What symbols and calls? | Symbol/disassembly | `nm -C`, `objdump -d`, IDA or headless Ghidra |
| What managed structure? | Metadata and decompile | `jadx`, `ilspycmd`, IDA/.NET, `monodis` |
| What wasm modules? | Binary/text form | `wasm-objdump -x`, `wasm2wat` |
| What does the JS bundle call? | Parse or instrument | `eval` with an AST parser; targeted regex only as a fallback |

## Workflow

1. **Identify.** Format, platform, hash, package manifest; record the toolchain that will read it.
2. **Unpack.** List first, then extract only the members the question needs; keep the tree and a file count.
3. **Sweep constants.** Query secrets, tokens, keys, endpoints, hosts, debug flags, test accounts, base64 blobs, and build paths. Each hit records its member or address and matching pattern.
4. **Map structure.** Imports/exports, procedures, native libraries, managed type graphs, wasm modules, embedded manifests, third-party versions.
5. **Correlate.** Match embedded endpoints and identifiers to the live surface; keep them `static_candidate` until a request observes them.
6. **Record.** Artifact path, hash, primitive and version, decisive output, unresolved questions.

## Build the missing primitive

`eval` first for parsing, extraction, and diffing. A bounded helper belongs in the task output directory with its source, command shape, and inputs recorded. Prefer the smallest parser that answers the question: a JSON/plist reader over a full decompiler, a symbol diff over a whole-binary analysis. Decompiler output is an aid to reading code; a claim still rests on the code or the observed behavior.
