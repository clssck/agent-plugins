---
name: cortex-sense-agent
description: "Create a CoWork / Snowflake Intelligence agent grounded in a built Cortex Sense context, or add Cortex Sense to an agent that already exists. Derives the domain profile automatically from the context's eval set, a cortex_sense probe, and the manifest — the builder confirms rather than fills in a questionnaire — then wires the agent with a single experimental flag, smoke-tests it against a real question, and reports the CoWork URL. Use when: turning a built context into an agent, deploying a context for end users, adding cortex_sense to an existing agent, reviewing how an agent uses SQL execution. Triggers: create an agent for <domain>, create a cowork agent for <domain>, deploy <domain> as an agent, make an agent from this context, add cortex sense to <agent>, wire <agent> to cortex sense, enable cortex_sense on <agent>, @cortex-sense resume <domain> + an agent verb."
parent_skill: cortex-sense
---

# Agent

Turns a built context into something people can actually ask questions of. Everything upstream of here — scope, build, eval — produces knowledge; this produces the consumer.

## When to load

The builder wants an agent that answers questions from a Cortex Sense context, or wants an existing agent to start using one.

If no manifest exists for the named domain, route to `../setup/SKILL.md`. A context that has never been built has nothing to ground an agent in.

## Setup

Read before writing any DDL:

- `../reference/AGENT_SPEC.md` — the spec contract: the one flag, the resulting tool inventory, the tools you must *not* declare, real `doc_type` values, preflight, DDL, retrofit merge, CoWork, smoke test. **All call shapes and SQL live there; do not restate them here.**
- `../reference/AGENT_INSTRUCTIONS.md` — how the domain profile is derived (§3) and how the two instruction blocks are composed (§4a). **Load before §3.**
- `../reference/CONTEXT_LOOKUP.md` — `cortex_sense` parameter semantics, and the cross-context filtering contract the §3 probe must apply.
- `../reference/SCOPE_MANIFEST.md` — manifest fields consumed in §2.
- `../reference/EVAL_FORMAT.md` — loading `eval.yaml`, the strongest input to the §3 profile.

`<WORKSPACE_DIR>` and `<SKILL_DIR>` are placeholders the agent resolves.

## Two modes

| Mode | Trigger | Path |
|---|---|---|
| **create** | "create an agent for `<domain>`", "deploy `<domain>` as an agent", "make a CoWork agent" | §0 → §1 → §2 → §3 → §4a → §4b → §5 → §6 → §8 |
| **retrofit** | "add cortex sense to `<agent>`", "enable cortex_sense on `<agent>`", "wire `<agent>` to `<domain>`" | §0 → §1 → §2 → §3 → §7 (uses §4a) → §5 → §8 |

When the builder names an existing agent, that is retrofit. When they name a domain, that is create. If they name both and the agent already exists, treat it as retrofit and say so in one line.

Both modes run §1 and §2 — retrofit needs the context FQN to pin into the instructions and the manifest to derive them from, exactly as create does. Both modes pass through §5, which is the only gate that authorises DDL. Neither mode writes anything before it.

**Two builder touchpoints, total.** §3's confirm (one look at the resolved context and the derived profile) and §5's DDL gate. Everything else is derived, defaulted, or reported. Do not add a third: no separate context confirmation, no build-status prompt, no grant question. If a step seems to need builder input, first check whether it can be derived from the eval set, the context, or the manifest.

## 0. Pre-flight

Run `doctor` once before any other call, and handle exactly as `../setup/SKILL.md` §1 does (full contract in `../reference/STORAGE.md`):

```bash
uv run --project <SKILL_DIR>/.. python <SKILL_DIR>/../scripts/persist_state.py doctor
```

- `snow_cli == "missing"` → render the install line and stop.
- `needs_database_schema: true` → ask once for a database and schema, set the env vars, re-run `doctor`. Never mention env-var names.
- Otherwise (`storage_ready: true`) → continue silently.

This is needed because §1 reads the context registry and §6/§7 issue DDL — both fail confusingly without a working connection.

## 1. Resolve the context

**Resolve silently — do not confirm here.** Everything this section learns is surfaced in §3's single confirm block. The only reason to prompt in §1 is genuine ambiguity.

