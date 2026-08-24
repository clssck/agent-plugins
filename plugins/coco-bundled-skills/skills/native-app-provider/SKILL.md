---
name: native-app-provider
description: >-
  REQUIRED entry point for **ALL** Snowflake Native App Framework work: app packages,
  manifest.yml, setup scripts, sharing data, testing, versions and patches, release channels and
  directives, publishing, upgrading consumers, marketplace listings, telemetry and health status
  (SYSTEM$REPORT_HEALTH_STATUS, log_level, trace_level, event definitions, event sharing,
  APPLICATION_STATE, lifecycle events), monitoring and debugging apps. Also for **ALL** SPCS
  (Snowpark Container Services) work inside native apps: adding containers, upgrading container
  services, building and pushing images, service specs, compute pools, service lifecycle. Also
  covers Streamlit UIs in apps (default_streamlit, get_active_session), restricted caller rights
  (RCR, EXECUTE AS RESTRICTED CALLER, GRANT CALLER, accessing consumer data with the consumer's
  privileges), and app-created agents and MCP servers (CREATE AGENT, CREATE MCP SERVER,
  DATA_AGENT_RUN, agent tools). Do NOT attempt native app development manually — invoke this skill
  first.
---

# Snowflake Native App Framework

This is a **routing skill**. It detects the user's intent and directs you to the correct sub-skill. You **MUST** load the sub-skill before doing any work — do NOT attempt native app tasks using only the information on this page.

## Running in Snowsight?

**⚠️ MANDATORY**: If your system prompt mentions Snowsight, load [`references/native-apps-snowsight.md`](references/native-apps-snowsight.md) before routing. It governs all env-specific decisions (CLI vs Workspaces vs stage fallback) for everything below.

## Key Concepts

- **Application Package**: Encapsulates the data content, application logic, metadata, and setup script required by an application. Also contains version and patch information
- **Manifest File** (`manifest.yml`): Defines configuration and setup properties required by the application, including the location of the setup script, versions, privileges, and references
- **Setup Script**: Contains SQL statements that run when a consumer installs or upgrades an application. Location is specified in the manifest file
- **Snowflake Native App**: The database object created in the consumer account when they install the application

## Snow CLI Support

The following sub-skills support an optional Snow CLI path alongside the default SQL path:

- **Setup** (`setup-app/SKILL.md`)
- **Deploy & Test** (`deploy-test/SKILL.md`)

When routing to one of these sub-skills, **load** `references/snow-cli-detection.md` and run the detection probe **before** loading the sub-skill. Pass the result (`snow_cli_available`, `snow_cli_version`) to the sub-skill.

For all other sub-skills, skip CLI detection — they use SQL only.

## Workflow Rules (All Sub-Skills)

These rules apply to **every** sub-skill loaded from the routing table below. Follow them regardless of which sub-skill you are executing.

### Rule 1: Generate a Task List Before Proceeding

Before executing any steps in a sub-skill, generate a numbered task list of the steps you plan to take and present it to the user for confirmation. **Do NOT begin work until the user approves the plan.** This educates the user on what will happen and surfaces potential issues early. Example:

```
Here's what I'll do:
1. Read manifest.yml and setup script
2. Add CREATE EXTERNAL ACCESS INTEGRATION privilege to manifest
3. Generate network rule and EAI in setup script
4. Generate app specification
5. Validate all objects

Shall I proceed?
```

### Rule 2: Generate a Task History After Completion

After completing all steps in a sub-skill, present a **task history summary** to the user. Include:

- **Steps taken**: Numbered checklist of what was done, with pass/fail status for each
- **Configuration**: Key names, roles, and settings used
- **Issues encountered**: Any errors hit and how they were resolved (or "None")
- **Next steps**: What the user should do next

### Rule 3: Generate a Knowledge Handoff for Issues

If any issues were encountered and resolved during execution, include a **knowledge handoff** section in the task history summary:

