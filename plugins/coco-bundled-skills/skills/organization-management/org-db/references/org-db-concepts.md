# Organization Database Concepts

Core concepts and architecture for the Organization Database (Org DB) feature.

## What is Organization Database?

The **Organization Database** (ORGANIZATION$DB) is a special, automatically-provisioned database that serves as the single source of truth for organization-wide schema objects. It enables centralized definition and management of objects that need to be consistent across all accounts in a Snowflake organization.

## Core Principles

### 1. Define Once, Use Everywhere

Create objects once in the organization account, and they're automatically available in all child accounts:

```
Organization Account (GLOBALORGADMIN)
    ↓ Creates org tag
    ↓
ORGANIZATION$DB.TAGS.COST_CENTER
    ↓ Replicates
    ↓
All Child Accounts (read-only)
    ↓ Apply tag
    ↓
Tagged Resources
```

### 2. Single Source of Truth

- All org-wide object definitions live in one place
- No divergence between accounts
- Centralized governance and control
- Consistent naming and definitions

### 3. Automatic Replication

- No manual configuration needed
- Changes propagate automatically
- All accounts receive updates simultaneously
- Zero-cost replication

## Architecture

### Database Structure

```
ORGANIZATION$DB (reserved name)
├── TAGS (default schema for org tags)
│   ├── COST_CENTER (tag)
│   ├── PROJECT (tag)
│   └── ENVIRONMENT (tag)
├── GOVERNANCE (optional custom schema)
│   └── DATA_CLASSIFICATION (tag)
└── [Future schemas for other org objects]
```

### Account Types and Access

| Account Type | Database State | Capabilities | Role Required |
|--------------|----------------|--------------|---------------|
| **Organization Account** | Read-Write | Create, alter, drop org objects | GLOBALORGADMIN |
| **Child Accounts** | Read-Only | View and apply org objects | ACCOUNTADMIN or delegated |

### Replication Model

```
Organization Account
       ↓
   GLOBALORGADMIN creates/modifies object
       ↓
   Change captured
       ↓
   Automatic replication
       ↓
   All Child Accounts updated
       ↓
   Read-only database reflects changes
```

**Replication Details**:
- **Scope**: All accounts in the organization
- **Content**: All objects in ORGANIZATION$DB (currently tags)
- **Cost**: Zero - no replication charges
- **Management**: Fully automatic, no customer configuration

## Naming Convention

### Reserved Database Name

`ORGANIZATION$DB` is a **reserved name** that:
- Cannot be used for customer-created databases
- Ensures unique identification across all accounts
- Signals that this is a system-managed, organization-level database

### Fully Qualified Names

Org objects always use the fully qualified name pattern:

```
ORGANIZATION$DB.<schema>.<object_name>
```

Examples:
- `ORGANIZATION$DB.TAGS.COST_CENTER` (org tag)
- `ORGANIZATION$DB.GOVERNANCE.DATA_CLASSIFICATION` (org tag in custom schema)

This ensures no ambiguity between org-level and account-level objects.

## Organization Tags

### What are Organization Tags?

Centralized tag definitions that are:
- Created once in the organization account
- Automatically replicated to all child accounts
- Applied to resources for consistent classification
- Used for cost attribution, governance, and organization-wide reporting

### Tag Lifecycle

```
1. CREATE TAG (org account, GLOBALORGADMIN)
   ↓
2. Automatic replication to all accounts
   ↓
3. APPLY TAG (any account, ACCOUNTADMIN+)
   ↓
4. Tag assignment tracked in ACCOUNT_USAGE.TAG_REFERENCES
   ↓
5. Org-wide visibility via ORGANIZATION_USAGE.TAG_REFERENCES
```

### Tag Properties

**Allowed Values**:
- Tags can have constrained allowed values (recommended)
- Or accept any string value
- Constraints are enforced across all accounts

**Example with allowed values**:
```sql
CREATE TAG ORGANIZATION$DB.TAGS.COST_CENTER
  ALLOWED_VALUES 'Marketing', 'Sales', 'Finance', 'Engineering';
```

