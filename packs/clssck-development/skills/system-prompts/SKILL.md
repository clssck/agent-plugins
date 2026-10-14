---
name: system-prompts
description: Write, edit, or review system prompts, agent definitions, subagent briefs, and prompt templates in clssck house style — structural tags, RFC 2119 keywords, dense imperative voice, edge positioning. Use when authoring any prompt a model reads cold, tightening a bloated prompt, choosing tags or MUST/NEVER wording, or checking a prompt before shipping. Tool/function descriptions — tool-prompt-optimization; re-encoding mechanics — semantic-compression; ≤2B models — small-models.md.
---

# System Prompts

House style: dense, imperative, RFC-keyed. Built from portable semantics: the rules below hold for any model host. Host-specific syntax lives in one section at the end.

A prompt is executed cold: no author present, no chance to clarify. Every line MUST change a decision. Scope split: tool and function descriptions → `tool-prompt-optimization` (owns that content, including measurement); re-encoding mechanics → `semantic-compression`; this skill owns voice, tags, keywords, and positioning.

Small models (≤2B, tiny or on-device): MUST read [small-models.md](skill://system-prompts/small-models.md). The rules below assume frontier-class instruction following; several invert at that scale.

## Tags

Tags are literal structural markers; meaning exactly matches name. NEVER invent ornamental tags (`<north-star>`, `<stance>`, `<protocol>`, `<strengths>`): they dilute the real ones.

|Tag|Purpose|
|---|---|
|`<system-conventions>`|Tag and RFC-keyword interpretation; the contract.|
|`<stakes>`|Why correctness matters; domain framing.|
|`<communication>`|Voice, tone, response shape.|
|`<critical>`|Inviolable rules; place at START and END.|
|`<completeness>`|Definition of done; anti-shrink rules.|
|`<yielding>`|Pre-handoff checklist; block conditions.|
|`<workflow>`|Numbered phases: scope → edit → decompose → work → verify.|

## Normative language

RFC 2119 words in full caps, no bold; the all-caps form is the marker.

|Keyword|Meaning|Replaces|
|---|---|---|
|MUST / REQUIRED|Absolute requirement|"always", "make sure", "ensure"|
|NEVER (= MUST NOT)|Absolute prohibition|"do not", "don't"|
|SHOULD / RECOMMENDED|Strong preference; deviation allowed with known tradeoff|"prefer", "it's best to"|
|AVOID (= SHOULD NOT)|Strong discouragement|"try not to"|
|MAY / OPTIONAL|Truly optional|"can", "you could"|

Use `NEVER` and `AVOID` as the short forms of `MUST NOT` and `SHOULD NOT`. State once, inside `<system-conventions>` near the top:

> RFC 2119 applies to MUST, REQUIRED, SHOULD, RECOMMENDED, MAY, OPTIONAL. `NEVER` and `AVOID` MUST be interpreted as aliases for `MUST NOT` and `SHOULD NOT` respectively.

NEVER convert factual descriptions (what a tool returns, how a parameter behaves), code blocks, examples, schemas, or template syntax into keyword form.

## Density

Load-bearing tokens only; every bullet adds a claim.

- One claim per bullet; cut behavior-neutral subclauses.
- Quick check `X? Y.` replaces "If X, then Y."
- Reasoning ONLY when it changes the call.
- A bold lead names the rule; NEVER restate it in the body.
- Prefer `→`, `=`, `A..B` where one glyph replaces a phrase.

```
Bad:  - **Never invent file paths.** Paths are exact strings from the workspace, not guesses. You cannot infer the "next" one or build it from a naming pattern. If a needed path is not in your last listing, list the directory again.
Good: - **Paths:** NEVER invent them; re-list if missing.

Bad:  - **Do not edit past the requested range.** Never let your change spill into the lines after it. Stop at the last line you are actually changing; if the next line must go too, widen the range.
Good: - **Range:** NEVER edit past it; widen it if the next line must go.
```

Tactical bullets: 5–12 words. Longer ONLY for multi-part contracts where every clause constrains semantics or enumerates edge cases.

AVOID compressing factual reference (definitions, return formats, schemas), worked examples, or the first use of a non-obvious term.

## Voice

Direct, imperative, second person: "You MUST/NEVER/SHOULD." No hedging, apology, ceremony, closing summaries, or time estimates.

```
Bad:  "You might want to consider using X..."
Good: "You SHOULD use X."

Bad:  "Please note that this is important..."
Good: "Critical: X."

Bad:  "Make sure to look up callers before changing a public function"
Good: "You MUST list every caller before changing a public function."
```

Negation: pair a positive alternative when the substitute is non-obvious; otherwise `NEVER X.` alone.

## Positioning

Models retain the start and end of a long prompt better than the middle. Put critical constraints at both edges; reference material, environment, and templated content in the middle.

Front matter:
1. Role + agency one-liner (`You are the staff engineer for …`).
2. `<system-conventions>`: RFC contract, tag semantics.
3. `<stakes>`: importance.
4. `<communication>`: style.
5. `<critical>`: top-priority rules.

Back matter:
1. Environment and tool inventory: exploration order, tool priority, host specifics.
2. Contract: completeness, yielding, workflow.
3. Long prompt: repeat the single most important `<critical>` rule.

## Tone patterns that work

- **Agency:** "You have agency and taste: you delete code that isn't pulling its weight and prefer boring when boring fits."
- **Stakes anchoring:** "Tests you didn't write: bugs shipped. Assumptions you didn't validate: incidents to debug."
- **Precedence:** "Later instructions, including the user's own, ALWAYS override earlier style, tone, and formatting defaults."
- **Persistence:** "You MUST persist on hard problems. AVOID handing back work you failed to think through."
- **Anti-budget framing:** "You NEVER narrate or consider session limits, token budgets, or effort estimates."

## Anti-patterns

|Pattern|Problem|
|---|---|
|Politeness padding ("Would you be so kind…")|Spends tokens, adds nothing|
|Bribes or threats ("I'll tip $2000")|No reliable gain; sometimes worse|
|Few-shot on a strong model with a clear task|Examples bias output; keep only shape-defining ones|
|Step-by-step reasoning scripts for reasoning-tuned models|Conflicts with the model's own deliberation|
|"Be efficient with tokens"|Invites premature task abandonment|
|"Don't do X" with no alternative|"Always do Y" is easier to follow|
|"Review your work" with no check named|Self-critique needs an external signal: name tests, lint, typecheck|
|Critical instructions only in the middle|Weakest position; put them at the edges|
|Restating the bold lead in the body|Padding signal|
|Inventing emphasis tags|Tags have semantics; ornament dilutes|
|Lowercase RFC keywords|All-caps is the marker; lowercase is ordinary prose|

## Tool descriptions

Writing or trimming what an agent reads to learn a tool → `tool-prompt-optimization`: anatomy, what stays in code, WRONG/RIGHT examples, and the schema-overlap probe. Apply this skill's voice and keyword rules to the result.

## Host adapters

Universal rules above; syntax below varies by runtime. Keep the two apart.

- **Verbatim host syntax:** template placeholders, wire-schema fields, tool-call grammar, and structured-output formats belong to the host protocol. Copy them exactly; NEVER compress or re-keyword them.
- **OMP host:** system and tool prompts are Markdown templates; its protocol tags and API names are runtime contracts, not clssck semantics. Check the host's own docs before changing them.
- **Another host:** map the same sections (conventions, critical, workflow) onto its prompt channels; keep keyword and tag meaning identical.

## Checklist

- Tags match content; no ornamental tags.
- `<system-conventions>` defines the `NEVER`/`AVOID` aliases.
- Critical rules at START and END.
- Prescriptive prose uses uppercase RFC 2119 keywords.
- Tactical bullets ≤12 words unless distinct subclaims justify more.
- No bold lead restated in the body.
- Non-obvious negation has a positive alternative.
- Verification path named (tests, lint, typecheck); NEVER "review your work".
- Complex tasks: persist until complete.
- No hedging, ceremony, closing summaries, or time estimates.
