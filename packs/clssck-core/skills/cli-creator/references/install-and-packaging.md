# Install and Packaging

Per-runtime build, local install, and binary location for a CLI that must run by name from any directory. Runtime choice and the approval rules for PATH changes are in [SKILL.md](../SKILL.md).

## Contents

- [Install commands](#install-commands)
- [Rust](#rust)
- [Go](#go)
- [Node and pnpm](#node-and-pnpm)
- [Bun single binary](#bun-single-binary)
- [Python](#python)
- [Sources](#sources)

## Install commands

Check the toolchain version first (`pnpm --version`, `uv --version`, `go version`); pnpm 11 changed global linking (see [Node and pnpm](#node-and-pnpm)).

|Runtime|Local install|Binary lands in|
|---|---|---|
|Rust|`cargo install --path . --locked`|Install root: `--root`, else `CARGO_INSTALL_ROOT`, else `install.root` config, else `CARGO_HOME`, else `~/.cargo`; binary in its `bin/`|
|Go|`go install ./cmd/<tool-name>`|`$GOBIN`, else `$GOPATH/bin`, else `$HOME/go/bin` (Windows `%USERPROFILE%\go\bin`)|
|Node + npm|`npm install -g .`|npm's global prefix `bin/` directory|
|Node + pnpm ≥ 11|`pnpm add -g .`|`$PNPM_HOME/bin`|
|Bun binary|`bun build ./src/cli.ts --compile --outfile <tool-name>`, then copy into the approved PATH dir|Wherever the copy puts it|
|Python|`uv tool install --editable .`|`uv tool dir --bin`|

Print the bin directory, confirm it is on `PATH`, and only then claim the tool is installed. Not on PATH? Report it and offer the PATH change; NEVER edit shell rc files without approval.

## Rust

- MUST pass `--locked`. Without it `cargo install` ignores the packaged `Cargo.lock` and re-resolves dependencies, so the installed binary can differ from the one you tested.
- User-chosen PATH directory: `cargo install --path . --locked --root <dir>`.

## Go

- Standard library `flag` suffices for flat commands; use a subcommand library only for nested command trees.
- `go install` writes executables to `$GOBIN`, else `$GOPATH/bin`, else `$HOME/go/bin`. Cross-compiled binaries are installed into `$GOOS_$GOARCH` subdirectories of that directory, so install natively and build release artifacts for other platforms separately.

## Node and pnpm

- `package.json` `bin` maps the command name to a file whose first line MUST be `#!/usr/bin/env node`; otherwise npm starts the script without Node.
- pnpm 11 removed `pnpm link --global` and argument-less `pnpm link`; `pnpm link <dir>` now links only into a project's `node_modules`. Global install of a local package is `pnpm add -g .`.

Bad (pnpm ≥ 11):

```bash
pnpm build && pnpm link --global
```

Good:

```bash
pnpm build && pnpm add -g .
```

- pnpm 11 global bins live in `$PNPM_HOME/bin`. If `pnpm bin -g` reports the directory is not in PATH, run `pnpm setup`; it edits shell config, so ask first.

## Bun single binary

`bun build --compile` bundles the code, its dependencies, and the Bun runtime into one executable.

```bash
bun build ./src/cli.ts --compile --minify --sourcemap \
  --no-compile-autoload-dotenv --no-compile-autoload-bunfig \
  --define BUILD_VERSION='"0.1.0"' --outfile <tool-name>
```

- Compiled executables load `.env` and `bunfig.toml` by default; the Bun docs offer the `--no-compile-autoload-*` flags for deterministic execution. A CLI run from arbitrary directories SHOULD disable both unless it deliberately reads them.
- `--define` bakes the version into the binary for `--version` and `doctor`.
- Cross-compile with `--target`: `bun-linux-x64`, `bun-linux-arm64`, `bun-windows-x64`, `bun-windows-arm64`, `bun-darwin-x64`, `bun-darwin-arm64`; `-musl` variants exist for Linux. Windows output gets `.exe` automatically.
- Binaries handed to other macOS users SHOULD be code-signed with `codesign` (Bun ≥ 1.2.4) to avoid Gatekeeper warnings.

## Python

Declare the command in `pyproject.toml`:

```toml
[project.scripts]
<tool-name> = "<package>.cli:main"
```

- Install with `uv tool install --editable .`: the tool gets an isolated environment and source edits apply without a reinstall.
- NEVER `pip install` into system or Homebrew Python; interpreters marked `EXTERNALLY-MANAGED` (PEP 668) make pip refuse, and `--break-system-packages` is the risky override. Use `uv tool install` or a virtualenv.
- `uv tool install` will not overwrite an executable it did not install (e.g. one from `pipx`). Treat that as a name collision: rename the tool or ask. Use `--force` only after the user agrees to replace the existing binary.
- `uv tool update-shell` adds the tool bin directory to shell config; ask first.
- Single-file tool with few dependencies: PEP 723 inline metadata plus an executable file. POSIX shebang:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx"]
# ///
```

On Windows use a `.cmd` or `.ps1` wrapper that runs `uv run --script <path>\<tool-name>.py` instead of the shebang.

## Sources

- Cargo Book, `cargo install`: https://doc.rust-lang.org/cargo/commands/cargo-install.html
- Go, How to Write Go Code (install directory): https://go.dev/doc/code
- Go command reference (`go install`): https://pkg.go.dev/cmd/go
- npm `package.json` `bin` field: https://docs.npmjs.com/cli/v11/configuring-npm/package-json
- pnpm `link` (v11 breaking changes): https://pnpm.io/cli/link
- pnpm `setup`: https://pnpm.io/cli/setup
- Bun single-file executables: https://bun.com/docs/bundler/executables
- uv tools concept (isolation, executable directory, overwrite rules): https://docs.astral.sh/uv/concepts/tools/
- uv scripts guide (inline metadata, `uv run --script` shebang): https://docs.astral.sh/uv/guides/scripts/
- PyPA, Externally Managed Environments (PEP 668): https://packaging.python.org/en/latest/specifications/externally-managed-environments/
