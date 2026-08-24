# Openflow Cortex Skill Architecture

This document explains the structure and development patterns for the Openflow skill. Read this before contributing or modifying the skill.

## Overview

The Openflow skill is a structured knowledge base that enables AI agents to perform NiFi-based data integration operations effectively. It provides guided navigation through OpenFlow's complexity, encoding expert knowledge into accessible workflows.

**Key characteristics:**
- 45+ reference files organized by category
- Surface-aware routing: SQL-only (Snowsight) vs full CLI/Desktop capability
- Tiered intent routing (Primary, Secondary, Advanced)
- Sub-router pattern for reference categories
- Session state management via cached infrastructure data
- Investigation diary methodology for complex operations
- Guided user setup and dependency management

This guidance is based on observed experience developing this Openflow skill and working extensively with Cursor over the past few years; your mileage may vary.

---

## Execution Surfaces

The skill runs on two surfaces, resolved by passive **surface detection** at the start of every session (SKILL.md, first step):

| Surface | Capability | How it runs SQL |
|---------|-----------|-----------------|
| **Snowsight** (Cortex in the Snowsight UI) | SQL only — no nipyapi, curl, or local shell | Native SQL against the session's account |
| **CLI / Desktop** (Cortex Code) | Full — SQL + nipyapi + curl | Native SQL against the active connection; `snow sql -c <connection>` for a non-primary account |

Work is routed on a **capability × intent** basis:

- **SQL/SOM operations** — infrastructure for any connector (deployments, runtimes, EAI) plus Gen2 connector lifecycle. Runs on either surface. (SOM = the `OPENFLOW` SQL grammar.)
- **NiFi-API operations** — Gen1 connector flows, canvas authoring, parameter contexts. Require nipyapi/curl, so **CLI/Desktop only**. On Snowsight the user is directed to the Openflow UI (already in front of them) or to CLI/Desktop.

**Bootstrap is CLI-only.** The `bootstrap-*` chain (install tooling, create nipyapi profiles, discover infrastructure, write the local cache) exists only for CLI/Desktop; Snowsight has nothing to provision.

Surface-specific references:
- `core-guidelines.md` (shared, SQL-safe) + `core-guidelines-cli.md` (nipyapi/curl tool layers, authoring).
- `core-session-sql.md` (SQL session init: connection + SOM probe) vs `core-session-cli.md` (nipyapi cache/profile session).

---

## The Challenge: Why OpenFlow Needs a Skill Architecture

OpenFlow presents a unique challenge for AI-assisted operations. Understanding this challenge explains why the skill is structured the way it is.

### A Multi-Domain Product

OpenFlow spans several distinct knowledge domains:

| Domain | Examples |
|--------|----------|
| **Snowflake Integration** | EAI infrastructure, authentication, runtime configuration |
| **Connector Deployment** | CDC, JDBC, Google Drive, Salesforce - each with unique parameters |
| **NiFi Internals** | Processors, controllers, connections, Expression Language, RecordPath |
| **Parameter Management** | Parameter contexts, sensitive values, assets, inheritance |
| **Operational Workflows** | Status monitoring, lifecycle management, troubleshooting |
| **Flow Authoring** | Custom processor creation, flow patterns, component layout |

No single person typically holds expertise across all these areas. An infrastructure engineer knows EAI but not RecordPath syntax. A data engineer understands connector parameters but not NiFi flow debugging.

### Varying User Entry Points

Users approach OpenFlow with different goals and different existing knowledge:

- **"Deploy a CDC connector for my Oracle database"** - Needs deployment workflow, Oracle-specific parameters
- **"My flow shows validation errors after an upgrade"** - Needs investigation methodology, bulletin interpretation
- **"I need to add custom transformation logic"** - Needs Expression Language, processor authoring patterns
- **"Why isn't data flowing?"** - Could be parameters, processors, connections, or infrastructure

Traditional documentation assumes you know what you're looking for. A skill architecture interprets and adapts to the user's evolving intent - starting with an initial goal, then navigating as that goal shifts or new needs emerge during the session.

### The Context Problem

