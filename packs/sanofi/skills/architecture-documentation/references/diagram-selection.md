# Diagram Selection

## C4 Model Overview

> **Important**: The C4 model describes systems at various abstraction levels. It does NOT
> imply a specific design process, team structure, or delivery workflow. This skill uses C4
> within a Sanofi documentation workflow, but the C4 levels themselves are purely descriptive.

You do NOT need all four levels. System Context and Container diagrams are sufficient for
most teams; add L3/L4 only when they answer a question the audience actually has.
Each diagram MUST be understandable without a narrative: title with type and scope, legend,
element types, and labelled relationships.

### Level 1: System Context

**What it shows**: The system as a single box surrounded by the people who use it and
the external systems it interacts with. This is a "zoomed out" big picture view.

**Audience**: Everybody, both technical and non-technical.

**Recommended**: Yes -- a System Context diagram is recommended for ALL teams.

**When to update**: New external integration, new user persona, system boundary change.

**Elements**:
- People / personas (who uses the system)
- The system itself (single box -- no internal details)
- External systems (systems we depend on or that depend on us)
- Relationships (labeled arrows with purpose -- NOT protocols at this level)

### Level 2: Container Diagram

**What it shows**: The high-level shape of the software architecture and how
responsibilities are distributed across containers.

**Audience**: Technical people (architects, developers, operations/support).

**Recommended**: Yes -- a Container diagram is recommended for ALL teams.

**When to update**: New service, new database, new frontend app, infrastructure change.

### Level 3: Component Diagram

**What it shows**: The internal structure of a single container -- groupings of related
functionality encapsulated behind well-defined interfaces.

**Audience**: Software architects and developers only.

**Recommended**: OPTIONAL. Only create if they add genuine value for understanding a
complex container.

### Level 4: Code Diagram

**What it shows**: Class/module level detail within a component.

**Recommended**: No. Most IDEs can generate this level of detail on demand.

**When to create**: Only on explicit request for a deep-dive into a specific component.
Not recommended for long-lived documentation.

**Key rule**: Show selectively -- include only the attributes and methods that tell the
story you want to tell, not a comprehensive class/module dump.

### Supplementary: System Landscape Diagram

**What it shows**: A system context diagram without a focus system: the people and software
systems within an enterprise, department, or portfolio.

**Audience**: Technical and non-technical people, inside and outside the team.

**When to create**: When the boundary question spans several systems (see
[large-system-workflow.md](large-system-workflow.md)) or a platform may be several systems.
Recommended for larger organisations; it bridges to enterprise architecture.

**Rules**: Systems and people only; no containers. Each system of interest keeps its own L1-L3 set.

### Supplementary: Dynamic Diagram

**Audience**: Both technical and non-technical people, inside and outside the team.

**Recommended**: No. Dynamic diagrams show a user story, use case, or feature at runtime.

**When to create**: SPARINGLY -- only for interesting/recurring patterns or features
requiring complex interaction sequences.

**Elements**: Systems, containers, or components. Pick one level per diagram.

**Styles**: Collaboration (free-form layout, numbered interactions) or sequence (timeline layout).
Both convey the same information -- choose whichever best suits your audience.

**Rules**: Number interactions to indicate ordering (1, 2, 3...).

### Supplementary: Deployment Diagram

**What it shows**: How containers map to infrastructure in a specific deployment
environment (production, staging, dev).

**When to create**: Recommended for all teams to document production deployment topology.

**Scope**: One or more software systems in ONE deployment environment. Create one diagram per environment (production, staging, dev); NEVER merge environments.

**Elements**: Deployment nodes (nestable), software system instances, container instances, and optional infrastructure nodes. Deploy only elements that exist in the L2 model.

**Rules**: Deployment nodes may be nested (e.g., AWS Region > Availability Zone > ECS Cluster > Container Instance). Infrastructure nodes (DNS, load balancers, firewalls) may be included. AWS/Azure/GCP provider icons are permitted if documented in the legend.

## arc42 Cross-Check

When the repository documents architecture with the arc42 template, place C4 views in its sections instead of creating a parallel document. The C4 FAQ maps sections 3 and 5 only; the Runtime and Deployment rows are this skill's extension.

| arc42 section | C4 view |
|---|---|
| 3 Context and Scope | System Context (or System Landscape) |
| 5 Building Block View, level 1 | Container |
| 5 Building Block View, level 2 | Component |
| 5 Building Block View, level 3 | Code |
| 6 Runtime View | Dynamic |
| 7 Deployment View | Deployment |

Sections 1, 2, 4, 8-12 (goals, constraints, strategy, crosscutting concepts, decisions, quality, risks, glossary) have no C4 equivalent. Link decisions to adr-writing output rather than restating them here.

## Sources

- C4 model, Diagrams: https://c4model.com/diagrams
- C4 model, System landscape diagram: https://c4model.com/diagrams/system-landscape
- C4 model, Dynamic diagram: https://c4model.com/diagrams/dynamic
- C4 model, Deployment diagram: https://c4model.com/diagrams/deployment
- C4 model, FAQ (arc42, scaling): https://c4model.com/faq
- arc42, Template overview: https://arc42.org/overview
