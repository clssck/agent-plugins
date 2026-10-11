# Versioning Guide

Versioning, changelog, artifact naming, Jira traceability, retroactive documentation, diff descriptions, archive, and change management for architecture artifacts. Version the logical artifact, not the file format: identifiers stay tool-neutral so history survives a change of diagramming tool.

---

## Semantic Versioning Rules

Format: `v{MAJOR}.{MINOR}.{PATCH}`

### MAJOR Version (X.0.0)

Increment MAJOR for **significant architectural changes** that fundamentally alter system structure or boundaries.

**Triggers:**
- System boundary redefinition (scope changes, what is "in" vs "out")
- Fundamental restructuring (monolith to microservices, or vice versa)
- Platform migration (e.g., moving from on-prem to AWS)
- Major technology replacement (e.g., replacing the database engine)
- Removal of a core subsystem
- Merger or split of software systems

**Examples:**

| From | To | Version Change | Summary |
|------|-----|---------------|---------|
| v1.5.2 | v2.0.0 | MAJOR | Migrated from monolith to microservices architecture |
| v2.3.1 | v3.0.0 | MAJOR | Merged User and Auth systems into Identity Platform |
| v3.0.0 | v4.0.0 | MAJOR | Replaced Oracle DB with PostgreSQL + DynamoDB |

### MINOR Version (x.Y.0)

Increment MINOR when **containers or components are added, removed, or significantly changed** without altering the system boundary.

**Triggers:**
- New container added (new service, new database, new queue)
- Container removed or deprecated
- New external system integration added or removed
- New deployment environment documented
- Significant rearchitecture within a container (new major component layer)
- New person/actor type introduced

**Examples:**

| From | To | Version Change | Summary |
|------|-----|---------------|---------|
| v2.0.0 | v2.1.0 | MINOR | Added Redis cache container for session management |
| v2.1.0 | v2.2.0 | MINOR | Integrated with Stripe payment processing (new external system) |
| v2.2.0 | v2.3.0 | MINOR | Removed legacy notification service (deprecated) |
| v2.3.0 | v2.4.0 | MINOR | Added SQS queue for async order processing |

### PATCH Version (x.y.Z)

Increment PATCH for **documentation corrections and minor updates** that leave the architecture unchanged.

**Triggers:**
- Renamed a component or container (same thing, better name)
- Updated a description for clarity
- Added missing labels or technology annotations
- Fixed typos in diagram text
- Updated metadata (owner, contact, SLA)
- Improved layout (moved elements for readability)
- Added or corrected protocol labels on relationships

**Examples:**

| From | To | Version Change | Summary |
|------|-----|---------------|---------|
| v2.3.0 | v2.3.1 | PATCH | Corrected technology label on API service (Express -> Fastify) |
| v2.3.1 | v2.3.2 | PATCH | Added missing protocol labels to L2 relationships |
| v2.3.2 | v2.3.3 | PATCH | Updated business owner in metadata table |

---

## Changelog Format

### Changelog Table Specification

Every architecture page carries a Change History table at the bottom, with these columns:

| Column | Format | Description |
|--------|--------|-------------|
| Version | `v{X.Y.Z}` | Semantic version number |
| Date | `YYYY-MM-DD` | Date of the change |
| Ticket | `{PROJ-123}` or `--` | Jira ticket that triggered the change |
| Level | `L1`, `L2`, `L3`, `Deploy`, `Dynamic`, `Landscape` | Which C4 level(s) were affected |
| Summary | Free text (one line) | What changed and why |
| Author | Name, or `AI-assisted (architecture-documentation)` when no named author is supplied; NEVER overwrite attribution on existing entries | Who made the change |

### Example Changelog

