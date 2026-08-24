# Horizon Catalog — MFA And Compliance

Load `_preamble.md` for shared identifier rules, custom instructions, and join relationships. Replace `__VIEW` placeholders with `SNOWFLAKE.ACCOUNT_USAGE.<VIEW>`.

This intent uses the `USERS` view defined in `roles-and-users.md`. Exclude disabled and deleted users by default: `DISABLED = FALSE` and `DELETED_ON IS NULL` (include them only when the user explicitly asks). `DISABLED` is a `VARIANT` holding a JSON boolean, so `DISABLED = FALSE` is the correct, invariant-consistent form.

## Verified queries

```yaml
verified_queries:
  - name: users enabled MFA
    question: "Do users MDOHERTY and HRANJAN have MFA enabled?"
    sql: |
      SELECT
        name AS user_name,
        has_mfa AS mfa_enabled
        FROM
        __USERS
        WHERE
        name IN ('MDOHERTY', 'HRANJAN')
        AND deleted_on IS NULL
        AND disabled = FALSE;

  - name: not changed initial password
    question: "Can I identify users who have never changed their initial password?"
    sql: |
      SELECT
        u.name AS username,
        u.login_name,
        u.created_on,
        u.password_last_set_time
      FROM
        __users AS u
      WHERE
        u.deleted_on IS NULL
        AND u.has_password = TRUE
        AND (u.password_last_set_time IS NULL OR u.password_last_set_time < DATEADD(SECOND, 1, u.created_on))
      ORDER BY
        u.created_on DESC NULLS LAST;

```