Call `list-contexts` per `../reference/STORAGE.md`. This is the only authoritative source of registered contexts — they are not in `INFORMATION_SCHEMA`, and a `SHOW OBJECTS` against the context schema returns nothing even when contexts exist.

Capture `name`, `database_name`, `schema_name`, and `last_processed_at` verbatim. The three-part FQN is pinned into the orchestration instructions in §4a and is case-sensitive — see `../reference/AGENT_SPEC.md` "Calling cortex_sense".

**Resolve the name** the same way `../query/SKILL.md` does. Context families commonly share a prefix (`<domain>`, `<domain>_mini`, `<domain>_v2`, `<domain>_v2_1`), so a typed name can match several:

- **Exact match on `name`** → use it, no prompt, even when other contexts share the prefix.
- **A single prefix/substring match** → use it; the resolution is visible in §3's confirm.
- **Two or more matches and no exact match** → this is the one case worth a prompt. Ask which, listing candidates with `last_processed_at`. Never pick the longest, newest, or highest-versioned name on the builder's behalf: the wrong sibling yields an agent that works but answers from the wrong knowledge base, which is much harder to notice than an error.
- **Not registered** → list what is available and stop.
- **Nothing named** → ask once, listing contexts with their `last_processed_at`.

**Note whether the context is built.** Compare `last_processed_at` against the manifest `updated_at` from §2. Do not prompt about it here — carry the verdict into §3, which reports the build age on its header line and adjusts its footer if the build has not landed. A builder provisioning an agent ahead of a build is legitimate and must never be blocked.

## 2. Load the manifest

Load `scope.yaml` per `../reference/STORAGE.md` "Loading — one call". Extract `business_domain`, `warehouse`, `sources[]`, `additional_instructions`, and — **if present** — `concepts[]`, `relationships[]`, `associations[]`.

**Expect the definition fields to be absent.** Many real manifests carry rich `sources[]` and nothing else: no `concepts` key at all, and `additional_instructions: []`. This is normal for a context scoped by pattern rather than curated by hand, so treat their absence as the common case, not an error.

Record which of the two definition inputs you actually have, because §4a block D depends on it:

| Manifest state | Consequence for §4a block D |
|---|---|
| `concepts[]` / `additional_instructions` populated | Block D is built from them. Normal path. |
| Both empty or absent | The *manifest* has no definitions — but the *built context* may still have plenty, so do not conclude anything yet. Fall back to `sources[]` (below) for vocabulary, and let §3's context probe supply the meaning. |

**Deriving vocabulary from `sources[]` when definitions are absent.** `sources[]` is more useful than it looks. Harvest, in this order:

1. **`streamlit_apps` rule `description` fields** — these are dashboard names, which are the product/business areas the team actually reports on (e.g. "Cortex Code Metrics", "Northstar", "Native Apps"). They are the single best vocabulary source for §4a item 1.
2. **`catalog_objects` pattern prefixes** — the in-scope databases and schemas, for the scope paragraph in block D.
3. **`excluded: true` rules** — these become hard prohibitions in block D (e.g. a dev-clone database that must never be queried). An exclusion in the manifest is a real instruction and must survive into the prompt.
4. **`semantic_views` rules** — named views are strong table candidates worth mentioning.

The manifest supplies *scope*: which tables are in play, and what must never be queried. It does not say what the metrics mean or what people actually ask — §3 derives that from the built context itself. Treat §2 as necessary but not sufficient, and never build instructions from the manifest alone.

If the manifest is missing, route to `../setup/SKILL.md`.

## 3. Derive the domain profile — do not interview the builder

**Do not ask the builder to describe the context.** The parent skill's builder principle governs here: CoCo proposes, the builder steers. Asking someone to type out who the audience is and what the traps are is asking them to do work CoCo can do — and it is work they already did once, when they scoped the context.

It also produces a worse result. An interview's realistic default is "skip", which yields the generic agent the interview was meant to prevent. Derivation has no skip path.

**The built context is richer than the manifest.** §2 read `scope.yaml`, which records *scope* — patterns and sources. The built context additionally contains `ontology_node` definitions, `qbe` production SQL, and `table_entity` grain and filters that appear nowhere in the manifest. A manifest with no `concepts` routinely sits in front of a context that returns real definitions, so never infer domain poverty from a thin manifest — query the context and find out.

