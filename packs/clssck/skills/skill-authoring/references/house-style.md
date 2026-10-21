# Clssck Skill House Style

Portable authoring rules for a skill consumed through OMP. OMP owns discovery, frontmatter, `skill://` resolution, and invocation semantics; this reference owns prose and structure.

## Voice

- Dense, direct, imperative. Every line MUST change a decision.
- RFC 2119 words stay full caps and outside bold: `**History:** MUST inspect it.`
- One claim per bullet. Bold lead names the rule; body never restates it.
- Facts stay factual. NEVER turn schemas, examples, defaults, or return shapes into normative prose.
- No ceremony, hedging, ornamental tags, or uncheckable “review your work” instructions.

## Structure

1. Trigger-rich frontmatter description: task, user phrasing, contexts, local exclusions.
2. `# Title` and a short governing principle.
3. `##` sections: task names for procedures, noun names for reference material.
4. Entry/exit gates where shortcuts are likely.
5. Exact outputs and observable verification.
6. Optional closing checklist; every item verifiable.

Use tables for real enumerations. Use runnable examples for syntax or shapes. Put reference detail in `references/` and executable helpers in `scripts/`; link every runtime entry point directly from `SKILL.md`.

## Payload grammar

Distilled from every bundled primitive at the pinned OMP commit. Match this shape unless the capability's own file says otherwise.

| Tag | Carries | Placement |
|---|---|---|
| `<directives>` | `MUST`/`NEVER`/`SHOULD` rules that gate behaviour | before the work |
| `<instruction>` | choices, fallback chains, source of truth | middle |
| `<procedure>` | numbered actions with entry and exit gates | middle |
| `<caution>`, `<example>` | failure modes; runnable sample | as needed |
| `<critical>` | 1-6 lines restating the load-bearing `MUST`/`NEVER` | **closing**, last block |

- `<critical>` is a recap, not the constraint block: it is the last block in 17 of 21 tagged host files, 1-6 lines, `MUST`/`NEVER` only. Open with it only when the constraint must gate the first action (`ci-green-request.md` is the host example).
- Constraints that gate behaviour go in `<directives>`, as `scout.md` and `task.md` do; the closing `<critical>` repeats only what a rushed reader must not miss.
- Rules are plain Markdown with no tags: the harness wraps the body in its own `<system-interrupt>` or `<system-reminder>`. Lead with one enforceable claim, then `## Why`, `## Avoid` / `## Use`, `## Exceptions`.
- Skills are heading-first. Tags are optional and used only when a block carries a decision; reference sections keep noun headings and no tags.
- State the completion condition as a checkable fact, not an encouragement. Name the source of truth when two observations can disagree.
- Tier: a prohibition inside `<instruction>`, or advice inside `<critical>`, is a defect. `<procedure>` and `<caution>` may carry `MUST`/`NEVER`.

The five semantic names are `<critical>`, `<instruction>`, `<procedure>`, `<caution>`, and `<example>`: they carry a fixed decision type, order, and tier. `<directives>` and any other lowercase kebab-case name (`<criteria>`, `<findings>`, `<output>`) are **section tags**, the host's own idiom. Section tags take optional `name="..."` attributes, may nest, and carry no order or tier rule.

Tags are semantics, not decoration. A `<critical>` holding advice, or an `<instruction>` holding a forbidden action, teaches the reader to discount both. NEVER wrap a whole document in one tag, and NEVER author a harness-owned name (`system-*`, `<objective>`); that impersonates host content.

Where a repository checks structure statically, this grammar is that check's contract: a retired or harness-owned name, an unclosed tag, a misordered semantic tag, or a tier inversion is a defect, not a style choice.

## Compression

Compression is re-encoding, not word deletion.

- Preserve identifiers, exact strings, negation, exceptions, numbers, units, bounds, defaults, precedence, conditions, and causality.
- Hoist repeated qualifiers once; merge genuine restatements.
- Keep trigger synonyms in descriptions even when redundant for a human reader.
- Stop when the next deletion forces a guess.

## Tool descriptions

Teach the decision surface, not implementation machinery:

1. One-line purpose in agent vocabulary.
2. Input grammar and verbatim syntax.
3. Worked examples: 3–8 common shapes; the example is the explanation.
4. Agent-owned failures and exact recovery action; omit silently recovered failures.
5. WRONG/RIGHT anti-patterns from real retries, never imagined ones.
6. `<critical>` recap: 3–6 load-bearing lines for agents that skip the body.

Keep defaults and their direction, output shape, routing/escalation, domain grammar, and constraints the schema cannot express. Exclude:

- Implementation file/function names and module layout.
- Recovery, retry, normalization, caching, fuzz matching.
- Performance characteristics, unless they change strategy.
- Telemetry, logging, debug flags, unsettable env vars.
- Version history, deprecated parameters, "previously this worked differently".
- Cross-tool plumbing, unless the agent must coordinate the tools.

## Boundaries

A sibling name MAY mark out-of-scope work. NEVER make behavior depend on whether another skill is installed. Required behavior lives in this skill or its references.
