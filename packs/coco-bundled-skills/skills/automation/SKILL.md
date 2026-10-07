---
name: automation
description: "Schedule recurring Cortex Code runs as Snowflake AGENT TASKs via the `cortex automation` CLI (aka `/automation`): daily/hourly/weekly tasks, recurring reports, unattended cron jobs, and checking automation fire history. NOT the LangGraph Cortex Automations product (see cortex-automations)."
---

# Cortex Code Automations: scheduled Cortex Code runs as Snowflake AGENT TASKs

An "automation" here is a Snowflake AGENT TASK that runs Cortex Code unattended
in a Snowflake-managed sandbox at `/workspace` on a recurring schedule. The task
runs as the creating user, so each fire's thread is visible to that user via the
same auth as `cortex conversations transcript`. No warehouses are needed to
execute an AGENT TASK.

Automations have NO access to your local filesystem and do NOT load local MCP
servers — only Cortex Code's built-in tools (bash, edit, etc.) and any
Snowflake-managed MCP servers you explicitly attach are available.

> **When NOT to use this skill.** This is about scheduling *Cortex Code* runs
> via AGENT TASK. It is unrelated to the **Cortex Automations** LangGraph
> managed-runtime product (`CREATE AUTOMATION`, `ctx.complete()`,
> `ctx.human_action()`, `automation.toml`, HITL). For that product use the
> `cortex-automations` skill instead.

## Prerequisites

- The account must have **AGENT TASK enabled** (an ACCOUNTADMIN one-time
  enablement). Without it, `cortex automation create` fails when the CREATE
  hits Snowflake.
- Drive everything through the `cortex automation …` CLI. `/automation` is the
  interactive entry point that walks you through the same flow.

## Driver: `cortex automation …` (DO NOT HAND-AUTHOR SQL)

Drive everything through `cortex automation …` via the bash tool. The CLI
handles CREATE AGENT TASK SQL generation, schedule parsing, and current-user
resolution. Only fall back to hand-written SQL if the user explicitly asks to
"show me the SQL" or the CLI doesn't cover the operation.

## DO NOT ask about — these are not parameters

AGENT TASK has fewer knobs than a regular Snowflake TASK. Do NOT ask the user
about any of the following; they don't apply to automations:

- **WAREHOUSE**: no warehouses are needed to execute an AGENT TASK. The CREATE
  AGENT TASK SQL the CLI generates intentionally has no WAREHOUSE clause —
  adding one is a syntax error. Never ask "which warehouse should this run on".
- **COMMENT**: AGENT TASK syntax doesn't accept COMMENT. Don't offer to add one.
- **ERROR_INTEGRATION / TASK_AUTO_RETRY_ATTEMPTS / SUSPEND_TASK_AFTER_NUM_FAILURES**:
  not on the AGENT TASK surface. Don't ask.