AI agents operate within context windows. Loading all possible knowledge into context:
- Wastes capacity on irrelevant material
- Creates ambiguity about which guidance applies
- Slows response time and increases cost

The skill architecture implements **lazy loading**: route to the right area first, then load deep knowledge only when needed. A user deploying a connector doesn't need RecordPath syntax. A user debugging Expression Language doesn't need connector deployment steps.

### What This Enables

A well-structured skill means:
- **Faster ramp-up** - New team members follow expert-encoded workflows
- **Fewer mistakes** - Structured procedures prevent skipped steps
- **Accessible expertise** - Deep NiFi knowledge available when needed, not memorized in advance
- **Consistent operations** - Check-Act-Check patterns, dry-run before modify, investigation diaries

---

## How the Skill Works: User Journeys

Before examining the skill structure in detail, it helps to see how users actually navigate it. These examples show the routing flow from initial request to resolution.

### Example 1: Deploying a Connector

**User says:** "I need to deploy a CDC connector for PostgreSQL"

```
SKILL.md (main router)
    ↓ Matches "deploy" + "connector" → Primary tier
    ↓
connector-main.md (category router)
    ↓ Generation Detection → Gen2 (SOM) or Gen1
    ↓
connector-postgres-gen2.md (Gen2 SQL) or connector-cdc.md (Gen1)
    ↓ PostgreSQL-specific parameters
    ↓
[Deployment workflow executes]
    ↓ If parameters needed
    ↓
ops-parameters-main.md → ops-parameters-configure.md
    ↓
[Return to connector-main.md for verification]
```

The agent loaded 3-4 references, not 45. Each reference was relevant to the actual task.

### Example 2: Troubleshooting an Error

**User says:** "My flow has errors after I changed a parameter"

```
SKILL.md (main router)
    ↓ Matches "error" → Secondary tier (problem indicators)
    ↓
ops-flow-investigation.md (investigation workflow)
    ↓ Checks bulletins, processor states
    ↓ Finds Expression Language error in bulletin
    ↓
nifi-main.md (advanced router)
    ↓ Needs Expression Language reference
    ↓
nifi-expression-language.md
    ↓ Identifies incorrect function syntax
    ↓
[Fix applied, returns to investigation]
    ↓
ops-flow-lifecycle.md (restart flow)
```

The investigation started broad, then drilled into Expression Language only when the bulletins revealed that was the issue. Without this routing, the agent would have needed to load all possible error causes upfront.

### Example 3: Customizing a Connector Flow

**User says:** "I need to add custom JSON transformation to my Kinesis connector before data goes to Snowflake"

```
SKILL.md (main router)
    ↓ Matches "Kinesis", "connector" → Primary tier
    ↓ But also "custom", "transformation" → needs authoring
    ↓
connector-main.md (connector router)
    ↓ Kinesis is a Connected connector
    ↓ Customization intent detected
    ↓
author-main.md (authoring router)
    ↓ Matches "add transformation" intent
    ↓
author-building-flows.md (processor CRUD operations)
    ↓ Adding JoltTransformJSON processor
    ↓ Configuring transformation spec
    ↓ If needs Expression Language for dynamic values
    ↓
nifi-expression-language.md
    ↓
[Transformation processor added and configured]
    ↓
ops-flow-lifecycle.md (restart the modified flow)
```

This example shows how intents can span categories. The user starts with a connector context but needs authoring capabilities. The routing flows through connector context first (establishing which flow), then into authoring (for the customization work).

### Why This Matters

In each example:
1. The **main router** matches intent to the appropriate tier, with a bias toward Primary for common operations
2. **Category routers** (`-main.md` files) narrow to specific sub-references
3. **Cross-references** load additional knowledge when the workflow needs it
4. The agent stays **focused on relevant content** throughout

This is why 45+ references should feel like a well-organized toolkit rather than overwhelming complexity. The routing ensures you only see what applies to your current goal.

---

## Skill Structure

### Directory Layout

