---
name: skill-development
description: "Capture sessions as OMP skills, refactor skill workflows, or compile deterministic fast paths. Use when turning completed work into a reusable workflow or optimizing an existing skill. General skill writing, descriptions, and quality review belong to skill-authoring."
---

# Skill Development

Build reusable OMP skills from completed work. Read `omp://skills.md` for discovery, frontmatter, and invocation semantics.

## Routing

| Task | Read |
|---|---|
| Create | `skill://skill-development/create-from-scratch/SKILL.md` |
| Capture session | `skill://skill-development/summarize-session/SKILL.md` |
| Audit | `skill://skill-development/audit-skill/SKILL.md` |
| Refactor | `skill://skill-development/refactor-skill/SKILL.md` |
| Compile deterministic fast path | `skill://skill-development/compile-skill/SKILL.md` |

## Workflow

1. Resolve scope from the request. Review/audit alone reports findings; write/fix/refactor completes the authorized edits.
2. Read the selected workflow and its required references. Inspect existing repository conventions and actual tool schemas.
3. Ask only for materially different tradeoffs the user must decide. Use conservative established defaults for routine choices; existing authorization remains valid.
4. Keep host paths and calls OMP-native. External capabilities require a configured, authenticated tool; missing capability means blocked.
5. Read back written files, validate references and frontmatter, and verify OMP discovery. Report evidence and remaining limitations.
