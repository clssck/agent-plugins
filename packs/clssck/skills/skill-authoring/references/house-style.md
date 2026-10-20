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

Normative content lives in tagged blocks, in a fixed order. Markdown headings stay for navigation and noun-named reference sections.

| Tag | Carries | Required when |
|---|---|---|
| `<critical>` | `MUST`/`NEVER` constraints, trust and authorization boundaries, the completion condition | Always |
| `<instruction>` | `SHOULD`/`MAY` choices: capability choice, fallback chain, source of truth | A choice or fallback exists |
| `<procedure>` | Numbered actions with entry and exit gates; loop-until condition for iterative work | The body performs ordered work |
| `<caution>` | Failure modes, misreads, and what looks like success but is not | The run can corrupt or silently under-deliver |
| `<example>` | Runnable snippet | Exact syntax is not obvious |

- Emit tags in that order. One concept per block; repeat a tag only for a genuinely separate block, such as a closing `<critical>` restating the completion condition of a long body.
- State the completion condition in `<critical>` as a checkable fact ("workflow runs for the latest HEAD succeed"), not an encouragement.
- Name the source of truth in `<instruction>` when two observations can disagree, and the fallback chain when a capability can be unavailable: "SHOULD use `xd://github` `op: run_watch` if available; else `gh`".
- Put refusal, degradation, and insufficient-output behavior in `<caution>`, not mid-procedure.
- A reference section MAY carry no tags when it expresses no decision.

Tags are semantics, not decoration. A `<critical>` holding advice, or an `<instruction>` holding a forbidden action, teaches the reader to discount both. NEVER wrap a whole document in one tag, and NEVER introduce a tag name outside this set.

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
