## Choose Your Approach

You've identified your existing project. Now decide how to proceed:

### Same Technology

Continue building within your current technology stack. This is the fast track — you'll receive specific guidance for expanding your pipeline using the patterns and tooling you already have in place. Best when:

- The new work has similar characteristics to what's already running
- Your team is productive with the current technology
- There's no strong signal that a different tool would be materially better

### Evaluate Alternatives

Enter the full requirements flow to compare all available transformation technologies against your specific use case. Best when:

- The new work has fundamentally different characteristics (e.g., real-time vs. batch)
- You suspect a different tool might be a better fit
- You want a data-driven comparison before committing


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

#### What do you want to do with this project? (`expand_approach`: single-select)
**What is this asking?**
Decide whether to continue building with the same technology your existing pipeline uses, or whether to evaluate alternative technologies that might be a better fit for the new work you are adding.

**Why does this matter?**
Continuing with the same technology is faster (no learning curve, consistent codebase, same deployment patterns) but may not be the best fit if your new requirements differ significantly from the original pipeline. Evaluating alternatives takes more time upfront but ensures you pick the right tool for the job rather than defaulting to what is already there.

**Options explained:**
- **Same Technology**: Continue building with the current technology. The system will provide guidance specific to extending your existing pipeline (e.g., adding new Dynamic Tables to an existing DAG, adding new dbt models to your project, adding new Tasks to your stream processing). This is the fastest path — no technology evaluation needed.
- **Evaluate Alternatives**: Check whether a different technology would be better for this specific use case. The system will run you through the full evaluation flow (freshness requirements, logic type, orchestration model, constraints) and recommend the best fit. Choose this when your new requirements feel different from what the existing pipeline handles.

**When to choose "Evaluate Alternatives":**
- Your existing pipeline is batch but the new requirement needs near-real-time freshness
- Your existing pipeline uses SQL but the new logic needs Python (ML features, API calls)
- Your current approach has scaling issues you want to avoid repeating
- You suspect a newer Snowflake feature (like Dynamic Tables) might simplify your approach

**More Information:**
* [Dynamic Tables vs Streams+Tasks](https://docs.snowflake.com/en/user-guide/dynamic-tables-about#comparison-with-streams-and-tasks) — When to use which
* [Snowpark Overview](https://docs.snowflake.com/en/developer-guide/snowpark/index) — Python/Scala transformations
**Options:**
- Same Technology
- Evaluate Alternatives

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
