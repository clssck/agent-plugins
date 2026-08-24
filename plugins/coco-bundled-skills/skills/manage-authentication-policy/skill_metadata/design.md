# Design — `database-security/iam/authentication/manage-authentication-policy`

> **Owner:** alan.hu@snowflake.com
> **Last reviewed:** 2026-05-08

## Purpose

Assists users with the Snowflake authentication-policy DDL (create / alter / drop / attach / detach) through a gated interactive workflow that consistently enforces the safety protocol: privilege pre-check, current-state capture via `DESC` + `GET_DDL`, per-DDL user approval, and revert instructions.

## When to use

Invoked interactively by a Snowflake admin (via Claude Code) when they explicitly want to create, modify, view, attach, detach, or drop an authentication policy, or discuss restricting auth methods / client types / MFA / PAT expiry / workload identity. Not part of any CI flow; every run expects a human at the terminal to answer AskUserQuestion prompts and approve each DDL before execution.

## Architecture

This skill provides an interactive workflow for managing Snowflake authentication policies. It follows a structured multi-step process:

1. **Current state presentation** — Queries existing authentication policies using SHOW AUTHENTICATION POLICIES and DESCRIBE to present what's currently configured. Shows both account-level and user-level policy attachments.

2. **Operation selection** — Presents available operations via AskUserQuestion:
   - Create a new authentication policy
   - Alter an existing policy
   - Drop a policy
   - Attach a policy (to account or user)
   - Detach a policy

3. **Privilege verification** — Checks that the current role has required privileges before proceeding:
   - SHOW policies: OWNERSHIP on policy OR USAGE on schema
   - Create policy: CREATE AUTHENTICATION POLICY on schema
   - Modify/Drop: OWNERSHIP on policy
   - Attach/detach account-level: APPLY AUTHENTICATION POLICY on Account
   - Attach/detach user-level: APPLY AUTHENTICATION POLICY on Account (global) OR on specific user

   Uses AskUserQuestion to confirm privilege status. Offers to switch roles if needed.

4. **Policy configuration** — For CREATE/ALTER, guides user through parameter selection:
   - `CLIENT_TYPES` — allowed client types (SNOWFLAKE_UI, SNOWSQL, DRIVERS, etc.)
   - `AUTHENTICATION_METHODS` — allowed auth methods (PASSWORD, SAML, OAUTH, KEYPAIR, etc.)
   - `MFA_AUTHENTICATION_METHODS` — methods requiring MFA
   - `SECURITY_INTEGRATIONS` — associated security integrations

5. **DDL generation and execution** — Generates the appropriate DDL (CREATE/ALTER/DROP/ALTER ACCOUNT SET/UNSET AUTHENTICATION POLICY) and presents for user approval before execution.

Uses AskUserQuestion extensively for the interactive flow. References Snowflake DDL syntax for authentication policies.

## Cost guards rationale

Interactive SQL skill with no additional LLM calls. Generates and optionally executes DDL statements.

Recommended ceilings:
- `cost_ceiling_usd`: 0.05 — orchestration tokens for interactive workflow
- `max_tokens_per_call`: 5000 — DDL generation and privilege tables
- `max_calls_per_invocation`: 12 — SHOW + DESCRIBE + privilege check + AskUser + DDL generate + execute
- `p95_latency_ms_target`: 60000 — multi-step interactive workflow with user pauses

## Production status

Experimental. Awaiting feedback from test users before moving this skill to beta.

## Severity tier rationale

**Tier 2 — High.** Blast radius is high in principle: the skill executes DDL against a live Snowflake account and can attach an account-level authentication policy that locks every user (including the admin running the skill) out of their preferred client or auth method. Reads are bounded (`SHOW AUTHENTICATION POLICIES`, `DESC`, `GET_DDL`, `CURRENT_ROLE()`) but writes include `CREATE / ALTER / DROP AUTHENTICATION POLICY` and `ALTER ACCOUNT | USER SET/UNSET AUTHENTICATION POLICY`. It is not Tier 1 because every DDL is gated behind an explicit user-approval AskUserQuestion, the modify/drop paths capture `GET_DDL` beforehand so the change can be reverted, and the workflow has no indirect side effects (no tickets, registry writes, Slack/JIRA, or merge gating).

## Failure modes

1. **Locking out users with overly restrictive policies** — An authentication policy that restricts CLIENT_TYPES or AUTHENTICATION_METHODS too aggressively can lock users (or the admin themselves) out of the account. Mitigation: the skill should warn about blast radius before attaching account-level policies and suggest testing with user-level attachment first.

2. **Privilege check incorrect for user-level policies** — The privilege model for user-level vs. account-level APPLY is nuanced. Misidentifying which privilege is needed may lead to failed DDL execution. Mitigation: the skill documents the full privilege matrix and verifies before attempting.

3. **Policy conflict between account and user levels** — A user-level policy overrides the account-level policy. Users may not realize they're creating a conflict. Mitigation: present both levels when showing current state and warn when creating a user-level policy that differs from account-level.

4. **MFA_AUTHENTICATION_METHODS without MFA enrollment** — Setting MFA requirements via policy for users who haven't enrolled in MFA will lock them out. Mitigation: recommend checking MFA enrollment status before applying MFA-required policies.

5. **DROP policy while attached** — Attempting to drop a policy that's still attached to accounts/users will fail. Mitigation: check POLICY_REFERENCES before DROP and offer to detach first.

## Trade-offs

1. **Interactive step-by-step vs. single-command** — The skill walks through operations interactively (select operation → verify privileges → configure → approve → execute). This is safer for sensitive auth configuration but slower for experienced admins.

2. **Privilege pre-check vs. attempt-and-catch** — Verifies privileges before attempting DDL rather than trying and handling errors. More user-friendly (clear error before wasting time) but adds an extra query step.

3. **Account-level focus vs. organization-level** — Manages policies within a single account. Organization-level authentication policy management (for multi-account setups) is not covered. This keeps the scope manageable but limits enterprise-scale operations.

4. **DDL approval gate vs. dry-run** — Shows DDL for user approval rather than using Snowflake's dry-run capability (which doesn't exist for DDL). This is the only option but means the user must manually validate the SQL.
