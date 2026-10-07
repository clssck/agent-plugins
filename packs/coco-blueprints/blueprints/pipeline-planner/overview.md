# Pipeline Planner

Collect pipeline requirements through structured discovery to identify the right Snowflake transformation technology

The Pipeline Planner collects your pipeline requirements through structured
discovery and produces an answers file — the contract for downstream tooling.

**What You Will Answer (3-10 questions depending on path):**
- Whether you're extending an existing pipeline or building new
- If extending with same tech: your technology, freshness, and consumers
- If building new or evaluating alternatives: full requirements and technology scoring
- Your source data reference and transformation intent

**Technologies Evaluated:**
- Dynamic Tables
- Streams & Tasks
- Snowpark
- dbt Projects on Snowflake (native)
- dbt Core (external)
- dbt + Dynamic Tables (combination)
- Stored Procedures

**Two Entry Paths:**
- **Expansion** — Extending an existing pipeline with the same technology? Fast-track through 3 questions.
- **Net-New / Evaluate** — Full requirements discovery and technology scoring.

**Output:**
An answers file containing all your pipeline requirements and technology selection.
Feed this file to the `pipeline-plan-generator` skill to produce an implementation plan.

