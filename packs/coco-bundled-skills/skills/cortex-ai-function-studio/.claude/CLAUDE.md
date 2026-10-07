<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Cortex AI Function Studio

A Cortex Code skill for the full lifecycle of custom AI functions: **create → evaluate → optimize**.

## Project Structure

```
SKILL.md                     # Main entry point — routes to sub-skills by intent
create/                      # Create AI functions (Direct or [research preview] Agent Research mode)
evaluate/                    # Evaluate against labeled data with metrics
optimize/                    # Function body optimization + model selection via GEPA optimizer
demos/                       # Interactive walkthroughs (redaction, classification, insurance routing)
references/                  # Shared reference docs loaded by sub-skills
src/                         # Python CLI tools, modules, and Jinja2 templates (run via uv / uploaded to Snowflake stage)
tests/                       # pytest suite — full round-trip e2e against Snowflake
```

## Key Concepts

- **AI Functions** are `LANGUAGE SQL` UDFs wrapping `AI_COMPLETE`. The body is a single SQL expression (not a statement block). Use `ARRAY_CONSTRUCT()` not `[...]`, `OBJECT_CONSTRUCT()` not `{...}`, and `PARSE_JSON('...')` for response_format.
- **Two creation modes**: Direct (simple AI_COMPLETE call) and [research preview] Agent Research (research approaches, propose SQL UDF structures with pre/post-processing).
- **Evaluate** uses a Python stored procedure (`EVALUATE_AI_FUNCTION`) that scores function output against labeled data. Metrics: `exact_match`, `fuzzy_match`, `contains_match`, `redaction_match`, `llm_judge`, or custom UDFs.
- **Optimize** uses `OPTIMIZE_AI_FUNCTION` (powered by GEPA) for iterative function body optimization. Runs multiple models concurrently. Results filtered to Pareto-optimal options (quality vs cost).
- **Async execution** available for both evaluate and optimize via Snowflake Tasks (`*_ASYNC` SPROCs).

## Running Scripts

All Python scripts require `uv` and are run from the skill directory:

```bash
PYTHONPATH=<SKILL_DIR>/src uv run --project <SKILL_DIR> python <SKILL_DIR>/src/<script>.py [args]
```

## Running Tests

See `tests/README.md` for prerequisites and usage (`make test`, `make test CONNECTION=my_conn`).

## Dependencies

- Python >=3.12,<3.13
- `snowflake-connector-python`, `snowflake-snowpark-python`
- `gepa` (optimization engine)
- `jinja2` (SPROC template rendering)
- `pandas`, `numpy`, `datasets`

## Skill Packaging

- `.skillignore` excludes dev-only files (tests, Makefile, dev/, .venv, uv.lock)
- `make copy COPY_DEST=/path` exports git-tracked files minus skillignore entries
- `make zip` creates a dated+hashed archive

## Python Style

Follow the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) for all Python code. This includes docstring format (Google-style), naming conventions (`snake_case` for functions/variables, `CamelCase` for classes), imports ordering, and type annotations.

**Before editing any Python in this package, read `cortex-ai-function-studio/CONVENTIONS.md` in full.**

## Conventions

- Fully qualified Snowflake names everywhere: `DB.SCHEMA.OBJECT`
- Function names in SCREAMING_SNAKE_CASE
- All SPROCs wrapped in query tags (see `references/query_tag.md`)
- Demo objects use `DEMO_` prefix
- Optimization experiments: `{FUNCTION_NAME}_OPT_EXP`
- Evaluation experiments: per-evaluation, named after the `run_id` (e.g., `ai_func_eval_{FUNCTION_NAME}_{ts_ms}`); single run inside is named `EVAL`. Per-row eval details live at `snow://experiment/{experiment_name}/versions/EVAL/eval_detail.json` (requires `ENABLE_EXPERIMENT_SNOWURL_READ_PATH_RESOLUTION`).
- Model prices maintained in `src/models.json` (updated via `make update-models`)