```
data-engineering/openflow/
├── SKILL.md                    # Main router and entry point
├── README.md                   # This file (architecture documentation)
└── references/
    ├── core-*.md               # Foundational context; shared + surface variants (core-session-sql/-cli, core-guidelines-cli)
    ├── bootstrap-*.md          # CLI environment bootstrap: tooling, profiles, discovery, cache (CLI surface only)
    ├── platform-*.md           # Infrastructure and runtime operations
    ├── ops-*.md                # Operational workflows and baseline capabilities
    ├── connector-*.md          # Connector-specific deployment and config (flat file)
    ├── connector-<name>/       # Subdirectory for complex connectors (sub-router pattern)
    │   ├── connector-<name>-<topic>.md
    │   └── assets/
    ├── author-*.md             # Custom flow authoring and Connector customisation
    └── nifi-*.md               # NiFi tool knowledge (EL, RecordPath, etc.)
```

### File Naming Conventions

Files are prefixed by category. The prefix indicates scope and typical loading order.

| Prefix | Purpose | Load Frequency |
|--------|---------|----------------|
| `core-` | Foundational context, safety rules, session management (shared + `-sql`/`-cli` surface variants) | Always at session start |
| `bootstrap-` | CLI environment bootstrap: tooling, profile creation, discovery, cache. **CLI surface only** | Once per Runtime (CLI) |
| `platform-` | Snowflake-level infrastructure (EAI, diagnostics) | When infrastructure issues arise |
| `ops-` | Operational workflows (deploy, lifecycle, parameters) | Most user requests |
| `connector-` | Connector-specific deployment and troubleshooting | When working with specific sources |
| `author-` | Custom flow authoring (processor CRUD, patterns) | Advanced users only |
| `nifi-` | NiFi tool knowledge (Expression Language, RecordPath) | When authoring or debugging |

### Connector Subdirectory Pattern

Most connectors are a single flat file (`references/connector-<name>.md`). For connectors whose combined reference would exceed ~400 lines or have 3+ separable sections (field reference, troubleshooting, fleet ops, worked examples), use a subdirectory:

- `references/connector-<name>.md` — top-level entry point registered in SKILL.md and connector-main.md. Contains the core deployment workflow and acts as a sub-router to sub-files.
- `references/connector-<name>/connector-<name>-<topic>.md` — sub-files loaded on demand via `**Load**` directives in the top-level file. Each sub-file must end with a return directive back to the top-level file.

The [`connector-shopify`](references/connector-shopify.md) layout is the reference implementation of this pattern. New complex connectors should follow the same structure.

### The `-main` Sub-Router Pattern

When a category has multiple sub-references, a `<prefix>-main.md` file serves as the category router:

```
connector-main.md       → Routes to connector-cdc.md, connector-googledrive.md, etc.
ops-parameters-main.md  → Routes to ops-parameters-configure.md, ops-parameters-assets.md, etc.
author-main.md          → Routes to author-building-flows.md, author-pattern-*.md, etc.
nifi-main.md            → Routes to nifi-expression-language.md, nifi-recordpath.md, etc.
bootstrap-cli.md           → Routes to bootstrap-auth.md, bootstrap-discovery.md, etc.
```

The main SKILL.md routes to these `-main` files, which then route to sub-references based on more specific intent.

**Why sub-routers?** This pattern implements lazy loading for agent context. Not all knowledge is needed for every task - there's no point loading RecordPath syntax when deploying a connector with parameters. By creating tiered gates to information, the agent only loads deep knowledge when entering an area where it's actually needed.

The structure works like this: the main router focuses the agent toward a workflow (good when intent is clear), sub-routers provide access to specialized knowledge areas, and cross-references allow loading focused documents as needed then moving on. This keeps context tight and relevant rather than front-loading everything the agent might possibly need.

This pattern appears to work well in my testing with claude-opus, ymmv with other models and skills and client-interaction patterns however.

---

## Intent Routing Architecture

### Entry Point: SKILL.md

SKILL.md is the main router. It contains:
1. Surface detection & session start (always first)
2. Routing principles (including surface gating)
3. Three tiered routing tables (Primary, Secondary, Advanced)
4. Reference index for discoverability

### Tiered Routing

