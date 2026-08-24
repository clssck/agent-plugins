# Legacy Event Accounts Reference

Use when CET event routing tables are not available, or for VPS / GOV / Sovereign / Private Link regions (unsupported by CET).

A provider collects shared events **only in the same region** where a consumer installs the app. An event account must exist in every consumer region **before** consumer installation — historical events cannot be shared retroactively.

> Dev-mode apps (`CREATE APPLICATION ... FROM APPLICATION PACKAGE`) automatically use the package account as the event account; no setup needed.

## Restrictions

- Role: **ORGADMIN** (or **GLOBALORGADMIN** in Orgs 2.0).
- The account must have an active event table (see `configure-event-sharing/SKILL.md` Path C).
- The account cannot be: locked/suspended, a reader account, a trial account, or a managed account.
- Only one event account per region; setting a new one replaces the previous.
- Always use the **account name** (not the locator/identifier).

## Set Event Account for a Region

```sql
USE ROLE ORGADMIN;

SELECT SYSTEM$SET_EVENT_SHARING_ACCOUNT_FOR_REGION(
  '<snowflake_region>',   -- e.g. 'AWS_US_WEST_2', 'AZURE_WESTUS2'
  '<region_group>',       -- e.g. 'PUBLIC'
  '<account_name>'        -- e.g. 'MY_EVENTS_WEST'
);
```

### Example — two regions

```sql
USE ROLE ORGADMIN;

SELECT SYSTEM$SET_EVENT_SHARING_ACCOUNT_FOR_REGION(
  'AWS_US_WEST_2', 'PUBLIC', 'MY_EVENTS_WEST'
);

SELECT SYSTEM$SET_EVENT_SHARING_ACCOUNT_FOR_REGION(
  'AWS_US_EAST_1', 'PUBLIC', 'MY_EVENTS_EAST'
);
```

## Inspect

```sql
USE ROLE ORGADMIN;
SELECT SYSTEM$SHOW_EVENT_SHARING_ACCOUNTS();
```

## Unset

```sql
USE ROLE ORGADMIN;

SELECT SYSTEM$UNSET_EVENT_SHARING_ACCOUNT_FOR_REGION(
  '<snowflake_region>',
  '<region_group>',
  '<account_name>'
);
```

## Helper Queries

```sql
SELECT CURRENT_REGION();         -- current account's region
SELECT CURRENT_ACCOUNT_NAME();   -- current account name
```

## Interaction with CET

CET rules take precedence over legacy for `PUBLIC` regions. If a region is not covered by any CET rule, the system falls back to the legacy event account for that region.
