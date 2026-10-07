---
name: team-workflow
description: "Multi-phase team orchestration for feature implementation. HIGHEST PRIORITY — load FIRST (before domain skills) when user requests teammates, teams, swarms, parallel agents, or the workflow auto-triggers (`/team`, `cortex --team`, ctrl+g)."
---

# Skill: team-workflow

## Setup

**Before any tool calls**, complete these steps:

1. Capture the current working directory as `{cwd}` — an absolute path.
2. `cortex ctx task add "<user's request>"` → task_id
   > If triggered without a prompt (ctrl+g, /team), create with a default title; update once a prompt arrives.
3. `cortex ctx task start <tid>`
4. Call `team_create(team_name="team-workflow-<tid>")` — returns `next_steps`, `phase_order`, `roles_by_phase`, and `role_agent_types`.
5. `task_update(task_id="<tid>", skill="{skill_dir}")`

> **Path A or C (explicit team request):** `team_create` activates plan mode automatically — do NOT call `EnterPlanMode` separately. Proceed directly to Teammate Selection.
> **Path B (autonomous — plan already written):** After `ExitPlanMode` is called and all 5 setup steps are completed, proceed to Teammate Selection.

---

## Teammate Selection

The workflow runs in five phases. Use the compact `roles_by_phase` manifest returned by `team_create` as the initial role map, then call `list_teammates(phase="all")` once at the beginning to inspect every registered teammate and description before selecting or spawning workers. Choose teammate roles and counts based on task complexity. The only hard constraint is the **45-agent budget**.

### Phases and Available Roles

| Phase | Roles | Description |
|-------|-------|-------------|
| **P1 Research** | `research`, `strategy` | Research agents explore specific questions; Strategy synthesizes findings into the plan (use for large/uncertain tasks) |
| **P2 Revise** | `reviser` | Reviser reviews the plan for gaps/risks |
| **P3 Implement** | `implementor` | Executes assigned steps from the approved plan |
| **P4 Verify** | `verifier` | Runs tests and reviews quality |
| **P5 Ship** | `pr` | Opens the pull request (optional, only if user wants a PR) |

### Phase-Transition Role Selection

Call `list_teammates(phase="all")` once immediately after `team_create`. Reconcile the all-teammates result with `roles_by_phase` from `team_create`; the list call is authoritative for project/user roles added after team creation or roles hidden by team config. Do not call `list_teammates` at every phase boundary by default. Use phase-specific calls only when the agent needs to narrow or refresh a known role set.

| Point | When to call | Call |
|------------|--------------|------|
| Setup → P1 | Immediately after `team_create` returns | `list_teammates(phase="all")` |
| Later phases | Only if role availability/descriptions are stale or unclear | `list_teammates(phase="all")` or a specific phase |

If the all-teammates list disagrees with `roles_by_phase`, prefer the list result and note the discrepancy briefly. This keeps team mode aware of project-scoped roles such as `.cortex/agents/roles/*`.

### Sizing Guidance

Scale the team to match the task — not every role is needed for every workflow:

- **Small/clear task** (few files, well-understood scope): 1–2 research, 1 implementor, 1 verifier. Skip strategy, reviser, and PR.
- **Medium task** (multiple files, some ambiguity): 2–3 research, 1 reviser, 2–3 implementors, 1 verifier.
- **Large/uncertain task** (broad codebase impact, architectural decisions): 3–6 research + 1 strategy, 1 reviser, 3–5 implementors, 1–2 verifiers + 1 PR.

> **Default to subagents.** The main agent's job is orchestration and plan writing. Always spawn subagents for research, revision, implementation, and verification work — even when only one worker is needed for a phase. The main agent should only do substantive work itself when writing/revising the plan.

**You MUST state your reasoning** when selecting teammates — e.g.:
> Teammate selection: 2 research (auth middleware + database schema), 1 reviser, 3 implementors (one per service layer), 1 verifier — total 7 of 45 budget.

**Path B (autonomous)**: If the task is small and clear with a plan already written, run the **Cleanup Procedure** — standard single-agent flow handles everything. Skill done.

For all other cases, after stating your teammate selection, draft a phase plan with roles and counts per phase, then build the dependency graph.