**Why tiers?** As intent tables grow large, agents tend to treat all options as equally likely. In practice, certain actions are far more common than others. User language often matches multiple possible intents - "check my connector" could mean status check, bulletin review, or parameter inspection. Tiered routing provides weighting toward more likely behaviors, ensuring common operations are preferred when language is ambiguous. This structure would be unnecessary for a small intent table.

| Tier | When to Route | User Language |
|------|---------------|---------------|
| **Primary** | Common operations, default choice | "deploy", "status", "start", "stop", "check" |
| **Secondary** | Problem indicators, investigation needed | "error", "troubleshoot", "configure", "not working" |
| **Advanced** | Explicit technical NiFi terminology | "processor", "Expression Language", "RecordPath", "custom flow" |

**Routing rules:**
1. Session first - Always validate session before routing
2. Confirm before executing - State detected intent, ask for confirmation
3. Primary wins ties - If ambiguous between tiers, choose Primary
4. Never suggest Advanced - Only route to Advanced on explicit technical language

### Routing Flow

```
User Request
    ↓
SKILL.md (main router)
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Match intent to tier:                                       │
│   Primary   → ops-status-check.md, connector-main.md, etc.  │
│   Secondary → ops-flow-investigation.md, platform-eai.md    │
│   Advanced  → author-main.md, nifi-main.md                  │
└─────────────────────────────────────────────────────────────┘
    ↓
Category router (-main.md) if applicable
    ↓
Specific reference file
    ↓
Execute workflow, cross-reference as needed
```

---

## Cross-Referencing Patterns

References frequently direct to other references. Use these patterns:

### Load Directive

Use when the agent should fully load another reference before continuing:

```markdown
**Load** `references/ops-parameters-main.md` for parameter configuration.
```

### Continue Directive

Use when returning to a calling reference after completing work:

```markdown
**Continue** to `references/connector-main.md` Step 7.
```

### See Also Section

Use at the end of references for related material:

```markdown
## See Also

- `references/ops-flow-lifecycle.md` - Start, stop, monitor
- `references/ops-parameters-main.md` - Parameter configuration
```

### Active vs Passive Language

Prefer active, directive language:

```markdown
# Good (directive)
**Load** `references/bootstrap-auth.md` to configure authentication.

# Bad (passive, ambiguous)
Return to the setup workflow when done.
```

---

## Reference File Structure

Every reference should follow this structure:

```markdown
---
name: openflow-<category>-<topic>
description: <What this covers>. <When to load it>.
---

# <Title>

## Scope

- What this reference covers
- What to load for other topics

## Prerequisites (if applicable)

- Required state or prior steps

## Workflow / Content

### Step 1: <Goal>

<Instructions, commands, decision points>

## Troubleshooting (if applicable)

### <Common Issue>

<Resolution>

## Related References / See Also

- `references/<related>.md` - <Brief description>
```

### Critical Structure Rules

1. **Scope within first 50 lines** - The scope statement should appear early so the agent quickly understands whether this reference applies, and they have a tendency to head the first ~50 lines
2. **Intent table for routers** - Router files (`-main.md`) should have an intent routing table near the top
3. **Active halting states** - Every path should end with a clear next step or explicit completion

---

## Development Process

This skill was developed iteratively alongside the nipyapi client using a coordinated feedback loop between two agents.

### Two Agents

- **Cortex agent** - The CLI-based agent (`cortex` command) that consumes these skills and performs Openflow operations. This is the target consumer.
- **Cursor agent** - The development assistant (Claude Opus or similar) used for analysis and implementing improvements to skill files and client code.

### Workspace Setup

Development uses a Cursor workspace containing both repositories:
- `nipyapi` - The Python client providing NiFi API access
- `cortex-code-skills` - This skill repository

Working with both in a single workspace allows the Cursor agent to understand the full stack when implementing improvements.

**Cursor Configuration:** When developing or modifying the skill files themselves, add this README (`data-engineering/openflow/README.md`) to your Cursor agent context. This ensures the Cursor agent has access to architecture guidance, development principles, and validation requirements without needing to load them each session.

### Iteration Cycle

1. **Run a Cortex session** - Use the Cortex agent (via CLI) to attempt a specific user goal (e.g., deploy a CDC connector, investigate a failing flow), or receive another user's session export as JSON to examine (~/.snowflake/cortex/conversations).

