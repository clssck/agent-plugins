---
name: describe-catalog-integration
description: >
  Describe the properties of a specific catalog integration
---

# DESCRIBE CATALOG INTEGRATION


Describes the properties of a catalog integration.

DESCRIBE can be abbreviated to DESC.

## Syntax

```sql
DESC[RIBE] CATALOG INTEGRATION <name>
```

## Parameters

- **`<name>`**

  Specifies the identifier for the catalog integration to describe. If the identifier contains spaces or special characters, the entire string must be enclosed in double quotes. Identifiers enclosed in double quotes are also case-sensitive.

## Output

The output of the command includes the following columns, which describe the properties and metadata of the object:

| Column | Description |
|---|---|
| property | The name of the property. This column can include the properties listed in the following table. |
| property_type | The property type. |
| property_value | The value assigned to the property. |
| property_default | The default property value. |

The `property` column can include the following properties of catalog integration object:

| Property | Description |
|---|---|
| enabled | Specifies whether the catalog integration is available to use for Apache Iceberg tables. |
| catalog_source | The type of catalog source; ICEBERG_REST, POLARIS, OBJECT_STORE, or GLUE (for non-REST Glue integrations). |
| refresh_interval_seconds | Specifies the number of seconds that Snowflake waits between attempts to poll the external Iceberg catalog for metadata updates for automated refresh. |
| rest_authentication | Specifies the REST authentication parameters for the catalog integration. |
| rest_config | Specifies the REST configuration parameters for the catalog integration. |
| catalog_namespace | The output for this column is as follows: If the catalog integration is for externally managed Iceberg tables, specifies the namespace of the external Iceberg catalog. If the namespace is specified at the table level only, this column has no value in the function output. If the catalog integration is for syncing a Snowflake-managed table with Snowflake Open Catalog, this column has no value in the function output because this field is not required. |
| table_format | The table format supplied by the catalog; for example, ICEBERG. |
| glue_aws_role_arn | (AWS Glue) The Amazon Resource Name (ARN) of the IAM role that Snowflake assumes to connect to AWS Glue. |
| glue_catalog_id | (AWS Glue) The ID of your AWS account. |
| glue_region | (AWS Glue) The AWS Region of your AWS Glue Data Catalog. |
| glue_aws_iam_user_arn | (AWS Glue) The ARN of the AWS IAM user created for your Snowflake account when you created the catalog integration. |
| glue_aws_external_id | (AWS Glue) The external ID that Snowflake uses to establish a trust relationship with AWS Glue. |
| comment | The comment for the catalog integration. |

## Access control requirements

A role used to execute this operation must have the following privileges at a minimum:

| Privilege | Object | Notes |
|---|---|---|
| USAGE | Integration (catalog) |  |

## Usage notes

- To post-process the output of this command, you can use the pipe operator (`->>`) or the RESULT_SCAN function. Both constructs treat the output as a result set that you can query.

  For example, you can use the pipe operator or RESULT_SCAN function to select specific columns from the SHOW command output or filter the rows.

  When you refer to the output columns, use double-quoted identifiers for the column names. For example, to select the output column `type`, specify `SELECT "type"`.

  You must use double-quoted identifiers because the output column names for SHOW commands are in lowercase. The double quotes ensure that the column names in the SELECT list or WHERE clause match the column names in the SHOW command output that was scanned.

## Examples

Describe a catalog integration:

```sql
DESC CATALOG INTEGRATION my_catalog_integration;
```

The following shows the output of DESCRIBE CATALOG INTEGRATION for an AWS Glue catalog integration. The output includes AWS Glue-specific properties (for example, `GLUE_AWS_ROLE_ARN`) and common catalog integration properties.

```
+-----------------------+---------------+----------------------------------+------------------+
|       property        | property_type |          property_value          | property_default |
+-----------------------+---------------+----------------------------------+------------------+
| ENABLED               | Boolean       | true                             | false            |
| CATALOG_SOURCE        | String        | GLUE                             |                  |
| CATALOG_NAMESPACE     | String        | dbname                           |                  |
| TABLE_FORMAT          | String        | ICEBERG                          |                  |
| GLUE_AWS_ROLE_ARN     | String        | arn:aws:iam::123:role/dummy-role |                  |
| GLUE_CATALOG_ID       | String        | 123456789012                     |                  |
| GLUE_REGION           | String        | us-west-2                        |                  |
| GLUE_AWS_IAM_USER_ARN | String        | arn:aws:iam::123:user/example    |                  |
| GLUE_AWS_EXTERNAL_ID  | String        | exampleGlueExternalId            |                  |
| COMMENT               | String        |                                  |                  |
+-----------------------+---------------+----------------------------------+------------------+
```
