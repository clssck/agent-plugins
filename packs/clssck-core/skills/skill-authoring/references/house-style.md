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
3. Task-named `##` sections in execution order.
4. Entry/exit gates where shortcuts are likely.
5. Exact outputs and observable verification.
6. Artifact-specific checklist only when the skill produces an artifact.

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
3. Runnable common examples.
4. Agent-owned failures and exact recovery action.
5. WRONG/RIGHT anti-patterns from real retries.
6. Short critical recap.

Keep defaults and their direction, output shape, routing/escalation, domain grammar, and constraints the schema cannot express. Omit module layout, internal algorithms, caches, telemetry, and silently recovered failures.

## Boundaries

A sibling name MAY route the reader, but required behavior MUST remain local. The skill still states what is out of scope, the safe alternative, and the stop condition when no sibling skill is present.
