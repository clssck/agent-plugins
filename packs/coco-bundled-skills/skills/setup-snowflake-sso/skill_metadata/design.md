# Design — `database-security/iam/authentication/setup-snowflake-sso`

> **Owner:** paulo.aguiar@snowflake.com
> **Last reviewed:** 2026-05-07 (seeded)

## Purpose

Guides users through end-to-end SSO configuration for Snowflake with their Identity Provider (Okta, Microsoft Entra ID, or generic SAML 2.0), including SCIM provisioning and advanced scenarios like Allowed Interfaces and Auto Redirect.

## When to use

Triggered interactively when a user asks to set up SSO, configure SAML, set up SCIM provisioning, configure Allowed Interfaces, or add a Snowflake Intelligence tile to their IdP.

## Architecture

This skill orchestrates SSO configuration for Snowflake across multiple Identity Providers (IdPs) using a **workflow dispatcher pattern** with sub-workflow files.

**Entry flow:**
1. Security notice display (mandatory) — Presents three configuration methods: Manual UI, Self-service API (curl commands for user to run), and Automated API (agent executes curls).
2. Account info gathering — Auto-executes `SELECT CURRENT_ORGANIZATION_NAME(), CURRENT_ACCOUNT_NAME()` to build the normalized Snowflake URL.
3. Existing integration check — Runs `SHOW SECURITY INTEGRATIONS` to detect pre-existing SAML2/SCIM integrations.
4. Task routing — User selects SSO Setup, Advanced Scenarios, or Snowflake Intelligence Tile.
5. IdP selection — Routes to provider-specific workflow files.

**Sub-workflows (loaded as separate files):**
- `workflows/okta-sso.md` — Okta SAML + SCIM
- `workflows/entra-sso.md` — Microsoft Entra ID SAML + SCIM
- `workflows/generic-saml.md` — Generic SAML 2.0
- `workflows/advanced-scenarios.md` — Allowed Interfaces, Auto Redirect
- `workflows/snowflake-allowed-interfaces.md` — SQL-based interface restrictions
- `workflows/okta-allowed-interfaces.md` / `entra-allowed-interfaces.md` — SCIM-based
- `workflows/add-snowflake-intelligence-tile.md` — IdP app launcher tile
- `workflows/okta-api-token-setup.md` — Okta API token for automated method

**Key constraints:**
- Agent must NEVER install CLI tools, SDKs, or sign in to IdPs.
- IdP API calls only when user explicitly opts into "Automated (API)" method.
- Step-by-step delivery enforced (one section at a time, with AskUserQuestion confirmations).
- Error handling requires showing errors to user and offering choices rather than auto-diagnosing.

## Cost guards rationale

The skill is primarily conversational guidance with minimal SQL (2-3 queries for account info and integration checks). The bulk of "work" is presenting instructions and executing user-approved curl commands.

- `cost_ceiling_usd`: 0.10 (long multi-turn conversation with many AskUserQuestion interactions)
- `max_tokens_per_call`: 6000 (sub-workflows are verbose with full curl command templates)
- `max_calls_per_invocation`: 25 (many back-and-forth steps across the full SSO setup)
- `p95_latency_ms_target`: 60000 (heavily interactive, human-paced workflow)

## Failure modes

1. **IdP API call fails (Automated mode)** — Agent cannot auto-diagnose per skill rules; must show error and offer choices. If user picks "Run diagnostic commands" the agent can investigate, but the error may be opaque (wrong tenant ID, expired token).
2. **Snowflake URL normalization error** — Underscores in account names must become hyphens; if the org/account names contain unexpected characters, the normalized URL may be wrong, causing SSO configuration to point to the wrong endpoint.
3. **Existing integration conflict** — If SAML2 integration already exists with different settings, creating a new one may fail or override. Skill offers "View existing" / "Modify existing" / "Create new" but modification workflows are complex.
4. **SCIM token exposure** — In Automated mode, SCIM bearer tokens appear in curl commands. If conversation logs are shared, tokens could leak. Mitigation: Skill uses environment variables for tokens but user must set them up.
5. **IdP-specific API changes** — Hardcoded API paths (Okta `/api/v1/apps`, Entra Graph API) may break if providers change endpoints. No version pinning.

## Trade-offs

1. **Three configuration methods vs. one** — Adds complexity but serves different security postures: orgs that prohibit agent API access use Manual, power users use Automated.
2. **Sub-workflow files vs. monolithic** — Keeps the main SKILL.md manageable (~300 lines) but requires 9+ referenced files to be present. File loading failures break the skill silently.
3. **Step-by-step delivery vs. all-at-once** — Prevents information overload but makes the workflow slower. Users who know what they're doing can't skip ahead.
4. **No IdP installation/sign-in vs. full automation** — Security boundary: agent never touches user's IdP directly (except via approved API calls), reducing blast radius of agent errors.

## Production status

In production. The skill is listed in `prod_manifest.yaml` (prod channel) and available to all Cortex Code users. Usage is uncommon since SSO setup is a one-time configuration task per account, so invocations are infrequent but can be of high-value.

## Severity tier rationale

**Tier: High** 

The skill's blast radius is limited:
- **Reads:** `SHOW SECURITY INTEGRATIONS` and `SELECT CURRENT_ORGANIZATION_NAME()/CURRENT_ACCOUNT_NAME()`
- **Writes:** The skill itself does not execute DDL (CREATE/ALTER SECURITY INTEGRATION) autonomously, it provides SQL for the user to review and approve, or generates curl commands targeting the IdP API. In Automated mode, curl commands are executed only after explicit user confirmation.
- **Production side effects:** Can create/modify SAML2 and SCIM security integrations in Snowflake (if user approves), and can make API calls to Okta/Entra (if user opts into Automated mode). Misconfiguration could lock users out of SSO or create duplicate integrations.