| Version | Date | Ticket | Level | Summary | Author |
|---------|------|--------|-------|---------|--------|
| v3.1.0 | 2026-02-11 | PROJ-456 | L2 Container | Added Redis cache for session management | AI-assisted (architecture-documentation) |
| v3.0.0 | 2026-01-28 | PROJ-412 | L1 Context, L2 Container | Added payment service integration (Stripe) | J. Smith |
| v2.0.1 | 2026-01-15 | PROJ-389 | L3 Component (API) | Updated auth middleware description | AI-assisted (architecture-documentation) |
| v2.0.0 | 2025-12-10 | PROJ-301 | L1 Context, L2 Container | Added notification service integration | A. Patel |
| v1.0.0 | 2025-11-01 | -- | L1, L2, L3 | Initial architecture documentation | AI-assisted (architecture-documentation) |

### Rules

- Newest first (most recent at top)
- Every entry MUST have a date and summary
- Every entry SHOULD have a Jira ticket; `--` only for initial documentation or non-ticket-driven changes such as periodic refresh
- "Level" column = diagrams modified; list all when several change in one update (e.g., "L1 Context, L2 Container")
- Per-level pages keep their own changelog (subset of the master)
- The master changelog page aggregates all changes across all levels

---

## Artifact Naming Convention

Tool-neutral logical identifier, plus the extension or native artifact format already established by the repository or destination. NEVER introduce a new diagramming format just to follow this skill.

### Core Views

```
{system-name}-L{level}-v{version}[.{repository-native-extension}]
```

| Component | Format | Example |
|-----------|--------|---------|
| system-name | kebab-case | `user-platform` |
| level | 1, 2, 3 | `L2` |
| version | MAJOR.MINOR.PATCH | `v3.1.0` |
| artifact extension | repository-native when a file is used | `.svg`, `.png`, `.pdf`, or an existing editable format |

Full examples:
```
user-platform-L1-v1.0.0
user-platform-L2-v3.1.0.svg
user-platform-L3-api-service-v2.0.0.pdf
```

### Component Views (L3)

L3 artifacts include the container name (several may exist):
```
{system-name}-L3-{container-name}-v{version}[.{repository-native-extension}]
```

Examples:
```
user-platform-L3-api-service-v2.0.0
user-platform-L3-web-app-v1.0.0.svg
user-platform-L3-worker-v1.0.0.pdf
```

### Supplementary Views

```
{system-name}-deploy-{env}-v{version}[.{repository-native-extension}]       # Deployment
{system-name}-dynamic-{feature}-v{version}[.{repository-native-extension}]   # Dynamic
{system-name}-landscape-v{version}[.{repository-native-extension}]           # System Landscape
```

Examples:
```
user-platform-deploy-prod-v1.0.0
user-platform-deploy-dev-v1.0.0.svg
user-platform-dynamic-order-processing-v1.0.0.pdf
user-platform-landscape-v1.0.0
```

---

## Jira Ticket Linkage

### Every Change Traces to a Ticket

Architecture documentation changes SHOULD trace to the work that caused them:

1. Changelog entry includes the Jira ticket ID
2. Jira ticket comment references the architecture update
3. PR modifying architecture-relevant code links the updated architecture page in its description

### Linkage Patterns

**Code change triggers architecture update:**
```
PROJ-123 (Jira Ticket: "Add Redis cache for sessions")
  -> PR #42 (adds Redis client code, Terraform for ElastiCache)
  -> Architecture update: L2 Container v3.1.0 (new Redis container)
  -> Changelog entry: "v3.1.0 | 2026-02-11 | PROJ-123 | L2 | Added Redis cache"
  -> Jira comment: "Architecture docs updated: [L2 Container v3.1.0](confluence-link)"
```

**Architecture-only update (periodic refresh):**
```
PROJ-500 (Jira Ticket: "Quarterly architecture review Q1 2026")
  -> Review existing diagrams against codebase
  -> Update descriptions, fix stale labels
  -> Changelog entry: "v3.1.1 | 2026-03-01 | PROJ-500 | L2 | Quarterly refresh"
```