- **Issue & Resolution table**: What went wrong, root cause, and fix applied
- **Gotchas for future work**: Non-obvious lessons learned during this session
- **Key decisions made**: Approach selections or design choices that were made

### Rule 4: Consult Troubleshooting Before Speculating on Errors

When an error occurs during any step, **read `references/troubleshooting.md` first** before speculating on the cause. Common errors (privilege failures, object conflicts, missing grants) have known root causes documented there. Do not assume a cause (e.g., missing privileges) without first checking whether a simpler explanation (e.g., name collision with an existing account-level object) is listed.

## Routing Table

**Before starting any work**, scan the user's full request and identify ALL matching intents from the table below. If the request spans multiple intents (e.g., sharing data AND deploying a version), load each relevant sub-skill before performing that phase of work — do NOT attempt SQL from memory.

> **⚠️ Consumer intent check — evaluate first**: If the user says they have **installed** an app, are **using** an app as a consumer, or are experiencing issues with an installed app (permission errors, agent not working, MCP not working, app not visible), do NOT route to any provider sub-skill. Tell the user: *"It sounds like you're working as a consumer of an installed app — let me load the consumer skill instead."* Then invoke the `native-app-consumer` skill. Trigger phrases: "I installed", "I have installed", "installed app", "I am using the app", "the app returns an error", "permission error on the app", "agent not working", "MCP not working" (when combined with a reference to an installed app rather than one being built).