**Example without constraints**:
```sql
CREATE TAG ORGANIZATION$DB.TAGS.PROJECT;
```

## Read-Only Enforcement

### In Child Accounts

Child accounts receive ORGANIZATION$DB as a **read-only database**:

```sql
-- ✅ Allowed: View org tags
SHOW TAGS IN DATABASE ORGANIZATION$DB;

-- ✅ Allowed: Apply org tag to resource
ALTER WAREHOUSE my_wh 
  SET TAG ORGANIZATION$DB.TAGS.COST_CENTER = 'Marketing';

-- ❌ NOT Allowed: Modify org tag definition
ALTER TAG ORGANIZATION$DB.TAGS.COST_CENTER 
  ADD ALLOWED_VALUES 'Operations';
  
-- ❌ NOT Allowed: Create new org tag
CREATE TAG ORGANIZATION$DB.TAGS.NEW_TAG;

-- ❌ NOT Allowed: Drop org tag
DROP TAG ORGANIZATION$DB.TAGS.COST_CENTER;
```

### Why Read-Only?

- **Consistency**: Prevents local modifications that would break org-wide consistency
- **Governance**: Ensures centralized control
- **Integrity**: Prevents accidental or malicious changes

## Cost Model

Organization Database has **no charges** for:
- Database storage (metadata only, no data)
- Replication (automatic propagation to accounts)
- Tag creation or management
- Tag application to resources

## Current Limitations

### Single Database

- Only **one** organization database: ORGANIZATION$DB
- Cannot create additional org databases

### No Custom Visibility

- All org tags are visible in all accounts
- Cannot restrict visibility to specific accounts or groups

### Supported Object Types

Currently supported in ORGANIZATION$DB:
- **Tags**: Full support
- **Schemas**: Can create custom schemas

NOT supported:
- Policies (masking, row access, etc.)
- Tables, views, or other data objects
- Stored procedures or UDFs

## Name Collisions

### Org Tags vs Account Tags

It's possible to have tags with the same name at org and account levels:

```sql
-- Org tag
ORGANIZATION$DB.TAGS.COST_CENTER

-- Account-level tag (different database)
FINANCE_DB.TAGS.COST_CENTER
```

These are **distinct objects** because they have different fully qualified names.

**Best Practices**:
- Prefer org tags for organization-wide consistency
- Use account tags only for account-specific classifications
- Document which tags are org-level vs account-level
- Consider migrating account tags to org tags if consistency is needed

## Organization Lifecycle

### Account Transfers

When an account is transferred to a different organization:
- Existing ORGANIZATION$DB is dropped during transfer
- New ORGANIZATION$DB from target org is provisioned
- All org tag assignments are removed
- Account must re-apply tags using new org's tag definitions

### Organization Merges

When two organizations merge:
- Target org's ORGANIZATION$DB is preserved
- Source org's ORGANIZATION$DB is dropped
- Accounts from source org receive target org's ORGANIZATION$DB

## Security and Access Control

### Role-Based Access Control (RBAC)

#### Organization Account

| Role | Privileges |
|------|-----------|
| GLOBALORGADMIN | Full control over ORGANIZATION$DB (create, alter, drop objects) |
| Other roles | Can be granted access via delegation from GLOBALORGADMIN |

#### Child Accounts

| Role | Privileges |
|------|-----------|
| ACCOUNTADMIN | View org objects, apply org tags to resources |
| Other roles | Can be granted APPLY privileges to use org tags |

### Database Ownership

- **Organization Account**: Database role (ORGANIZATION_DB_ADMIN) owns the database
- **Child Accounts**: SYSTEM owns the replicated database (read-only)

## References

- Parent skill: `organization-management/org-db/SKILL.md`
- Tag management: `organization-management/org-db/org-tags/SKILL.md`
- Discovery: `organization-management/org-db/org-db-discovery/SKILL.md`
