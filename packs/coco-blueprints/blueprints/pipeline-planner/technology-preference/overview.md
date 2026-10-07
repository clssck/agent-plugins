## Technology Preference

This step determines whether you have existing technology needs or constraints that should influence the recommendation.

### How It Works

- **No Preference**: The engine recommends based purely on your requirements — freshness, logic type, trigger model, consumers, and constraints. This produces the most unbiased recommendation.

- **Yes — I Have Existing Needs**: You describe your existing technology stack, organizational standards, or specific constraints in a follow-up. The system maps your response to known technologies and applies a boost (+25 points) to matching Snowflake technologies. This also captures signal about external tools (Airflow, Databricks, Spark, etc.) that may influence ecosystem-match scoring (+10 points).

### When to Select "No Preference"

Select this if:
- You genuinely don't have a leaning toward any specific technology
- You want the engine to recommend based purely on your requirements
- You're exploring options and want an unbiased recommendation

### When to State Existing Needs

State existing needs if:
- Your team has existing expertise in a technology
- You have organizational standards or guidelines
- You are running external tools (Airflow, Databricks, Informatica, etc.) that constrain your options
- You want to validate whether your current stack aligns with the data-driven recommendation

### Important

Existing technology needs cannot override a hard veto from constraints. If your stack conflicts with a constraint, the system explains why and recommends the next best option.


### Configuration Questions

#### Do you have existing technology needs or constraints? (`technology_preference`: single-select)
**What is this asking?**
Indicate whether you have pre-existing technology needs, constraints, or preferences that should influence the recommendation. If you select "Yes," you will be asked to describe your existing technology stack in a follow-up question.

**Why does this matter?**
Team familiarity, organizational standards, existing tooling investments, and ecosystem dependencies are all valid reasons to prefer a technology. The recommendation engine respects these by boosting matching technologies in the scoring. However, existing preferences cannot override hard constraints — if your preference conflicts with a requirement (e.g., you prefer Dynamic Tables but need Python processing), the system will explain the conflict and suggest the next best option.

**Options explained:**
- **No Preference**: Let the engine recommend based purely on your requirements. Best when you are open to any technology and want an unbiased recommendation.
- **Yes — I Have Existing Needs**: You have an existing technology stack, organizational standards, or specific constraints you want factored into the recommendation. You will be asked to describe these in a follow-up, which gives us signal on what technologies you are running — including tools outside Snowflake (Airflow, Databricks, Spark, Informatica, etc.).

**More Information:**
* [Transformation Options](https://docs.snowflake.com/en/guides/getting-started-data-pipelines) — Overview of Snowflake pipeline technologies
* [Dynamic Tables Overview](https://docs.snowflake.com/en/user-guide/dynamic-tables-about) — When to use Dynamic Tables
* [dbt Materializations](https://docs.getdbt.com/docs/build/materializations) — dbt materialization strategies
**Options:**
- No Preference
- Yes — I Have Existing Needs

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
