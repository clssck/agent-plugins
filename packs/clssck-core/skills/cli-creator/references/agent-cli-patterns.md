# Agent CLI Patterns

Command, JSON, and companion-skill contract for CLIs an agent runs repeatedly from any repo. Workflow, runtime choice, and permission gates live in [SKILL.md](../SKILL.md).

## Contents

- [Mental model](#mental-model)
- [Command surface](#command-surface)
- [Help is interface](#help-is-interface)
- [Command shape](#command-shape)
- [Discovery, resolve, read, context](#discovery-resolve-read-context)
- [Text, JSON, files, exit codes](#text-json-files-exit-codes)
- [Pagination and breadth](#pagination-and-breadth)
- [Writes and raw escape hatch](#writes-and-raw-escape-hatch)
- [Companion skill](#companion-skill)

## Mental model

The CLI is the agent's command layer: it turns a service, app, API, log source, or database into shell commands. Expose composable primitives. AVOID one command that "does the whole investigation"; discover, read, resolve, download, inspect, draft, and upload compose better.

## Command surface

Sketch these in chat before coding. Every CLI SHOULD offer:

|Command family|Contract|
|---|---|
|`--help`|Lists every major capability|
|`--version`|Prints the version and exits 0; the installed binary and `doctor --json` report the same value|
|`--json doctor`|Reports config, auth source, version, endpoint reachability, missing setup; works without auth|
|`init`|Stores local config when env-only auth is painful|
|Discovery|Finds accounts, projects, workspaces, teams, queues, channels, repos, dashboards|
|Resolve|Turns names, URLs, slugs, permalinks, build links into stable IDs|
|Read|Fetches exact objects; lists/searches collections with bounded `--limit`, cursor, or offset|
|Write|One named action each: create, update, delete, upload, schedule, retry, comment, draft|
|`--json`|Stable machine-readable output on every command|
|Raw escape hatch|`request`, `tool-call`, `api`, or nearest honest name|

- Writes take the narrowest stable resource ID.
- Writes offer `--dry-run`, `draft`, or `preview` first when the service allows.
- NEVER hide writes inside broad commands such as `fix`, `debug`, or `auto`.
- NEVER ship only a generic `request` command; give high-level verbs for repeated jobs.

## Help is interface

Write `--help` for an agent that has only the binary and a vague task. Short description per command; flag names literal to the product or API. Top-level help answers:

- What containers can I discover?
- What exact objects can I read?
- What stable IDs can I resolve?
- What files can I download or upload?
- Which write actions exist?
- What is the raw escape hatch?

## Command shape

Product nouns, then verbs; be consistent:

```bash
tool-name --json doctor
tool-name --json accounts list
tool-name --json channels resolve --name general
tool-name --json messages search "exact phrase"
tool-name --json messages context <message-id> --before 3 --after 3
tool-name --json logs download <build-url> --failed --out ./logs
tool-name --json media upload --file ./image.png
tool-name --json drafts create --body-file draft.json
```

Direct verbs are fine when the product noun is already strong:

```bash
tool-name --json social-sets
tool-name --json drafts list --social-set <id>
tool-name --json request get /v2/me
```

Useful shapes from mature CLIs; implement filtering or templating only when the user needs it:

```bash
# Field-selected output
tool-name issues list --json number,title,url,state
tool-name issues list --json number,title --jq '.[] | select(.state == "open")'

# Human text by default, full API object on request
tool-name pods get <name>
tool-name pods get <name> -o json

# Workflow commands, not just REST nouns
tool-name logs tail
tool-name webhooks listen --forward-to localhost:4242/webhooks
```

## Discovery, resolve, read, context

Design first-pass commands in this order:

1. **Discover** broad containers: workspaces, accounts, repos, projects, channels, queues.
2. **Resolve** human input into IDs: user names, channel names, permalinks, PR URLs, build URLs.
3. **Read** an exact object: issue, event, thread, draft, customer, job, run.
4. **Context** around an anchor: nearby messages, parent thread, surrounding logs, audit history.

NEVER force repeated searches when a stable ID is already known.

## Text, JSON, files, exit codes

`--json` rules:

- JSON to stdout only; progress and diagnostics to stderr.
- Document the policy: API pass-through versus CLI envelope, success shape, error shape, one example per command family.
- Errors are machine-readable and contain no credentials.
- Redact tokens, cookies, customer secrets, private headers, unrelated payloads.

Downloads and exports:

- Write under a user-provided `--out` path when possible.
- Return file path, byte count if cheap, source URL or ID, and follow-up command.

Exit codes:

- Zero on success, including an empty result.
- Nonzero on auth failure, invalid input, network failure, parse failure, API error, incomplete upload/download.
- Map nonzero codes to the main failure modes and document them in `--help` or the README. Reference points: argparse exits 2 on invalid arguments; `gh` uses 1 failure, 2 cancelled, 4 authentication required.
- `doctor --json` MUST report missing auth instead of crashing.

Non-interactive behavior (agents have no TTY):

- Prompt only when stdin is a TTY. Otherwise fail fast with an error that names the flag to pass. Offer `--no-input` to force this.
- Command expects piped stdin but stdin is a TTY? Print help or an error; NEVER hang waiting.
- Accept secrets via `--token-file` or stdin, never as a flag value.
- Disable color when stdout/stderr is not a TTY, when `NO_COLOR` is set and non-empty, or when `TERM=dumb`; support `--no-color`. No spinners or progress animations when stdout is not a TTY.
- Network calls MUST have a configurable timeout with a finite default. Ctrl-C MUST still interrupt a hung request.
- `--force` bypasses confirmations; `--dry-run` describes changes without making them.

## Pagination and breadth

Shallow by default; explicit knobs for breadth:

```bash
tool-name --json messages search "topic" --limit 10
tool-name --json messages search "topic" --limit 50 --all-pages --max-pages 3
tool-name --json drafts list --limit 20 --offset 40
```

Return `next_cursor`, `next_url`, `offset`, `page_count`, or whatever the provider really uses.

## Writes and raw escape hatch

The raw command is a repair hatch, not the main interface. It MUST still use configured auth, base URL, JSON parsing, redaction, status/error handling, and `--json`.

```bash
tool-name --json request get /v2/me
```

- Reads first; treat POST/PUT/PATCH/DELETE as live writes.
- NEVER hide raw writes behind a `debug` command.
- Media, artifact, or presigned upload flows: test each phase separately (create upload, transfer bytes, poll status, attach resulting ID).

## Companion skill

The companion skill is an omp skill that teaches the path through the tool. It MUST be smaller than the CLI README. Location and file contract are in [SKILL.md](../SKILL.md#companion-skill).

Body skeleton:

````md
---
name: tool-name
description: <What the CLI does>. Use when <concrete triggers>. Not for <sibling or alternative>.
---

# Tool Name

Wrapper for <service>; run by command name from any directory.

## Start

```bash
tool-name --json doctor
tool-name --json accounts list
```

## <Common job>

```bash
tool-name --json ...
tool-name --json ...
```

## Rules

- Run the installed `tool-name` by name; verify with `command -v tool-name` (PowerShell: `Get-Command tool-name`).
- Use `--json` when analyzing output.
- Create drafts by default.
- NEVER publish, delete, retry, or submit without an explicit user request.
- Use `request get ...` only when high-level commands are missing.

## Checklist

- `doctor --json` passes before other commands.
````

- Order the body as an agent uses the CLI, not as a feature tour.
- Cover: verify command exists, first command, auth setup, discovery command for the common ID, safe read path, draft/write path, raw escape hatch, what needs approval, three copy-pasteable examples.
- Keep API reference in the CLI docs or a linked reference file.
- Add JSON shape notes only where they decide the next command.
- CLI installed locally but not on PATH? Show the absolute path in place of the bare name.

## Sources

- Command Line Interface Guidelines (clig.dev): https://clig.dev/
- GitHub CLI, exit codes: https://cli.github.com/manual/gh_help_exit-codes
- GitHub CLI, environment variables (`GH_TOKEN`, `NO_COLOR`, `GH_PROMPT_DISABLED`): https://cli.github.com/manual/gh_help_environment
- GitHub CLI, `gh auth login` (`--with-token` on stdin): https://cli.github.com/manual/gh_auth_login
- Python `argparse` (exit status 2 on invalid arguments): https://docs.python.org/3/library/argparse.html
- Agent Skills specification (frontmatter, file references one level deep): https://agentskills.io/specification
- omp skills documentation: `docs/skills.md` in the oh-my-pi repository (discovery layout, `skill://` URLs)
