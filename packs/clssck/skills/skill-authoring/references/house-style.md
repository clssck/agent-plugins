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
