## Identify Your Project

This step identifies which existing project you're expanding. Describe what you're currently working with so we can tailor our guidance.

### What to Include

- The technology your pipeline uses today (Dynamic Tables, dbt, Streams + Tasks, Stored Procedures, etc.)
- The project or pipeline name, if applicable
- A brief description of what the pipeline does

### How This Shapes Recommendations

Your existing technology choice and project context determine whether to continue with the same approach or evaluate alternatives. Projects with established patterns, deployment processes, and team familiarity benefit from consistency — but sometimes a new use case genuinely calls for a different tool.


### Configuration Questions

#### What pipeline or project are you expanding? (`expand_target_project`: text)
**What is this asking?**
Describe the existing pipeline or project you want to expand. Include what the project does, what technology it uses, and where it lives in Snowflake.

**Why does this matter?**
Identifying your existing project allows the system to determine the current technology in use and provide appropriate next steps. If you are using Dynamic Tables, the guidance will differ from a dbt project or a Streams+Tasks pipeline. Knowing the project context also helps determine whether continuing with the same technology or evaluating alternatives makes more sense.

**How to describe your project:**
Be as specific as possible. Include the technology, database/schema location, and what the pipeline does. Examples:
- "My dbt project in analytics_db that transforms raw Salesforce data into reporting tables"
- "The Dynamic Tables in the REPORTING schema that aggregate daily sales metrics"
- "The Streams+Tasks pipeline in RAW_DB.PROCESSING that processes incoming order events"
- "A set of Stored Procedures in FINANCE.ETL that run nightly close calculations"
- "The Snowpark jobs in DATA_SCIENCE schema that generate ML feature tables"

**What happens next:**
Based on your description, the system will identify the technology and ask whether you want to continue building with the same approach or evaluate whether a different technology might be better suited for your new requirements.

**More Information:**
* [SHOW DYNAMIC TABLES](https://docs.snowflake.com/en/sql-reference/sql/show-dynamic-tables) — List existing Dynamic Tables
* [SHOW TASKS](https://docs.snowflake.com/en/sql-reference/sql/show-tasks) — List existing Tasks
* [SHOW PROCEDURES](https://docs.snowflake.com/en/sql-reference/sql/show-procedures) — List existing Stored Procedures

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