---

## Building the Dependency Graph

After deciding your teammate selection, build the full step graph **before** spawning any workers.

1. Use `cortex ctx step add -t <tid> "<step text>" --role <role>` for each step.
2. Use `--depends-on <sid> [<sid>...]` to declare dependencies between steps.
3. Steps with `--depends-on` are not claimable until all listed steps are `completed`.
4. P3+ steps are created **lazily** — only after `ExitPlanMode` and user plan approval.

> **Steps are unbounded; role counts cap WORKERS, not steps.** Workers atomically claim from a shared pool, so N workers can drain M ≥ N steps. Write one step per discrete work item.

### Main-Agent Self-Work

The main agent coordinates by default. If the main agent performs substantive work itself — exploratory research beyond quick routing checks, plan synthesis/revision, implementation, verification, or failure recovery — that work must be represented as a ctx step before it starts:

1. Add a step with `--role main` and any phase dependencies that prevent duplicate teammate work.
2. Claim it with `cortex ctx step claim -t <tid> --role main` (or start that specific step if it was created only for main).
3. Do only the claimed scope, then mark that step done or failed before advancing gates.

Short coordination actions do not need self-work steps: reading notifications, running gate probes, sending `STRATEGY_SIGNAL`, spawning workers, or updating task metadata. Anything that could overlap with a teammate's assignment does need a step.