Assemble the profile from these sources, in priority order — full contract, including the cross-context filter, in `../reference/AGENT_INSTRUCTIONS.md` "Deriving the profile":

1. **`eval.yaml`** — the strongest signal. Confirmed questions are real questions real users asked.
2. **A `cortex_sense` probe of the context itself** — the built context holds definitions the manifest does not. `context_names` is not a hard filter; filter results against the manifest scope before using them.
3. **Manifest definitions** — `concepts[]`, `relationships[]`, `associations[]`, `additional_instructions` from §2.
4. **Manifest `sources[]`** — dashboard descriptions as vocabulary, pattern prefixes as scope, `excluded: true` as prohibitions.

Stop when you have enough; the first two usually suffice.

### The single confirm

This block is the **only** confirmation before the §5 DDL gate. It carries everything §1 resolved and everything derivation found, so the builder gets one look and one decision. Lead with the resolved context and its build age so a wrong-sibling pin or a stale build is obvious at a glance:

```
Building an agent on <domain>
(<DB>.<SCHEMA>.<name>, built <N> days ago)

  Purpose      <one line: what this agent answers>
  Asked about  <top areas / metrics, from eval questions + qbe METRIC_NAMEs>
  Key tables   <2–4 workhorse tables with their grain>
  Definitions  <metrics with canonical formulas found, or "none found in context">
  Watch out    <traps actually observed: exclusions, near-duplicate metrics,
                always-applied filters seen in qbe patterns>

  (from <n> eval questions · <n> context documents · manifest)

  type: go · or tell me what's wrong
```

Advance only on an **affirmation** — `go`, `ok`, `yes`, `looks good`, `proceed`, or an equivalent. A **question** is not a `go`: answer it and re-display the block. An **edit** is not a `go` either: fold it in, echo it in one line, and continue — re-render the whole block only if the correction changes which context or which tables are in play. Silence is not consent; wait.

Omit any row derivation could not fill rather than printing an empty label. If only `Purpose` and `Asked about` are available, show two rows.

**Not every row goes into the prompt.** `Purpose` and `Asked about` feed §4a item 1, `Watch out` feeds item 9 — but `Key tables` and `Definitions` are builder-facing evidence only, never copied into the instructions. The reasoning and the full mapping are in `../reference/AGENT_INSTRUCTIONS.md` "What of this reaches the prompt".

**If the build has not landed**, replace the header's build age with `build not finished` and extend the footer — this is the one variant:

```
  type: go (it'll work once the build lands) · check build · or tell me what's wrong
```

On `check build`, route to `../test/SKILL.md`, which owns that verb and the status-inference contract, then return here.

If the builder volunteers a metric definition the context does not have, offer once to record it via `../refine/SKILL.md` so the *next build* learns it. A definition that lives only in an agent prompt is invisible to every other consumer of the context and to eval — the prompt is not the knowledge layer.

**When derivation comes up empty** — no `eval.yaml` and no documents from the probe — say so inside the same block rather than adding a round-trip:

```
Building an agent on <domain>
(<DB>.<SCHEMA>.<name>, build not finished)

  I couldn't learn much yet — the context returned no documents, so this agent
  will be generic until the build lands. Scope is <n> patterns across <DB list>.

  type: go · check build · or tell me in a sentence what it's for
```

That last verb is an offer, not a gate. `go` proceeds.

## 4a. Compose the instructions

Compose both instruction blocks per `../reference/AGENT_INSTRUCTIONS.md` "Composing the instructions", which carries the nine required items grouped A–D and the rule that block D is the only part making this agent different from a generic one.

Two things to hold onto while composing, because they are the ones most often lost:

- **Item 2, the retrieval gate** — one `cortex_sense` call first, pinned to the §1 FQN, no SQL before it returns.
- **Block D** — if the manifest carried no definitions and the probe found none, block D reduces to scope plus the honesty clause. Say so at §5 rather than letting the builder believe the agent learned more than it did.

## 4b. Anti-patterns to avoid

**Do not carry over these** from hand-written Cortex Sense agents. Each was verified obsolete or actively harmful:

