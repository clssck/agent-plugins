## Define Freshness Requirements

Freshness is the strongest eliminator in technology selection. Your data freshness requirement can immediately rule out technologies that cannot meet it.

### How Freshness Eliminates Technologies

- **Continuous** (seconds to ~15 minutes) eliminates dbt Core and dbt Cloud — both are schedule-driven and cannot react to changes as they arrive. Streams & Tasks, Dynamic Tables, Snowpark (triggered by streams), and Stored Procedures all remain viable. Note that sub-minute scenarios narrow further in practice: Tasks have ~5s scheduling overhead and Dynamic Tables have 15-30s scheduling overhead for simple operations, so genuinely sub-minute freshness is realistic only for relatively simple transformations.

- **Batch** (hourly or less frequent) is the most common scenario and the most flexible requirement. All technologies handle batch well, so the decision falls to other factors like logic type, trigger model, and constraints.

### Think About the Actual Business Need

Before selecting "Continuous," consider whether the business truly requires sub-15-minute freshness or if Batch would satisfy the use case. Choosing Continuous when Batch would suffice eliminates options unnecessarily and often increases complexity and cost.


### Configuration Questions

#### How current does your transformed output need to be? (`data_freshness_requirement`: single-select)
**What is this asking?**
Define the maximum acceptable delay between when source data changes and when your transformed output reflects those changes. This is about latency tolerance — how stale can your output be before it becomes a problem?

**Why does this matter?**
Freshness requirement is the single strongest signal for technology elimination. Continuous requirements eliminate dbt (both Core and Cloud), since dbt is schedule-driven and cannot react to changes as they arrive. Batch requirements open up the widest range of options (and the simplest, most cost-effective architectures). Getting this right prevents over-engineering (building continuous pipelines when batch suffices) or under-engineering (using batch when business needs low-latency freshness).

**Options explained:**
- **Continuous**: Output must reflect source changes within seconds to ~15 minutes. Use cases include operational alerting, live dashboards, event-driven applications, fraud detection, operational reporting, monitoring dashboards, SLA tracking, and near-live analytics. Eliminates dbt Core and dbt Cloud — both are schedule-driven and cannot achieve continuous or near-continuous freshness. Streams+Tasks, Dynamic Tables, Snowpark (triggered by streams), and Stored Procedures all remain viable. Note that sub-minute scenarios narrow further in practice: Tasks have ~5 second scheduling overhead and Dynamic Tables have 15-30 second scheduling overhead for simple operations, so genuinely sub-minute freshness is realistic only for relatively simple transformations on foundation tables.
- **Batch**: Changes are reflected hourly, daily, or less frequently. Use cases include financial reporting, daily aggregations, historical analytics, regulatory submissions, and data warehouse loads. All technologies support batch — this opens the widest selection. Choose based on other factors like logic type and orchestration preference.

**Cost implications:**
Continuous pipelines consume more compute (warehouses running continuously or frequently) than batch pipelines that run on a schedule. Choose the freshness level your business actually needs, not what sounds impressive.

**More Information:**
* [Dynamic Tables Target Lag](https://docs.snowflake.com/en/user-guide/dynamic-tables-refresh#understanding-target-lag) — Configuring refresh frequency
* [Task Schedules](https://docs.snowflake.com/en/user-guide/tasks-intro#task-scheduling) — Clock-based and CRON scheduling
* [Streams](https://docs.snowflake.com/en/user-guide/streams-intro) — Change data capture for event-driven processing
**Options:**
- Continuous
- Batch

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
