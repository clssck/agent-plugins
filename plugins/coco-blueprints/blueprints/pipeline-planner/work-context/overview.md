## Getting Started

This is the entry point for the Data Transformation Technology Selector. Before we can recommend the right technology for your workload, we need to understand your starting point.

### Two Paths

- **Extend Existing** — You already have a transformation pipeline running in Snowflake and want to add to it. This path is faster: typically 2–3 questions before a recommendation.
- **Build New** — You're building a transformation pipeline from scratch (or evaluating a fundamentally different approach). This path walks through your full requirements to compare all available technologies.

### Why This Matters

Expansion users benefit from continuity — staying within a proven technology reduces risk and speeds delivery. Net-new users need a thorough evaluation because the wrong technology choice compounds over the life of the pipeline.

There is no "unsure" option. If you're uncertain whether your work extends an existing project, choose **Build New** — it's the safe default that ensures nothing is missed.


### Configuration Questions

#### Are you extending an existing pipeline, or building something new? (`work_context`: single-select)
**What is this asking?**
Determine whether you are adding to or modifying a data transformation pipeline that is already running in production, or creating an entirely new transformation pipeline from scratch.

**Why does this matter?**
This is the first routing decision in the recommendation engine. If you are extending an existing pipeline, the system will identify your current technology and help you decide whether to continue with it or evaluate alternatives. If you are building new, the system evaluates all available technologies against your requirements without any prior technology bias.

**Options explained:**
- **Extend Existing**: You have a pipeline already running in Snowflake (Dynamic Tables, dbt project, Streams+Tasks, Stored Procedures, or Snowpark jobs) and want to add new transformations, modify existing logic, or expand its scope. The system will identify your project and ask whether to continue with the same technology or evaluate alternatives.
- **Build New**: You are creating a new transformation pipeline from scratch. There is no existing pipeline to extend, or you want to treat this as a greenfield effort regardless of what else exists in the account. The system will evaluate all technologies against your requirements.

**When in doubt, choose "Build New"** — it is the safe default that ensures a thorough evaluation of all options. Choose "Extend Existing" only when you have a specific pipeline you want to add to.

**More Information:**
* [Dynamic Tables](https://docs.snowflake.com/en/user-guide/dynamic-tables-about) — Declarative transformation pipelines
* [Streams and Tasks](https://docs.snowflake.com/en/user-guide/streams) — Change data capture and scheduling
* [dbt on Snowflake](https://docs.snowflake.com/en/developer-guide/dbt/dbt-overview) — dbt Projects deployed natively
**Options:**
- Extend Existing
- Build New
