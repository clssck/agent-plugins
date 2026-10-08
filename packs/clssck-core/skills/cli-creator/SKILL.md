---
name: cli-creator
description: Build a durable, composable CLI from API docs, OpenAPI, curl examples, an SDK, a web app, or an existing script, with stable JSON output, auth handling, and a companion omp skill. Use when a tool must run by command name from any directory. Not for one-off scripts that fit in the current repo.
---

# CLI Creator

Build a real CLI an agent can run by command name from any working directory, plus a companion omp skill that teaches it.

Durable tools only. A short script in the current repo solves the task? Write the script there.

## Start

Name three things before scaffolding:

|Item|Examples|
|---|---|
|Source|API docs, OpenAPI JSON, SDK docs, curl examples, browser app, internal script, shell history|
|First jobs|`list drafts`, `download failed job logs`, `search messages`, `upload media`|
|Install name|Short binary: `ci-logs`, `slack-cli`, `buildkite-logs`|

- Personal tool location: `~/code/clis/<tool-name>` (PowerShell: `$env:USERPROFILE\code\clis\<tool-name>`), unless the user names a repository.
- Creating a new directory is a local write; state the location first.
- Check the name is free before scaffolding:

```bash
command -v <tool-name> || true
```

```powershell
Get-Command <tool-name> -ErrorAction SilentlyContinue
```

- Name exists? Choose a clearer install name or ask.

## Platform Preflight

Detect OS, active shell, toolchains, repository convention, and a user-writable PATH directory before generating install commands. NEVER emit PowerShell syntax for a POSIX shell or the reverse.

```bash
command -v cargo rustc node pnpm npm python3 uv
echo "$PATH"; echo "${XDG_CONFIG_HOME:-$HOME/.config}"; echo "${TMPDIR:-/tmp}"
```

```powershell
Get-Command cargo, rustc, node, pnpm, npm, python, uv -ErrorAction SilentlyContinue
$env:TEMP
[Environment]::GetEnvironmentVariable('Path', 'User')
```

- Use the repository's existing package manager and install convention when one exists.
- Search source material with `grep`, `glob`, `read`; NEVER shell `rg`/`find`/`Select-String`.

## Choose the Runtime

|Runtime|Choose when|
|---|---|
|Rust (default)|Durable CLI wanted: one fast binary, strong arg parsing, good JSON|
|TypeScript/Node|Official SDK, auth helper, browser automation, or existing repo tooling is the advantage|
|Python|Data work, local file transforms, SQLite/CSV/JSON analysis, Python-heavy admin tooling|
|Go|Repo or team already uses Go; one static binary, easy cross-compile|

- NEVER pick a language that adds setup friction without material benefit.
- Best language missing? Install the toolchain with user approval, or take the next-best installed option.
- MUST state the choice in one sentence before scaffolding: reason plus toolchain found.

Defaults per runtime:

|Runtime|Use|
|---|---|
|Rust|`clap`, `reqwest`, `serde`/`serde_json`, `toml`, `anyhow`|
|TypeScript/Node|`commander` or `cac`; native `fetch` or official SDK; `zod` only where payload validation prevents real breakage; `package.json` `bin` (first line `#!/usr/bin/env node`); build tool per repo (`tsup`, `tsx`, `tsc`); `bun build --compile` for a single binary with no Node on the target|
|Python|`argparse` (or `typer` for deep subcommands); `urllib`/`requests`/`httpx` matching nearby code; `json`, `csv`, `sqlite3`, `pathlib`, `subprocess`; `pyproject.toml` `[project.scripts]`; `uv`/virtualenv only when dependencies need it|
|Go|Standard `flag` for flat commands; `go install` for local install|

- Add an install target matching repo and platform: `make install-local`, `cargo install --path . --locked`, `pnpm build` + `pnpm add -g .` (pnpm 11 removed `pnpm link --global`), `uv tool install --editable .`, or a PowerShell script on Windows. Per-runtime commands, bin locations, and gotchas: [install-and-packaging.md](references/install-and-packaging.md).
- Document what the install depends on (`uv`, virtualenv, system Python).
- Install into a user-approved, user-writable PATH directory; NEVER assume `~/.local/bin`. NEVER `pip install` into system Python (PEP 668).

## Command Contract

Sketch the command surface in chat before coding: binary name, discovery, resolve, read, write, raw escape hatch, auth/config choice, install command. Shape, JSON policy, pagination, and exit codes: [agent-cli-patterns.md](references/agent-cli-patterns.md).

## Auth and Config

Precedence:

1. Environment variable with the service's standard name (`GITHUB_TOKEN`).
2. User config in a documented OS-appropriate directory: `~/.config/<tool-name>` (Windows: `$env:APPDATA\<tool-name>`).
3. `--token-file <path>` or token on stdin (`--with-token`, as `gh auth login` does) for headless setup. NEVER accept a secret as a plain flag value: it leaks into `ps` output and shell history.

