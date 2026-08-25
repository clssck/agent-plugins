## Source Data Identification

Understanding where your data comes from is a key signal for technology fit. The origin of your source data influences which transformation technology will integrate most naturally with your pipeline.

### How Source Location Affects Technology Fit

- **Streaming sources** (Kafka, Kinesis, Confluent) strongly favor **Streams & Tasks**, which natively process incoming data in near real-time as it arrives via Snowpipe Streaming or connectors.

- **Cloud storage / files** (S3, GCS, Azure Blob) favor **Snowpark** for flexible file processing — especially when files require parsing, transformation, or complex loading logic beyond standard COPY INTO.

- **Data already in Snowflake** is ideal for **Dynamic Tables**, which declaratively transform existing tables with automatic refresh and no external orchestration.

- **External APIs** typically require Python for extraction, pointing toward **Snowpark** for the full extract-and-transform pipeline.

- **SaaS applications** usually land in Snowflake via managed connectors (Fivetran, Airbyte), after which they're treated as Snowflake-internal data.

### Scoring Impact

Source type contributes a **+15 boost** to the best-fit technology in the scoring engine. This is a contributing signal — not an eliminator — so other factors (freshness, logic type, constraints) may override it.


### Configuration Questions

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
