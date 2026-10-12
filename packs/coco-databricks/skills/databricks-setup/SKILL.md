---
name: databricks-setup
description: >
  Install, update, and manage the Databricks AI Dev Kit skills for OMP.
  Handles prerequisites, installer execution, and profile management.
  Use when: install databricks skills, set up databricks tools, setup databricks,
  update ai dev kit, databricks ai dev kit, databricks setup, dev kit install,
  add databricks skills, reinstall databricks tools, change skill profile,
  list available skills.
---

# Databricks Skills Setup

Install the Databricks AI Dev Kit skills into the current project so OMP discovers them.

## Critical: OMP Compatibility

- Always pass `--tools codex` to the installer. The codex target writes skills to the
  project-local `.agents/skills/` layout, which OMP discovers natively.
- **NEVER** pass `--tools claude`, and **NEVER** create `.claude/` directories or symlinks
  from `.claude/skills/` (or any Claude path) to `.agents/skills/`. OMP does not use Claude
  discovery.
- Install **project-local** (omit `--global`). A dev/global profile is not needed.

## Prerequisites

Before running the installer, verify these are available:

| Tool | Check | Install |
|------|-------|---------|
| `git` | `git --version` | Pre-installed on most systems |
| `curl` | `curl --version` | Pre-installed on most systems |
| `uv` | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Databricks CLI ≥1.0.0 | `databricks --version` | See `databricks-cli-install` skill |

The user must also have Databricks authentication configured (see `databricks-cli-install` skill, Step 4).

## Workflow

### Step 1: Check Prerequisites

Run each check command:

```bash
git --version
curl --version
uv --version
databricks --version
```

If `uv` is missing:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

If the **Databricks CLI** is missing, outdated (below 1.0.0), or auth is not configured,
**STOP — read `skill://databricks-cli-install`** and follow it with a required minimum of 1.0.0 to install/update the CLI and configure authentication. Return here only after `databricks --version` reports 1.0.0 or newer, then continue with Step 2.

Verify Databricks auth is configured:
```bash
databricks auth token
```

If auth fails, **STOP — follow `skill://databricks-cli-install`** (Step 4: Configure Authentication).

### Step 2: Determine Install Options

**>>> STOPPING POINT: Use the `ask` tool for these choices <<<**

Scope is fixed: project-local install into `./.agents/skills/` in the current project root.
Do not offer a global install.

1. **Databricks profile**: Which Databricks CLI profile to use?
   - Run `databricks auth profiles` to show available profiles and offer them as options
   - Default is `DEFAULT`

2. **Skill profile**: Which set of skills to install?

| Profile | Description |
|---------|-------------|
| `all` | Every available skill |
| `data-engineer` | Pipelines, ETL, Spark, streaming, jobs |
| `analyst` | SQL, dashboards, Genie, metric views |
| `ai-ml-engineer` | Model serving, vector search, agents, MLflow |
| `app-developer` | Databricks Apps, Lakebase, APX |
| Custom | Pick individual skills from the list |

To see all available skills (the list changes upstream; do not rely on a fixed count):
```bash
bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) --list-skills
```

### Step 3: Run the Installer

Run from the project root. Build the command from the user's choices.

**Template** (non-interactive):
```bash
bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) \
  --tools codex \
  --profile <DATABRICKS_PROFILE> \
  --skills-profile <SKILL_PROFILE> \
  --force \
  --silent
```

Where:
- `--tools codex` — **Required**. Installs into `.agents/skills/`, which OMP discovers. Never use `--tools claude`.
- `--profile <NAME>` — Databricks CLI profile (default: `DEFAULT`)
- `--skills-profile <PROFILE>` — One of: `all`, `data-engineer`, `analyst`, `ai-ml-engineer`, `app-developer`
- No `--global` — always project-local
- `--force` — Overwrite existing installation
- `--silent` — Skip interactive prompts

For **custom skill selection**, replace `--skills-profile` with `--skills`:
```bash
--skills "databricks-config,databricks-docs,databricks-jobs,databricks-dbsql"
```

**Example** — data engineer skills, DEFAULT profile:
```bash
bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) \
  --tools codex --profile DEFAULT --skills-profile data-engineer --force --silent
```

Run the command and verify it completes successfully.

### Step 4: Verify Installation

1. **Skills installed**: use the `glob` tool with path `.agents/skills/*/SKILL.md` and count
   the results; `read` one installed `SKILL.md` to confirm its frontmatter has `name` and
   `description`.
2. **No Claude artifacts**: `glob` `.claude/**` should not contain anything created by this
   install. If the installer created `.claude/` entries or symlinks, the wrong `--tools` value
   was used — remove only what this install created and re-run with `--tools codex`.
3. **Databricks auth works** (via the configured profile):
```bash
databricks auth token --profile <DATABRICKS_PROFILE>
```

**>>> STOPPING POINT: Report results to the user <<<**

Present a summary:
- Number of skills installed (from the glob count)
- Auth status
- If anything failed, provide remediation steps

Suggest: "Try asking me a Databricks question to verify the skills work"

## Update / Reinstall

To update an existing installation, re-run the installer from the project root with `--force`:
```bash
bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) \
  --tools codex --profile <DATABRICKS_PROFILE> --skills-profile <SKILL_PROFILE> --force --silent
```

## Available Skills Reference

Representative skills (run `--list-skills` for the current list):

**Core** (always installed): databricks-config, databricks-docs, databricks-python-sdk, databricks-unity-catalog

**Databricks skills**: databricks-agent-bricks, databricks-ai-functions, databricks-aibi-dashboards, databricks-app-python, databricks-bundles, databricks-dbsql, databricks-genie, databricks-iceberg, databricks-jobs, databricks-lakebase-autoscale, databricks-lakebase-provisioned, databricks-metric-views, databricks-mlflow-evaluation, databricks-model-serving, databricks-spark-declarative-pipelines, databricks-spark-structured-streaming, databricks-synthetic-data-gen, databricks-unstructured-pdf-generation, databricks-vector-search, databricks-zerobus-ingest, spark-python-data-source

**MLflow skills**: agent-evaluation, analyze-mlflow-chat-session, analyze-mlflow-trace, instrumenting-with-mlflow-tracing, mlflow-onboarding, querying-mlflow-metrics, retrieving-mlflow-traces, searching-mlflow-docs

**APX skills**: databricks-app-apx

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `uv: command not found` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` then restart shell |
| `databricks: command not found` | Follow `skill://databricks-cli-install` |
| CLI below 1.0.0 | Follow `skill://databricks-cli-install` to update |
| Auth token fails | Follow `skill://databricks-cli-install` (Step 4: Configure Authentication) |
| Skills not detected by OMP | `glob` `.agents/skills/*/SKILL.md` in the project root; re-run with `--tools codex` if empty. Do not add Claude symlinks |
| Installer hangs | Use `--silent` flag to skip interactive prompts |

## Stopping Points

- **Step 1**: If Databricks CLI is missing, outdated, or auth fails — follow `skill://databricks-cli-install`
- **Step 2**: `ask` the user for Databricks profile and skill profile before proceeding
- **Step 4**: Present verification results

## Output

Present the final status to the user:
- What was installed (skills count, profile used)
- Location (`.agents/skills/` in the project)
- Databricks profile configured
- Any warnings or manual steps remaining
- Suggest: "Try asking me a Databricks question to verify the skills work"
