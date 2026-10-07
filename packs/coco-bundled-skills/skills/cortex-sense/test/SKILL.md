---
name: cortex-sense-test
description: "Test a built Cortex Sense use case. Queries the active context via the cortex_sense MCP tool (when available) or the SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT SQL function fallback, and reports best-effort build status. For scored eval sets (generate questions, score answer correctness, diff runs), use eval/SKILL.md. For cross-context search without a named use case, use query/SKILL.md instead. Use when: validating a use case after the build, checking if the build is done, looking up what the active context knows, spot-checking answers. Triggers: test the <use case> context, validate sales context, run questions against <use case>, check build, is the build done, look up <table> in <use case>, what does the <use case> context know about <X>, @cortex-sense resume <use case> + a query."
parent_skill: cortex-sense
---

# Test

## When to load

The user wants to validate a domain context or look up what the active context knows.

If a manifest doesn't exist for the named domain, route to `setup/SKILL.md`.

## Status

Context lookup is **fully functional** through two paths: the `cortex_sense` MCP tool (when registered) and the `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT` SQL system function (fallback, no env vars required — see `../reference/CONTEXT_LOOKUP.md`).

For structured evaluation (generating questions, scoring answer correctness, diffing runs), use `../eval/SKILL.md` — route there when the builder asks for an eval set or replies to the setup confirm block with test questions.

<!-- Structured eval (generate questions, score answer correctness, diff runs) is implemented in
     ../eval/SKILL.md. Route there when the builder says "generate eval", "run eval",
     "score the context", or replies to the setup confirm block with test questions. -->

## On entry: load the manifest

Before rendering anything, run `doctor` once and handle exactly as `../setup/SKILL.md` §1 does (full contract in `../reference/STORAGE.md`): `snow_cli == "missing"` → install line and stop; `needs_database_schema: true` → ask once for a database and schema, set the env vars, then re-run `doctor`; otherwise continue silently. The SQL fallback (`SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT`) is available whenever `snow` works — it needs no env vars (see `../reference/CONTEXT_LOOKUP.md`).

```bash
uv run --project <SKILL_DIR>/.. python <SKILL_DIR>/../scripts/persist_state.py doctor
```

Then load the manifest to get the domain's metadata for the one-line summary.

Use `get-stage-file` per `../reference/STORAGE.md` "Loading — one call". The SQL handles both legacy base64-encoded files and plain-YAML files automatically. Read `updated_at` from the loaded YAML — that is the "last updated" value for the one-line summary below.

If the load returns no manifest, route to `../setup/SKILL.md`.

`<WORKSPACE_DIR>` and `<SKILL_DIR>` are placeholders the agent resolves.

## Open the session

Render once, on entry:

```
Testing the <domain> context.

(This sub-skill echoes what the active context returns for queries you give me.
 To build a scored eval set, type: generate eval)
```

Then a one-line summary per `../reference/SUMMARY_FORMAT.md` so the builder sees what they're testing against (domain name, and the `updated_at` loaded above rendered as a relative "last updated" time).

## Verb: check build

If the builder asks whether the build is done / running / failed ("check build", "is the build ready?", "did the build finish?"), report **best-effort** status by following the full contract in `../reference/BUILD_STATUS.md` (inputs, inference table, and the single verdict line). Do not restate its steps here.

This is inference, not a true state field — never imply a precise progress percentage or a specific ETA. If the verdict is `ready`, offer the aha-moment demo (see "Aha moment" below). If `processed, empty`, lead with the normal lag (table/query-history context can take a few hours to appear) and suggest checking back; only if it persists, point the builder to the access preflight remediation in `../reference/ACCESS_PREFLIGHT.md`.

## Verb: lookup

Extract from the user's request:

- `query` — natural-language question or concept name
- `fully_qualified_names` — any `DB.SCHEMA.TABLE` strings

If neither was present, ask once:

```
What would you like to look up?
  • a question (e.g. "what is the grain of orders?")
  • a fully-qualified table (e.g. SALES.DATA.OPPORTUNITIES)
  • or both
```

**Follow the full lookup contract in `../reference/CONTEXT_LOOKUP.md`:**