- `datamart_max_results: 0` — obsolete, and it suppresses a document class. See `../reference/AGENT_SPEC.md`.
- Instructions for suppressing `snowscope_search` / `generic_semantic_context` — those tools are absent.
- A fallback-to-sandbox path — there is no `code_execution` tool unless the builder explicitly asked for one.
- Prose `doc_type` labels — they never match the API response.
- **Table names or metric formulas pinned into the prompt.** The most tempting mistake, because it makes the agent look better on the first question and worse on every question after a rebuild. Schema-level scope and prohibitions belong in the prompt; specific tables, columns, grains, and formulas come from retrieval. See §3 "What of this reaches the prompt".

## 5. Show the spec and confirm

Render the full spec for review before any DDL. **This section is the only gate that authorises writing to Snowflake** — both modes pass through it, and nothing before it mutates anything.

In create mode render `Here's the agent I'll create:`; in retrofit mode render `Here's the change I'll apply to <agent>:` and show the merged spec plus the instruction diff from §7. The footer verb changes with the mode (`create` vs `apply`); everything else is identical.

```
Here's the agent I'll create:            ← retrofit: "Here's the change I'll apply to <agent>:"

  Name          <DB>.<SCHEMA>.<AGENT_NAME>
  Display name  <Readable Name>
  Context       <DB>.<SCHEMA>.<context_name>
  Model         auto
  Flags         EnableCortexSense (the only one needed)
  Tools         cortex_sense, system_execute_sql, table_details
                (present without being declared — nothing goes in tools[])
  Grounded on   <n> eval questions · <n> context documents · manifest scope

Orchestration instructions (<n> lines):
<the composed instructions, in full — do not summarise or elide>

  type: create · edit <what to change> · done      ← retrofit: "apply · edit … · done"
```

Show the instructions in full. They are the entire substance of the agent, and a builder cannot review a summary of them.

Accept free-form edits ("make it stricter about trial accounts", "it should decline forecasting questions"), fold them into §4a, and re-render this block.

Default the agent name to the domain name uppercased with a readable `display_name`; accept an override. Default the target schema to the context's own `<DB>.<SCHEMA>`; accept an override.

> ⚠️ **MANDATORY CHECKPOINT — do not run any DDL until the builder confirms.**
> Valid triggers: `create` / `apply` / `ok` / `go` / `yes`, or an equivalent affirmation.
> **Rendering this block is NOT confirmation.** Anything else is an edit — fold it in, re-render, and wait again.
> On confirmation: create mode → §6. Retrofit mode → §7 step 6 (the write-back).

## 6. Preflight, then create

> ⚠️ Reached only after the §5 checkpoint. If you arrived here without an explicit confirmation, go back.

Run the role and privilege preflight from `../reference/AGENT_SPEC.md` "Preflight". Resolve it before attempting the DDL — the error message when the primary role is wrong misleadingly suggests a missing grant when the role simply needs switching.

Then create the agent per `../reference/AGENT_SPEC.md` "DDL", which begins with a `SHOW AGENTS LIKE` collision check. **Never `CREATE OR REPLACE` here** — the agent name is derived from the domain, so a second run would silently overwrite a deployed agent and undo the §5 checkpoint. On a collision, offer retrofit (§7) or a new name; a collision is the signal the builder wanted retrofit mode.

Set the profile per "CoWork" — without a `display_name` the agent shows in CoWork as a raw identifier.

**Do not ask about grants.** The creating role can already use the agent, which is all a first draft needs. Adding a "who else should access this?" prompt taxes every builder to serve the minority who are ready to share on day one. Create it creator-only, and mention sharing once in the §8 report.

Only run the grants from `../reference/AGENT_SPEC.md` "CoWork" if the builder actually asks to share it — then also mention that consuming users need a default role and default warehouse on their Snowflake user, or CoWork cannot start a session for them.

Detect an explicit Snowflake Intelligence object rather than assuming one exists.

Report failures plainly and stop; do not retry a permission error against a different schema. Continue to §8.

## 7. Retrofit — add Cortex Sense to an existing agent

Read, merge, show the delta, **then hand off to §5 for confirmation before writing**. The risk here is not the flag — it is silently changing an agent someone already depends on. Steps 1–5 are read-only; step 6 is the only write and it runs only after the §5 checkpoint.