2. **Review the session** - Conversation history typically reveals:
   - **New situations** - Edge cases or system responses not yet encoded in the skills
   - **Convoluted processes** - The goal was achieved but required complex scripts, excessive discovery, or unnecessary steps that could be simplified
   - **Guidance gaps** - Incorrect commands or routing decisions indicating missing or unclear skill content

3. **Analyze root cause** - Understand what drove the observation:
   - Was knowledge missing that would have prevented the issue?
   - Could a simpler client function have avoided complex code generation?
   - Was routing ambiguous, leading to the wrong reference being loaded?

4. **Identify the improvement type**:
   - **Skill improvement** - Missing guidance, unclear routing, or undocumented patterns → update reference files
   - **Client improvement** - Complex API requiring simplified wrapper, missing CLI command, or verbose output needing parsing → PR against nipyapi

5. **Implement and retest** - Apply the fix (using Cursor agent for implementation), run another Cortex session targeting the same goal, verify the improvement

### Coordination

Skill files reference specific nipyapi functions. When the client changes:
- New functions may enable new skill capabilities
- Simplified functions may allow removing complex guidance
- Breaking changes require skill updates

The nipyapi `ci` module was specifically designed to provide high-level operations that reduce Cortex agent complexity. Many functions exist because a skill workflow revealed the need.

---

## Design Philosophy

### Content Types

Reference files serve different purposes and vary in how prescriptive they are:

| Type | Description | Examples |
|------|-------------|----------|
| **Functional references** | Discrete operations: "call this to do that" | `ops-status-check.md`, `ops-bulletins.md` |
| **Procedures** | Prescriptive multi-step workflows with specific sequencing | `connector-main.md`, `bootstrap-cli.md` |
| **Open-ended processes** | Discovery-oriented workflows where the agent navigates based on findings | `ops-flow-investigation.md`, `author-main.md` |
| **Baseline knowledge** | Tool syntax and concepts the agent needs but wouldn't know otherwise | `nifi-expression-language.md`, `nifi-recordpath.md` |

Procedures are highly prescriptive ("do step 1, then step 2"). Open-ended processes provide structure but expect the agent to discover its way through, potentially loading functional references or baseline knowledge as needed.

For frequently-used operations, the CLI commands are designed to be as deterministic as possible: a given call with specific inputs returns an expected result structure or a well-known set of errors. This reduces agent ambiguity and guessing, making common operations feel more like MCP-style tool invocation than open-ended code generation.

### Inclusion Criteria

Every piece of knowledge in this skill exists because it proved necessary for a specific user goal. We avoid including "nice to have" information that might help in theory. If something isn't directly supporting a top-level action a user might request, it doesn't belong here.

This discipline keeps context focused and prevents the skill from bloating with reference material that competes for the agent's attention.

### Command Simplification

Where possible, the underlying nipyapi client has been designed to simplify commands the agent must construct. Goals:

- **Reduce structured JSON in responses** - Complex nested objects are parsed and flattened
- **Minimize Python code generation** - Prefer CLI commands over multi-line Python scripts
- **Lower ambiguity** - Fewer parameters and simpler signatures reduce the likelihood of errors

When the agent doesn't need to construct complex DTOs or write intricate code, it's less likely to hallucinate incorrect syntax or parameter values.

Conversely, when user intent is investigative - troubleshooting errors, understanding unexpected behavior - the agent operates in discovery mode. Rather than executing predetermined commands, it checks `--help` to understand available arguments, verifies assumptions before acting, and may start an investigation diary when complexity grows. The skill is structured to recognize these different intent modes and load context that matches the appropriate response mode.

### Operational Patterns

Certain high-level patterns govern how operations are executed:

- **Check-Act-Check** - Read state before modifying, execute the change, verify the result. NiFi operations are often asynchronous; the returned object may reflect intermediate state.
- **Dry-run before modifying** - For parameter updates and bulk changes, run with `--dry_run` first and present results for user confirmation.
- **Discover before executing** - For template commands (vs exact commands), check `--help` to understand arguments before constructing the call.

These patterns are documented in `references/core-guidelines.md` and applied throughout operational references.