**Initial documentation (no prior ticket):**
```
Changelog entry: "v1.0.0 | 2025-11-01 | -- | L1, L2, L3 | Initial documentation"
```

---

## Retroactive Documentation

Documenting an existing system for the first time (no prior architecture docs):

### Step 1: Initial Version (v1.0.0)

Create all applicable C4 levels from the current codebase state:
- Version: `v1.0.0`
- Jira Ticket: `--` (or a specific ticket if one was created for this task)
- Summary: "Initial architecture documentation"

### Step 2: Discover Historical Context

Gather past-change context where possible:
- Read git history for major architectural commits
- Review PRDs and tech specs in Confluence
- Ask the engineering team about key decisions
- Record known decisions in the "Key Decisions" section

### Step 3: Ongoing Updates

Every change follows normal versioning:
- Code change affecting architecture → new architecture-artifact version
- Each version increment has a Jira ticket and changelog entry

### Step 4: Handling Unknown History

History not recoverable:
- Changelog note: "History prior to v1.0.0 is not documented"
- Document the current state accurately
- Track every later change fully

---

## Diff Descriptions

Summarize each new version's changes so reviewers can assess impact quickly.

### Format

```
v{NEW} (from v{OLD}):
- ADDED: {element} - {reason}
- REMOVED: {element} - {reason}
- CHANGED: {element} from {old state} to {new state} - {reason}
- RENAMED: {old name} -> {new name}
```

### Examples

```
v3.1.0 (from v3.0.0):
- ADDED: Redis Cache container [ElastiCache Redis] - session management for
  horizontal scaling (PROJ-456)
- ADDED: Relationship: API Service -> Redis Cache "Stores/retrieves sessions [Redis/TCP]"
- CHANGED: API Service description updated to mention session caching

v3.0.0 (from v2.0.1):
- ADDED: Payment Service (external system, grey) - Stripe integration for
  order processing (PROJ-412)
- ADDED: Relationship: API Service -> Payment Service "Processes payments [HTTP/REST]"
- CHANGED: L1 Context updated to show Payment Service as external dependency
- CHANGED: L2 Container updated to show API -> Payment relationship with protocol
```

---

## Archive Policy

### When to Archive

- When a system is fully decommissioned, archive all architecture artifacts
- When a MAJOR version represents a complete re-architecture, archive the previous
  major version series (keep the final version of each MAJOR)
- Keep at minimum the last 3 MAJOR versions accessible

### How to Archive

1. Archive old architecture artifacts in the repository's established location or,
   for Confluence pages, use `confluence-html-editor` to preserve page structure and
   attachments while recording the archive status
2. Add an info panel on the archived page: "This version is archived. Current
   version: [link to current page]"
3. Do NOT delete archived diagrams -- they serve as historical record
4. Maintain the master changelog with all entries (NEVER remove old entries)

### Retention

| Content | Retention Period (default; the system's records-retention policy overrides) |
|---------|-----------------|
| Current architecture artifacts | Indefinite (always available) |
| Previous MAJOR versions | Minimum 2 years |
| Changelog entries | Indefinite (NEVER delete) |
| GxP system diagrams | Per the system's approved records-retention policy; confirm the period with Quality/Compliance |

---

## Change Management Flow

For significant architecture changes (MAJOR/MINOR), follow this flow:

```
1. Request          -> Jira ticket created describing the architectural change
2. Impact Analysis  -> Identify which C4 levels and artifacts are affected
3. Draft Update     -> Agent prepares new model content and artifact version(s)
4. Review           -> Engineer reviews the draft for accuracy
5. Approval         -> Technical lead approves the architecture change
6. Implementation   -> Publish to Confluence through confluence-html-editor when a live page is in scope
7. Communication    -> Team notified of architecture update
8. Validation       -> Verify published diagrams render correctly
```

PATCH changes (typos, label fixes): steps 5-7 collapse to a quick review by any team member.
