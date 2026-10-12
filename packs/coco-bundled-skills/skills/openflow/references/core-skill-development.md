---
name: openflow-core-skill-development
description: Stub pointing to README for skill development guidelines.
---

<!-- omp-compat:start -->
> **OMP compatibility**
>
> - Selected paths may require external capabilities not built into OMP: `nipyapi`. Before using one, verify a configured tool providing that capability is available and authenticated. If the selected path requires an unavailable capability, stop and report `blocked: missing <capability>`; never substitute an unrelated shell command or claim execution.
<!-- omp-compat:end -->

# Openflow Skill Development

For comprehensive guidelines on extending or modifying the Openflow skill, see `data-engineering/openflow/README.md`.

The README covers:
- Development process and iteration cycle
- Design philosophy and content types
- File naming conventions and router patterns
- Cross-referencing patterns
- Reference file structure and templates
- Development principles
- nipyapi function prioritization
- Validation methodology (CYOA analysis)

**For contributors:** Add the README to your Cursor always-load context when working on this skill.
