# ODCS v3.1.0 Template

Template and field reference for [Open Data Contract Standard v3.1.0](https://github.com/bitol-io/open-data-contract-standard/tree/v3.1.0), the skill default. Schema: [odcs-json-schema-v3.1.0.json](https://raw.githubusercontent.com/bitol-io/open-data-contract-standard/v3.2.0/schema/odcs-json-schema-v3.1.0.json). Both YAML blocks below validate against it with `validate_odcs.py`. v3.2.0 additions: [v3.2.0 Delta](#v320-delta).

Type mapping tables: [full-guide.md](full-guide.md#type-mapping-tables). Source extraction: [source-parsing.md](source-parsing.md).

## Standard vs Sanofi Policy

Keep the two separate in reviews. NEVER reject a contract that is valid ODCS because it skips Sanofi policy; NEVER invent values to satisfy policy.

| Level | Rule |
|-------|------|
| ODCS-required (root) | `version`, `apiVersion`, `kind`, `id`, `status` |
| ODCS-required (nested) | `schema[].name`; `servers[].server` + `type`; Snowflake server `account`, `database`, `schema`; `slaProperties[].property` + `value`; library quality `metric` |
| Sanofi policy (authoring default) | `name`, `tenant: sanofi`, `domain`, `dataProduct`, `description.purpose`, object + property `description` |
| Sanofi policy (default values) | `status: draft`, `version: 1.0.0`, classification `restricted` when source gives none |

## Minimal Contract

```yaml
apiVersion: v3.1.0
kind: DataContract
id: 8f2b6f6e-3c1a-4b7e-9d52-1a6c0e4f7a10
version: 1.0.0
status: draft
name: orders
tenant: sanofi
domain: sales
dataProduct: order-management
description:
  purpose: Order facts for sales reporting
  usage: Join on order_id; read-only for consumers
schema:
  - name: orders
    logicalType: object
    physicalType: table
    description: One row per customer order
    properties:
      - name: order_id
        logicalType: integer
        physicalType: NUMBER(38,0)
        description: Unique order identifier
        primaryKey: true
        primaryKeyPosition: 1
        required: true
        unique: true
```

## Full Contract Template

Replace sample values. Omit any section without source data. Enum-valued fields (`logicalType`, `type`, `dimension`, `metric`) MUST hold real values.

```yaml
apiVersion: v3.1.0
kind: DataContract
id: 8f2b6f6e-3c1a-4b7e-9d52-1a6c0e4f7a10   # UUID v4
version: 1.0.0                              # semver
status: draft                               # proposed | draft | active | deprecated | retired
name: sales-orders                          # kebab-case schema name
tenant: sanofi
domain: sales
dataProduct: order-management
tags: [sales, orders]
description:
  purpose: Order facts for sales reporting
  usage: Join on order_id; read-only for consumers
  limitations: Excludes cancelled orders older than 2 years

servers:
  - server: snowflake-prod
    type: snowflake
    environment: prod
    description: Production Snowflake schema
    account: myorg-myaccount
    database: SALES_PROD
    schema: ORDERS
    warehouse: REPORTING_WH

schema:
  - name: orders
    logicalType: object
    physicalType: table                     # table | view | materialized view
    physicalName: ORDERS
    description: One row per customer order
    quality:
      - type: library
        metric: rowCount
        description: Table must not be empty
        dimension: completeness
        mustBeGreaterOrEqualTo: 1
      - type: library                       # composite key: schema-level rule
        metric: duplicateValues
        description: (order_id, line_id) must be unique together
        dimension: uniqueness
        arguments:
          properties: [order_id, line_id]
        mustBe: 0
    properties:
      - name: order_id
        logicalType: integer
        physicalType: NUMBER(38,0)
        description: Unique order identifier
        primaryKey: true
        primaryKeyPosition: 1               # 1-based, source key order
        required: true                      # NOT NULL
        unique: true                        # single-column unique only
        classification: restricted          # only when differing from the policy default
        tags: [identifier]
        examples: [1001]
      - name: status
        logicalType: string
        physicalType: VARCHAR(50)
        description: Current order status
        required: true
        logicalTypeOptions:
          maxLength: 50
        quality:
          - type: library
            metric: invalidValues
            description: Status must be a known value
            dimension: conformity
            arguments:
              validValues: [placed, shipped, completed, returned]
            mustBe: 0
      - name: ordered_at
        logicalType: timestamp
        physicalType: TIMESTAMP_TZ
        description: Time the order was placed
        required: true
        logicalTypeOptions:
          timezone: true
      - name: customer_id
        logicalType: integer
        physicalType: NUMBER(38,0)
        description: Customer who placed the order
        required: true
        relationships:
          - to: customers.customer_id       # property-level: `from` is implicit
            type: foreignKey

slaProperties:
  - property: freshness
    value: 24
    unit: h
    description: Data refreshed daily
  - property: retention
    value: 7
    unit: y
  - property: generalAvailability
    value: "2026-01-01"

team:
  name: sales-data-team
  members:
    - username: jane.doe@example.com        # required by TeamMember
      name: Jane Doe
      role: owner
    - username: john.roe@example.com
      role: steward

support:
  - channel: sales-data-support
    tool: slack
    url: https://example.com/channels/sales-data-support

authoritativeDefinitions:
  - type: businessDefinition
    url: https://example.com/glossary/orders

customProperties:
  - property: dataClassificationPolicy      # contract-level policy: not inherited by properties
    value: restricted
```

## Field Reference

### Root Fields

| Field | ODCS | Notes |
|-------|------|-------|
| `apiVersion`, `kind`, `id`, `version`, `status` | Required | `kind: DataContract`; `id` UUID v4; `status` free string, vocabulary `proposed`/`draft`/`active`/`deprecated`/`retired` |
| `name`, `tenant`, `domain`, `dataProduct` | Optional | Sanofi policy fills them. ODCS marks `dataProduct` deprecated since v3.1.0 (still valid); keep it for Sanofi policy |
| `description` | Optional object | `purpose`, `usage`, `limitations`, `authoritativeDefinitions`, `customProperties` |
| `tags` | Optional | Free strings |
| `servers`, `schema`, `team`, `roles`, `support`, `price` | Optional | |
| `slaDefaultElement`, `slaProperties` | Optional | SLAs; NEVER `serviceLevel`; NEVER `slaDefaultElement` (deprecated since v3.1.0, removed in ODCS v4) |
| `authoritativeDefinitions`, `customProperties`, `contractCreatedTs` | Optional | Links go in `authoritativeDefinitions` |

NEVER emit root `classification`, `quality`, `links`, or `serviceLevel`. The schema sets `additionalProperties: false`.

### Schema Object

| Field | Notes |
|-------|-------|
| `name` | Required. Table or view name |
| `logicalType` | `object` |
| `physicalType` | `table`, `view`, `materialized view` |
| `physicalName`, `description`, `businessName`, `tags`, `dataGranularityDescription` | Optional |
| `properties`, `quality`, `relationships` | Optional lists |

NEVER emit `type: table` on the schema object.

### Property Object

| Field | Notes |
|-------|-------|
| `name` | Required |
| `logicalType` | `string`, `date`, `timestamp`, `time`, `number`, `integer`, `object`, `array`, `boolean` |
| `logicalTypeOptions` | Per-type options (`maxLength`, `format`, `timezone`, `minimum`, ...). `array` takes `items` |
| `physicalType` | Exact source type |
| `primaryKey`, `primaryKeyPosition` | Position starts at 1 |
| `required` | `true` = NOT NULL. Inverse of `isNullable` |
| `unique` | Single-column UNIQUE only |
| `classification`, `tags`, `examples`, `criticalDataElement` | Property level only |
| `quality`, `relationships` | Optional lists |

NEVER emit `isPrimaryKey`, `isNullable`, `isUnique`.

### Server Object

| Field | Notes |
|-------|-------|
| `server`, `type` | Required. `type` is an enum: `snowflake`, `postgresql`, `bigquery`, `s3`, `redshift`, `databricks`, `kafka`, `custom`, ... |
| `environment`, `description`, `roles` | Optional |
| Snowflake: `account`, `database`, `schema` | Required when `type: snowflake` |
| Snowflake: `warehouse`, `host`, `port` | Optional |

### Quality Rules

Place rules on a schema object or a property. NEVER at root.

| Field | Notes |
|-------|-------|
| `type` | `library` (default), `sql`, `custom`, `text` |
| `metric` | Required for `library`: `nullValues`, `missingValues`, `invalidValues`, `duplicateValues`, `rowCount` |
| `arguments` | `invalidValues`: `validValues` or `pattern`. `duplicateValues`/`nullValues` at schema level: `properties` |
| `query` | Required for `sql`; `${table}`, `${column}` variables |
| `engine`, `implementation` | Required for `custom` (`dbt`, `soda`, ...) |
| `dimension` | `accuracy`, `completeness`, `conformity`, `consistency`, `coverage`, `timeliness`, `uniqueness` |
| `description`, `severity`, `schedule`, `unit`, `name`, `tags` | Optional |

Operators (one per rule): `mustBe`, `mustNotBe`, `mustBeGreaterThan`, `mustBeGreaterOrEqualTo`, `mustBeLessThan`, `mustBeLessOrEqualTo`, `mustBeBetween`, `mustNotBeBetween`.

### SLA Properties

| Field | Notes |
|-------|-------|
| `property`, `value` | Required. Common properties: `latency`, `freshness`, `frequency`, `retention`, `generalAvailability`, `endOfSupport` |
| `unit` | `d`, `h`, `m`, `y`, ... |
| `element`, `driver`, `description`, `schedule` | Optional |

### Team and Support

| Field | Notes |
|-------|-------|
| `team.name`, `team.members[]` | `team` is an object. The bare array is deprecated |
| `members[].username` | Email or id. Optional `name`, `role`, `dateIn`, `dateOut` |
| `support[]` | `channel`, `url`, `tool`, `scope`, `description` |

NEVER emit `email` on a team member.

## v3.2.0 Delta

Set `apiVersion: v3.2.0` only when the user asks for it or the consuming tool requires it. NEVER put these fields in a `v3.1.0` contract: the v3.1.0 schema rejects them (`Unevaluated properties are not allowed`). The changelog marks each addition optional and non-breaking; after bumping `apiVersion`, re-run the validator.

| Addition | Where | Shape |
|----------|-------|-------|
| `enum` | property | Non-empty list of unique `{value, label?, id?, description?, tags?}` |
| `logicalType: map` | property | Requires a `map` object with `key` and `value` property definitions |
| `logicalType: vector` | property | `logicalTypeOptions.dimensions` required; optional `elementType`, `distanceMetric`, `normalized`, `embeddingModel` |
| `semanticType` | property | `column` (default), `measure`, `dimension`; measure expression in `transformLogic` |
| `synonyms` | schema object, property | List of `{synonym, id?, description?, locale?, source?, status?}` |
| `deprecated` | schema object, property | Boolean, default `false` |
| `context` | root, schema object | String, or `{instructions, verifiedStatements, constraints}` for AI tools |
| `${VAR}`, `${VAR:-default}` | any string value | Resolved by tooling at run time; secrets and hostnames stay out of the file. Server `port` may be a string |
| Server `type` | `servers[]` | New: `hana`, `iceberg`, `exasol`, `teradata`, `ingres`, `vectorwise`, `versant`, `poet`; optional `encoding` on file/stream servers; Athena `workgroup` |
| `vendor`, `id` | `customProperties[]`, `relationships[]` | Optional strings |
| `customProperties`, `authoritativeDefinitions` | `slaProperties[]` | Optional |

`id` values on nested objects: the tag-pinned v3.1.0 schema and the CLI's bundled v3.1.0 schema accept only `[A-Za-z0-9_-]`; the v3.2.0-tag schemas also accept namespaced ids (`urn:uuid:...`). Prefer `[A-Za-z0-9_-]` so every tool accepts the contract.

## Sources

- [ODCS CHANGELOG (v3.2.0 "Peter Flook", v3.1.0)](https://github.com/bitol-io/open-data-contract-standard/blob/main/CHANGELOG.md)
- [ODCS releases](https://github.com/bitol-io/open-data-contract-standard/releases) (v3.2.0 published 2026-09-08)
- [ODCS schema directory and versioning policy](https://github.com/bitol-io/open-data-contract-standard/tree/v3.2.0/schema)
- [odcs-json-schema-v3.2.0.json](https://raw.githubusercontent.com/bitol-io/open-data-contract-standard/v3.2.0/schema/odcs-json-schema-v3.2.0.json) (`dataProduct`, `slaDefaultElement` marked deprecated in the v3.1.0 file)
