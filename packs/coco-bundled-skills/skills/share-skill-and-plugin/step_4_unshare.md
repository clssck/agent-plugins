# Step 4: Unshare (Revoke All READ Grants)

Revoke every non-owner READ grant on the Cortex Extension. Production unshare
does **not** DROP the extension and does **not** ABORT — only REVOKEs.

## Resolve the FQN

From step 1 you should already have `<DB>`, `<SCHEMA>`, `<EXTENSION_NAME>`
(parsed from extension FQN or `snow://skill_catalog/...` URI). No file upload
in unshare — SQL only in both runtime modes.

Validate the three parts are non-empty.

## Enumerate Current Grantees

If [SKILL.md](SKILL.md) § **Cortex Extension — user-facing one-liner** has not
yet been shown during this run, surface it once now.

```sql
SHOW GRANTS ON CORTEX EXTENSION "<DB>"."<SCHEMA>"."<EXTENSION_NAME>";
```

Revoke list = rows where `PRIVILEGE = READ`, `GRANTED_TO = ROLE`,
`GRANTEE_NAME` is `PUBLIC` OR a role that is not an owner of the extension.
If empty → no-op success: report "no active READ grants on `<FQN>`; nothing
to revoke" and stop.

## ⚠️ MANDATORY STOPPING POINT

Show the full revoke list and FQN in chat, then call `ask_user_question` per
share_interactive_prompts.md
§ **Unshare confirm**. Do NOT run any REVOKE until the user confirms.

## Execute REVOKEs

Iterate in order. Track `<revoked_count>` and `<total>`:

```sql
REVOKE READ ON CORTEX EXTENSION "<DB>"."<SCHEMA>"."<EXTENSION_NAME>"
  FROM ROLE "<ROLE_UPPERCASE>";
```

## Partial-Failure Message

On REVOKE failure, stop and surface ONE of these **verbatim**:

- `<revoked_count> == 0`:
  > Failed to revoke artifact read for role `<role>`: `<error>` No READ
  > grants were revoked before the failure.
- `<revoked_count> > 0`:
  > Failed to revoke artifact read for role `<role>`: `<error>` Some
  > READ grants were already revoked (`<revoked_count>` of
  > `<total>`); retry unshare to remove the remaining grants.

Do NOT retry silently — user re-runs unshare to clear the remainder.

## Do NOT

- `DROP CORTEX EXTENSION`
- `ALTER … ABORT`
- toggle DISCOVERABLE
- delete the share schema

## Next

Continue to `step_5_report_result.md`.
