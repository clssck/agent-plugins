## Technology Recommendation

This step presents the scored recommendation based on all your inputs.

### How the Recommendation Works

1. **Routing table** maps your (freshness × logic × trigger) combination to a primary technology
2. **Constraint vetoes** eliminate technologies that conflict with your hard requirements
3. **Preference boost** adds +25 points to your preferred technology (if stated)
4. **Source data boost** adds +15 points to the technology best suited for your data source
5. **Alternative** is provided when a close second-place option exists

### Scoring Transparency

The full scoring rationale is shown so you can understand why a specific technology was recommended. Key factors displayed:
- Which routing rule matched your inputs
- Whether any constraints vetoed or boosted technologies
- Whether your existing tech needs aligned with or conflicted with the recommendation
- Source data affinity notes

### Tradeoffs

Each recommended technology includes a **"Tradeoffs to consider"** section that lists known disadvantages and limitations. This helps you make an informed decision by weighing the pros against the cons. Alternatives also include their tradeoffs for comparison.

### After the Recommendation

You can:
- **Accept** the recommendation and proceed with implementation guidance
- **Override** it based on your judgment — you know your context best
- **Re-run** the selector with different inputs if you want to explore alternatives

The selected technology determines what next-steps guidance you receive.


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

#### Who or what decides when your transformation runs? (`pipeline_trigger_model`: single-select)
**What is this asking?**
Define how your transformation pipeline gets triggered — what causes it to execute. This is about orchestration: the mechanism that decides "now is the time to run this transformation."

**Why does this matter?**
The trigger model is a strong technology differentiator. Dynamic Tables are uniquely suited to automatic management (you define the output, Snowflake decides when to refresh). Streams+Tasks excel at change-driven execution. Scheduled Tasks and external orchestrators provide clock-based or dependency-based triggering. Choosing the wrong trigger model means fighting the technology.

**Options explained:**
- **Snowflake Handles It Automatically**: You define what the output should look like (as a SQL query), and Snowflake automatically keeps it fresh within a target lag you specify. You do not write scheduling logic, monitor for new data, or manage dependencies between transformations. This is the Dynamic Tables model — fully declarative, zero orchestration code. Best when you want simplicity and can express your transformation as SQL.
- **New or Changed Data Triggers It**: Your transformation fires when new rows arrive or existing rows change in the source tables. Snowflake Streams capture change data (inserts, updates, deletes) and Tasks check whether the stream has data before executing. This gives you fine-grained control over what triggers execution while still being event-driven. Best for CDC patterns, incremental processing, and when you need to process only what changed.
- **A Schedule (Clock-based)**: Your transformation runs at fixed intervals — every 5 minutes, hourly, daily at 2 AM, on the first of each month. Snowflake Tasks support CRON expressions and minute-based intervals. Best for batch workloads with predictable timing requirements (daily reports, hourly aggregations, nightly loads).
- **An External System Orchestrates It**: Something outside Snowflake decides when to run your transformation — Apache Airflow, Dagster, Prefect, dbt Cloud, GitHub Actions, or custom CI/CD pipelines. The external system calls Snowflake (via SQL, API, or connector) to trigger execution. Best when your data pipeline spans multiple systems or when you already have an orchestrator managing broader workflows.

