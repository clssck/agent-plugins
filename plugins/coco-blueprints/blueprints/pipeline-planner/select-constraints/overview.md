## Select Constraints

Constraints act as hard vetoes or boosts on technologies in the recommendation engine.

### How Constraints Work

- A **veto** completely eliminates a technology from consideration — no amount of scoring can override it
- A **boost** favors a technology but doesn't force it — it adds points to the score
- Select only constraints that genuinely apply — over-constraining limits your options unnecessarily
- "None of these apply" is a valid and common choice

### Constraint Impact Table

| Constraint | Vetoes | Boosts |
|---|---|---|
| Must integrate with Airflow/Dagster/Prefect | Dynamic Tables | dbt Core, Snowpark |
| Must use existing dbt project | Dynamic Tables, Stored Procs | dbt Core, dbt Projects on SF |
| Needs row-level error handling | Dynamic Tables | Stored Procs, Snowpark |
| Must process data in Python | Dynamic Tables, dbt | Snowpark |
| Pipeline spans multiple systems | Dynamic Tables | Snowpark, dbt Core |
| Minimize operational overhead | Streams & Tasks, Stored Procs | Dynamic Tables, dbt+DTs |
| Data arrives as continuous stream | dbt, Stored Procs | Streams & Tasks |
| Must support CI/CD | — | dbt, Snowpark |
| Want everything native to Snowflake | dbt Core (external) | Dynamic Tables, S+T, dbt Projects on SF |

### Guidance

- If you're unsure whether a constraint applies, err on the side of not selecting it
- You can always come back and re-run the selector with different constraints
- Multiple constraints can be selected — their effects stack


### Configuration Questions

#### Select any constraints that apply to your pipeline. (`pipeline_constraints`: multi-select)
**What is this asking?**
Identify hard constraints that your pipeline must satisfy. These are non-negotiable requirements that will either eliminate technologies (vetoes) or strongly favor them (boosts). Select all that genuinely apply to your use case.

**Why does this matter?**
Constraints are the most powerful inputs to the recommendation engine. A single constraint can eliminate an otherwise perfect technology. For example, "Must Process Data in Python" immediately eliminates Dynamic Tables (SQL-only). "Minimize Operational Overhead" strongly favors Dynamic Tables (zero orchestration code). Be honest — only select constraints that are truly non-negotiable.

**Options explained:**
- **Must Integrate with Existing Airflow/Dagster/Prefect**: Your organization already runs an external orchestrator and this pipeline must be part of that DAG. Vetoes technologies that cannot be externally triggered. Boosts dbt Core (External) and Stored Procedures.
- **Must Use Our Existing dbt Project**: New transformations must be added to an existing dbt project (shared refs, shared testing, shared CI/CD). Vetoes non-dbt approaches. Locks recommendation to dbt (native or external, depending on current deployment).
- **Needs Row-level Error Handling**: Individual rows that fail transformation must be captured, logged, and potentially retried — not silently dropped. Vetoes Dynamic Tables (all-or-nothing refresh). Boosts Streams+Tasks and Stored Procedures.
- **Must Process Data in Python**: Transformation logic requires Python libraries, ML inference, complex string parsing, or API calls that cannot be expressed in SQL. Vetoes Dynamic Tables (SQL-only). Boosts Snowpark and Stored Procedures (Python).
- **Pipeline Spans Multiple Systems**: The transformation pipeline involves steps outside Snowflake (e.g., call an external API between SQL steps, write to a non-Snowflake target, coordinate with non-Snowflake services). Boosts external orchestration and Stored Procedures with external access.
- **Minimize Operational Overhead**: You want the simplest possible approach with the least code to maintain, no external infrastructure, and minimal monitoring. Strongly boosts Dynamic Tables (fully managed). Boosts dbt Projects on Snowflake (native, no external infra).
- **Data Arrives as Continuous Stream**: Source data is continuously ingested via Snowpipe Streaming or similar. Boosts Streams+Tasks (designed for CDC) and Dynamic Tables (auto-refresh on new data).
- **Must Support CI/CD Deployments**: Transformations must be version-controlled and deployed via CI/CD pipelines (GitHub Actions, GitLab CI, Azure DevOps). Boosts dbt (built for CI/CD) and Stored Procedures (DDL-based deployment). Dynamic Tables support CI/CD via CREATE OR REPLACE.
- **Want Everything Native to Snowflake**: Strong preference for Snowflake-native solutions with no external dependencies. Boosts Dynamic Tables, Streams+Tasks, dbt Projects on Snowflake, and Stored Procedures. Vetoes dbt Core (External).
- **None of These Apply**: No hard constraints exist. The recommendation will be based purely on freshness, logic type, orchestration preference, and downstream consumers.

**More Information:**
* [Dynamic Tables Limitations](https://docs.snowflake.com/en/user-guide/dynamic-tables-tasks-create#limitations) — What Dynamic Tables cannot do
* [Snowpark External Access](https://docs.snowflake.com/en/developer-guide/external-network-access/external-network-access-overview) — Calling external services
* [dbt CI/CD](https://docs.getdbt.com/docs/deploy/continuous-integration) — CI/CD with dbt
**Options:**
- Must Integrate with Existing Airflow/Dagster/Prefect
- Must Use Our Existing dbt Project
- Needs Row-level Error Handling
- Must Process Data in Python
- Pipeline Spans Multiple Systems
- Minimize Operational Overhead
- Data Arrives as Continuous Stream
- Must Support CI/CD Deployments
- Want Everything Native to Snowflake
- None of These Apply

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