---

## Development Principles

### 1. Scope at the Top

Every reference file should declare its scope early (within the first ~50 lines). This helps the agent quickly determine if the reference is relevant and what to load instead if not.

```markdown
## Scope

This reference covers:
- Deploying connectors from the Snowflake registry
- General connector configuration guidance

For custom flow authoring, see `references/author-main.md`.
```

### 2. Use Explicit References, Not Snippets

When referencing content from another file, use a load directive rather than copying content:

```markdown
# Good
**Load** `references/ops-snowflake-auth.md` for Snowflake authentication configuration.

# Bad
Snowflake authentication requires KEY_PAIR auth. Configure using:
... [copied snippet that will go stale]
```

**Why:** Duplicated content goes stale when the source changes. References ensure the agent always gets current information.

### 3. Do Not Cross Domain Boundaries

Each reference should stay within its domain. Do not include examples or procedures from other skill areas.

```markdown
# Bad
For Cortex Analyst semantic models, you can also use this pattern...

# Good
[Simply don't include cross-skill content]
```

**Why:** Other skills have their own maintenance cycles. Cross-references create hidden dependencies that break silently.

### 4. Commands: Exact vs Template

Mark commands clearly so the agent knows whether discovery is needed:

```markdown
# Exact command (run as-is, substitute session variables only)
**Run exactly** (substitute `<profile>` from session):
```bash
nipyapi --profile <profile> ci list_flows
```

# Template command (requires discovery or user input)
**Discover arguments first:**
```bash
nipyapi canvas create_processor --help
```
```

### 5. Check-Act-Check Pattern

For operations that modify state, document the verification steps:

```markdown
### Stop Flow

**Check** current state:
```bash
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

**Act** - stop the flow:
```bash
nipyapi --profile <profile> ci stop_flow --process_group_id "<pg-id>"
```

**Check** new state:
```bash
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```
Expect: `stopped_processors` > 0, `running_processors` = 0

### 6. Investigation Diary for Complexity

When operations become complex (5-10+ exchanges, multiple hypotheses, unclear root cause), suggest starting an investigation diary. See `references/core-investigation-diary.md` for the methodology.

---

## Adding New References

1. Create the file in `references/` with appropriate naming prefix
2. Add frontmatter with `name` (format: `openflow-<prefix>-<topic>`) and `description`
3. Add scope statement within first 50 lines
4. Add routing entry to the appropriate router:
   - If Primary tier: add to SKILL.md Primary Routing Table
   - If Secondary tier: add to SKILL.md Secondary Routing Table
   - If Advanced tier: add to SKILL.md Advanced Routing Table
   - If sub-reference: add to the category's `-main.md` router
5. Add to SKILL.md Reference Index
6. Include "Related References" or "See Also" section at the end
7. Validate reachability using CYOA analysis (see below)

---

## Validation: CYOA Analysis

The skill forms a soft state machine a bit like a Choose Your Own Adventure novel.
Validation covers both structural properties (graph traversal) and content properties (reading and comparing files).

### Structural Validation

These properties can be checked by tracing the routing graph:

| Property | Validation Check |
|----------|------------------|
| **Reachability** | Every reference is loadable from SKILL.md (directly or via a router) |
| **Determinism** | Each routing decision has defined outcomes |
| **Termination** | Every path ends with a clear halting state or return directive |
| **Transition clarity** | Uses active voice: "Load X", "Continue to Y" |
| **No orphans** | No reference files exist that aren't reachable from any router |

Run structural validation by:
1. Starting at SKILL.md and tracing all routing targets
2. For each target, trace its decision points and outcomes
3. Verify every path reaches a halting state (success, user choice, error, or return)
4. Check all files in `references/` are reachable from some path

### Content Validation

These properties require reading and comparing file contents:

| Property | Validation Check |
|----------|------------------|
| **No duplication** | Guidance appears in exactly one place excepting single prescriptive commands; other files cross-reference rather than repeat |
| **No conflicts** | Different references do not offer contradictory instructions for the same operation |
| **Intent disambiguation** | Where user language could match multiple intents, routing rules provide a clear tiebreaker (Primary tier wins ambiguous cases) |