1. Try the `cortex_sense` MCP tool first (coding-agent, per-account gate). Use `max_results: 5`, `datamart_max_results: 0`.
   - After the first MCP response, run **Signal A** of the wrong-account detection check from `../reference/CONTEXT_LOOKUP.md` "Wrong-account detection". If it triggers, switch to path 2 for the rest of the session.
   - If the MCP returns `NotFound` for the named domain, run **Signal B** (parallel `list-contexts` + unscoped MCP call) before concluding the context was deleted.
2. If the tool is not registered, fall back to the SQL system function (`SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT`) — available whenever `snow` works (no env vars required).
3. If both are unavailable (the SQL function itself errors), render the dead-end and stop.

The contract file defines the exact call shapes, response parsing, rendering table, error handling, and all copy verbatim — do not duplicate it here.

After all sections:

```
type another query, promote to ontology, or: **done**
```

If the builder uses "promote to glossary", "add to ontology", "push to glossary", "add this/these to the glossary", "suggest for the glossary", "add these concepts to ontology", "promote this domain to ontology", or any unambiguous phrasing to move content into Business Ontology:

**Pre-flight: check `ontology_available`.** If the session-level flag is `false` (see `../reference/CONTEXT_LOOKUP.md` "Ontology availability — session-level flag"), surface **once** and stop:
```
(Business Ontology is not enabled on this account — contact your account admin to enable it.)
```

**Route based on what the builder is pointing at:**

1. **Something from "From Cortex Sense context"** — extract `entity_key` and the document body (`markdown` if non-empty, else `cam_content` — see `../reference/CONTEXT_LOOKUP.md` content contract) from the last rendered CortexSense document; route to `$business-ontology` with that content as pasted text (BG `import/SKILL.md` Path B — AI extraction) and `target_domain_hint: <domain>`. Say: "Routing to Business Ontology to add `<entity_key>` as a candidate term."

2. **Something from "From Business Ontology"** — the term is already in the ontology. Reply: "That term is already in the Business Ontology. To update it, use the Business Ontology skill directly." Do not route.

3. **"Promote all" / "promote this domain"** with no specific document referenced — full manifest promotion. Say: "Routing to Business Ontology to promote the `<domain>` context." Route to `$business-ontology` with the domain name and `target_domain_hint: <domain>`; BG `import/SKILL.md` Path D loads the manifest and handles the rest.

4. **Ambiguous "add this to ontology"** with no clear prior document — ask once: "Which item do you want to add — the last lookup result, or the full `<domain>` context?"

## Aha moment (after a fresh build)

When `check build` reports **ready** — or the builder returns right after a build completes — offer one concrete before/after so they *see* the value, rather than being told the build finished. Keep it to **one** question and make it opt-in.

1. Pick a representative in-scope question from the domain — prefer one tied to a concept, metric, or key table in the manifest (e.g. "what is the grain of `<in-scope table>`?" or "how is `<concept>` defined?").
2. Run it through context lookup (`../reference/CONTEXT_LOOKUP.md`).
3. Present it as a grounded contrast:

   ```
   Try asking CoCo: "<question>"

   Without your context, CoCo would guess from table names alone. With the <domain>
   context you just built, here's the grounded answer it now gives:

   <rendered lookup result>
   ```

If the lookup returns nothing, don't fake a contrast — fall back to the "processed but 0 docs" guidance (access preflight) or the normal "returns nothing" copy. Never fabricate a "before" answer.

## When lookup is unavailable

If neither the MCP tool nor the SQL fallback is available, render the dead-end copy from `../reference/CONTEXT_LOOKUP.md` "Dead-end — both unavailable", then stop.

## When the lookup returns nothing

Use the verbatim copy from `../reference/CONTEXT_LOOKUP.md` "When lookup returns nothing", then:

```
type another query, or: refine — record a correction · done
```

## What this skill never does

- Render a layered debug taxonomy ("Layer 1 / Layer 2 / QBE")
- Suggest `ALTER TASK ... RESUME` or any operator-level SQL
- Run SQL against `INFORMATION_SCHEMA`, `ACCOUNT_USAGE`, or the QBE pipeline tasks
- Handle grading or eval scoring inline — route to `../eval/SKILL.md` instead
