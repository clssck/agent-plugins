## Expansion Technology Selection

You're continuing with your existing technology. Tell us which one you're using so we can generate a plan that matches your current patterns.

### Instructions

1. Present the question: "Which technology is your existing pipeline using?"
2. Show all 7 options.
3. Record the response as `selected_transform_technology`.


### Configuration Questions

#### Confirm your selected transformation technology. (`selected_transform_technology`: single-select)
**What is this asking?**
Confirm the transformation technology you will implement. The recommendation engine has scored all technologies against your requirements and presented a ranked recommendation above. You can accept the top recommendation or override it by selecting a different option.

**Why does this matter?**
This is the final decision point before implementation guidance begins. Once confirmed, the system will provide technology-specific next steps, architecture patterns, sample code, and deployment instructions tailored to your selected technology. Selecting a technology different from the recommendation is allowed — the system will note the trade-offs but proceed with your choice.

**Options explained:**
- **Dynamic Tables**: Best for declarative SQL transformations where you want Snowflake to manage refresh timing, dependency ordering, and incremental processing automatically. Zero orchestration code. Requires that all logic can be expressed as a single SQL SELECT.
- **Streams and Tasks**: Best for event-driven pipelines where you need fine-grained control over execution triggers, row-level error handling, or conditional processing logic. Ideal for CDC patterns and pipelines that must react to specific data changes.
- **Snowpark**: Best for Python/Scala transformations that require ecosystem libraries, ML feature engineering, external API calls, or DataFrame-style processing. Runs on Snowflake compute with full access to Python packages.
- **dbt Projects on Snowflake**: Best for SQL transformations that benefit from testing, documentation, modular references, and CI/CD practices. Deployed natively in Snowflake, orchestrated by Tasks. No external infrastructure required.
- **dbt Core (External)**: Best when you already have dbt Cloud or an external orchestrator (Airflow, Dagster) and want dbt's full feature set with external CI/CD integration. Requires infrastructure outside Snowflake.
- **dbt + Dynamic Tables**: Best when you want dbt's software engineering practices (tests, docs, refs) combined with Dynamic Tables' automatic refresh management. dbt defines the transformations; Snowflake handles the orchestration.
- **Stored Procedures**: Best for complex procedural logic with control flow, error handling, retries, and multi-step transactions. Supports both SQL and Python. Ideal when transformation logic cannot be expressed declaratively.

**Overriding the recommendation:**
You can select any technology regardless of the recommendation. If your selection conflicts with a constraint you identified earlier, the system will flag the conflict and explain the implications, but will still proceed with your choice.

**More Information:**
* [Data Pipeline Best Practices](https://docs.snowflake.com/en/guides/getting-started-data-pipelines) — Snowflake pipeline patterns
* [Dynamic Tables](https://docs.snowflake.com/en/user-guide/dynamic-tables-about) — Declarative pipelines
* [Streams and Tasks](https://docs.snowflake.com/en/user-guide/streams) — Event-driven processing
* [Snowpark](https://docs.snowflake.com/en/developer-guide/snowpark/python/index) — Python transformations
* [dbt on Snowflake](https://docs.snowflake.com/en/developer-guide/dbt/dbt-overview) — dbt integration
**Options:**
- Dynamic Tables
- Streams and Tasks
- Snowpark
- dbt Projects on Snowflake
- dbt Core (External)
- dbt + Dynamic Tables
- Stored Procedures

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
