---
name: databricks-setup
description: >
  Install, update, and manage the Databricks AI Dev Kit skills for Cortex Code.
  Handles prerequisites, installer execution, and profile management.
  Use when: install databricks skills, set up databricks tools, setup databricks,
  update ai dev kit, databricks ai dev kit, databricks setup, dev kit install,
  add databricks skills, reinstall databricks tools, change skill profile,
  list available skills.
---

# Databricks Skills Setup

Install the Databricks AI Dev Kit skills into Cortex Code.

## Critical: Cortex Code Compatibility

The AI Dev Kit installer does not natively support Cortex Code. Cortex Code is
compatible with Claude Code's skill format, so we pass `--tools claude` to the
installer.

## Prerequisites

Before running the installer, verify these are available:

| Tool | Check | Install |
|------|-------|---------|
| `git` | `git --version` | Pre-installed on most systems |
| `curl` | `curl --version` | Pre-installed on most systems |
| `uv` | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Databricks CLI ≥0.278.0 | `databricks --version` | See `databricks-cli-install` skill |

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

If the **Databricks CLI** is missing, outdated (below 0.278.0), or auth is not configured,
**STOP — invoke the `databricks-cli-install` skill** to install/update the CLI and configure
authentication. Then return here to continue with Step 2.

Verify Databricks auth is configured:
```bash
databricks auth token
```

If auth fails, **STOP — invoke the `databricks-cli-install` skill** (Step 4: Configure Authentication).

### Step 2: Determine Install Options

**>>> STOPPING POINT: Ask the user these questions <<<**

1. **Scope**: Global (all projects) or project-local (current directory only)?
   - Global installs skills to `~/.claude/skills/`
   - Project installs to `./.claude/skills/`
   - **Recommend global** for most users

2. **Databricks profile**: Which Databricks CLI profile to use?
   - Run `databricks auth profiles` to show available profiles
   - Default is `DEFAULT`

3. **Skill profile**: Which set of skills to install?

| Profile | Description |
|---------|-------------|
| `all` | Every available skill (34 skills) |
| `data-engineer` | Pipelines, ETL, Spark, streaming, jobs |
| `analyst` | SQL, dashboards, Genie, metric views |
| `ai-ml-engineer` | Model serving, vector search, agents, MLflow |
| `app-developer` | Databricks Apps, Lakebase, APX |
| Custom | Pick individual skills from the list |

To see all available skills:
```bash
bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) --list-skills
```

### Step 3: Run the Installer

Build and run the install command based on the user's choices.

**Template** (non-interactive):
```bash
bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) \
  --tools claude \
  --profile <DATABRICKS_PROFILE> \
  --skills-profile <SKILL_PROFILE> \
  <SCOPE_FLAG> \
  --force \
  --silent
```

Where:
- `--tools claude` — **Required**. Tells the installer to use Claude Code format (compatible with Cortex Code)
- `--profile <NAME>` — Databricks CLI profile (default: `DEFAULT`)
- `--skills-profile <PROFILE>` — One of: `all`, `data-engineer`, `analyst`, `ai-ml-engineer`, `app-developer`
- `<SCOPE_FLAG>` — Use `--global` for global install, omit for project-local
- `--force` — Overwrite existing installation
- `--silent` — Skip interactive prompts

For **custom skill selection**, replace `--skills-profile` with `--skills`:
```bash
--skills "databricks-config,databricks-docs,databricks-jobs,databricks-dbsql"
```

**Examples**:

Global install with all skills, DEFAULT profile:
```bash
bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) \
  --tools claude --profile DEFAULT --skills-profile all --global --force --silent
```

Project-local install for data engineers:
```bash
bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) \
  --tools claude --profile DEFAULT --skills-profile data-engineer --force --silent
```

Run the command and verify it completes successfully.

### Step 4: Verify Installation

Run these checks to confirm the installation succeeded:

1. **Skills installed**:
```bash
# Global
ls ~/.claude/skills/databricks-*/SKILL.md 2>/dev/null | wc -l
# Project
ls .claude/skills/databricks-*/SKILL.md 2>/dev/null | wc -l
```

2. **Databricks auth works** (via the configured profile):
```bash
databricks auth token --profile <DATABRICKS_PROFILE>
```

**>>> STOPPING POINT: Report results to the user <<<**

Present a summary:
- Number of skills installed
- Auth status
- If anything failed, provide remediation steps

Suggest: "Try asking me a Databricks question to verify the skills work"

## Update / Reinstall

To update an existing installation, re-run the installer with `--force`:
```bash
bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) \
  --tools claude --profile <PROFILE> --skills-profile <PROFILE> --global --force --silent
```

## Available Skills Reference

**Core** (always installed): databricks-config, databricks-docs, databricks-python-sdk, databricks-unity-catalog

**Databricks skills**: databricks-agent-bricks, databricks-ai-functions, databricks-aibi-dashboards, databricks-app-python, databricks-bundles, databricks-dbsql, databricks-genie, databricks-iceberg, databricks-jobs, databricks-lakebase-autoscale, databricks-lakebase-provisioned, databricks-metric-views, databricks-mlflow-evaluation, databricks-model-serving, databricks-spark-declarative-pipelines, databricks-spark-structured-streaming, databricks-synthetic-data-gen, databricks-unstructured-pdf-generation, databricks-vector-search, databricks-zerobus-ingest, spark-python-data-source

**MLflow skills**: agent-evaluation, analyze-mlflow-chat-session, analyze-mlflow-trace, instrumenting-with-mlflow-tracing, mlflow-onboarding, querying-mlflow-metrics, retrieving-mlflow-traces, searching-mlflow-docs

**APX skills**: databricks-app-apx

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `uv: command not found` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` then restart shell |
| `databricks: command not found` | Invoke the `databricks-cli-install` skill |
| CLI version too old | Invoke the `databricks-cli-install` skill to update |
| Auth token fails | Invoke the `databricks-cli-install` skill (Step 4: Configure Authentication) |
| Skills not detected by Cortex | Verify files exist under `~/.claude/skills/` (global) or `.claude/skills/` (project) |
| Installer hangs | Use `--silent` flag to skip interactive prompts |

## Stopping Points

- **Step 1**: If Databricks CLI is missing, outdated, or auth fails — delegate to `databricks-cli-install` skill
- **Step 2**: Ask user for scope, Databricks profile, and skill profile before proceeding
- **Step 4**: Present verification results

## Output

Present the final status to the user:
- What was installed (skills count, profile used)
- Scope (global vs project)
- Databricks profile configured
- Any warnings or manual steps remaining
- Suggest: "Try asking me a Databricks question to verify the skills work"
