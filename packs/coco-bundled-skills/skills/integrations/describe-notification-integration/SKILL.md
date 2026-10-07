---
name: describe-notification-integration
description: >
  Describe the properties of a specific notification integration
---

# DESCRIBE NOTIFICATION INTEGRATION


Describes the properties of a notification integration.

DESCRIBE can be abbreviated to DESC.

## Syntax

```sql
{ DESC | DESCRIBE } NOTIFICATION INTEGRATION <name>
```

## Parameters

- **`<name>`**

  Specifies the identifier for the notification integration to describe.

  If the identifier contains spaces or special characters, the entire string must be enclosed in double quotes. Identifiers enclosed in double quotes are also case-sensitive.

## Output

The output of the command includes the following columns, which describe the properties and metadata of the object:

| Column | Description |
|---|---|
| `property` | The name of the property (see Properties of notification integrations). |
| `property_type` | The data type of the property (for example, `Boolean` or `String`). |
| `property_value` | The value assigned to the property. |
| `property_default` | The default value of the property. |

The `property` column can include the following properties of the notification integration:

Properties of notification integrations

| Property | Description |
|---|---|
| `ENABLED` | Specifies whether or not the notification integration is enabled. |
| `DIRECTION` | Specifies whether the notification integration supports sending notifications (`OUTBOUND`) or receiving notifications (`INBOUND`). |
| `COMMENT` | Specifies the comment for the notification integration. |
| Additional properties specific to the notification integration type. | These are the properties that you set when creating or altering the notification integration. For more information about these properties, see the CREATE NOTIFICATION INTEGRATION or ALTER NOTIFICATION INTEGRATION command for the specific type. |

## Access control requirements

A role used to execute this SQL command must have at least one of the following privileges at a minimum:

| Privilege | Object | Notes |
|---|---|---|
| USAGE | Integration |  |
| OWNERSHIP | Integration | OWNERSHIP is a special privilege on an object that is automatically granted to the role that created the object, but can also be transferred using the GRANT OWNERSHIP command to a different role by the owning role (or any role with the MANAGE GRANTS privilege). |

## Usage notes

- To post-process the output of this command, you can use the pipe operator (`->>`) or the RESULT_SCAN function. Both constructs treat the output as a result set that you can query.

  For example, you can use the pipe operator or RESULT_SCAN function to select specific columns from the SHOW command output or filter the rows.

  When you refer to the output columns, use double-quoted identifiers for the column names. For example, to select the output column `type`, specify `SELECT "type"`.

  You must use double-quoted identifiers because the output column names for SHOW commands are in lowercase. The double quotes ensure that the column names in the SELECT list or WHERE clause match the column names in the SHOW command output that was scanned.

## Examples

Describe the properties of a notification integration named `my_notify_int`:

```sql
DESC INTEGRATION my_notify_int;
```
