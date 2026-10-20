---
name: cli-creator
description: Build a durable, installable CLI from API docs, OpenAPI specs, SDKs, curl captures, internal scripts, or shell history, plus a companion omp skill that teaches it. Use when asked to wrap a service or API as a command-line tool, make a script callable from anywhere, add doctor/JSON/pagination to a CLI, or package and install a binary on PATH. Not for one-off scripts or CI/CD pipeline authoring.
---

# CLI Creator

Builds a real CLI an agent runs by command name from any working directory, plus a companion omp skill that teaches it. Durable tools only: a short script in the current repo solves the task? Write the script there. The CLI is the agent's command layer — composable discover/resolve/read/write primitives with stable `--json`, no TTY assumptions, and no secret leakage — because an agent drives it cold, repeatedly, without a human to answer prompts.

License: Apache-2.0; see `licenses/clssck/cli-creator/LICENSE.txt`. Command, JSON, and companion-skill contract → [agent-cli-patterns.md](skill://cli-creator/references/agent-cli-patterns.md). Per-runtime install → [install-and-packaging.md](skill://cli-creator/references/install-and-packaging.md).

<instruction>

Name three things before scaffolding:

|Item|Examples|
|---|---|
|Source|API docs, OpenAPI JSON, SDK docs, curl examples, browser app, internal script, shell history|
|First jobs|`list drafts`, `download failed job logs`, `search messages`, `upload media`|
|Install name|Short binary: `ci-logs`, `slack-cli`, `buildkite-logs`|

- **Location:** `~/code/clis/<tool-name>` (PowerShell: `$env:USERPROFILE\code\clis\<tool-name>`) unless the user names a repository. New directory = local write; state the location first.
- **MUST check the name is free:** `command -v <tool-name> || true` (PowerShell: `Get-Command <tool-name> -ErrorAction SilentlyContinue`). Taken → clearer install name, or ask.

</instruction>

<instruction>

Detect OS, active shell, toolchains, repository convention, and a user-writable PATH directory before generating install commands. **NEVER emit PowerShell syntax for a POSIX shell or the reverse.**

```bash
command -v cargo rustc bun node pnpm npm python3 uv go
echo "$PATH"; echo "${XDG_CONFIG_HOME:-$HOME/.config}"; echo "${TMPDIR:-/tmp}"
```

```powershell
Get-Command cargo, rustc, bun, node, pnpm, npm, python, uv, go -ErrorAction SilentlyContinue
$env:TEMP
[Environment]::GetEnvironmentVariable('Path', 'User')
```

- Repo has a package manager and install convention → use it (existing convention wins over any default here).
- New TypeScript/JavaScript CLI, no existing convention or Node-only constraint → **prefer Bun** (`bun install`, `bun run`, `bun test`, `bun build --compile`). Fall back to npm/pnpm when the repo already uses them, the target requires Node/npm, or a dependency fails under Bun; Bun is not compatible with every Node SDK.
- Search source material with `grep`, `glob`, `read`; NEVER shell `rg`/`find`/`Select-String`.

</instruction>

<instruction>

|Runtime|Choose when|Defaults|
|---|---|---|
|Rust (default)|Durable CLI: one fast binary, strong arg parsing, good JSON|`clap`, `reqwest`, `serde`/`serde_json`, `toml`, `anyhow`|
|TypeScript/JavaScript (Bun preferred)|Official SDK, auth helper, browser automation, or existing repo tooling is the advantage|Bun for package management, running, testing, and `bun build --compile` single binary (no Node needed on target); npm/pnpm/Node only when the repo or target requires it; `commander` or `cac`; native `fetch` or official SDK; `zod` only where payload validation prevents real breakage; `package.json` `bin`; build tool per repo (`tsup`, `tsx`, `tsc`)|
|Python|Data work, local file transforms, SQLite/CSV/JSON analysis, Python-heavy admin tooling|uv project from `uv init --package` with `[project.scripts]` and committed `uv.lock`; `argparse` (or `typer` for deep subcommands); `httpx`/`requests`/`urllib` matching nearby code; PEP 723 single file for one-module tools|
|Go|Repo or team already uses Go; one static binary, easy cross-compile|Standard `flag` for flat commands; a subcommand library only for nested trees|

- **MUST state the choice in one sentence before scaffolding:** reason + toolchain found.
- NEVER pick a language that adds setup friction without material benefit. Best language missing → install the toolchain with user approval, or take the next-best installed option.
- Install target matching repo and platform (`make install-local`, or a PowerShell script on Windows); document what it depends on (toolchain, `uv`, runtime version).
- **Install into a user-approved, user-writable PATH directory;** NEVER assume `~/.local/bin`. NEVER `pip install` into system Python (PEP 668).

</instruction>

<critical>

Precedence: env var with the service's standard name (`GITHUB_TOKEN`) > user config in a documented OS-appropriate directory (`~/.config/<tool-name>`; Windows `$env:APPDATA\<tool-name>`) > `--token-file <path>` or token on stdin (`--with-token`, as `gh auth login` does) for headless setup.

- **NEVER accept a secret as a plain flag value** — it leaks into `ps` output and shell history.
- **NEVER print full tokens.**
- `--json doctor` reports: token available, auth source category (`env`, `config`, `token-file`, `stdin`, provider default, `missing`), missing setup step. Offline or no-auth tool → says so: fixture mode, fixture found, auth not required.
- **Internal web app from DevTools curls:** sanitized endpoint notes first — resource, method/path, required headers, auth, CSRF, request body, response ID fields, pagination, errors, one redacted sample.
- NEVER commit copied cookies, bearer tokens, customer secrets, full production payloads.
- Screenshots show workflow and vocabulary only; NEVER API evidence without a request, export, docs page, or fixture.

</critical>

<procedure>

1. **Inventory the source:** resources, auth, pagination, IDs, file flows, rate limits, dangerous writes. OpenAPI available → inspect before naming commands. Wrapping an official SDK or version-sensitive library (`clap`, `commander`, `reqwest`) → pull its current API docs from the `context7` MCP server, else `web_search` the vendor docs; NEVER code against a remembered SDK surface.
2. **Sketch the command surface in chat before coding:** binary name, discovery, resolve, read, write, raw escape hatch, auth/config choice, install command. Short, shell-friendly names; shape, JSON policy, pagination, exit codes per [agent-cli-patterns.md](skill://cli-creator/references/agent-cli-patterns.md).
3. Scaffold with a README or equivalent.
4. Implement `doctor`, discovery, resolve, reads, one narrow draft or dry-run write if requested, raw escape hatch.
5. **Install on PATH only when the user asks** for a globally callable command; state the target first. Otherwise keep the verified local wrapper.
6. Smoke test from a fresh directory — not `cargo run`, `uv run`, or other package-manager wrappers.
7. Run format, typecheck/build, unit tests (request builders, pagination, body builders), no-auth `doctor`, help output, and one fixture, dry-run, or live read-only call.

### Source shapes

- **Existing script or shell history:** split into phases (setup, discovery, download/export, transform/index, draft, upload, poll, live write); keep the user's flags, paths, env vars; wrap repeatable phases with stable IDs, bounded JSON, file outputs.
- **Fixture-backed prototype:** fixtures at a predictable path the installed CLI finds; smoke test from a temp directory (`${TMPDIR:-/tmp}`; Windows `$env:TEMP`).
- **Log-oriented CLI:** deterministic snippet extraction separate from model interpretation; emit filenames, line numbers or byte ranges, matched rules, short excerpts.

### Live writes

- **Live write needed for confidence → ask first;** reversible or draft-only.
- Raw escape hatch: reads first; NEVER non-GET/HEAD against a live service unless the user asked for that write.

</procedure>

<procedure>

Installed on PATH:

```bash
cd "$(mktemp -d)" && command -v <tool-name> && <tool-name> --help && <tool-name> --json doctor
```

```powershell
Set-Location (New-Item -ItemType Directory (Join-Path $env:TEMP "smoke-$(Get-Random)"))
Get-Command <tool-name>; <tool-name> --help; <tool-name> --json doctor
```

Not on PATH → run the wrapper or binary by absolute path from the fresh directory; NEVER install just to pass the smoke test.

**TTY behavior:** the omp `bash` tool runs with no TTY on stdin or stdout, so the smoke commands above are the no-TTY check; set a short `timeout` so a prompt that waits instead of failing fast shows up as a timeout, not a stall. Interactive prompts or a TUI → drive the ordinary CLI on a real PTY with `xd://tui` (`{"op":"start","bin":"<tool-name>","args":[…]}`, then `screen`, `send` the terminal input, and `stop`); reserve `keys` for OMP/pi-tui hosts with the debug socket. If `xd://tui` is unavailable, use `bash` with `pty: true`.

Done = all hold: `--help`, `--version`, `--json doctor`, discovery, resolve, reads, raw escape hatch present · runs without a TTY (no prompts without one, documented nonzero exit codes, `NO_COLOR` honored, network timeout set) · `--json` errors carry no credentials · Python is a uv project or PEP 723 script, nothing `pip install`ed into system Python · no live write without approval.

</procedure>

## Companion skill

After the CLI works, create or update a normal omp skill that teaches it.

|Location|Path|Use when|
|---|---|---|
|User skills|`~/.omp/agent/skills/<tool-name>/SKILL.md` (Windows: `$env:USERPROFILE\.omp\agent\skills\<tool-name>\SKILL.md`)|Personal tool, default|
|Pack|`skills/<tool-name>/SKILL.md` in an agent-plugins pack, e.g. `clssck`|User names a pack or repo|
|Project|`.omp/skills/<tool-name>/SKILL.md`|Tool belongs to one repository|

- **Layout:** one level deep, `<skills-root>/<tool-name>/SKILL.md`; folder name = `name`.
- **Frontmatter:** `name` + `description`; `disable-model-invocation: true` only for a manual-only skill (OMP extension frontmatter — omit it from standard `plugin.json` packages; strict validation rejects unknown fields). Description = retrieval surface: purpose + concrete "Use when" triggers; `Not for …` only against sibling confusion. Authoring style → `skill-authoring`.
- **Body:** `# Title`, dense intro, `##` sections (task names for procedures, noun names for reference), bold-lead rules. Detail in `references/*.md`; link every runtime asset with `skill://<tool-name>/...`. Skeleton → [agent-cli-patterns.md](skill://cli-creator/references/agent-cli-patterns.md#companion-skill).
- **Bundled scripts:** PEP 723 header with `#!/usr/bin/env -S uv run --script`; invoke as `uv run "$(realpath skill://<tool-name>/scripts/<file>.py)"` in the omp `bash` tool. Bare `skill://` path fails in external programs; `realpath` prints the physical path.
- **Verify:** `read skill://<tool-name>` resolves, every link resolves, example commands run from a fresh directory. Pack skill → also `bun scripts/sync.ts --local` from the repo root (`skill-authoring` → Validate).
