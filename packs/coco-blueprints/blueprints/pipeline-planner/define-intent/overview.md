## Transformation Intent

This step **asks the user one question** — their transformation intent.

### Instructions

1. Check whether `downstream_consumers` is populated from Blueprint 1 answers.
2. Choose the appropriate mode:

**Mode A (consumers known):** Present a guided prompt:
> "Based on your source data ({source_seed_reference}) and downstream consumers
> ({downstream_consumers}), describe what you want this transformation to produce.
> Focus on the output grain (one row per what?), key dimensions, and any filtering."

**Mode B (consumers unknown):** Present an open-ended prompt:
> "What do you want to get out of this data? Describe the output you want to produce."
> Provide examples:
> - "Daily revenue summary by region and customer segment"
> - "Latest order status per customer for the support dashboard"
> - "A flat event stream filtered to completed orders"
> - "Customer lifetime value table updated hourly"

3. Record the user's response as `transformation_intent`.


### Configuration Questions

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

#### What do you want to get out of this data? (`transformation_intent`: text)
Describe what your transformation should produce. Be specific about output
grain, key dimensions, and purpose.

**Good examples:**
- "Daily revenue summary by region and customer segment, excluding cancelled orders"
- "A flat event stream of completed orders enriched with customer attributes"
- "Latest order status per customer with running totals"
- "ML feature table with customer lifetime value, recency, and frequency metrics"

**What makes a good intent:**
- Names the output grain (daily, per-customer, per-event)
- References specific dimensions or measures from your source data
- States filters or exclusions
- Identifies the consumer perspective


#### Where does your source data live? (`source_seed_reference`: text)
Provide a reference to your source data at whatever granularity you know.
The system will automatically resolve this to specific objects.

**Any of these work:**
- Single table: `RAW.INGEST.ORDERS`
- Multiple tables: `RAW.INGEST.ORDERS, RAW.INGEST.CUSTOMERS`
- A schema (we'll find the tables): `RAW.INGEST`
- A database (we'll find the schemas and tables): `RAW`
- A stage: `@RAW.INGEST.FILES/orders/`
- An external source: "Kafka topic orders-v2"

**How to find it:**
```sql
SHOW DATABASES;
SHOW SCHEMAS IN DATABASE <database>;
SHOW TABLES IN SCHEMA <database>.<schema>;
```


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
