---
name: certify-object
description: >
  Apply, verify, and manage the SNOWFLAKE.CORE.CERTIFICATION_STATUS tag on Snowflake objects
  to mark them as trusted sources in the data catalog.
  Triggers: certify this table, mark as certified, apply certification, tag as trusted,
  mark this object as certified, certify it.
  Use when: user wants to mark a specific Snowflake object as certified.
---

# Object Certifier

Apply `SNOWFLAKE.CORE.CERTIFICATION_STATUS = 'CERTIFIED'` to a confirmed Snowflake object so
future users can discover it as a trusted source.

## When to Use

- User explicitly asks to certify or mark a specific object as trusted
- User says "certify it", "mark it as certified", "tag this as trusted"

## Prerequisites

- The target object (`<database>.<schema>.<table_or_view>`) must already be identified
- `APPLY TAG` privilege on `SNOWFLAKE.CORE.CERTIFICATION_STATUS`, or `ACCOUNTADMIN` role

## Workflow

### Step 1: Confirm the Target Object

**Goal:** Confirm which object to certify before making any changes.

If the user has not already named a specific object, ask:
```
Which object would you like to certify? Please provide the fully qualified name:
  <database>.<schema>.<table_or_view>
```

### Step 2: Ask Permission (Unless Pre-Authorized)

**Goal:** Get explicit user consent before applying the tag.

If the user has not already given permission (e.g., said "certify it" or "you have my permission"), ask:
```
Would you like me to mark <database>.<schema>.<table> as CERTIFIED?
This will set the SNOWFLAKE.CORE.CERTIFICATION_STATUS tag to 'CERTIFIED',
making it discoverable as a trusted source in the data catalog.
(Yes / No)
```

**If user declines, stop entirely.**

### Step 3: Apply the Certification Tag

**Goal:** Set `SNOWFLAKE.CORE.CERTIFICATION_STATUS = 'CERTIFIED'` on the target object.

For tables:
```sql
ALTER TABLE <database>.<schema>.<table>
  SET TAG SNOWFLAKE.CORE.CERTIFICATION_STATUS = 'CERTIFIED';
```

For views:
```sql
ALTER VIEW <database>.<schema>.<view>
  SET TAG SNOWFLAKE.CORE.CERTIFICATION_STATUS = 'CERTIFIED';
```

**⚠️ If the ALTER fails due to permissions**, do not block the workflow. Inform the user:
```
To apply the CERTIFIED tag, your role needs the APPLY TAG privilege on SNOWFLAKE.CORE.CERTIFICATION_STATUS.
An admin can grant it with:
  GRANT APPLY ON TAG SNOWFLAKE.CORE.CERTIFICATION_STATUS TO ROLE <your_role>;
You can then run:
  ALTER TABLE <database>.<schema>.<table> SET TAG SNOWFLAKE.CORE.CERTIFICATION_STATUS = 'CERTIFIED';
```

### Step 4: Verify the Tag Was Applied

**Goal:** Confirm the tag is live on the object.

```sql
SELECT SYSTEM$GET_TAG('SNOWFLAKE.CORE.CERTIFICATION_STATUS', '<database>.<schema>.<table>', 'TABLE');
```

For views, use `'VIEW'` as the third argument.

If the result is `'CERTIFIED'`, proceed. If null or error, report the issue to the user.

### Step 5: Inform the User

```
✅ Marked <database>.<schema>.<table> as CERTIFIED.

Future users can find all certified objects with:
  SELECT OBJECT_DATABASE, OBJECT_SCHEMA, OBJECT_NAME, DOMAIN
  FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
  WHERE TAG_NAME = 'CERTIFICATION_STATUS' AND TAG_VALUE = 'CERTIFIED'
    AND TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE';

Note: TAG_REFERENCES has up to 2–3 hour lag. The tag is live immediately
but may not appear in this view right away.
```

## Stopping Points

- ✋ Step 1: If no object identified, ask for it
- ✋ Step 2: Ask permission before tagging (unless user pre-authorized); stop if declined
- ✋ Step 3: If tagging fails due to permissions, provide exact SQL and stop

## Output

- `SNOWFLAKE.CORE.CERTIFICATION_STATUS = 'CERTIFIED'` applied to the target object
- Verification via `SYSTEM$GET_TAG` confirming the tag is live
- SQL for the user to run if permissions are insufficient

## Notes

- `SNOWFLAKE.CORE.CERTIFICATION_STATUS` is a built-in Snowflake tag — no need to create it
- `TAG_REFERENCES` has up to 2–3 hour lag; `SYSTEM$GET_TAG` reflects the tag immediately
- To remove certification: `ALTER TABLE <db>.<schema>.<table> UNSET TAG SNOWFLAKE.CORE.CERTIFICATION_STATUS`
