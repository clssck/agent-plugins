# Personal Databases (PDBs)

Sometimes `snowflake.yml` will default to a PDB (e.g. database name that starts with "USER$") as the deployment location for the app. PDB app deployments are intended for development purposes, similar to a staging environment.

The differences in app behavior when deploying to PDB are:
1. PDB apps cannot be used by other users or shared with other roles.
2. For owner's right in PDB apps, the Snowflake connection uses the owner user as `current_user` with the default role being the primary role (`current_role`), but with all other roles activated as secondary roles.

If deploying to PDB, use `code_workspace` in `snowflake.yml`. Otherwise, use `code_stage` with name like `<appName>_CODE`.
