---
name: architecture-documentation
description: Create or update C4 models, architecture narratives, diagrams, and versioned architecture artifacts from a codebase using Sanofi modeling conventions. Use when documenting system context, containers, components, or deployment, or versioning architecture changes. Not for ADRs (adr-writing), API specs, code comments, or Confluence publishing (confluence-html-editor).
---

# Architecture Documentation

C4 modeling, content, and versioning for architecture documentation. Artifact-neutral: preserve the repository's source format; NEVER make a diagramming tool a prerequisite.

## Handoffs

- This skill: C4 scope, element classification, relationships, reviewable page and diagram content, versions, change history.
- Live Confluence create/update: MUST use the confluence-html-editor skill. It fetches the page, preserves macros and attachments, publishes HTML, verifies.
- NEVER build or paste a Confluence storage-format payload here.
- Visuals: use the repository's native format or a tool-neutral diagram spec. Model and narrative MUST stay useful without an editable visual.
- Decisions behind the architecture: adr-writing skill.

## Workflow

1. Establish the user-facing system boundary and audience BEFORE inferring from teams, repos, or deployment config.
2. Inspect the smallest code and infrastructure scope that answers the C4 question; widen only on evidence. Use `glob` and `grep`; NEVER shell `rg`/`find`.
3. Classify systems, containers, components, externals by runtime responsibility and relationships.
4. Produce model narrative, relationship labels, requested diagram content. If the repository holds C4 as code (Structurizr DSL, C4-PlantUML, Mermaid C4), detect it with `glob`/`grep` and edit that format in place; see [diagrams-as-code.md](references/diagrams-as-code.md).
5. Apply version and change-history convention to the logical artifact.
6. Hand live Confluence work to confluence-html-editor with prepared content and target-page context.
7. Run [c4-notation-checklist.md](references/c4-notation-checklist.md) before presenting.

## C4 Abstractions

| Element | Means | NEVER |
|---|---|---|
| Person | Human role | A team |
| Software System | Meaningful product/application boundary | A repo shortcut |
| Container | Runtime or data-store responsibility | A Docker image |
| Component | Significant responsibility inside one container | A fixed-count quota |

- Browser SPA is normally a container. Add API, asset host, or other server container ONLY as a distinct in-scope runtime.
- Managed cloud services: container when in scope and relevant; external when merely consumed; omit when it does not help the audience.
- Queues and topics you own: one data-store container each. NEVER a single message-bus/broker hub container; the broker belongs on the Deployment view.
- Definitions, boundary evidence, mistakes: [c4-abstractions-guide.md](references/c4-abstractions-guide.md).

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

Match requested scope and audience. L1 and L2 suffice for most teams; do not add levels by default. See [diagram-selection.md](references/diagram-selection.md), which also maps views to arc42 sections.

## Versioning

- MAJOR: system boundary change, platform migration.
- MINOR: container/component added or removed, new integration.
- PATCH: label or description fix.
- Identifier `{system-name}-L{level}-v{version}`; keep the repo's native extension.
- Author: named person, or `AI-assisted (architecture-documentation)`. NEVER rewrite existing attribution.
- Rules, changelog, naming variants, archive: [versioning-guide.md](references/versioning-guide.md).

## References

| File | Read when |
|---|---|
| [c4-abstractions-guide.md](references/c4-abstractions-guide.md) | Classifying elements |
| [codebase-analysis-patterns.md](references/codebase-analysis-patterns.md) | Detecting architecture from code |
| [large-system-workflow.md](references/large-system-workflow.md) | Many containers or multiple repos; huge codebases |
| [diagram-selection.md](references/diagram-selection.md) | Picking views per audience |
| [diagrams-as-code.md](references/diagrams-as-code.md) | Editing or choosing Structurizr DSL, C4-PlantUML, Mermaid C4; current Structurizr tooling |
| [confluence-page-templates.md](references/confluence-page-templates.md) | Preparing page content per level |
| [page-hierarchy.md](references/page-hierarchy.md) | Organizing a multi-page set |
| [versioning-guide.md](references/versioning-guide.md) | Versions, changelog, Jira links |
| [c4-notation-checklist.md](references/c4-notation-checklist.md) | Pre-publish validation |
| [drawio-c4-templates.md](references/drawio-c4-templates.md) | ONLY when an existing Draw.io source must stay compatible |

## Checklist

- Boundary and audience stated before modeling.
- Each element classified by responsibility, not repo or team.
- Version, changelog, and attribution recorded.
- Notation checklist passed.
- Existing diagram-as-code source edited in place, not replaced.
- Live publishing handed to confluence-html-editor.
