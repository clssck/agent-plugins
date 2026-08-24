# Snowsight URLs ↔ workspace FQNs

`<host>/<org>/<account>/#/workspaces/ws/<DB>/<SCHEMA>/<WS>[/<path>]` — URL-encode every `$` → `%24` and space → `%20` per segment.

A decoded URL segment that isn't all-uppercase letters/digits/`$`/`_` (mixed-case or has spaces) must be double-quoted in the FQN: `hEllo%20how%20are%20you` ↔ `"hEllo how are you"`. Strip the outer `"..."` from quoted FQN segments before URL-encoding.

**URL → cortex ws spec:** take everything after `/#/workspaces/ws/`, drop trailing `/`, decode `%XX`. First three `/`-segments are DB/SCHEMA/WS (quote any whose decoded form isn't all-uppercase/digits/`$`/`_`); rest is path. Output `<DB>.<SCHEMA>.<WS>:/<path>` (use `:/` alone for root).

**FQN+path → URL:** run `SELECT CURRENT_ORGANIZATION_NAME(), CURRENT_ACCOUNT_NAME(), CURRENT_REGION();`. Host: `https://preprod.app.snowflake.com` if region contains `PREPROD`, else `https://app.snowflake.com`. For each FQN segment: strip outer `"..."` if present, then encode `$` → `%24` and space → `%20`. Assemble per anatomy. Drop trailing `/` for root. Accepts both `<FQN>:/<path>` and `snow://workspace/<FQN>/versions/<live|head>/<path>`.

Example (snowhouse, org `SFCOGSOPS`, account `SNOWHOUSE_AWS_US_WEST_2`, region `PUBLIC.AWS_US_WEST_2`):
- `USER$.PUBLIC.DEFAULT$:/gitPerf3.sql` ↔ `https://app.snowflake.com/SFCOGSOPS/SNOWHOUSE_AWS_US_WEST_2/#/workspaces/ws/USER%24/PUBLIC/DEFAULT%24/gitPerf3.sql`
- `USER$.PUBLIC."hEllo how are you":/foo.sql` ↔ `https://app.snowflake.com/SFCOGSOPS/SNOWHOUSE_AWS_US_WEST_2/#/workspaces/ws/USER%24/PUBLIC/hEllo%20how%20are%20you/foo.sql`
