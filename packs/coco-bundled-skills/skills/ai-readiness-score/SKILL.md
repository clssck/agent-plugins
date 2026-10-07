---
name: ai-readiness-score
description: >
  Measure AI readiness for this Snowflake account. Scores Consumption-Ready (CR)
  tables, Semantic View (SV) coverage and quality, and demand coverage. Generates
  an HTML scorecard report with recommendations. Runs in Snowsight (notebook) or
  CLI mode (direct SQL), auto-detected by environment. Caches results for fast reruns.
  Use when: AI readiness, readiness score, how AI-ready am I, measure my ai readiness,
  semantic view coverage, Semantic View (SV) quality, Consumption-Ready (CR) tables,
  demand coverage, CR tables, AI readiness report, score my account.
---

# AI Readiness Score — Dispatcher

This skill measures your account's AI readiness. It has two execution modes
depending on how it was invoked:

| Mode | Environment | What happens |
|------|-------------|--------------|
| **Snowsight** | Snowsight Workspaces CoCo UI | Builds and runs a notebook, generates an HTML report |
| **CLI** | CoCo CLI (terminal) | Runs SQL directly, outputs scores and generates an HTML report |

---

## Environment Detection

Determine which mode to use based on the following signals:

- **Snowsight Workspace** — System reminders mention "Current workspace:" or the
  skill was loaded from a path containing `/snowflake/stages/`.
- **Snowsight non-workspace** — The `get_page_context` tool is in the tool list,
  but there is no "Current workspace:" reminder and no `/snowflake/stages/` path.
  The user is on a Snowsight page (home, catalog, etc.) but not in a Workspace.
- **CoCo CLI** — The `get_page_context` tool is not in the tool list.

**Decision rule (check in this order):**

1. If there is a "Current workspace:" system reminder or the skill was loaded from
   a path containing `/snowflake/stages/` → **Snowsight Workspace mode**
2. If the `get_page_context` tool is available in the tool list → **Snowsight non-workspace**
   - Use the `snowsight_navigate` tool with `route: "workspaces"` to prompt the user
     to switch to a Workspace.
   - Print: "This skill creates a notebook to run the analysis. Navigating to Workspaces..."
   - Once the user is in a Workspace, proceed with **Snowsight Workspace mode**.
   - If the user skips/declines navigation, print:
     > "The AI Readiness Score skill requires a Workspace to create and run the
     > analysis notebook. Please navigate to a Workspace and re-trigger the skill
     > when you're ready."
   - Stop execution.
3. If `get_page_context` is not in the tool list → **CLI mode**

---

## Routing

Once you have determined the mode, read the corresponding sub-skill file from the
skill directory (the same directory this file lives in) and follow its instructions.

### If Snowsight Workspace mode:

Read the file `skill-snowsight.md` from the skill directory and follow all its phases.

### If CLI mode:

Read the file `skill-cli.md` from the skill directory and follow all its phases.

---

## Shared Components

Both modes share the same `scripts/` directory:

| File | Purpose |
|------|---------|
| `scripts/build_notebook.py` | Builds the .ipynb notebook (Snowsight only) |
| `scripts/notebook_cells.py` | Cell content definitions (Snowsight only) |
| `scripts/cr_tables.sql` | CR table scoring query |
| `scripts/sv_quality.sql` | SV quality scoring query |
| `scripts/recommendations.py` | Builds recommendation text from scores |
| `scripts/report.py` | Renders the HTML report |