Run content validation by:
1. Search for similar content across files; suggest consolidating significant duplicates to a single source with cross-references
2. Compare instructions for the same operations across references; resolve contradictions
3. Review routing tables for overlapping intent language; confirm tiebreaker rules exist and are documented

---

## Lessons Learned

### What Works

- **Tiered routing reduces confusion** - Users get routed to appropriate complexity levels
- **Sub-router files prevent SKILL.md bloat** - Category routers keep the main file focused
- **Explicit load directives** - Active voice prevents ambiguous navigation
- **Session prerequisites** - Catching missing setup early prevents failures downstream, caching provides efficiency
- **Investigation diary** - Maintains context for complex multi-step troubleshooting and later session review

### What to Avoid

- **Duplicating content across references** - Goes stale when source changes
- **Vague cross-references** - "See also the parameters documentation" vs "Load `references/ops-parameters-main.md`"
- **Mixing tiers** - Primary operations shouldn't reference Advanced concepts without explicit routing
- **Orphan references** - Files that exist but aren't reachable from any router
- **Missing halting states** - Paths that trail off without clear next steps

---

## nipyapi Client Development

When improvements require changes to the nipyapi client rather than skill files, follow these guidelines.

### Finding the Right Function

For function discovery, use CLI help or Python introspection:

```bash
nipyapi <module> --help              # List functions in a module
nipyapi canvas get_processor --help  # Get specific function signature
```

```python
help(nipyapi.canvas)                 # Module overview
help(nipyapi.canvas.get_processor)   # Function details
```

### Relevant Modules for Openflow

Openflow Runtimes use URL + Bearer token authentication, so security/auth modules don't apply. Focus on these:

| If you need to... | Use |
|-------------------|-----|
| Deploy flows, configure params, start/stop (high-level) | `nipyapi.ci` |
| Manage processors, process groups, connections | `nipyapi.canvas` |
| Import/export versioned flows | `nipyapi.versioning` |
| Work with parameter contexts | `nipyapi.parameters` |
| Position components on canvas | `nipyapi.layout` |
| Get system/cluster info | `nipyapi.system` |
| Retrieve/filter/clear bulletins | `nipyapi.bulletins` |
| Manage NiFi extensions (NARs) | `nipyapi.extensions` |
| Direct NiFi API access (when helpers insufficient) | `nipyapi.nifi.*` |

Most of these are already in use within existing subskills, if you do find yourself unsure how to use a specific new function you can instruct your agent to inspect the nipyapi/tests for it to see intended usage.

### Documentation Links

| Resource | Location |
|----------|----------|
| Full API reference | https://nipyapi.readthedocs.io |
| CLI usage | `nipyapi --help` |
| Profile configuration | `docs/profiles.rst` in nipyapi repo |
| Contributing to nipyapi | `AGENTS.md` in nipyapi repo |

### Function Prioritization

When adding nipyapi functionality, follow this priority:

| Priority | Location | When to Use |
|----------|----------|-------------|
| 1 | `nipyapi.ci` | Operations useful in CI/CD (deploy, configure, start, stop, status) |
| 2 | CLI-accessible | Interactive operations not needed in automation |
| 3 | Helper wrapper | Complex DTO construction that's error-prone for users |

**CI module (`nipyapi ci`):**
- Highest-level interface with environment variable fallbacks
- Returns structured JSON for parsing
- Preferred for pipeline operations
- Excellent home for more complex operations where the agent benefits from summary output

**CLI-accessible functions:**
- Already available via `nipyapi <module> <function>`
- Sufficient for interactive use cases
- Excellent for wrapping asynchronous calls or handling embedded knowledge about API or server behaviour.

**Helper wrappers:**
- Create when raw API requires complex object construction
- Accept simple parameters, handle DTO building internally
- If you find your agent reaching for the low level nipyapi.nifi functions, then likely a new helper function would make things easier here.

---

## Related Documentation

- `skill_development/SKILL_BEST_PRACTICES.md` - General skill authoring guidelines
- `references/core-guidelines.md` - Foundational operational context (loaded by the Cortex agent)
