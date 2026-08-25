## Characterize Transformation Logic

The type of code you write determines which technologies are compatible. This is often the most decisive factor after freshness.

### Logic Type Compatibility

- **SQL** is the most flexible — compatible with Dynamic Tables, Streams & Tasks, Stored Procedures, and dbt. If your transformation is expressible in SQL, you have the widest range of options.

- **dbt** is specialized SQL tooling that adds testing, lineage tracking, documentation, and packages on top of standard SQL. It comes in two variants:
  - **dbt Projects on Snowflake** — runs natively within Snowflake, orchestrated by Tasks
  - **dbt Core (External)** — runs outside Snowflake via dbt Cloud, Airflow, or CLI

- **Python/Scala** (DataFrame operations, ML, API calls) requires **Snowpark**. This is the only technology supporting non-SQL logic within Snowflake's compute environment.

- **Procedural** logic (control flow, loops, retries, error handling) narrows options to **Stored Procedures** or **Snowpark** — the only technologies with native procedural support.

### Key Insight

If you can express your logic in SQL, do so — it gives you the most technology options and typically the best performance. Reserve Python/procedural approaches for logic that genuinely cannot be expressed declaratively.


### Configuration Questions

#### What kind of transformation code are you writing? (`transformation_logic_type`: single-select)
**What is this asking?**
Identify the primary language and paradigm you will use to express your transformation logic. This is about how you write the code, not how it gets orchestrated or scheduled.

**Why does this matter?**
Different technologies excel at different logic types. Dynamic Tables only support declarative SQL. Snowpark is built for Python/Scala DataFrames. dbt adds testing, documentation, and Jinja templating on top of SQL. Stored Procedures handle imperative control flow. Choosing the right technology for your logic type prevents fighting against the tool.

**Options explained:**
- **SQL**: Standard SQL queries — SELECTs, JOINs, GROUP BYs, window functions, CTEs, MERGE statements. Your transformation can be expressed entirely as declarative SQL without needing loops, conditionals, or external library calls. This is the broadest option — Dynamic Tables, Streams+Tasks, dbt, and Stored Procedures all handle SQL well.
- **dbt**: Jinja-templated SQL with built-in testing (not_null, unique, relationships), documentation (schema.yml), packages (dbt_utils, dbt_expectations), and incremental materializations. Choose this if you already use dbt patterns or want the software engineering discipline dbt provides (version control, CI/CD, modular refs, data contracts).
- **Python or Scala**: DataFrame transformations, ML feature engineering, calling external APIs or libraries, complex string parsing, geospatial calculations, or anything requiring packages not available in SQL. Snowpark provides a DataFrame API that executes on Snowflake compute. Choose this when SQL cannot express your logic or when you need Python/Scala ecosystem libraries.
- **Procedural**: Imperative logic with control flow — IF/ELSE branching, FOR/WHILE loops, TRY/CATCH error handling, retry logic, multi-step transactions, conditional execution paths. Choose this when your transformation requires decision-making logic that cannot be expressed declaratively.

**More Information:**
* [Dynamic Tables SQL](https://docs.snowflake.com/en/user-guide/dynamic-tables-tasks-create) — Supported SQL in Dynamic Tables
* [Snowpark Python](https://docs.snowflake.com/en/developer-guide/snowpark/python/index) — Python DataFrame API
* [Stored Procedures](https://docs.snowflake.com/en/developer-guide/stored-procedure/stored-procedures-overview) — Procedural logic in Snowflake
* [dbt on Snowflake](https://docs.snowflake.com/en/developer-guide/dbt/dbt-overview) — dbt integration overview
**Options:**
- SQL
- dbt
- Python or Scala
- Procedural

#### Which dbt approach will you use? (`dbt_variant`: single-select)
**What is this asking?**
Choose between running dbt natively inside Snowflake as a first-class object, or running dbt externally using dbt Cloud, Airflow, CLI, or another external orchestrator.

**Why does this matter?**
This decision affects your deployment model, orchestration approach, operational complexity, and how tightly integrated your dbt project is with Snowflake. Native dbt (dbt Projects on Snowflake) eliminates external infrastructure entirely — the project is deployed as a Snowflake object and orchestrated by Tasks. External dbt requires maintaining infrastructure outside Snowflake but offers more flexibility in orchestration and may integrate better with existing CI/CD pipelines.

**Options explained:**
- **dbt Projects on Snowflake**: Your dbt project is deployed as a native Snowflake object using `snow dbt deploy`. It runs entirely within Snowflake — no external compute, no dbt Cloud subscription, no Airflow DAGs. Orchestration uses Snowflake Tasks (scheduled or event-driven). Ideal when you want everything in one platform with minimal operational overhead. Supports dbt Core features including models, tests, seeds, and snapshots.
- **dbt Core (External)**: Your dbt project runs outside Snowflake using dbt Cloud, Apache Airflow, Dagster, Prefect, GitHub Actions, or the dbt CLI. The project connects to Snowflake as a target but execution happens externally. Choose this when you already have an external orchestrator, need dbt Cloud features (IDE, docs hosting, semantic layer), or when your dbt project is part of a larger pipeline that spans multiple systems.

**Key differences:**
| Aspect | dbt Projects on Snowflake | dbt Core (External) | |--------|---------------------------|---------------------| | Infrastructure | None (Snowflake-native) | External compute required | | Orchestration | Snowflake Tasks | dbt Cloud, Airflow, etc. | | Deployment | `snow dbt deploy` | Git-based CI/CD | | Cost model | Snowflake credits only | Credits + external tool cost | | Best for | Snowflake-first teams | Multi-tool ecosystems |

**More Information:**
* [dbt Projects on Snowflake](https://docs.snowflake.com/en/developer-guide/dbt/dbt-snowflake-projects) — Native deployment guide
* [dbt Cloud](https://docs.getdbt.com/docs/cloud/about-cloud-setup) — External orchestration with dbt Cloud
* [dbt + Airflow](https://docs.getdbt.com/guides/airflow-and-dbt-cloud) — External orchestration with Airflow
**Options:**
- dbt Projects on Snowflake
- dbt Core (External)

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