- **ROLE / EXECUTE AS**: AGENT TASK runs as the creating user (= the
  connection's current user). No EXECUTE AS / IMPERSONATE configuration to
  gather.

## Gathering parameters — ask the user only for what's missing

1. **prompt**: what should the automation do each fire? Required.
2. **cadence**: convert natural phrasing into the CLI's `--schedule` string. Examples:
     - "every morning" -> `"every 1440 minutes"` (or "every Monday at 9am" for time-of-day)
     - "hourly"        -> `"every 60 minutes"`
     - "every 5 min"   -> `"every 5 minutes"`

   Multi-weekly schedules can be combined: "every Tue at 1:15 and every Fri at 9am".
3. **timezone** (`--timezone`): the CLI defaults to UTC, but users almost always
   mean their LOCAL time when they say "every Monday at 9am". Resolve the user's
   local IANA zone via bash BEFORE building the create command:

   ```bash
   readlink /etc/localtime | sed 's|.*/zoneinfo/||'
   # If readlink returns empty (e.g. Debian/Ubuntu copy, not symlink):
   timedatectl show --property=Timezone --value 2>/dev/null
   ```

   Use whichever command returns a non-empty IANA name (e.g.
   `America/Los_Angeles`). Do NOT use `date +%Z` output (PDT/EST/etc.) as the
   `--timezone` value — those are short labels, not valid IANA names.

   For schedules that include a time-of-day ("at 9am", "at 1:15"), pass
   `--timezone <IANA>` so the AGENT TASK fires at the user's local clock-time.
   The CLI translates the local time into a UTC cron expression server-side. For
   pure interval schedules ("every 60 minutes", "every 5 minutes") timezone is
   irrelevant — omit `--timezone`. When the local zone is genuinely UTC (or both
   resolvers fail) skip the flag and let the CLI default apply. Mention the
   resolved zone in the summary you show the user before scheduling so they can
   correct it.
4. **name**: auto-generate a short purpose-based name if the user doesn't care.
   The CLI applies its internal identifier prefix automatically if missing; the
   prefix is not user-facing.
5. **workspace stage** (`--workspace`): ask only if the prompt clearly involves
   writing files that should persist across fires (e.g. "build up a running
   ledger of …", "incrementally append to a file"). The default per-user
   workspace stage is fine for most one-shot tasks. Skip the mount entirely with
   `--no-workspace` if `/workspace` files don't matter.
6. **MCP servers** (`--mcp`): if the prompt clearly needs a third-party tool
   (Slack, Gmail, Google Drive, Atlassian, Glean, Google Calendar — e.g. "post
   to #channel", "send an email", "read this Jira"), discover the FQN by running
   BOTH of the following — they list disjoint server sets, and skipping either
   misses servers the user has access to:

   ```sql
   SHOW MCP SERVERS IN ACCOUNT;          -- Snowflake-managed MCP servers
   SHOW EXTERNAL MCP SERVERS IN ACCOUNT; -- customer-brought (BYO) MCP servers
   ```

   Then pass each FQN as a separate `--mcp` flag (the CLI accepts the flag
   multiple times). Most useful third-party connectors (Atlassian, Glean, Slack,
   Jira, etc.) are typically brought in by the customer as EXTERNAL MCP SERVERs
   and only show up in `SHOW EXTERNAL MCP SERVERS` — running only `SHOW MCP
   SERVERS` will miss them. Common connector FQNs (which form they live under
   depends on how the account was set up — verify by running both SHOW commands
   above):
   - `SNOWFLAKE_INTELLIGENCE.MCP.SLACK`
   - `SNOWFLAKE_INTELLIGENCE.MCP.GMAIL`
   - `SNOWFLAKE_INTELLIGENCE.MCP.GOOGLE_DRIVE`
   - `SNOWFLAKE_INTELLIGENCE.MCP.GOOGLE_CALENDAR`
   - `SNOWFLAKE_INTELLIGENCE.MCP.ATLASSIAN`
   - `SNOWFLAKE_INTELLIGENCE.MCP.GLEAN`

   To inspect a specific server's tool surface before attaching, use the
   matching DESCRIBE — `DESCRIBE MCP SERVER <FQN>` for entries from `SHOW MCP
   SERVERS`, `DESCRIBE EXTERNAL MCP SERVER <FQN>` for entries from `SHOW EXTERNAL
   MCP SERVERS`. The forms aren't interchangeable; using the wrong one returns a
   "does not exist" error. (E.g. on most accounts GLEAN is an EXTERNAL MCP SERVER
   — `DESCRIBE MCP SERVER` on it fails; `DESCRIBE EXTERNAL MCP SERVER` works.)

   Don't attach servers the prompt doesn't need — extra tools waste tokens.
7. **model** (`--model`): the automation fires with `model="auto"` by default,
   which the orchestrator resolves to the highest-ranked coding-agent model
   available to the account. Almost always leave this alone. Only override with
   `--model <id>` if your task specifically requires a particular model. Run
   `cortex automation --help` for the current flag surface.
8. **GitHub access** (`--github <SECRET_FQN>`): when the prompt needs to clone,
   fetch, or push a **private** GitHub repo, pass `--github` pointing at a
   Snowflake `SECRET` that holds a GitHub PAT (e.g.
   `USER$YOU.PUBLIC.GITHUB_PAT`). The sandbox then gets authenticated git/gh
   egress to github.com: the orchestrator fetches the SECRET server-side and
   injects the token only on egress, so `git clone https://github.com/org/repo`
   and `gh` work with no token handling in the prompt. Only the SECRET FQN
   (never the token) enters the request — do **not** put PATs in the prompt.
   Public-repo-only clones need nothing. Note: if a fire fails git auth despite
   `--github`, check the SECRET's PAT first — it must be unexpired, carry repo
   read (or write) scope, and be **SSO-authorized** for the org (orgs with SAML
   SSO enforced reject un-authorized PATs); surface the fire's error from
   `cortex automation doctor` rather than retrying blindly.
9. **Hooks** (`--pre-run-hook` / `--post-run-hook`): deterministic bash that
   runs inside the sandbox around each fire, without spending an LLM turn. Use
   for fixed setup/teardown, e.g. `--pre-run-hook "cd /workspace && git pull
   --ff-only"` or `--post-run-hook "cd /workspace && git add -A && git commit -m
   auto && git push"`. Pre-run runs before the agent loop (a nonzero exit aborts
   the fire); post-run runs after the final response (failures are logged, not
   fatal). Optional `--pre-run-timeout` / `--post-run-timeout` in seconds
   (`0` = default 60/30, max 300). For hooks that change between runs, commit a
   JSON config to the workspace and pass `--hooks-config-path <path>` instead
   (mutually exclusive with the inline hook flags). Only add hooks when the
   setup/teardown is truly fixed — one-off work belongs in the prompt.

The automation always lives in the user's own personal database under `PUBLIC`;
that location isn't a parameter the user picks.

## Authoring the prompt — invariants every automation prompt must include

Automations fire unattended; the model has nobody to ask and no clarifying-turn
budget. Bake these invariants into the prompt body itself so each fire just
executes. Without them, the most common failure mode is the automation wasting a
fire pausing on a clarifying question.

1. **Lead with the unattended framing** — verbatim or close to it:
   > "You are running unattended in a Snowflake AGENT TASK. There is no human to ask follow-up questions; complete the task autonomously."
2. **Add an explicit no-clarify directive**:
   > "Do NOT ask any clarifying questions; just execute."
3. **Pre-resolve names -> IDs BEFORE writing the prompt.** Resolve once during
   the `/automation` chat, then hardcode the IDs into the prompt body. The model
   inside the automation should never be doing fuzzy name lookup — that's where
   it pauses to ask "I found 3 people named X, which one?".
   - Slack user name -> Slack user ID (e.g. `U05GTCDQKN2`). Use the Slack MCP's
     user-search tool during the `/automation` chat to resolve, then hardcode.
   - Slack channel name -> channel ID. Use the Slack MCP's channel-search tool,
     then hardcode.
   - Repo name -> full URL (`https://github.com/<org>/<repo>`).
   - Google Drive doc name -> file ID.
4. **End with a machine-parseable single-line status** so transcripts are
   greppable from `cortex automation doctor`:
   > "After completing, print exactly one of:
   >    `<NAME>_OK <key=value pairs>`
   >    `<NAME>_FAILED:<one-line reason>`"
5. **Pre-resolve MCP tool names where known** so the model doesn't fish:
   > "Use the Slack `post_message` tool to send the DM."
   > "Use Google Drive search to find the doc, then read it."
6. **Don't write "ask the user before X" or "pause for review"** — there is no
   user. Permission gating is OFF for automation fires, so even destructive tools
   run without prompting; author prompts that assume no approval step, and be
   deliberate about what side effects the prompt is allowed to cause.

Keep the prompt itself task-focused. The scaffolding above is invariant — apply
it to every automation prompt regardless of the task domain.

Note: the automation prompt must not contain the `$$` token (it collides with
the SQL body delimiter the CLI generates). Rephrase or write the prompt to a
file and use `--prompt-file`.

## Create flow — RECOMMENDED two-step (test run first)

Production automations fire on schedule and silently fail if the prompt is
wrong; debugging after the fact is slow. Always offer a test run first.

**Step A: try the prompt once**

1. Show the user a SUMMARY (NOT the SQL or the bash command). Cover only what
   they need to confirm:
   - Automation name (lives in your personal database under `PUBLIC`)
   - Cadence in human terms (e.g. "every 5 minutes")
   - Timezone (only when the schedule has a time-of-day; show the IANA zone you
     resolved from `/etc/localtime` so the user can override)
   - Workspace stage (default per-user stage, `--no-workspace`, or explicit FQN)
   - Attached MCP servers (none / list of FQNs)
   - The prompt the automation will run each fire

   Plus these caveats:
   - Runs in a Snowflake-managed sandbox at `/workspace`, not local files
   - No local MCPs; only the listed Snowflake-managed MCPs (and Cortex Code's
     built-in tools: bash, edit, etc.) are available
2. Ask: "Want me to try it once now, or put it straight on the schedule?"
   Default to trying it once — a production schedule with no test run is the
   most common foot-gun.
3. If they want the test run: run `cortex automation create` with `--dry-run`
   first to show the shape, then run a one-shot `SELECT $$<body>$$` via
   `sql_execute` (the same body the AGENT TASK would run, just executed once
   interactively). Pull the resulting thread_id, run `cortex conversations
   transcript <id>`, and show the user the rendered conversation. They confirm
   tools fired correctly and side effects (email, Slack post, etc.) actually
   happened.
4. Only after the test run succeeds, ask explicit yes/no to schedule.

**Step B: schedule**

5. Run the create via the bash tool:

   ```bash
   cortex automation create --name <NAME> --prompt "<PROMPT>" --schedule "<SCHEDULE>" \
     [--timezone <IANA>] [--mcp <FQN>] [--workspace <STAGE_FQN> | --no-workspace] \
     [--github <SECRET_FQN>] [--pre-run-hook "<bash>"] [--post-run-hook "<bash>"]
   ```

   For multi-line prompts, write the prompt to a file and use `--prompt-file`.
   Add `--connection <name>` if the user has a non-default Snowflake connection.
6. Report back the FQN, schedule, attached MCPs, and a one-liner pointing to
   `cortex automation doctor <name>` for inspecting fires.

## Debugging a fire — when the user asks "why did <automation> not do X"

1. `cortex automation doctor <name>` — shows the last N fires (state, error,
   query_id) joined with thread_ids when fires produced threads.
2. For a SUCCEEDED fire with a thread_id, run:

   ```bash
   cortex conversations transcript <thread_id>
   ```

   This renders the full conversation: user prompt, assistant tool calls (bash,
   etc.), tool results, and the final assistant message — exactly what executed
   inside the sandbox. Use this to diagnose silent failures like "email never
   sent" where TASK_HISTORY shows SUCCEEDED but the side effect didn't happen.

## Management verbs — interpret the user's intent and run the corresponding CLI

The CLI exposes exactly these subcommands: `list`, `describe`, `doctor`,
`suspend`, `resume`, `drop`. The phrasings on the left are NATURAL-LANGUAGE
intents the user might express; map them to the CLI subcommand on the right.

- "list" / "what automations do I have" / "show me all automations"
  -> `cortex automation list`
- "show <name>" / "describe <name>" / "details for <name>"
  -> `cortex automation describe <name>`
- "debug <name>" / "why did <name> fail" / "last fires of <name>"
  -> `cortex automation doctor <name>`
- "suspend <name>" / "pause <name>"
  -> `cortex automation suspend <name>`
- "resume <name>" / "start <name>"
  -> `cortex automation resume <name>`
- "drop <name>" / "delete <name>" / "cancel <name>"
  -> `cortex automation drop <name>`
- "where do I see my automations" / "where's the automation list in the UI" /
  "show me these in Snowsight" / "link me to my automations" /
  "what's the URL for the automations page"
  -> not `list` — see "Where the automations list is in the UI" below.

If a NAME matches multiple split tasks (multi-weekly schedules expand to one task
per fire), mutating verbs need `--all` to confirm.

USE THE BASH TOOL for all CLI invocations. Surface the JSON output plainly, or
summarize it for the user. Run `cortex automation --help` if you need the full
surface.

## Where the automations list is in the UI

Answer this when the user asks where their automations live in the UI, or asks
for a link to them. Otherwise stay on the CLI — don't volunteer the UI.

In Snowsight, open CoCo with the floating button, then click the
**calendar-clock icon in the panel header**. There is **no URL for it** — nothing
to link or bookmark, and `snowsight_navigate` cannot reach it. On Snowsight, the
`coco-snowsight-guide` skill documents this view; load it if the user wants more
than the location.
