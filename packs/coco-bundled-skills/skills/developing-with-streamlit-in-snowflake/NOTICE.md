# NOTICE

This directory contains a parent skill with two sub-skills:

- `developing-with-streamlit/` — OSS Streamlit content, **synced verbatim** from the [Streamlit](https://github.com/streamlit/streamlit) PyPI wheel under `streamlit/.agents/skills/developing-with-streamlit/`. Streamlit is licensed under the Apache License 2.0, the same license as this repository (see [LICENSE](../../LICENSE)).

  - **Source of truth**: upstream at <https://github.com/streamlit/streamlit>. Edits to this sub-skill should be made upstream, not in this repo.
  - **Sync mechanism**: `scripts/sync-streamlit-pypi-skills.py` refreshes this content from the latest published Streamlit wheel. A daily Slack nag (from the eval Jenkins orchestrator, `evals/jenkins/Jenkinsfile.orchestrator`) prompts a maintainer to run the script and open a PR when a newer release is published.
  - **Pinned version**: see `developing-with-streamlit/.synced-from-version`.

- `sf/` — Snowflake-specific scaffolds for Streamlit apps (Snowflake-wired dashboards, the Snowflake-branded theme, SiS deployment + runtime references). Skill name: `scaffolding-streamlit-in-snowflake` (the folder is shortened to `sf/` to keep paths under the Windows `MAX_PATH` ceiling for installer tooling). Authored in this repo; not derived from Streamlit's wheel.

The parent `SKILL.md` routes user prompts between the two sub-skills.
