---
name: architecture-documentation
description: "Document a system's architecture with the C4 model at Sanofi: system context, container, component, deployment, landscape, and dynamic views. Use when reverse-engineering architecture from a codebase, editing Structurizr DSL, C4-PlantUML, Mermaid C4 or Draw.io sources, versioning diagrams, preparing Confluence architecture page content, or arc42 mapping. Not for ADRs — use adr-writing; not for live Confluence publishing — use confluence-html-editor; API specs out of scope."
---

# Architecture Documentation

C4 modeling (context, container, component, deployment, landscape), architecture narratives, diagrams-as-code (Structurizr, C4-PlantUML, Mermaid C4), and versioned artifacts derived from a codebase, under Sanofi conventions. Governing principle: **the model and narrative are the deliverable; a picture is optional.** The skill is artifact-neutral — preserve the repository's source format and NEVER make a diagramming tool a prerequisite, because a model that needs a specific editor stops being maintained once that editor is unavailable.

Classification follows runtime responsibility, never repo layout or team ownership: repos and teams are evidence, not boundaries.

## Scope and Handoffs

| Concern | Owner |
|---|---|
| C4 scope, element classification, relationships, reviewable page and diagram content, versions, change history | this skill |
| Live Confluence create/update — fetch page, preserve macros and attachments, publish HTML, verify | `confluence-html-editor` (MUST) |
| Decisions behind the architecture | `adr-writing` |
| API specifications | out of scope |

- **No storage format here:** NEVER build or paste a Confluence storage-format payload.
- **Tool-neutral visuals:** use the repository's native format or a tool-neutral diagram spec. Model and narrative MUST stay useful without an editable visual.

## Workflow

1. **Boundary and audience first.** Establish the user-facing system boundary and audience BEFORE inferring from teams, repos, or deployment config. Unclear → `ask`.
2. **Smallest scope.** Inspect the least code and infrastructure that answers the C4 question; widen only on evidence. Use `glob` and `grep`; NEVER shell `rg`/`find`. Patterns → [codebase-analysis-patterns.md](references/codebase-analysis-patterns.md).
3. **Classify** systems, containers, components, externals by runtime responsibility and relationships.
4. **Produce** model narrative, relationship labels, requested diagram content. Repository holds C4 as code (Structurizr DSL, C4-PlantUML, Mermaid C4) → detect with `glob`/`grep`, edit that format in place → [diagrams-as-code.md](references/diagrams-as-code.md).
5. **Version** the logical artifact and record change history.
6. **Validate** with [c4-notation-checklist.md](references/c4-notation-checklist.md) before presenting or handing off.
7. **Hand off** live Confluence work to `confluence-html-editor` with prepared content and target-page context.

## Classify Elements

| Element | Means | NEVER |
|---|---|---|
| Person | Human role | A team |
| Software System | Meaningful product/application boundary | A repo shortcut |
| Container | Runtime or data-store responsibility | A Docker image |
| Component | Significant responsibility inside one container | A fixed-count quota |

- **Browser SPA:** normally a container. Add API, asset host, or other server container ONLY as a distinct in-scope runtime.
- **Managed cloud services:** in scope and relevant → container; merely consumed → external; no help to the audience → omit.
- **Queues and topics you own:** one data-store container each. NEVER a single message-bus/broker hub container; the broker belongs on the Deployment view.
- Definitions, boundary evidence, Sanofi Systems-vs-Stores framework, mistakes → [c4-abstractions-guide.md](references/c4-abstractions-guide.md).

## Choose the Level

| Need | View |
|---|---|
| Users, scope, external relationships | L1 Context |
| Several systems, or platform boundary unclear | System Landscape |
| Runtime and data-store responsibilities | L2 Container |
| One container needs explanation | L3 Component (one container) |
| Explicitly requested only | L4 |
| Significant, recurring interaction (sparingly) | Dynamic |
| Runtime mapped to ONE environment | Deployment |

Match requested scope and audience. L1 + L2 suffice for most teams; NEVER add levels by default. Audiences, per-view rules, arc42 section mapping → [diagram-selection.md](references/diagram-selection.md). Many containers or multiple repos → [large-system-workflow.md](references/large-system-workflow.md).

## Version and Attribute

| Bump | Trigger |
|---|---|
| MAJOR | System boundary change, platform migration |
| MINOR | Container/component added or removed, new integration |
| PATCH | Label or description fix |

- **Identifier:** `{system-name}-L{level}-v{version}`; keep the repo's native extension.
- **Author:** named person, or `AI-assisted (architecture-documentation)`. NEVER rewrite existing attribution.
- Changelog format, naming variants, Jira linkage, archive → [versioning-guide.md](references/versioning-guide.md).

## Before Handoff

- Boundary and audience stated before modeling.
- Each element classified by responsibility, not repo or team.
- Version, changelog, attribution recorded.
- [c4-notation-checklist.md](references/c4-notation-checklist.md) passed.
- Existing diagram-as-code source edited in place, not replaced.
- Live publishing handed to `confluence-html-editor`.

## References

| File | Read when |
|---|---|
| [c4-abstractions-guide.md](references/c4-abstractions-guide.md) | Classifying elements |
| [codebase-analysis-patterns.md](references/codebase-analysis-patterns.md) | Detecting architecture from code |
| [large-system-workflow.md](references/large-system-workflow.md) | Many containers or multiple repos; huge codebases |
| [diagram-selection.md](references/diagram-selection.md) | Picking views per audience |
| [diagrams-as-code.md](references/diagrams-as-code.md) | Editing or choosing Structurizr DSL, C4-PlantUML, Mermaid C4; current Structurizr tooling |
| [confluence-page-templates.md](references/confluence-page-templates.md) | Preparing page content per level; organizing a multi-page set |
| [versioning-guide.md](references/versioning-guide.md) | Versions, changelog, Jira links |
| [c4-notation-checklist.md](references/c4-notation-checklist.md) | Pre-publish validation |
| [drawio-c4-templates.md](references/drawio-c4-templates.md) | ONLY when an existing Draw.io source MUST stay compatible |