**More Information:**
* [Dynamic Tables Refresh](https://docs.snowflake.com/en/user-guide/dynamic-tables-refresh) — Automatic refresh behavior
* [Streams](https://docs.snowflake.com/en/user-guide/streams-intro) — Change data capture
* [Task Scheduling](https://docs.snowflake.com/en/user-guide/tasks-intro#task-scheduling) — CRON and interval scheduling
* [Snowflake REST API](https://docs.snowflake.com/en/developer-guide/sql-api/index) — External triggering via API
**Options:**
- Snowflake Handles It Automatically
- New or Changed Data Triggers It
- A Schedule (Clock-based)
- An External System Orchestrates It

#### Where does your source data live? (`source_data_location`: single-select)
**What is this asking?**
Identify where the raw data that feeds your transformation pipeline currently resides. This is about the source — where data originates before any transformation happens.

**Why does this matter?**
Source data location is a strong signal for technology recommendation. Data that arrives as a continuous stream has very different requirements than data already sitting in Snowflake tables. The ingestion pattern directly influences which transformation technology will work best downstream.

**Options explained:**
- **Streaming Platform**: Data arrives continuously via Kafka, Amazon Kinesis, Confluent Cloud, Azure Event Hubs, or similar message streaming systems. This strongly favors technologies that handle continuous data (Snowpipe Streaming + Streams+Tasks, or Dynamic Tables with micro-batch ingestion).
- **Cloud Storage**: Data lands as files in Amazon S3, Google Cloud Storage, or Azure Blob Storage. Formats include Parquet, CSV, JSON, Avro, or ORC. This is the most common pattern and works well with all transformation technologies via Snowpipe or external stages.
- **External API**: Data is fetched from REST APIs, webhooks, GraphQL endpoints, or custom connectors. This typically requires Python-based ingestion (Snowpark, external functions, or a connector service) before transformation can begin.
- **Already in Snowflake**: Source data is already loaded into Snowflake tables, views, or stages. This is the simplest case — all transformation technologies work equally well since no ingestion step is needed.
- **SaaS Application**: Data comes from business applications like Salesforce, HubSpot, SAP, Workday, NetSuite, or similar platforms. These typically use managed connectors (Fivetran, Airbyte, Snowflake connectors) that land data in Snowflake, after which any transformation technology applies.
- **Multiple Sources**: Data comes from a mix of the above. Select this when your pipeline combines data from streaming, storage, APIs, and/or SaaS platforms. The system will optimize for the most demanding source pattern.

**More Information:**
* [Snowpipe Streaming](https://docs.snowflake.com/en/user-guide/data-load-snowpipe-streaming-overview) — Low-latency streaming ingestion
* [External Stages](https://docs.snowflake.com/en/user-guide/data-load-s3) — Loading from cloud storage
* [Snowflake Connectors](https://other-docs.snowflake.com/en/connectors) — Pre-built SaaS connectors
**Options:**
- Streaming Platform
- Cloud Storage
- External API
- Already in Snowflake
- SaaS Application
- Multiple Sources

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

#### What will consume your transformed output? (`downstream_consumers`: multi-select)
**What is this asking?**
Identify what systems, teams, or processes will read from your transformed output tables. Select all that apply — most pipelines serve multiple consumers.

**Why does this matter?**
Downstream consumers influence technology choice in subtle but important ways. BI dashboards need predictable freshness and stable schemas. ML pipelines need feature tables with point-in-time correctness. Operational applications need low-latency reads and high availability. Data sharing requires clean, well-documented output. Understanding consumers helps the engine recommend a technology whose output characteristics match what consumers expect.

**Options explained:**
- **BI Dashboards**: Tableau, Sigma, Power BI, Snowsight dashboards, Looker, or similar visualization tools query your output. These consumers need predictable refresh timing, stable column names, and typically tolerate batch latency. Dynamic Tables and dbt both excel here due to their declarative, well-documented output.
- **Data Science / ML Pipelines**: Notebooks, model training jobs, feature stores, or ML inference pipelines read your output. These consumers need historical point-in-time data, feature tables with specific schemas, and often large scans over historical windows. Snowpark and dbt with incremental models work well for building ML feature tables.
- **Operational Applications**: APIs, microservices, or business applications query your output for real-time decisions (e.g., inventory checks, pricing engines, recommendation systems). These need low-latency reads, high concurrency, and near-real-time freshness. Dynamic Tables or Streams+Tasks with short intervals are often best here.
- **Other Downstream Pipelines**: Your output feeds into additional transformation layers (silver → gold, staging → mart). This creates a DAG of dependencies. Dynamic Tables handle multi-layer DAGs automatically. dbt manages dependencies via refs. Streams+Tasks require explicit dependency wiring.
- **External Data Sharing**: Your output is shared with other Snowflake accounts via Secure Data Sharing, listings, or the Snowflake Marketplace. Shared data needs clean schemas, documentation, and predictable refresh. dbt and Dynamic Tables both produce well-structured output suitable for sharing.
- **Not Yet Defined**: You are building the pipeline before consumers are finalized. This is common for speculative data products or platform teams building shared assets. Choose a flexible technology that supports multiple output patterns.

**More Information:**
* [Secure Data Sharing](https://docs.snowflake.com/en/user-guide/data-sharing-intro) — Sharing transformed output
* [Dynamic Table DAGs](https://docs.snowflake.com/en/user-guide/dynamic-tables-refresh#understanding-dynamic-table-dags) — Multi-layer pipelines
* [dbt Documentation](https://docs.getdbt.com/docs/collaborate/documentation) — Documenting output for consumers
**Options:**
- BI Dashboards
- Data Science / ML Pipelines
- Operational Applications
- Other Downstream Pipelines
- External Data Sharing
- Not Yet Defined

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
