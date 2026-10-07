---
name: show-delegated-authorizations
description: >
  List active delegated authorizations for a user, integration, or the entire account
---

# SHOW DELEGATED AUTHORIZATIONS


Lists the active delegated authorizations for which you have access privileges. This command can be used to list the DELEGATED AUTHORIZATIONS for a specified user or integration (or the current user), or your entire account.

## Syntax

```sql
SHOW DELEGATED AUTHORIZATIONS

SHOW DELEGATED AUTHORIZATIONS BY USER <username>

SHOW DELEGATED AUTHORIZATIONS TO SECURITY INTEGRATION <integration_name>
```

## Variants

- **SHOW DELEGATED AUTHORIZATIONS BY USER <username>**

  Lists all the active delegated authorizations that have been approved by a user. This variant requires the MODIFY privilege on the user.

- **SHOW DELEGATED AUTHORIZATIONS TO SECURITY INTEGRATION <integration_name>**

  Lists all the active delegated authorizations that have been approved for an integration. This variant requires the ACCOUNTADMIN role.

For more details on each of these variants, see:

- Viewing Delegated Authorizations for OAuth User Consent

- Display OAuth Consents in OAuth Partner Applications

## Usage notes

- The command doesn't require a running warehouse to execute.

- The command only returns objects for which the current user's current role has been granted at least one access privilege.

- The MANAGE GRANTS access privilege implicitly allows its holder to see every object in the account. By default, only the account administrator (users with the ACCOUNTADMIN role) and security administrator (users with the SECURITYADMIN role) have the MANAGE GRANTS privilege.

- To post-process the output of this command, you can use the pipe operator (`->>`) or the RESULT_SCAN function. Both constructs treat the output as a result set that you can query.

  For example, you can use the pipe operator or RESULT_SCAN function to select specific columns from the SHOW command output or filter the rows.

  When you refer to the output columns, use double-quoted identifiers for the column names. For example, to select the output column `type`, specify `SELECT "type"`.

  You must use double-quoted identifiers because the output column names for SHOW commands are in lowercase. The double quotes ensure that the column names in the SELECT list or WHERE clause match the column names in the SHOW command output that was scanned.

- The command returns a maximum of ten thousand records for the specified object type, as dictated by the access privileges for the role used to execute the command. Any records above the ten thousand records limit aren't returned, even with a filter applied.

  To view results for which more than ten thousand records exist, query the corresponding view (if one exists) in the Snowflake Information Schema.

## Examples

List all delegated authorizations for your account:

```sql
SHOW DELEGATED AUTHORIZATIONS;

+-------------------------------+-----------+-----------+-------------------+--------------------+
| created_on                    | user_name | role_name | integration_name  | integration_status |
|-------------------------------+-----------+-----------+-------------------+--------------------|
| 2018-11-27 07:43:10.914 -0800 | JSMITH    | PUBLIC    | MY_OAUTH_INT1     | ENABLED            |
| 2018-11-27 08:14:56.123 -0800 | MJONES    | PUBLIC    | MY_OAUTH_INT2     | ENABLED            |
+-------------------------------+-----------+-----------+-------------------+--------------------+
```

List all delegated authorizations for a specified user:

```sql
SHOW DELEGATED AUTHORIZATIONS BY USER jsmith;

+-------------------------------+-----------+-----------+-------------------+--------------------+
| created_on                    | user_name | role_name | integration_name  | integration_status |
|-------------------------------+-----------+-----------+-------------------+--------------------|
| 2018-11-27 07:43:10.914 -0800 | JSMITH    | PUBLIC    | MY_OAUTH_INT1     | ENABLED            |
+-------------------------------+-----------+-----------+-------------------+--------------------+
```

List all delegated authorizations for a specified integration:

```sql
SHOW DELEGATED AUTHORIZATIONS TO SECURITY INTEGRATION my_oauth_int2;

+-------------------------------+-----------+-----------+-------------------+--------------------+
| created_on                    | user_name | role_name | integration_name  | integration_status |
|-------------------------------+-----------+-----------+-------------------+--------------------|
| 2018-11-27 08:14:56.123 -0800 | MJONES    | PUBLIC    | MY_OAUTH_INT2     | ENABLED            |
+-------------------------------+-----------+-----------+-------------------+--------------------+
```
