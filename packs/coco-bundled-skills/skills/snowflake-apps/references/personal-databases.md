# Personal Databases (PDBs)

Sometimes the deployment manifest will default to a PDB (e.g. database name that starts with "USER$") as the deployment location for the app. PDB app deployments are intended for development purposes, similar to a staging environment.

The differences in app behavior when deploying to PDB are:
1. PDB apps cannot be used by other users or shared with other roles.
2. For owner's right in PDB apps, the Snowflake connection uses the owner user as `current_user` with the default role being the primary role (`current_role`), but with all other roles activated as secondary roles.

If deploying to PDB from a `snowflake.yml` project, use `code_workspace`. Otherwise, use `code_stage` with a name like `<appName>_CODE`.

In an `app.yml` `version: 2` project, leave both `code_stage` and `code_workspace` unset and let the CLI decide per deploy — it already routes a PDB destination through a workspace. A `code_stage` pinned in the manifest is honoured even when it resolves into a PDB, which is exactly the case that fails during upload. See [`manifests.md`](manifests.md).

`database: USER$` in an `app.yml` v2 manifest is shorthand: the CLI expands it to the caller's `USER$<user>`.
