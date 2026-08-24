---
name: integrations
description: >
  Create, replace, alter, drop, describe, and show Snowflake integrations.
  Covers API, catalog, external access, notification, security, and storage integration types.
  Use when the user wants to manage integrations or asks about integration SQL commands.
---

# Snowflake Integration Commands

Integration commands enable you to manage your integrations in Snowflake.

## Routing

Route to the matching sub-skill based on the user's intent. If the user asks about a specific integration type (API, catalog, storage, etc.), prefer the type-specific sub-skill over the general one.

## Sub-Skills by Category

### General

| Command | Sub-Skill | When to Use |
|---------|-----------|-------------|
| CREATE INTEGRATION | `create-integration/SKILL.md` | Create or replace an integration (generic overview — use a type-specific command when available) |
| ALTER INTEGRATION | `alter-integration/SKILL.md` | Modify or replace an existing integration (generic — use a type-specific command when available) |
| SHOW INTEGRATIONS | `show-integrations/SKILL.md` | List integrations in the account, optionally filtered by type |
| DESCRIBE INTEGRATION | `describe-integration/SKILL.md` | Describe properties of an integration of any type |
| DROP INTEGRATION | `drop-integration/SKILL.md` | Remove any type of integration from the account (cannot be recovered) |

### API

| Command | Sub-Skill | When to Use |
|---------|-----------|-------------|
| CREATE API INTEGRATION | `create-api-integration/SKILL.md` | Create or replace an API integration for AWS API Gateway, Azure API Management, Google Cloud API Gateway, or Git repositories |
| ALTER API INTEGRATION | `alter-api-integration/SKILL.md` | Modify or replace an existing API integration (AWS API Gateway, Azure API Management, Google Cloud API Gateway, or Git repository) |

### Catalog

| Command | Sub-Skill | When to Use |
|---------|-----------|-------------|
| CREATE CATALOG INTEGRATION | `create-catalog-integration/SKILL.md` | Create or replace a catalog integration for Apache Iceberg tables (AWS Glue, Object Store, Snowflake Open Catalog, Apache Iceberg REST, or SAP Business Data Cloud) |
| ALTER CATALOG INTEGRATION | `alter-catalog-integration/SKILL.md` | Modify an existing catalog integration (REST auth credentials, refresh interval, comment) |
| DROP CATALOG INTEGRATION | `drop-catalog-integration/SKILL.md` | Remove a catalog integration from the account (cannot be recovered) |
| SHOW CATALOG INTEGRATIONS | `show-catalog-integrations/SKILL.md` | List catalog integrations with their metadata and properties |
| DESCRIBE CATALOG INTEGRATION | `describe-catalog-integration/SKILL.md` | Describe properties of a specific catalog integration |

### External Network Access

| Command | Sub-Skill | When to Use |
|---------|-----------|-------------|
| CREATE EXTERNAL ACCESS INTEGRATION | `create-external-access-integration/SKILL.md` | Create an external access integration for network access to external locations from a UDF or procedure handler (network rules, authentication secrets) |
| ALTER EXTERNAL ACCESS INTEGRATION | `alter-external-access-integration/SKILL.md` | Modify or replace an existing external access integration for UDF or procedure handlers |

### Notification

| Command | Sub-Skill | When to Use |
|---------|-----------|-------------|
| CREATE NOTIFICATION INTEGRATION | `create-notification-integration/SKILL.md` | Create or replace a notification integration for cloud message queuing services (Azure Event Grid, Google Pub/Sub, Amazon SNS), email services, or webhooks |
| ALTER NOTIFICATION INTEGRATION | `alter-notification-integration/SKILL.md` | Modify or replace an existing notification integration (cloud messaging, email, or webhook) |
| DESCRIBE NOTIFICATION INTEGRATION | `describe-notification-integration/SKILL.md` | Describe properties of a specific notification integration |
| SHOW NOTIFICATION INTEGRATIONS | `show-notification-integrations/SKILL.md` | List notification integrations with their metadata and properties |

### Security

| Command | Sub-Skill | When to Use |
|---------|-----------|-------------|
| CREATE SECURITY INTEGRATION | `create-security-integration/SKILL.md` | Create or replace a security integration (SCIM, SAML2, OAuth, or API Authentication) for interfacing with third-party services |
| ALTER SECURITY INTEGRATION | `alter-security-integration/SKILL.md` | Modify or replace an existing security integration (SCIM, SAML2, OAuth, or API Authentication) |
| SHOW DELEGATED AUTHORIZATIONS | `show-delegated-authorizations/SKILL.md` | List active delegated authorizations for a user, integration, or the entire account |

### Storage

| Command | Sub-Skill | When to Use |
|---------|-----------|-------------|
| CREATE STORAGE INTEGRATION | `create-storage-integration/SKILL.md` | Create or replace a storage integration for Amazon S3, Google Cloud Storage, or Microsoft Azure Blob Storage |
| ALTER STORAGE INTEGRATION | `alter-storage-integration/SKILL.md` | Modify or replace an existing storage integration (Amazon S3, Google Cloud Storage, or Microsoft Azure Blob Storage) |
