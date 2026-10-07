## Expansion Consumers

What will consume the output of this expansion? Knowing the consumers shapes the output structure and topology of the plan.

### Instructions

1. Ask: "What will consume the output of this pipeline?"
2. Options (multi-select): BI Dashboards | Data Science / ML Pipelines | Operational Applications | Other Downstream Pipelines | External Data Sharing | Not Yet Defined
3. Record the response as `downstream_consumers`.


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
