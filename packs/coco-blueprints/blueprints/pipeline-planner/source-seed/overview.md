## Source Data Reference

Provide a reference to your source data at whatever granularity you know:
- A specific table: `DB.SCHEMA.TABLE`
- A schema containing your source tables: `DB.SCHEMA`
- A database: `DB`
- A stage: `@DB.SCHEMA.STAGE/path/`
- An external system: describe it (e.g., "Kafka topic orders-v2")

The system will resolve this to specific objects automatically.


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