| Intent | Triggers | Sub-Skill to Load |
|--------|----------|--------------------|
| **Setup** — Create a new app from scratch | "create native app", "new app package", "set up app", "write manifest", "setup script", "build native app", "walk me through", "get started" | `setup-app/SKILL.md` |
| **Add Containers (SPCS)** — Add Snowpark Container Services to a native app | "container", "SPCS", "Snowpark Container Services", "compute pool", "service spec", "container_services", "grant_callback", "add containers", "specification file", "specification template", "container native app", "default_web_endpoint", "uses_gpu", "upgrade service", "version_initializer", "SPCS upgrade", "service upgrade", "ALTER SERVICE", "services", "service job" | `add-containers/SKILL.md` |
| **Shared Data** — Share tables/views with consumers | "share data", "share table", "secure view", "grant data", "external table", "Iceberg table", "REFERENCE_USAGE", "shared content", "data content" | `shared-data/SKILL.md` |
| **Deploy & Test** — Deploy files and test the app | "deploy app", "test app", "install app", "development mode", "upgrade app", "create application", "test from version", "test from stage" | `deploy-test/SKILL.md` |
| **Debug App** — Debug an app in a developer account | "debug app", "debug mode", "session debug", "inspect objects", "query history", "redaction", "DISABLE_APPLICATION_REDACTION", "SYSTEM$BEGIN_DEBUG_APPLICATION", "debug setup script", "see all objects", "view app queries", "reproduce consumer issues" | `debug-app/SKILL.md` |
| **Version & Release** — Register versions, manage release channels, publish | "register version", "add version", "add patch", "release channel", "publish app", "release directive", "upgrade consumers", "publish to customers" | `app-version-release/SKILL.md` |
| **Privilege Config** — Configure auto-granted privileges for the app | "privilege", "auto-grant", "manifest privileges", "app permissions", "privilege configuration", "consumer privileges", "missing privileges", "request privileges", "configure privileges" | `request-account-privilege/SKILL.md` |
| **External Access Integration** — Configure external API access (EAI) | "external access integration", "EAI", "external API", "network rule", "app spec EAI", "consumer EAI", "external access", "egress", "outbound API", "host_ports", "allowed_network_rules", "configuration_callback" | `request-external-access-integration/SKILL.md` |
| **Security Integration** — Configure OAuth / API authentication | "security integration", "OAuth", "API authentication", "CLIENT_CREDENTIALS", "AUTHORIZATION_CODE", "JWT_BEARER", "OAuth token endpoint", "OAuth scopes", "CREATE SECURITY INTEGRATION" | `request-security-integration/SKILL.md` |
| **Add Streamlit** — Add a Streamlit UI to an existing or new native app (warehouse runtime). **Load this whenever the request mentions Streamlit, even if you are building from scratch.** | "add streamlit", "streamlit native app", "native app UI", "streamlit frontend", "add UI", "streamlit in native app", "CREATE STREAMLIT", "default_streamlit", "environment.yml", "get_active_session", "with a streamlit", "streamlit UI", "native app with streamlit", "create app with streamlit", "with streamlit" | `add-streamlit-warehouse/SKILL.md` |
| **Object Access Request** — Request access to consumer objects | "object reference", "consumer table", "consumer object", "access consumer", "register_callback", "SYSTEM$REFERENCE", "request reference", "bind object", "reference definition", "consumer warehouse", "consumer view", "access existing object" | `request-object-access/SKILL.md` |
| **Add Agent / MCP Server** — Add a Cortex Agent, Snowflake-managed MCP server, or SPCS-hosted MCP server to the app; analyze required caller grants; test the agent | "add agent", "cortex agent in app", "app-created agent", "CREATE AGENT", "agent in native app", "agent tools", "MCP server native app", "CREATE MCP SERVER", "CREATE CUSTOM MCP SERVER", "app MCP", "caller grants for agent", "test agent in app", "DATA_AGENT_RUN", "app agent" | `add-agent-mcp/SKILL.md` |
| **Add RCR** — Add restricted caller rights to access consumer data or perform account-level operations | "restricted caller", "RCR", "EXECUTE AS RESTRICTED CALLER", "GRANT CALLER", "caller rights", "access consumer data", "consumer data from app", "restricted_callers_rights", "caller grants", "consumer's role", "caller's privileges", "consumer's privileges" | `use-rcr/SKILL.md` |
| **Configure Telemetry & Health** — Configure telemetry levels, event definitions, health reporting, object-level overrides | "health status", "logging", "tracing", "telemetry", "event definitions", "log_level", "trace_level", "metric_level", "SYSTEM$REPORT_HEALTH_STATUS", "configure telemetry", "health check", "health update" | `configure-telemetry-event-and-health-update/SKILL.md` |
| **Monitor App Telemetry & Status** — Query APPLICATION_STATE, lifecycle events, consumer health | "APPLICATION_STATE", "lifecycle events", "monitor app", "query health", "check app status", "upgrade tracking", "audit trail", "consumer health", "app monitoring" | `monitor-app-telemetry-event-and-status/SKILL.md` |
| **Configure Event Sharing** — Configure event routing tables, event accounts, event tables, and centralized event sharing to receive consumer telemetry across regions | "centralized event sharing", "event sharing", "event accounts", "event sharing setup", "event routing", "event routing table", "CREATE EVENT ROUTING TABLE", "ALTER ORGANIZATION SET EVENT ROUTING TABLE", "SYSTEM$SET_EVENT_SHARING_ACCOUNT_FOR_REGION", "provider event table", "event account region", "configure event sharing", "receive consumer telemetry", "cross-region events" | `configure-event-sharing/SKILL.md` |
| **Listing** — Share data back to provider or third-party accounts | "listing", "share data back", "CREATE SHARE", "CREATE LISTING", "data sharing", "compliance reporting", "telemetry", "shareback", "target accounts", "cross-region sharing", "auto-fulfillment" | `request-listing/SKILL.md` |
| **Publish Listing** — Create a listing to publish the app package to consumers | "publish listing", "create listing", "publish to marketplace", "make available to consumers", "share app", "private listing", "marketplace listing", "publish app to consumers" | `references/publish-listing.md` |
| **Manifest Reference** — Look up manifest field details | "manifest reference", "manifest fields", "manifest_version", "artifacts field", "privileges field", "references field" | `references/manifest-reference.md` |
| **Troubleshooting** — Look up common errors and fixes | "error", "not working", "failed", "troubleshooting" | `references/troubleshooting.md` |

**If the intent is ambiguous** or the user seems new to native apps, ask the user to clarify before proceeding.