- NEVER print full tokens.
- `doctor --json` reports: token available, auth source category (`env`, `config`, `token-file`, `stdin`, provider default, `missing`), missing setup step.
- Works offline or without auth? `doctor --json` says so: fixture mode, fixture found, auth not required.
- Internal web app from DevTools curls? Write sanitized endpoint notes first: resource, method/path, required headers, auth, CSRF, request body, response ID fields, pagination, errors, one redacted sample.
- NEVER commit copied cookies, bearer tokens, customer secrets, full production payloads.
- Screenshots show workflow and vocabulary; NEVER treat them as API evidence without a request, export, docs page, or fixture.

## Build Workflow

1. Read the source to inventory resources, auth, pagination, IDs, file flows, rate limits, dangerous writes. OpenAPI available? Inspect it before naming commands.
2. Sketch the command list in chat; short, shell-friendly names.
3. Scaffold with a README or equivalent.
4. Implement `doctor`, discovery, resolve, reads, one narrow draft or dry-run write if requested, raw escape hatch.
5. Install on PATH only when the user asks for a globally callable command; state the target location first. Otherwise keep the verified local wrapper.
6. Smoke test from a fresh directory, not `cargo run` or package-manager wrappers.
7. Run format, typecheck/build, unit tests (request builders, pagination, body builders), no-auth `doctor`, help output, and one fixture, dry-run, or live read-only call.

Smoke test, installed on PATH:

```bash
cd "$(mktemp -d)" && command -v <tool-name> && <tool-name> --help && <tool-name> --json doctor
```

```powershell
Set-Location (New-Item -ItemType Directory (Join-Path $env:TEMP "smoke-$(Get-Random)"))
Get-Command <tool-name>; <tool-name> --help; <tool-name> --json doctor
```

Not installed on PATH: run the wrapper or binary by absolute path from the fresh directory; NEVER install just to pass the smoke test.

Rules:

- Live write needed for confidence? Ask first; make it reversible or draft-only.
- Raw escape hatch: reads first; NEVER run non-GET/HEAD requests against a live service unless the user asked for that write.
- Existing script or shell history: split into phases (setup, discovery, download/export, transform/index, draft, upload, poll, live write); keep the user's flags, paths, env vars; wrap repeatable phases with stable IDs, bounded JSON, file outputs.
- Fixture-backed prototype: fixtures at a predictable path the installed CLI can find; smoke test from a temp directory (`${TMPDIR:-/tmp}`; Windows `$env:TEMP`).
- Log-oriented CLI: deterministic snippet extraction separate from model interpretation; emit filenames, line numbers or byte ranges, matched rules, short excerpts.

## Companion Skill

After the CLI works, create or update a companion skill. It is a normal omp skill.

|Location|Path|Use when|
|---|---|---|
|User skills|`~/.omp/agent/skills/<tool-name>/SKILL.md` (Windows: `$env:USERPROFILE\.omp\agent\skills\<tool-name>\SKILL.md`)|Personal tool, default|
|Pack|`skills/<tool-name>/SKILL.md` in an agent-plugins pack, e.g. `clssck-core`|User names a pack or repo|
|Project|`.omp/skills/<tool-name>/SKILL.md`|Tool belongs to one repository|

Contract:

- One level deep: `<skills-root>/<tool-name>/SKILL.md`; folder name = `name`.
- Frontmatter: only `name` and `description` (plus omp keys `hide`, `disable-model-invocation`, `globs`, `alwaysApply` if needed).
- Description: what the CLI does, then `Use when ...` with concrete triggers, then `Not for ...` when a sibling fits better. Under ~350 characters.
- Body: `# Title`, purpose, ordered workflow, rules, `## Checklist`; under ~150 lines.
- Detail goes in `references/*.md`; link with relative Markdown links. Every file linked from `SKILL.md`.
- Scripts: `python3 skill://<tool-name>/scripts/<file>.py`.
- Body skeleton and content list: [agent-cli-patterns.md](references/agent-cli-patterns.md#companion-skill).
- Verify: `/skill:<tool-name>` loads, every link resolves, example commands run from a fresh directory.

## Checklist

- Source, jobs, install name stated; name free of collisions.
- Runtime choice stated with reason.
- `--help`, `--version`, `--json doctor`, discovery, resolve, reads, raw escape hatch present.
- Runs without a TTY: no prompts without one, documented nonzero exit codes, `NO_COLOR` honored, network timeout set.
- Auth never printed; secrets never accepted as flag values; errors under `--json` carry no credentials.
- Smoke test ran from a fresh directory with the right command form.
- No live write without user approval.
- Companion skill in an omp location with valid frontmatter and working links.

License: [LICENSE.txt](LICENSE.txt).