1. **Read the current spec** (`DESCRIBE AGENT`) and merge additively per `../reference/AGENT_SPEC.md` "Retrofitting". Preserve every existing `experimental` key, including undocumented ones.

2. **Check for committed versions.** If the agent has any, the spec change goes to LIVE but unversioned runs resolve to DEFAULT — the change will appear to do nothing. Surface this and route to `cortex-agent/agent-versioning` rather than guessing:

   ```
   <agent> has committed versions (<list>), so a change to LIVE won't affect
   normal runs until it's committed and made default. I can write it to LIVE
   now; committing and promoting is handled by the agent-versioning skill.
   ```

3. **Show the tool delta.** Derive it **analytically** — do not ask the agent to enumerate its own tools. A live `DATA_AGENT_RUN` self-report names tools inconsistently ("the SQL execution tool" vs `system_execute_sql`), can be partial, and varies between runs.

   Instead: read the `experimental` block and `tools[]` from the `DESCRIBE AGENT` spec in step 1, then look up what each flag contributes using `../reference/AGENT_SPEC.md` "Tool inventory". That table is exact — it was established with a no-flag control — so the before and after inventories are computable without asking. Note that an agent with a `cortex_analyst_text_to_sql` tool may already have `system_execute_sql`, so listing it as new would be wrong:

   ```
   Adding Cortex Sense to <agent> changes its tools:

     + cortex_sense          retrieves context from <context FQN>
     + <other tools that are genuinely new for this agent>

     already present: <tools it had before that also appear after>
     unchanged:       <existing declared tools>
   ```

4. **Work through the SQL-execution implication explicitly.** Whether or not `system_execute_sql` is new to this agent, after the change it is not scoped to a semantic view — the agent can query anything its caller can read. For an agent that until now only had Analyst tools, that is a real widening and deserves a deliberate decision, not a footnote. Adjust the framing to which case applies:

   ```
   This gives <agent> the ability to run SQL against any table its caller can
   read — not just the ones behind a semantic view. Two things follow:

     • Its instructions need a retrieval-first rule, or it may write SQL from
       guessed table names. I'll add one.
     • Its blast radius is now the caller's read access. The agent can't exceed
       what the user could already query themselves, but it can reach further
       than a semantic-view-only agent could.

   How should it prefer its tools?
     a) Cortex Sense first, SQL only to compute a value  (recommended)
     b) Keep existing tools primary, Cortex Sense as a fallback
     c) Cortex Sense only — don't use the SQL tool for analysis
   ```

   Fold the answer into the orchestration instructions. For (b), the existing tools keep priority and Cortex Sense is described as a supplement — do not impose the strict retrieval gate from §4a item 2 on an agent whose primary path is a semantic view, because a hard gate in front of a working Analyst tool makes it slower without making it more correct.

5. **Merge instructions rather than replacing them.** If the agent already has orchestration instructions, append a Cortex Sense section and leave the rest intact. Show a diff of what is being added. Replacing an existing prompt wholesale destroys tuning you cannot see.

   Compose that appended section per **§4a**, with two adjustments: item 1 (identity) is already covered by the existing prompt, so skip it; and item 2 (the retrieval gate) is written as a gate only if the builder chose (a) in step 4 — for (b) it becomes a supplement, for (c) the SQL guidance is dropped. Run **§3** first if the profile has not already been derived in this session; without it the appended section will be as generic as any hand-written one.

6. **Give the builder a restore path, then hand off to §5 and write back.** Retrofit mutates an agent others may depend on, and this path is not yet verified end-to-end — so surface the rollback before the write, not after a failure. The current spec is already in hand from step 1; print it as a runnable restore statement and say plainly what it is for:

   ```
   Saving the current spec first. If this goes wrong, restore it with:

     ALTER AGENT <name> MODIFY LIVE VERSION SET SPECIFICATION $$
     <the spec read in step 1, verbatim>
     $$;
   ```

   Also write it to `<WORKSPACE_DIR>/<agent_name>.spec.bak.yaml` so it survives the conversation. A builder will not think to capture this themselves, and a retrofit that drops tuned instructions is unrecoverable without a reference copy.

   Then render the merged spec and instruction diff through §5 and wait for its checkpoint. Only after the builder confirms, write back with `ALTER AGENT ... MODIFY LIVE VERSION SET SPECIFICATION` per `../reference/AGENT_SPEC.md` "Retrofitting". Continue to §8.

   Never write back directly from this section. An `ALTER` that has not passed §5 is an unapproved change to an agent other people may be using.

