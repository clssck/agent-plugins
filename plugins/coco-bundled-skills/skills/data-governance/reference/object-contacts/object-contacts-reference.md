# Object Contacts — Reference

Supporting reference material for [`workflows/object-contacts.md`](../../workflows/object-contacts.md).

---

## Common Use Cases

### Use Case 1: New Database Setup
1. Create a governance contacts schema (e.g., `GOVERNANCE_DB.CONTACTS`)
2. Create contacts: data steward, support, access approver
3. Assign at database level → all objects inherit automatically
4. Run Option 5 contact report to verify coverage

### Use Case 2: Migrate an Existing Database
1. Run Option 5 to identify objects without contacts
2. Create the necessary contacts (Option 2)
3. Assign at schema level for inheritance (Option 3A)
4. Override specific tables if they need a different steward (Option 3B)
5. Run Option 5 again to verify

### Use Case 3: Change Data Steward (Department Reorg)
1. Create the new contact (Option 2)
2. Use Option 4 to find all objects with the old contact
3. Reassign at schema/database level (Option 3A)
4. Drop the old contact once no longer referenced

### Use Case 4: Compliance Audit
1. Run Option 5 (comprehensive report)
2. Identify objects without contacts
3. Export to a Snowflake table for audit documentation
4. Assign missing contacts before the audit deadline

---

## Best Practices

### ✅ Do's
- **Use schema-level assignment** for consistent governance (Option 3A)
- **Store contacts in a dedicated schema** (e.g., `GOVERNANCE_DB.CONTACTS`)
- **Use descriptive names** (e.g., `data_stewards_sales`, `support_analytics`)
- **Use email distribution lists** — avoids individual-user dependency
- **Run Option 5 regularly** to spot coverage gaps

### ❌ Don'ts
- **Don't assign to individual tables** unless granular control is truly needed
- **Don't hardcode individual usernames** in contacts (use `USERS` groups or distribution lists)
- **Don't forget to verify** with `GET_CONTACTS` after any change
- **Don't mix contact purposes** — keep steward, support, and approver contacts separate

---

## Troubleshooting

### Contact Not Appearing on Object
```sql
-- 1. Verify contact exists
SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACTS
WHERE contact_name = '<name>' AND deleted IS NULL;

-- 2. Check direct assignment
SELECT * FROM TABLE(SNOWFLAKE.CORE.GET_CONTACTS('<object>', 'TABLE'));

-- 3. Check references (direct + inherited)
SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES
WHERE contact_name = '<name>' AND deleted IS NULL;
```

### Insufficient Privileges
| Action | Required Privilege |
|---|---|
| Create contact | `CREATE CONTACT` on schema + `USAGE` on schema/database |
| Assign contact | `APPLY CONTACT` on account **or** (`APPLY` on contact + `OWNERSHIP` on object) |
| View contacts | Any privilege on the object |
| Modify contact | `OWNERSHIP` or `MODIFY` on contact |
| Drop contact | `OWNERSHIP` on contact |

**Grant example:**
```sql
GRANT APPLY CONTACT ON ACCOUNT TO ROLE GOVERNANCE_ADMIN;
GRANT CREATE CONTACT ON SCHEMA GOVERNANCE_DB.CONTACTS TO ROLE GOVERNANCE_ADMIN;
```

### Inherited Contact Not Showing
- Verify the parent object has a contact assigned
- Ensure the child object doesn't have a direct assignment for the same purpose (it overrides)
- Use `GET_CONTACTS` to inspect the full inheritance chain

---

## Quick Reference SQL

```sql
-- Create contact
CREATE CONTACT <db>.<schema>.<name>
  EMAIL_DISTRIBUTION_LIST = 'email@company.com';

-- Assign contact
ALTER TABLE <db>.<schema>.<table>
  SET CONTACT STEWARD = <contact_name>;

-- View contacts (including inherited)
SELECT * FROM TABLE(SNOWFLAKE.CORE.GET_CONTACTS('<object>', 'TABLE'));

-- Find all objects for a contact
SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES
WHERE contact_name = '<name>' AND deleted IS NULL;

-- Remove contact
ALTER TABLE <db>.<schema>.<table>
  UNSET CONTACT STEWARD;
```

---

## External References

- [Snowflake Contacts Documentation](https://docs.snowflake.com/en/user-guide/contacts-using)
- [CREATE CONTACT](https://docs.snowflake.com/en/sql-reference/sql/create-contact)
- [ALTER … SET CONTACT](https://docs.snowflake.com/en/sql-reference/sql/alter-table)
- [GET_CONTACTS Function](https://docs.snowflake.com/en/sql-reference/functions/get_contacts)
- [ACCOUNT_USAGE.CONTACTS](https://docs.snowflake.com/en/sql-reference/account-usage/contacts)
- [ACCOUNT_USAGE.CONTACT_REFERENCES](https://docs.snowflake.com/en/sql-reference/account-usage/contact_references)