**IMPORTANT — plan-mode restriction:** During plan mode (P1 Research and P2 Revise), the main agent runs under a restricted bash allowlist that permits only `cortex ctx step add` and `cortex ctx step list` — it cannot `claim`, `start`, or `done` a step. Therefore, do **not** create a `--role main` step that gates other steps (i.e. one that appears in another step's `--depends-on`) during P1/P2: it cannot be transitioned to terminal until plan mode exits, so it will block all its dependents indefinitely. Instead, either (a) record that main work as a discovery / findings note rather than a gated step, or (b) create the main step without dependents and defer it (and anything that would depend on it) to P3+, where it can be claimed and completed.

Example:
```bash
# P1 — no dependencies
cortex ctx step add -t 42 "Research auth middleware" --role research    # → s-1
cortex ctx step add -t 42 "Research database schema" --role research   # → s-2

# P2 — depends on P1
cortex ctx step add -t 42 "Revise plan" --role reviser --depends-on s-1 s-2 # → s-3

# P3 — created after ExitPlanMode + user approval
cortex ctx step add -t 42 "Implement middleware" --role implementor --depends-on s-3 # → s-4
cortex ctx step add -t 42 "Implement handlers" --role implementor --depends-on s-3  # → s-5

# P4 — depends on P3
cortex ctx step add -t 42 "Verify implementation" --role verifier --depends-on s-4 s-5 # → s-6
```

---

## Spawning Workers

Before spawning workers for a phase, select from the initial `list_teammates(phase="all")` result and `roles_by_phase.<Phase>`. Call `list_teammates` again only when the agent needs to refresh role availability or descriptions.

**ALWAYS use `spawn_teammate(role, task_id, count)` to launch team workers.** Do NOT use the `task` tool directly with role names like "implementor" or "verifier" — those roles are not available as task subagent types. The `spawn_teammate` tool handles agent type resolution, budget tracking, and worker prompt construction.

`spawn_teammate` returns both worker labels (`spawned`) and real background agent ids (`agent_ids`). Use `agent_ids["<worker-name>"]` with `agent_output`; labels like `reviser-1` are not valid `agent_output` ids.

Workers use the claim-loop: each worker calls `cortex ctx step claim --role <role>`, executes the step, marks it done, then claims again.

**Default to notification-driven flow.** Workers surface output as task notifications. React to notifications; do not busy-loop `step list`.

Between notifications, do other useful work (drafting next-phase steps, reading discoveries).

If everything is idle and only one agent is finishing, prefer `agent_output(wait=true)` on that agent over polling.

### Notification Stall Fallback

Notifications can occasionally fail to arrive, or workers can exit silently without claiming a step (spawned before any matching step existed, or step had wrong role).

After **2 minutes** with no notifications while workers are expected to be running, run a stall-recovery probe:

1. **Step probe.** `cortex ctx step list -t <tid>` to see step state.
2. **Agent health check.** `agent_output(agent_id=<id>)` for each expected-alive worker. Cross-reference with `cortex ctx team get team-workflow-<tid> --json`.

| Probe finding | Action |
|---------------|--------|
| Step `completed`, no notification processed | Run **Completion Contract** |
| Step `in_progress`, agent alive with recent output | Wait; do NOT duplicate worker |
| Worker exited without claiming (e.g. `no_ready_step`) | Diagnose: missing step? blocked dep? Add/wait, then respawn |
| Worker process dead/failed, step still `claimed` or `in_progress` | Run **Failure Contract** (release + retry per phase). Only after this health check may the main agent recover or complete the step itself. |

After a probe, reset the 2-minute timer. Do not probe more than once per 2 idle minutes.

---

## Phase Gates

### Gate Authority

Phase advancement is valid only after the main agent runs `cortex ctx step list -t <tid>` and verifies the relevant role steps. Notifications are pointers, not proof. Agent output is proof only after `agent_output(wait=true)` or a completed task notification confirms the worker has exited and the final worker line is `Step <sid> complete:` or `Step <sid> FAILED:`.

Before advancing from any phase, run `cortex ctx step list -t <tid>` and verify that every step for the current phase's roles is terminal (`completed`, `failed`, or `cancelled`). Do **not** infer phase completion from spawned worker notifications alone.

If a worker failed/cancelled/exited and left its claimed step non-terminal, the main agent owns recovery only after a health check (`agent_output` plus step list/team state) proves the worker is no longer running. Apply the Failure Contract, either respawn the worker or claim a `main` recovery step and complete the work directly, then mark the step terminal before advancing.

Hard gates:
- **P1 → P2**: all Research-phase steps (`research`, `strategy`) completed or explicitly failed/cancelled under the Failure Contract, and the plan exists when `strategy` was used.
- **P2 → ExitPlanMode/P3**: all Revise-phase steps (`reviser`) completed or explicitly failed/cancelled under the Failure Contract. `ExitPlanMode` is forbidden while any reviser step is `pending`, `claimed`, or `in_progress`. Read reviser discoveries and update `{plan_path}` before `ExitPlanMode`. If a reviser failed and will not be retried, write a user-visible note plus a discovery documenting the missing review coverage; do not silently convert the step to done.
- **P3 → P4**: all Implement-phase steps terminal. Do not verify while implementation steps are still claimed/running.
- **P4 → P5/Cleanup**: all Verify-phase steps terminal. Do not ship without verifier results unless the user explicitly overrides after being told verification did not complete.

---

## ExitPlanMode Gate

- **Path A/C (explicit team request):** ExitPlanMode after P2 (Revise) phase completes. If the main agent decided to skip P2 (small task with no reviser), ExitPlanMode after the P1 plan is written.
- **Path B (autonomous — plan already written):** ExitPlanMode was already called before skill loaded — skip.

### Main-Agent Plan Writing (no strategy agent)

When the main agent writes the plan itself (strategy agent was skipped), it MUST follow the same plan format as the strategy agent. Specifically, every implementation step in `.cortex/plans/plan-<tid>.md` MUST include a `#### Context Sources` subsection that cites the discoveries and offloaded research results that informed it. This ensures implementors and revisers have traceable context.

Required format per step:
```markdown
### Step N: <Title>
<What file(s) to change, what to change, and why>

#### Context Sources
- Discovery `<msg-id>` (<sender>): <one-line summary of the finding>
- Offload `<msg-id>` (<sender>): `<file_path>` — Cache: <offload_cache_path>
  Key excerpt (lines N-M): <relevant signatures or config>
```

If a step has no relevant discoveries, write `No external context needed` with a brief explanation. A plan without context sources forces implementors to re-research from scratch — defeating the purpose of P1.

Before calling `ExitPlanMode`, run `cortex ctx step list -t <tid>` and confirm the P2 gate above. If any Revise-phase step is still `pending`, `claimed`, or `in_progress`, wait/recover; do not call `ExitPlanMode` yet.

### Plan File Write Gate

Before calling `ExitPlanMode`, verify `.cortex/plans/plan-<tid>.md` exists, is non-empty, and includes revisions from P2 feedback when P2 ran. If plan-mode write tools are unavailable or fail, do **not** call `ExitPlanMode`. Instead, recover by waiting for/respawning `strategy`, asking the user whether to continue without team implementation, or aborting with the Cleanup Procedure.

After ExitPlanMode returns and the user accepts the plan, use the initial all-teammates list plus `roles_by_phase.Implement` to select implementor roles, then create P3+ steps and spawn implementors. Call `list_teammates` again only if the available roles/descriptions are stale or unclear.

---

## Main Agent Rules

1. Complete Setup BEFORE doing anything else.
2. Do NOT call `AskUserQuestion` before completing setup.
3. Do NOT call `EnterPlanMode` manually — plan mode is activated by `team_create` during Setup. Only call `EnterPlanMode` in revision cycles (after a prior `ExitPlanMode`).
4. `ExitPlanMode` is called exactly once per plan mode cycle.
5. During plan mode, update `{plan_path}` only via `Write`, `Edit`, or `str_replace_editor`. No `apply_patch`. No mutating source files.
6. Do NOT narrate orchestration mechanics. Use brief user-facing updates: "Researching...", "Planning...", "Implementing...", "Reviewing...".
7. **Canonical plan path:** `{plan_path}` MUST be `.cortex/plans/plan-<tid>.md` (under `{cwd}`, not at root) — `spawn_teammate` workers default to this path. Always pass `--plan .cortex/plans/plan-<tid>.md` to `cortex ctx task update`. If misplaced, move it before `ExitPlanMode` or P3 spawning.
8. Do not directly implement until all pre-P3 gates are satisfied: P2 gate passed, Plan File Write Gate passed, `ExitPlanMode` returned, the user approved the plan, P3 steps were created lazily, and implementors were spawned.
9. Do not do teammate-like work outside the task graph. If you are going to research, revise a plan, implement, verify, or recover a failed worker yourself, first add/claim a `main` step so teammates and phase gates see the work.
10. Do not create a dependency-gating `--role main` step during P1/P2 (plan mode). The main agent's plan-mode bash allowlist only permits `cortex ctx step add`/`list`, so it cannot `claim`/`start`/`done` a step until plan mode exits — a gating main step would block its dependents indefinitely. Record such work as a discovery, or defer the main step (without dependents) to P3+. See **Main-Agent Self-Work**.

### Forbidden Anti-Patterns

- Do not call `ExitPlanMode` while a `reviser` worker is still running or its step is still `pending`, `claimed`, or `in_progress`.
- Do not mark a running worker's step done based on partial output, stale notifications, or because the main agent wants to advance phases. The only exception is after a health check proves the worker failed/exited and the main agent has performed explicit recovery.
- Do not start implementation while plan mode is active or before user approval of the plan.
- Do not treat a failed plan-file write as permission to skip review and implement directly.
- Do not perform unscheduled exploration or edits that overlap with worker assignments; add and claim a `main` step first.

---

## Completion and Failure Contracts

Completion notifications are pointer-only `<task-notification>` blocks (`<agent-id>`, `<agent-name>`, `<worker-role>`, `<status>`, optional `<output-var>`, `<hint>`). Worker output is NOT inlined — call `agent_output(agent_id=<id>)` to read it and find the terminal `Step <sid> complete:` / `Step <sid> FAILED:` line.

### Completion Contract

When a `<task-notification>` arrives with `<status>completed</status>`:
1. Call `agent_output(agent_id=<id>, wait=true)` to read the worker's full output and confirm it has exited.
2. Find the final `Step <sid> complete: <text>` line. If the output is missing this line, treat it as incomplete and run the Failure Contract instead of advancing.
3. Run `cortex ctx step list -t <tid>` to confirm the step is `completed`. If still `in_progress`, run `cortex ctx step done <sid> -t <tid>` only when the worker has exited and the final completion line names the same `<sid>`.
4. Check for newly unblocked steps — spawn workers for them if it's the right phase.

**Do NOT leave a completed step `in_progress` while proceeding. Do NOT mark a still-running worker's step done.**

If a worker's step is `claimed` or `in_progress` and the worker has not produced a terminal completion/failure line, the main agent must not call `cortex ctx step done`. First run a health check: `agent_output(agent_id=<id>, wait=true)` when a notification says the worker ended, or `agent_output(agent_id=<id>)` plus `cortex ctx team get team-workflow-<tid> --json` during stall recovery. If the health check shows the worker is still running, wait. If it proves the worker failed/exited, run the Failure Contract; only after explicit recovery may the main agent mark the step terminal.

### Failure Contract

When a `<task-notification>` arrives with `<status>failed</status>` or `<status>cancelled</status>`, OR when `agent_output` shows a `Step <sid> FAILED: <reason>` line:
1. Run `cortex ctx step list -t <tid>` to refresh.
2. Confirm the worker is no longer running with `agent_output(agent_id=<id>, wait=true)` when an agent id is available. Do not mark its step done while the worker is still alive.
3. Log the failure:
   ```
   cortex ctx discovery add "Agent failed step <sid>: <reason>" --title "Step failure" --tags agent-failure --team team-workflow-<tid>
   ```
4. By phase:
   - **P1 Research**: Wait for other researchers. Partial research is OK — note the gap.
   - **P2 Revise**: Proceed with available reviser feedback. Note missing coverage.
   - **P3 Implementation**: Retry once (spawn new Implementor). If fails again, ask user.
     > Budget note: Retry spawns count against the 45-agent budget. If a retry would exceed 45, do the work directly.
   - **P4 Review/Ship**: Respawn failed Verifier. Do NOT ship without verifier results.

---

## Reference

### Agent Budget

Hard budget: **45 agents per workflow.** This is the only enforced limit — there are no per-phase advisory budgets.

Before every spawn, check `budget_remaining` from the `spawn_teammate` response. If a spawn would exceed 45 total agents (including retries from earlier failures), do the work directly instead of spawning.

Retries count against the 45-agent budget. A failed agent that gets respawned costs two slots. Plan accordingly — leave headroom for retries when selecting initial team size.

### Discovery Read Discipline

Read discoveries minimally — only when:
1. A subagent fails and you need context to respawn or complete the step yourself.
2. At end of P2 to incorporate reviser feedback into the plan (`--type reviser --team`).
3. At end of P4 if verifier flagged issues (`--type verifier --team`).

Always include `--team {team_name}` to prevent cross-team bleed.

### Reviser Completion Flow

When the Reviser completes: confirm via `cortex ctx step list`. Read its discoveries. Revise `{plan_path}`. Confirm all other Revise-phase steps are terminal. Then call `ExitPlanMode`.

### Shared Procedures

#### Cleanup Procedure
0. If plan mode is still active — any workflow that never called `ExitPlanMode` (research/analysis-only, plan-only, or an abort during Research/Revise) — call `ExitPlanMode` before teardown, so `team_delete` and `cortex ctx task done` are not subject to the plan-mode work-transition guard. If `ExitPlanMode` can't be called or fails, proceed to step 1 anyway rather than dead-stopping.
1. Call `team_delete` (no args — reads `CORTEX_TEAM_NAME`). It also disables the team-mode toggle and closes tmux panes; do NOT shell out to `cortex ctx team delete` directly.
2. `cortex ctx task done <tid>` — auto-deletes the plan file and archives steps.

If `team_delete` fails: run `cortex ctx team delete team-workflow-<tid>`, clear messages/discoveries with `cortex ctx {message,discovery} clear --team team-workflow-<tid>`, then `/team off`.

#### Workflow Abort

If the workflow fails before P4 cleanup, always run the **Cleanup Procedure**. If the failure happened during Research or Revise (still in plan mode), begin with Cleanup step 0 (`ExitPlanMode`) so `team_delete` and `cortex ctx task done` are not blocked by the plan-mode work-transition guard.

#### CLI quirks

- `cortex ctx step start` takes ONE id per call — chain with `&&`.
- `discovery`: scope reads with `--type <role>`; always pass `--team {team_name}`; `discovery search` accepts no filter flags.