## 8. Smoke test, then report

Verify the wiring rather than asserting it. Pick one question: prefer a confirmed question from the domain's eval set (`eval.yaml`) if one exists — it already has a known expected answer — otherwise derive one from a manifest concept.

Run it per `../reference/AGENT_SPEC.md` "Smoke test" and check the four signals:

| Signal | Read from | If it fails |
|---|---|---|
| `cortex_sense` was called | a `tool_use` entry naming it | The retrieval gate is not binding — strengthen §4a item 2 and re-apply. |
| Retrieval returned documents | the `tool_result` content | Likely the build hasn't landed or the FQN is wrong. Re-check the FQN's case against `list-contexts`. |
| SQL executed | a `system_execute_sql` `tool_use` with `status: success` | On a missing-warehouse error, set the manifest `warehouse`; on a permission error, report the object and stop. |
| An answer came back | a `text` entry | Report what was missing — never present an unverified agent as working. |

Then report, with the outcome stated rather than implied:

```
Created <DB>.<SCHEMA>.<AGENT_NAME>, grounded in <context FQN>.

Smoke test — "<question>"
  cortex_sense       <n> documents (<doc_type list>)
  system_execute_sql <success / error>
  answer             <the answer, trimmed>

Open it in CoWork: https://ai.snowflake.com
  (Look for "<display_name>".)

Only you can use it right now. To let others in, say "share it with <role>".

  type: test another question · edit instructions · done
```

If the smoke test failed, lead with the failure and what it means. An agent that was created but cannot answer is not a success, and reporting it as one wastes the builder's next hour.

**Footer verbs.** `test another question` re-runs this section with a new question. `edit instructions` returns to §4a to recompose, then re-renders §5 and waits at its checkpoint again before writing — an instruction change is a spec change and needs the same approval as the original. `done` ends the session.

## What this skill never does

- Declare `system_execute_sql`, `cortex_sense`, `table_details`, `read`, or `server_skill` in `tools[]` — they are present without being declared; declaring them breaks the agent at runtime
- Run `CREATE AGENT`, `ALTER AGENT`, `GRANT`, or any other DDL before the §5 checkpoint has been explicitly confirmed
- Use `CREATE OR REPLACE AGENT` in create mode, or auto-rename around a name collision — surface the collision and offer retrofit
- Ask an agent to enumerate its own tools; derive the inventory from `DESCRIBE AGENT` plus the verified table in `../reference/AGENT_SPEC.md`
- Write back a retrofit without first giving the builder a runnable restore statement
- Treat a builder's question as consent to proceed
- Add any experimental key other than `EnableCortexSense`, or remove an existing one without showing the builder the consequence
- Pass `datamart_max_results` in the generated instructions
- Write orchestration instructions that reference tools the agent does not have
- Pin table names, columns, grains, or metric formulas into the prompt — those are retrieved per turn; the prompt carries vocabulary, schema-level scope, and policy only
- Copy the §3 confirm block into the instructions wholesale; `Key tables` and `Definitions` are builder-facing evidence, not prompt content
- Branch on prose `doc_type` labels instead of the real API values
- Replace an existing agent's instructions wholesale during retrofit
- Interview the builder for anything it can derive from the eval set, the built context, or the manifest
- Add a builder touchpoint beyond §3's confirm and §5's DDL gate — no separate context confirmation, no build-status prompt, no grant question
- Ask who to grant the agent to; create it creator-only and mention sharing in the §8 report
- Report success without a smoke test, or describe a failed smoke test as working
- Record a new metric definition only in the prompt — offer `../refine/SKILL.md` so the context learns it
- Run `CREATE SNOWFLAKE INTELLIGENCE`, or `ALTER SNOWFLAKE INTELLIGENCE` without first confirming the object exists
- Handle version commits or promotion — route to `cortex-agent/agent-versioning`
- Delete or replace an agent the builder did not name
