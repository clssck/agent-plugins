# Step 3: Apply Audience Grants and DISCOVERABLE

Bring the extension's `READ` grants and `DISCOVERABLE` to the user-requested
state. Revoke stale grants on re-share.

If `<intent> = share-resync`, **skip this step entirely**.

## Audience modes (mandatory wording)

**If `<share_choice>` is already set** (collected in step 1 ambiguous reshare
combined stop, or in step 2 before plugin Option A CLI), skip this question
entirely — use the stored values directly.

Otherwise, call `ask_user_question` per
share_interactive_prompts.md
§ **Locked audience labels**. Do not substitute synonyms or add a fourth
choice. If the user picks **To a specific ROLE…**, ask once in chat for
comma-separated role names.

**SQL mapping (after the user chooses):**

| User choice | `READ` grants | `DISCOVERABLE` |
|-------------|---------------|----------------|
| 1 | `TO ROLE PUBLIC` | `TRUE` |
| 2 | `TO ROLE PUBLIC` | `FALSE` |
| 3 | `TO ROLE "<each role>"` (one `GRANT` per role) | `TRUE` |

Split role names on commas, trim, uppercase for quoting.

When collecting fresh audience here, set `<share_choice>`, `<share_roles>`,
and `<discoverable_value>` per step 2 § Collect share options mapping.

## Inspect Current Grants (re-share only)

```sql
SHOW GRANTS ON CORTEX EXTENSION "<DB>"."<SCHEMA>"."<EXTENSION_NAME>";
```

Filter: `PRIVILEGE = READ`, `GRANTED_TO = ROLE`, `GRANTEE_NAME` is `PUBLIC`
OR a role not holding `OWNERSHIP` on the same object.

## Compute Diffs

- `<revoke_set>` = `<current> \ <desired>`
- `<grant_set>` = `<desired> \ <current>`

## ⚠️ MANDATORY STOPPING POINT

If `<revoke_set>` is non-empty, show every role in chat, then call
`ask_user_question` per
share_interactive_prompts.md
§ **Re-share REVOKE narrow confirm** before any REVOKE.

## Revoke Stale Grants, Then Apply New Grants

Run REVOKEs first:

```sql
REVOKE READ ON CORTEX EXTENSION "<DB>"."<SCHEMA>"."<EXTENSION_NAME>"
  FROM ROLE "<ROLE_UPPERCASE>";

GRANT READ ON CORTEX EXTENSION "<DB>"."<SCHEMA>"."<EXTENSION_NAME>"
  TO ROLE "<ROLE_UPPERCASE>";
```

**Publish-path REVOKE failure** — stop verbatim:

> Failed to revoke read privilege from role `<role>`: `<error>`.

## Set DISCOVERABLE

Run **only after** every grant succeeded:

```sql
ALTER CORTEX EXTENSION "<DB>"."<SCHEMA>"."<EXTENSION_NAME>"
  SET DISCOVERABLE = TRUE;   -- or FALSE per <discoverable_value>
```

## Resolve the Share URI

```sql
DESCRIBE CORTEX EXTENSION "<DB>"."<SCHEMA>"."<EXTENSION_NAME>";
```

Rewrite `snow://cortex_extension/` → `snow://skill_catalog/` when present.

## Next

Continue to `step_5_report_result.md`.
