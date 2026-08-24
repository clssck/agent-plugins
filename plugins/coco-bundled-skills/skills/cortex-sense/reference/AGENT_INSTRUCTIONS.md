# Agent instructions — derivation and composition contract

Loaded by `agent/SKILL.md` §3 and §4a. This file owns *how* the domain profile is derived and *how* the two instruction blocks are composed. The workflow, the confirm block, and every gate stay in `agent/SKILL.md`.

> **Reading the cross-references.** Every `§n` in this file refers to a section of `agent/SKILL.md`, not to this document — `§1` is context resolution, `§2` the manifest load, `§5` the DDL gate. Where a numbered **item** is cited (`item 1`, `item 9`), that means an item in "Composing the instructions" below.

---

## Deriving the profile (§3)

Assemble the profile from these, in priority order. Stop when you have enough; do not run all four if the first two suffice.

**1. `eval.yaml` — the strongest signal, if it exists.** Load it per `EVAL_FORMAT.md` "Loading a file". Confirmed questions are *real questions real users asked*, already curated. They give you audience, phrasing, vocabulary, and typical grain for free, and each `expected_answer` names a canonical table or value. Ten confirmed questions tell you more about what the agent is for than any interview answer.

**2. A `cortex_sense` probe of the context itself.** One or two calls, pinned to the FQN from §1, asking what the domain covers — e.g. `query: "<business_domain> key metrics and definitions"` and, if needed, `query: "<business_domain> most frequently queried tables"`.

   > **`context_names` is not a hard filter.** Retrieval reads an account-wide shared index, so pinning the FQN scopes but does not guarantee. Verified: a probe pinned to one context returned `qbe` documents whose SQL targeted another domain's tables entirely. Before shaping the profile, check each document's `database` / `schema` / `entity_key` against the manifest `sources[]` patterns from §2 and de-prioritise anything clearly outside the domain. Do not silently discard — genuinely shared reference content exists — but never let an out-of-scope `ontology_node` define a metric for this domain. Full contract in `CONTEXT_LOOKUP.md` "Cross-context contamination".

   Read the returned `doc_type`s per `AGENT_SPEC.md` "Document types":
   - `ontology_node` → the metric definitions and their canonical formulas.
   - `qbe` → what the team actually computes, and how often (`METRIC_NAME`, `EXECUTION_COUNT`). High-execution metrics are the ones the agent must get right.
   - `table_entity` → the workhorse tables, their grain, and their default filters. Near-duplicate table names here are a real trap worth naming in item 9 below.
   - `datamart` → curated candidates.

**3. Manifest definitions, when present** — `concepts[]`, `relationships[]`, `associations[]`, `additional_instructions` from §2.

**4. Manifest `sources[]`** — the §2 fallback harvest: dashboard descriptions as product-area vocabulary, pattern prefixes as scope, `excluded: true` rules as prohibitions.

---

### What of this reaches the prompt — and what must not

The block serves two audiences, and they need different subsets. **Do not copy the profile into the orchestration instructions wholesale.**

| Row | Into the prompt? | Why |
|---|---|---|
| `Purpose` | **Yes** → item 1 below | Framing. Stable, and cheap to carry. |
| `Asked about` | **Yes** → item 1 below | Vocabulary. Gives the model retrieval terms and colloquial-to-formal mappings ("CoCo" → "Cortex Code"). Areas and short names only — not table names. |
| `Watch out` | **Yes** → item 9 below | Policy. Retrieval cannot enforce a prohibition; an exclusion has to be an instruction or the agent will query the excluded object when retrieval surfaces it. |
| `Key tables` | **No** | Fact. The context returns these fresh on every turn. |
| `Definitions` | **No** | Fact. Same. |

**Why the last two stay out.** Pinning table names or metric formulas into the prompt breaks the thing that makes a Cortex Sense agent worth building:

- **It goes stale invisibly.** Rebuild the context with a new canonical table and the prompt still names the old one. The agent stays fluent and self-consistent while being wrong — the hardest failure to notice.
- **It suppresses retrieval.** An agent that already "knows" the table will skip the retrieval gate in item 2, and then it is a plain SQL bot with a hardcoded schema.
- **It duplicates the knowledge layer.** The same reason a builder-volunteered definition goes to `refine/SKILL.md` instead of into the prompt applies to a derived one.

`Key tables` and `Definitions` are in the block as **evidence for the builder** — proof that the right context is pinned and the build is healthy. A confirm block showing `none found in context` on a context that should be rich is the signal to stop and check the build, which is exactly what the builder needs to see and the agent does not need to be told.

Scope in the prompt stays at **schema level** (in-scope databases and schemas, plus prohibitions). That is policy and it is stable. Table level is retrieval's job.

---

## Composing the instructions (§4a)


