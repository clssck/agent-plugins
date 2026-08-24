# Skill Best Practices for Cortex Code

This guide provides best practices for creating skills for Cortex Code, derived from proven patterns in production skills.

---

## Table of Contents

1. [Core Principles](#core-principles)
2. [Understanding Skill Architecture](#understanding-skill-architecture)
3. [Skill File Structure](#skill-file-structure)
4. [Writing Effective Frontmatter](#writing-effective-frontmatter)
5. [Designing Workflows](#designing-workflows)
6. [Tool Definitions](#tool-definitions)
7. [Scripts in Skills](#scripts-in-skills)
8. [User Interaction Patterns](#user-interaction-patterns)
9. [Sub-Skills, References, and Modularity](#sub-skills-references-and-modularity)
10. [Advanced Skill Patterns](#advanced-skill-patterns)
11. [Common Patterns](#common-patterns)
12. [Common Pitfalls to Avoid](#common-pitfalls-to-avoid)
13. [Quality Red Flags](#quality-red-flags)
14. [Example: Complete Skill](#example-complete-skill)

---

## Core Principles

### Conciseness is Key

The context window is shared—skills compete with conversation history, other skills, and user requests. **Challenge every piece of information:** "Does Cortex Code really need this?"

- Keep SKILL.md under **500 lines**
- Prefer concise examples over verbose explanations
- Move detailed reference material to separate files (references/ or sub-skills)
- Cortex Code is already smart—only add what it doesn't already know

### Degrees of Freedom

Match the level of specificity to the task's fragility:

| Freedom | When to Use | Format |
|---------|-------------|--------|
| **High** | Multiple valid approaches, context-dependent decisions | Text instructions, heuristics |
| **Medium** | Preferred pattern exists, some variation acceptable | Pseudocode, parameterized examples |
| **Low** | Fragile operations, consistency critical, specific sequence required | Exact scripts, specific commands |

Think of Cortex Code exploring a path: a narrow bridge needs specific guardrails (low freedom), while an open field allows many routes (high freedom).

### Explain the Why

LLMs are smart. Rather than rigid "ALWAYS" or "NEVER" rules, explain the reasoning behind instructions. When the model understands *why* something matters, it can apply that understanding to novel situations.

| Approach | Example |
|----------|---------|
| **Rigid (weak)** | "ALWAYS use absolute paths" |
| **Explained (strong)** | "Use absolute paths because `uv run` executes from an isolated environment where relative paths resolve unexpectedly" |

If you find yourself writing instructions in ALL CAPS, that's a signal to reframe—explain the consequence or trade-off instead.

### Generalize, Don't Overfit

Skills are used across many prompts and contexts. When improving a skill based on test cases:

- **Don't** add narrow fixes that only help specific examples
- **Do** identify the underlying pattern and address it generally
- **Consider** using different metaphors or approaches if a fix feels "fiddly"

A skill that only works for your test prompts is useless. Generalize.

| Approach | Example |
|----------|---------|
| **Overfitting (weak)** | Add `if "semantic model" in prompt: check YAML syntax` because one test case had a YAML error |
| **Generalizing (strong)** | Add "Validate file syntax before processing" as a universal step, covering YAML, JSON, SQL, etc. |

### Read Transcripts, Not Just Outputs

When debugging skill issues, don't just look at final outputs—read the full agent transcript:

- **Check for unproductive exploration**: Did the agent spend 5 turns trying approaches before finding the right one?
- **Look for repeated code**: Did the agent write similar scripts multiple times? Bundle these in `scripts/`.
- **Spot instruction confusion**: Did the agent misinterpret a step, then recover? The instruction may be ambiguous.

Outputs show *what* happened; transcripts show *why*.

---

## Understanding Skill Architecture

### What is a Skill?

A skill is a markdown file that teaches Cortex Code how to complete a specific task. Skills provide:

1. **Structured guidance**: Step-by-step workflows
2. **Tool references**: What tools to use and when
3. **Decision logic**: How to handle different scenarios
4. **User checkpoints**: Where to pause for user input

### Skill Complexity Levels

Skills can be simple or complex depending on the task:

**Simple Skill (Single File):**
```
my-skill/
└── SKILL.md          # Everything in one file
```

**Complex Skill (With Sub-Skills):**
```
my-skill/
├── SKILL.md          # Entry point with intent detection
├── sub-task-a/
│   └── SKILL.md      # Loaded for Intent A
├── sub-task-b/
│   └── SKILL.md      # Loaded for Intent B
└── reference.md      # Supporting documentation
```

**Key Principle:** Start simple. Only add sub-skills when your single file exceeds ~200 lines or has clearly distinct workflow branches. Many effective skills are just one file.

---

## Skill File Structure

### Required Sections

Every skill should have these sections:

```markdown
---
name: skill-name
description: "Clear description with trigger phrases"
---

# Skill Title

## When to Use/Load
[Criteria for when this skill applies]

## Workflow
[Step-by-step instructions]

## Tools (if applicable)
[Tool definitions with parameters]

## Stopping Points
[Where to pause for user input]

## Output
[What the skill produces]
```

### Optional Sections

```markdown
## Prerequisites
[What needs to be in place]

## Setup
[Initial configuration steps]

## Success Criteria
[How to verify completion]

## Troubleshooting
[Common issues and solutions]

## Notes
[Additional context or caveats]
```

---

## Writing Effective Frontmatter

### Core Fields: name + description

The frontmatter should primarily contain only `name` and `description`. The description is the **primary trigger mechanism**—it determines when the skill activates.

```yaml
---
name: my-skill
description: "What it does + when to use it. Include trigger phrases."
---
```

### Writing Good Descriptions

The description should include:
1. **What the skill does** (purpose)
2. **When to use it** (trigger conditions)
3. **Specific keywords** that should activate it

**Good Pattern:**
```yaml
---
name: pdf-editor
description: "Create, edit, rotate, and extract content from PDF files. Use when working with PDFs for: creating documents, modifying pages, extracting text, rotating pages, or merging files."
---
```

**Bad Pattern:**
```yaml
---
name: my-skill
description: "A skill for doing things with data"
---
```

**Why it fails:** Too vague, no trigger keywords, doesn't explain when to use.

### Combat Undertriggering

LLMs tend to *not* use skills even when they would help. Make descriptions "pushy":

| Too Passive | Pushy (Better) |
|-------------|----------------|
| "Create dashboards with Streamlit" | "Create dashboards with Streamlit. Use this skill whenever the user mentions dashboards, data visualization, charts, or wants to display data, even if they don't explicitly ask for Streamlit." |
| "Debug semantic models" | "Debug semantic models. Invoke this skill for ANY semantic model issues including validation errors, query failures, relationship problems, or unexpected results." |

Include edge cases and adjacent scenarios that should still trigger the skill.

### Optional: Additional Frontmatter Fields

These fields are optional and should only be used when needed:

```yaml
---
name: child-skill
description: "..."
# Optional - only if this skill requires others to be loaded first
required_skills: [parent-skill, reference/concepts]
# Optional - if this is a sub-skill
parent_skill: main-skill
---
```

---

## Designing Workflows

### Step Structure

Use numbered steps with clear actions:

```markdown
### Step 1: [Goal Statement]

**Goal:** [What this step accomplishes]

**Actions:**

1. **Ask** the user for [specific information]:
   ```
   [Template of what to ask]
   ```

2. **Load** `reference_doc.md` for context

3. **Execute** [specific action]:
   ```bash
   [command or tool call]
   ```

**Output:** [What this step produces]

**Next:** Proceed to Step 2
```

### Decision Points

When the workflow branches:

```markdown
### Step 2: Route Based on User Choice

**Ask** user which option they prefer:

```
Select your approach:
1. Option A - [brief description]
2. Option B - [brief description]
3. Option C - [brief description]
```

**If user selects Option A:**
- **Load** `option-a/SKILL.md`
- Follow Option A workflow

**If user selects Option B:**
- **Load** `option-b/SKILL.md`
- Follow Option B workflow
```

### Workflow Diagrams

Include ASCII diagrams for complex flows:

```markdown
## Workflow Decision Tree

```
Start
  ↓
Step 1: Setup
  ↓
Step 2: Intent Detection
  ↓
  ├─→ Intent A → Load skill-a/SKILL.md
  │
  ├─→ Intent B → Load skill-b/SKILL.md
  │
  └─→ Intent C → Load skill-c/SKILL.md
```
```

---

## Tool Definitions

### Standard Tool Section Format

```markdown
## Tools

### Tool 1: tool_name

**Description**: [What the tool does]

**Parameters**: [List key parameters]
- `param1`: [type] - [description]
- `param2`: [type] - [description]

**Example:**
```bash
tool_name --param1 value1 --param2 value2
```

**When to use:** [Specific scenarios]
**When NOT to use:** [What this tool shouldn't be used for]
```

### Script-Based Tools

For Python scripts with `uv`:

```markdown
### Tool: my_script.py

**Description**: [What it does]

**Usage:**
```bash
uv run --project <SKILL_DIRECTORY> python <SKILL_DIRECTORY>/scripts/my_script.py [args]
```

**Arguments:**
- `arg1`: [description]
- `arg2`: [description]

**⚠️ IMPORTANT:** Always use absolute paths for both `--project` and the script path.
```

---

## Scripts in Skills

Scripts extend skills with reusable automation. Many production skills include a `scripts/` directory with Python scripts that handle complex operations like API calls, data processing, or Snowflake interactions.

### When to Use Scripts

**Use scripts when:**
- The operation involves API calls or external services
- Logic is complex and benefits from a real programming language
- The same operation needs to run with different parameters
- You need proper error handling, retries, or validation
- The operation would be tedious to describe in markdown instructions

**Keep it in markdown when:**
- Simple SQL queries (use `snowflake_sql_execute` tool)
- File operations that Cortex Code can do directly
- Logic is straightforward and doesn't need abstraction

### Directory Structure

Skills with scripts follow this structure:

```
my-skill/
├── SKILL.md              # Main skill file (required)
├── pyproject.toml        # Python dependencies (if scripts)
├── scripts/              # Executable code
│   ├── script_one.py
│   ├── script_two.py
│   └── utils.py          # Shared utilities (optional)
├── references/           # Documentation loaded as needed (optional)
│   └── detailed_guide.md
├── assets/               # Files used in output (optional)
│   └── template.pptx
└── sub-skill/            # Sub-skills (optional)
    └── SKILL.md
```

### Assets Directory

The `assets/` directory contains files used in skill output—not loaded into context, but used in what Cortex Code produces:

**When to include assets:**
- Templates (PowerPoint, Word, HTML boilerplate)
- Images (logos, icons)
- Fonts
- Sample files to copy/modify

**Examples:**
```
assets/
├── logo.png              # Brand assets
├── slides_template.pptx  # Presentation template
├── frontend-template/    # React/HTML boilerplate
└── report_template.docx  # Document template
```

Assets are referenced in workflows: "Copy `assets/frontend-template/` to the output directory."

### Setting Up pyproject.toml

Every skill with scripts needs a `pyproject.toml` to manage dependencies:

```toml
[project]
name = "my-skill"
version = "0.1.0"
description = "Description of what this skill does"
requires-python = ">=3.11"
dependencies = [
    "requests>=2.32.0",
    "snowflake-snowpark-python>=1.40.0",
    # Add other dependencies as needed
]
```

**Common dependencies:**
- `snowflake-snowpark-python` - Snowflake connectivity
- `requests` - HTTP API calls
- `pyyaml` - YAML file handling
- `python-dotenv` - Environment variable management

### Package Management with uv (Recommended)

**uv is strongly recommended** for skills with scripts. It simplifies dependency management by automatically creating isolated environments and installing packages from `pyproject.toml`.

**Why uv:**
- Automatic dependency resolution and installation
- Isolated environments per project
- No manual `pip install` or virtual environment setup
- Reproducible builds via `uv.lock`

**Alternative:** If you choose not to use uv, you'll need to manage dependencies manually with `pip` and virtual environments. Document this in your skill's prerequisites.

### Ensuring uv is Installed

**If your skill uses uv, include a setup/prerequisites step:**

```markdown
## Prerequisites

### Install uv (if not already installed)

Check if uv is installed:
```bash
uv --version
```

If not installed, install it:
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with Homebrew
brew install uv

# Or with pip
pip install uv
```

After installation, restart your terminal or run `source ~/.bashrc` (or equivalent).
```

**Alternatively**, add a check in your workflow:

```markdown
### Step 1: Verify Environment

**Actions:**

1. **Check** uv is installed:
   ```bash
   uv --version
   ```

   If this fails, install uv first (see Prerequisites).

2. **Proceed** with script execution...
```

### Running Scripts with uv

Use `uv run` to ensure dependencies are available:

```bash
# Pattern: uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/<script>.py [args]

# Example with absolute paths:
uv run --project /path/to/my-skill \
  python /path/to/my-skill/scripts/my_script.py \
  --arg1 value1 --output output.json
```

**What happens:** uv automatically installs dependencies from `pyproject.toml` into an isolated environment before running the script.

**Common Mistakes:**

```bash
# ❌ WRONG: Relative script path
uv run --project /path/to/skill python scripts/my_script.py

# ❌ WRONG: cd into directory first
cd /path/to/skill && uv run python scripts/my_script.py

# ✅ CORRECT: Absolute paths for both --project and script
uv run --project /path/to/skill python /path/to/skill/scripts/my_script.py
```

### Alternative: Running Scripts Without uv

If your skill doesn't use uv, document the manual setup in prerequisites:

```markdown
## Prerequisites

### Python Environment Setup

1. Create a virtual environment:
   ```bash
   cd <SKILL_DIRECTORY>
   python -m venv .venv
   source .venv/bin/activate  # macOS/Linux
   # or: .venv\Scripts\activate  # Windows
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   # or from pyproject.toml:
   pip install .
   ```

3. Run scripts with the activated environment:
   ```bash
   python scripts/my_script.py [args]
   ```
```

**Note:** If not using uv, include a `requirements.txt` file as an alternative to `pyproject.toml` for simpler setups.

### Script Documentation Pattern

Document each script in your SKILL.md:

```markdown
## Tools

### Script: get_agent_config.py

**Description**: Retrieves agent configuration from Snowflake via REST API.

**Usage:**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/get_agent_config.py \
  <agent_name> \
  --database <DATABASE> \
  --schema <SCHEMA> \
  --output <output_file.json>
```

**Arguments:**
- `agent_name`: Name of the agent to retrieve (positional, required)
- `--database`: Database name (default: SNOWFLAKE_INTELLIGENCE)
- `--schema`: Schema name (default: AGENTS)
- `--output`: Output file path (default: stdout)
- `--connection`: Snowflake connection name (default: snowhouse)

**Example:**
```bash
uv run --project /path/to/skill python /path/to/skill/scripts/get_agent_config.py \
  MY_AGENT --output agent_config.json
```

**Output:** JSON file with complete agent specification

**When to use:** Before modifying an agent, to capture current state
**When NOT to use:** For quick agent testing (use test_agent.py instead)
```

### Script Best Practices

1. **Use argparse for CLI arguments** - Makes scripts self-documenting
2. **Include --help support** - But skills shouldn't need to call it
3. **Handle errors gracefully** - Print clear error messages
4. **Use environment variables for secrets** - Never hardcode credentials
5. **Keep scripts focused** - One script = one job
6. **Share utilities** - Put common code in `utils.py`
7. **Never print secrets** - Avoid logging or echoing sensitive values to console
8. **Pass file paths for complex data** - For certificates, tokens, or configs, pass file paths rather than reading content into context (reduces errors, keeps secrets out of history)

### Example: Complete Script Setup

```python
#!/usr/bin/env python3
"""
get_data.py - Retrieve data from Snowflake

Usage:
    uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/get_data.py \
        --table TABLE_NAME --output output.json
"""

import argparse
import json
import os
from snowflake.snowpark import Session

def get_connection():
    """Create Snowflake connection from environment."""
    connection_name = os.environ.get("SNOWFLAKE_CONNECTION_NAME", "snowhouse")
    return Session.builder.config("connection_name", connection_name).create()

def main():
    parser = argparse.ArgumentParser(description="Retrieve data from Snowflake")
    parser.add_argument("--table", required=True, help="Table name to query")
    parser.add_argument("--output", required=True, help="Output JSON file")
    parser.add_argument("--limit", type=int, default=100, help="Row limit")
    args = parser.parse_args()

    session = get_connection()
    try:
        df = session.table(args.table).limit(args.limit)
        result = df.to_pandas().to_dict(orient="records")

        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, default=str)

        print(f"✅ Wrote {len(result)} rows to {args.output}")
    finally:
        session.close()

if __name__ == "__main__":
    main()
```

### Avoid Extraneous Documentation

Do **not** create auxiliary documentation files in skills:
- ❌ README.md
- ❌ CHANGELOG.md
- ❌ INSTALLATION_GUIDE.md

Skills are for AI agents, not human documentation. All necessary information should be in SKILL.md or loaded as references when needed.

### Alternative: External CLI Tools

Skills can reference installed CLI tools instead of embedded scripts:

```bash
# External CLI tool (installed separately)
snow sql -q "SELECT * FROM my_table LIMIT 10" --format json
```

Use this pattern when the tool is useful beyond the skill or has its own release cycle. Document installation in Prerequisites.

---

## User Interaction Patterns

### Mandatory Stopping Points

Mark where the workflow MUST pause:

```markdown
**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until user responds.

Ask user:
```
[Question to user]

Options:
1. [Option A]
2. [Option B]
3. [Option C]

Please select (1-3):
```
```

### Approval Gates

Before making changes, get explicit approval:

```markdown
**⚠️ MANDATORY CHECKPOINT**: Before applying changes:

Present to user:
```
I will make the following changes:
1. [Change 1]
2. [Change 2]

Do you approve? (Yes/No/Modify)
```

Wait for explicit approval (e.g., "approved", "looks good", "proceed").
NEVER proceed without user confirmation.
```

### Resume Conditions

Clarify when to continue:

```markdown
## Stopping Points

- ✋ After diagnosis if ground truth needed
- ✋ After analysis for approval

**Resume rule:** Upon user approval, proceed directly to next step without re-asking.
```

---

## Sub-Skills, References, and Modularity

**Modularity is optional.** Many skills work perfectly as a single file.

### When to Keep It Simple

Keep everything in one SKILL.md when:
- The workflow is linear (no major branches)
- Total content is under ~500 lines
- The task has a single clear purpose
- Steps are sequential without complex routing

**Example:** A skill that runs a script, validates output, and reports results—this doesn't need splitting.

### Two Approaches to Modularity

When content grows, you have two options:

**Option A: References (`references/`)** - For documentation/context
- Use when: Detailed information Cortex Code should reference while working
- Examples: schemas, API docs, domain knowledge, detailed guides
- Loaded on-demand, keeps SKILL.md lean

```
my-skill/
├── SKILL.md
└── references/
    ├── aws.md        # Loaded when user chooses AWS
    ├── gcp.md        # Loaded when user chooses GCP
    └── schemas.md    # Loaded when needed
```

**Option B: Sub-Skills** - For distinct workflows
- Use when: Different intents require completely different step-by-step workflows
- Examples: CREATE vs DEBUG vs OPTIMIZE modes
- Each sub-skill is a complete workflow

```
my-skill/
├── SKILL.md          # Intent detection + routing
├── create/SKILL.md   # Full workflow for CREATE
└── debug/SKILL.md    # Full workflow for DEBUG
```

### Single Intent Table

Keep routing logic in one place. If a skill routes to sub-skills, use a single intent table rather than scattering routing decisions. This prevents drift when routing logic needs updates.

### When to Split

Consider splitting when:
- Content exceeds ~500 lines
- A workflow has 3+ distinct branches with 3+ steps each
- The logic is reusable across multiple parent skills
- Different user intents require completely different workflows

### Sub-Skill Structure

Sub-skills include a parent reference:

```markdown
---
name: specific-task
description: [Description]
parent_skill: main-skill
---

# Specific Task

## When to Load
[Main skill] Step X: After [condition]

## Prerequisites
- [What should already be done]

## Workflow
[Specific steps]

## Output
[What this produces]

## Next Skill
If [condition] → Load `next-skill.md`
```

### Loading Sub-Skills

In the parent skill:

```markdown
**If user selects Option A:**
1. **Load** `sub-skill-a/SKILL.md`
2. Follow the sub-skill workflow
3. After completion, return here for next steps
```

### Validating Modular Skills (CYOA Analysis)

Modular skills form a **soft state machine**—a directed graph where states (files/sections) connect via transitions (routing decisions). Unlike deterministic code, transitions are interpreted by a language model, making structural clarity critical.

The "Choose Your Own Adventure" (CYOA) analogy captures this: readers navigate through pages based on choices, and poorly designed books have unreachable pages or dead ends. The same problems occur in modular skills.

**State Machine Properties to Validate:**

| Property | Good State | Bad State |
|----------|------------|-----------|
| **Reachability** | Every reference is loadable from the router | Orphaned files no route leads to |
| **Determinism** | Each decision point has defined outcomes | Ambiguous or missing routing for some intents |
| **Termination** | Clear halting states (success, user choice, error) | Paths that trail off without direction |
| **Transition clarity** | Active voice: "Load X", "Continue to Y" | Passive: "return to...", "see also..." |
| **Loop bounds** | Retry logic has max attempts or timeout | Infinite loops with no escape |

**Running CYOA Analysis:**

For complex modular skills, trace the graph:

1. Start at the router (SKILL.md) and identify all routing targets
2. For each target, trace decision points and their outcomes
3. Verify every path reaches a halting state
4. Check transitions use directive language with explicit targets

**Valid Halting States:**

| Type | Example |
|------|---------|
| Success | "Setup complete. Ready for operations." |
| User choice | "Multiple options found. Which do you prefer?" |
| Error escalation | "Cannot proceed. Contact administrator." |
| Return to caller | "Continue to connector-main.md Step 5." |

**Transition Language:**

Prefer active, directive language that tells the agent exactly what to do:

```markdown
# Good (directive)
**Continue** to `references/setup-auth.md` to configure authentication.

# Bad (passive, ambiguous)
Return to the setup workflow when done.
```

---

## Advanced Skill Patterns

### When to Use Agent Teams

For long-running, complex tasks involving multiple distinct phases or parallel workstreams, use **agent teams** via the `ctx-workflow` skill instead of a single monolithic skill.

**Signs you need agent teams:**
- Task takes >10 minutes to complete
- Multiple independent subtasks that could run in parallel
- Different phases require different expertise/context
- Workflow has natural handoff points between stages

**Architecture:**
```
Coordinator (thin, <200 lines)
  ├─ Specialist Agent 1 → does one thing well
  ├─ Specialist Agent 2 → different expertise
  ├─ Critic Agent → validates outputs
  └─ File-based gate (state.json) → survives context overflow
```

Note: Agents cannot spawn other agents. The coordinator spawns all specialists and critics as peers.

**Reference:** Load `ctx-workflow` skill for agent team orchestration patterns.

### Cost and Runtime Awareness

For skills involving expensive operations (large queries, API calls, model inference), warn users before executing.

**Pattern:** Add a stopping point before expensive operations that explains the scope:

```markdown
**⚠️ STOP**: This operation will scan a large dataset.

- Scope: [describe what will be processed]
- Alternatives: [sampling, caching, narrower filter]

Proceed? (Yes/No/Narrow scope)
```

When specific cost or runtime estimates are available, include them to help users make informed decisions.

---

## Common Patterns

### Setup Pattern

```markdown
## Setup

1. **Load** `reference/concepts.md`: Required context
2. **Load** `best-practices/SKILL.md`: Required guidance

**Verify prerequisites:**
- [ ] [Prerequisite 1 is met]
- [ ] [Prerequisite 2 is met]
```

### Menu Selection Pattern

```markdown
Present menu to user:

```
Select mode:

1. Mode A - [Description]
2. Mode B - [Description]
3. Mode C - [Description]

Enter your selection (1-3):
```

**Route based on selection:**
- Option 1 → **Load** `mode-a/SKILL.md`
- Option 2 → **Load** `mode-b/SKILL.md`
- Option 3 → **Load** `mode-c/SKILL.md`
```

### Validation Pattern

```markdown
### Step N: Validate Results

**Validation Checklist:**
- ✅ [Criterion 1]
- ✅ [Criterion 2]
- ✅ [Criterion 3]

**If validation fails:**
- Return to Step [X] with error context
- Maximum 3 retry attempts

**If validation succeeds:**
- Proceed to Step [N+1]
```

### System of Record Pattern

For skills that modify persistent state:

```markdown
## System of Record

**Before modifying:**
1. Create backup/snapshot
2. Log planned changes
3. Get user approval

**After modifying:**
1. Verify changes applied
2. Update log with results
3. Present summary to user

**Directory structure:**
```
workspace/
├── log.md           # Running log of changes
├── versions/        # Snapshots before changes
└── outputs/         # Results of operations
```
```

---

## Common Pitfalls to Avoid

### 1. ❌ Vague Trigger Descriptions

```yaml
# BAD
description: "A skill for working with agents"

# GOOD
description: "Use for **ALL** requests that mention: create agent, build agent, debug agent. DO NOT attempt agent work manually - invoke this skill first."
```

### 2. ❌ Missing Stopping Points

```markdown
# BAD
### Step 3: Apply Changes
Apply all the changes identified above.

# GOOD
### Step 3: Apply Changes
**⚠️ MANDATORY CHECKPOINT**: Present changes to user for approval before applying.
```

### 3. ❌ Unclear Tool Usage

```markdown
# BAD
Run the script to do the thing.

# GOOD
```bash
uv run --project /path/to/skill python /path/to/skill/scripts/tool.py \
  --param1 value1 \
  --param2 value2
```
```

### 4. ❌ Overly Complex Single Files

```markdown
# BAD
One 500-line skill file with multiple unrelated workflows crammed together

# GOOD (Option A - Split if complex)
Main skill (100 lines) + sub-skills for distinct branches

# ALSO GOOD (Option B - Keep simple if linear)
Single 150-line skill with a clear, linear workflow
```

**Note:** Not every skill needs sub-skills. A focused, linear workflow works great in one file.

### 5. ❌ No Error Handling Guidance

```markdown
# BAD
Step 3: Execute the command.

# GOOD
Step 3: Execute the command.

**If error occurs:**
- Error X: [How to handle]
- Error Y: [How to handle]
- Unknown error: Ask user for guidance
```

### 6. ❌ Chaining Without Approval

```markdown
# BAD
After identifying issues, immediately apply fixes.

# GOOD
After identifying issues:
1. Present findings to user
2. **⚠️ Wait for explicit approval**
3. Only then apply fixes
```

### 7. ❌ Fabricated Commands

Never include commands that haven't been tested. Plausible-sounding but non-existent commands waste time and erode trust.

```markdown
# BAD
Generate a token using: snow session token --format JSON  # untested

# GOOD
If no token is available, ask the user how they authenticate.
```

### 8. ❌ Unverified Assertions

Use flexible language when uncertain and definitive language only when verified. Products evolve; stating "you must use X" becomes incorrect when new options are added.

```markdown
# BAD
On BYOC deployments, you must configure key-pair authentication.

# GOOD
Key-pair is a common BYOC authentication strategy. Other options may be available.
```

### 9. ❌ Duplicated Content

Information should live in exactly one place. Duplicated examples or instructions become stale when the source changes.

```markdown
# BAD
See `other-skill` for details. Quick reference: [copy of other-skill content]

# GOOD
See `other-skill` for details.
```

---

## Quality Red Flags

These patterns indicate a skill needs attention. Use this checklist when auditing skills.

| Flag | Issue | Severity | Why It's Bad |
|------|-------|----------|--------------|
| F1 | Lines > 500 | High | Agent loses track of earlier instructions |
| F2 | Router > 200 lines | High | Routers should be thin; move logic to sub-skills |
| F3 | No frontmatter | High | Skill discovery relies on name + description |
| F4 | Vague description (<20 chars) | High | Skill won't trigger reliably |
| F5 | >5 sub-rules in one step | Medium | Agent drops rules when overloaded |
| F6 | "for EACH file" without tracking | Medium | Files missed; use file-based state |
| F7 | State in LLM text only | Medium | Context overflow loses progress |
| F8 | No stopping points | Medium | Agent chains without approval |
| F9 | Contradictory rules | Medium | Nondeterministic behavior |
| F10 | Scripts miss patterns agent must catch | Low | Detection gaps |
| F11 | No evals exist | Low | Can't measure skill value |

### Severity Ratings

| Verdict | Criteria |
|---------|----------|
| **Critical** | Any High flag AND in production |
| **Needs-Work** | Any High flag (non-prod), OR 2+ Medium |
| **Acceptable** | 1 Medium or Low flags only |
| **Good** | No flags |

### File-Based State Pattern

For skills processing multiple files or multi-phase workflows:

**Don't**: Keep state in LLM memory ("I've processed files A, B, C...")
**Do**: Write state to a JSON file after each step

```json
{
  "manifest": ["file1.py", "file2.py"],
  "processed": {"file1.py": "done"},
  "current": "file2.py"
}
```

The coordinator reads this at the start of each turn. If context overflows, work resumes from last checkpoint.

---

## Example: Complete Skill

Here's a complete example of a well-structured skill:

```markdown
---
name: example-workflow
description: "Completes example tasks with structured guidance. Use when: user wants a demo workflow or example task. Triggers: example task, demo workflow."
---

# Example Workflow

## Setup

1. **Load** `references/concepts.md` if detailed context needed
2. **Verify** prerequisites are met

## Prerequisites

- Access to required resources
- Configuration file exists at expected location

## Workflow

### Step 1: Gather Information

**Goal:** Collect required inputs from user

**Actions:**

1. **Ask** user for configuration:
   ```
   Please provide:
   - Name: [identifier for this task]
   - Target: [where to apply changes]
   ```

2. **Validate** inputs are complete

**Output:** Validated configuration

### Step 2: Analyze Current State

**Goal:** Understand what exists before making changes

**Actions:**

1. **Execute** analysis:
   ```bash
   uv run python scripts/analyze.py --target TARGET_NAME
   ```

2. **Present** findings to user

**⚠️ MANDATORY STOPPING POINT**: Get user confirmation before proceeding.

### Step 3: Apply Changes

**Goal:** Make the requested modifications

**Actions:**

1. **Apply** changes:
   ```bash
   uv run python scripts/apply.py --target TARGET_NAME --changes CHANGES
   ```

2. **Verify** changes applied correctly

**Output:** Modified resource

## Tools

### Tool 1: analyze.py

**Description**: Analyzes target resource state
**Parameters**:
- `--target`: Resource identifier

### Tool 2: apply.py

**Description**: Applies changes to resource
**Parameters**:
- `--target`: Resource identifier
- `--changes`: Changes specification

## Stopping Points

- ✋ After Step 2 analysis (for approval)
- ✋ After Step 3 if validation fails

## Success Criteria

- ✅ Resource modified correctly
- ✅ No errors during execution
- ✅ User confirmed satisfaction

## Output

Modified resource at specified location with change log.

## Troubleshooting

**Error: Resource not found**
- Verify target identifier is correct
- Check access permissions

**Error: Validation failed**
- Review changes specification
- Retry with corrected inputs
```

---

## Quick Reference Checklist

When creating a new skill, verify:

**Conciseness:**
- [ ] SKILL.md is under 500 lines
- [ ] Only essential information included (Cortex Code is already smart)
- [ ] Detailed content moved to references/ if needed
- [ ] No extraneous docs (README.md, CHANGELOG.md, etc.)

**Frontmatter:**
- [ ] Has `name` and `description`
- [ ] Description includes what it does + when to use + trigger keywords
- [ ] Name doesn't conflict with existing skills in target repository

**Workflow:**
- [ ] Steps are numbered and clear
- [ ] Appropriate degree of freedom (high/medium/low) for each step
- [ ] Mandatory stopping points marked with ⚠️
- [ ] No chaining actions without user approval

**Tools/Scripts (if applicable):**
- [ ] Scripts documented with usage examples
- [ ] Dependency management (`pyproject.toml` with uv)
- [ ] Absolute paths used for `uv run`

**Structure:**
- [ ] Assets in `assets/` if templates/images needed
- [ ] References in `references/` for detailed docs
- [ ] Sub-skills only for distinct workflow branches

**Production readiness:**
- [ ] `prod_manifest.yaml` entry added (with appropriate `channel`)
- [ ] Subset manifests considered: add to `prod_manifest_snowsight.yaml` (Snowsight) and/or `prod_manifest_desktop.yaml` (CoCo Desktop) if the skill should ship on those surfaces
- [ ] If shipping to production (`channel: prod`): [Bundled Skills](https://docs.snowflake.com/en/user-guide/cortex-code/bundled-skills) page updated via PR in snowflake-prod-docs repo
