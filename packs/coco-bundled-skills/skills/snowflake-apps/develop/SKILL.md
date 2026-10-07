---
name: snowflake-apps-develop
description: "Local development, testing, and iteration for Snowflake Apps. Use when the user wants to run locally, test, add features, or iterate on an existing app."
---

# Develop Snowflake App

Local iteration on an existing Snowflake App. The template-specific mechanics — how to run it, what to verify, and framework-specific pitfalls — live in the project's own `README.md`.

## Run Locally

Run the app locally, reading the project's `README.md` for the framework-specific run command and smoke checks. Start any dev server in the background, since it's a long-running process. (Local development is not available in every environment — if it isn't supported where you are running, tell the user and route them to `../deploy/SKILL.md` instead.)

## Watch the Dev Server While You Work

When you start the dev server in the background, keep the returned `shell_id` — it's how you read new output later. A dev server surfaces most problems in its own output (compile failures, stack traces, failed requests), so read that output yourself instead of waiting for the user to paste it.

You don't have a background timer, so "poll continuously" isn't a real option — you can only read output when you act. Check it at the moments errors actually appear: **right after the server starts**, and **after any edit that triggers a recompile or reload**. Use the `bash_output` tool (it's a tool call, not a shell command) with `wait` so it blocks until fresh output arrives rather than returning an empty buffer:

```
bash_output(bash_id: "<shell_id>", wait: true, timeout_ms: 15000)
```

Where it's available, the `monitor` tool is purpose-built for streaming matching lines from a long-running process and is a good fit for watching a dev server. It's host-only (unavailable when the cocobox VM sandbox is enabled), so fall back to `bash_output` when it isn't.

**What counts as an error is framework-specific** — the project's `README.md` (its local-dev / "verify" section) lists the output signatures to watch for and the smoke checks to run. Read it rather than assuming a fixed pattern set.

### Fix loop

When the output shows a real error:

1. Read the **full** message or traceback — for a stack trace, the root cause is usually near the top of your own code, not the framework frames.
2. Diagnose the root cause and decide the smallest fix. This diagnosis is read-only, so do it without pausing.
3. **⚠️ Before editing any file, tell the user what's broken and the fix you propose.** In an active "get it running" / "fix it" iteration loop, that request is standing approval for the obvious repair — you don't have to re-ask for each one. Pause for an explicit go-ahead when the change is large or ambiguous, touches a config file or a dependency, or needs a server restart.
4. Apply the fix, then read `bash_output` again to confirm a clean recompile, and tell the user what was wrong and what you changed.

Bound the loop: if the same error persists after ~2 attempts, stop and show the user the error and what you tried instead of looping. Not every dev-time message is a real failure (hot-reload notices, a first-compile warning that clears itself, or an expected request error while you're mid-edit) — confirm an error persists before acting on it.

If a fix needs a full restart (e.g. a config-file change the dev server can't hot-reload), stop the server with `kill_shell(shell_id: "<shell_id>")`, relaunch it in the background, and capture the new `shell_id`.

## Verify Before Declaring Success

Once it's running, confirm it renders without errors and is fetching **real** Snowflake data (not mock data). Run any additional smoke checks the README specifies. Diagnose any failures before telling the user the app is up.

## Secrets

For reading secrets, consult the project's `README.md`. Keep one platform-level guardrail in mind: declare each secret as a **top-level** `secrets:` block in `app.yml` (a sibling of `install:` / `run:`), **not** nested under `run:`, or the secret is never mounted. This placement is the same in both manifest layouts.

In an `app.yml` `version: 2` project the CLI applies these declaratively, so a secret dropped from the manifest is also unmounted from the running service on the next deploy — see [`@../references/manifests.md`](../references/manifests.md).

## Next Steps

When the app is ready, validate it, then ask the user if they'd like to deploy — the router will load the `deploy` sub-skill.