Compose both instruction blocks. Length is not the goal — every line must earn its place by changing what the agent does. A short prompt that matches the real tool inventory beats a long one that describes tools the agent does not have.

`instructions.orchestration` has four jobs. Cover them in this order, and check each off before moving on — the later ones carry the domain value and are the easiest to lose.

**A. Ground the agent (items 1–2)**

1. **Identity and domain** — one paragraph: what the agent answers, taken from the §3 profile's `Purpose` and `Asked about` lines. Name the product/business areas and their colloquial short forms so the model has vocabulary for retrieval (a user asking about "CoCo" must retrieve "Cortex Code").
2. **The retrieval gate** — the first action on any new question is one `cortex_sense` call, pinned to the context FQN from §1. No SQL before retrieval returns. State *why*: there is no semantic view, so skipping retrieval means guessing at table names.

**B. Teach it the tools and the response shape (items 3–4)**

3. **The tool inventory — exactly what the agent has.** Name `cortex_sense` and `system_execute_sql` (both added by the flag), and `table_details` (a platform default). Do **not** describe `snowscope_search`, `generic_semantic_context`, or `code_execution` — with only `EnableCortexSense` set, they do not exist, and instructions about suppressing them are dead weight that dilutes the rest. See `AGENT_SPEC.md` "Tool inventory".
4. **Reading the response** — branch on the real `doc_type` values (`table_entity`, `qbe`, `ontology_node`, `ontology_edge`, `datamart`) and say what each is for. Take the table from `AGENT_SPEC.md` "Document types" rather than inventing labels. Include the content contract: read `markdown` or `cam_content`, whichever is non-empty; dedupe on `entity_key`.

   **This item must also carry a scope check** — the deployed agent needs it more than the builder does, because nobody reviews its retrieval. Retrieval reads an account-wide index and `context_names` does not hard-filter, so instruct the agent: list the in-scope databases and schemas, check each returned document's `database` / `schema` against them, prefer in-scope documents, and if it uses an out-of-scope one say so in the answer rather than presenting it as domain-canonical. Without this an agent in a multi-context account can define a metric from a neighbouring domain and never flag it.

**C. Bound it (items 5–7)**

5. **Access limits** — SQL runs as the caller's primary role, secondary roles inactive, and retrieval is not fully access-filtered, so retrieval can name tables the caller cannot read. On a permission error: stop, report which object and which privilege, never substitute a different table silently, never fabricate a number.
6. **Relative time windows** — "the past month", "recently", "this quarter" arrive with no dates, and the naive reading (`CURRENT_DATE` backwards) silently includes a partial final day. Instruct the agent to resolve a relative period against the data's own `MAX()` of the date column, use complete periods only, state the exact window it used, and label or exclude a partial period rather than letting it read as a decline. If the domain has a fiscal calendar, say so here — "this quarter" is otherwise ambiguous.
7. **Decline rule** — if retrieval returns nothing, say the data is not discoverable from this context rather than guessing a table name. Add anything the §3 profile showed to be out of scope.

**D. Give it the domain (items 8–9) — do not skip this block**

8. **Conventions from the manifest.** When `concepts[]` / `additional_instructions` are populated: `concepts[]` become metric definitions, `additional_instructions` become standing rules, `relationships[]`/`associations[]` become join and equivalence guidance. Attribute them: these came from the context, not from the model's judgement.

   Keep this at the level of *convention* — naming rules, standing filters, equivalences. A `concepts[]` entry that is really just a table pointer is retrieval's job, not the prompt's.

   **When they are empty** (the common case — see §2), build this item from `sources[]` instead:
   - the in-scope databases and schemas, as a scope paragraph — schemas, not tables;
   - every `excluded: true` rule as an explicit prohibition — an exclusion the builder recorded must survive into the prompt, or the agent will happily query a dev clone;
   - and one honesty clause, because there is nothing authoritative to cite: instruct the agent not to describe any formula it uses as canonical or "the standard definition" unless a retrieved `ontology_node` or `qbe` document actually said so, and to state when it chose an interpretation itself.

   That honesty clause is not optional when definitions are absent. Without it the agent will present its own composition as a blessed metric.

9. **Cautions from the §3 profile** — the `Watch out` line, as explicit named rules: near-duplicate metrics or tables that are easy to confuse, filters that `qbe` patterns always apply, and anything the builder corrected during §3. These are observed traps, not hypothetical ones.

Blocks A–C are largely the same for every agent built this way; **block D is the only part that makes this agent different from a generic one.** If §3's derivation came up empty (no eval set and an unbuilt context), block D reduces to scope plus the honesty clause — say so plainly at §5 rather than letting the builder believe the agent learned more than it did.

**`instructions.response` must cover:** answer format and depth for the audience implied by the §3 profile; stating which filters were applied in words, not just SQL; not attributing a filter or formula to a source that was not actually retrieved; and naming the tables actually queried.
