---
name: create-native-app-listing
description: "Create a Native App data product for Snowflake Marketplace. Use when: provider wants to build a full native application with Streamlit UI, stored procedures, UDFs, SPCS containers, or complex logic. Triggers: native app, application package, setup script, manifest, streamlit app, SPCS, container services, native application."
---

# Native App

> ⚠️ **MANDATORY — READ BEFORE PROCEEDING**
>
> **Do NOT build the app using content from this file.** The content below is Marketplace-specific reference context only.
> You MUST invoke `skill(command: "native-app-provider")` as your next action before writing any SQL, manifest content, or setup scripts. Do not skip this step even if the build details here seem sufficient.

Full-featured applications with custom logic, Streamlit UIs, stored procedures, UDFs, and optional Snowpark Container Services (SPCS). Runs inside the consumer's account.

> **How this skill works:** Steps marked **Execute** run SQL directly. Steps marked **Invoke** hand off to another skill. Steps marked **Tell the provider** give the provider UI steps to follow in Snowsight or Provider Studio.

> If the application does data processing **on the provider's platform** (not inside Snowflake), it should be a Connected App, not a Native App.

### Phase 1: Design & Develop

Before writing a line of code, review the [Enforced Requirements](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps#native-applications). Key design principles:

**Core functionality must run on Snowflake.** The consumer's UI, configuration, and execution of logic must happen inside Snowflake. Calling external APIs is fine — but the app cannot redirect consumers off-platform for setup or core use.
- Allowed: Streamlit UI inside Snowflake that calls your API, writes results to a Snowflake table
- Not allowed: App that just links consumers to `mycompany.com/configure`

**Authentication methods.** Username/password is deprecated. For key-pair auth, providers must generate the key pair and share only the public key with the consumer — consumers must never be asked to share their private key. Other acceptable methods: PAT tokens and OAuth.

**Manifest version: 1 vs. 2**
- `manifest_version: 1` — Requires consumers to manually grant privileges through the app's Streamlit UI via the Permissions SDK.
- `manifest_version: 2` — Recommended. Privileges are declared directly in the manifest; consumers approve them at install/upgrade time without manual steps. Required for external access integrations, security integrations, and data sharing.

**Warehouse: create vs. consumer-granted**

| Consideration | App creates own warehouse | Consumer grants their warehouse |
|---|---|---|
| Installation | Consumer approves CREATE WAREHOUSE once | Consumer must run GRANT USAGE manually |
| Performance | Provider controls size; guaranteed baseline | Dependent on consumer's shared warehouse |
| Workload isolation | App queries don't interfere with consumer work | Consumption harder to attribute |
| Cost attribution | Consumers can attribute cost to the app directly | Cost blended with consumer's warehouse spend |

### Phase 2: Build

**Stop here and invoke `skill(command: "native-app-provider")` before doing anything else.** Do not write manifest content, `setup.sql`, or setup scripts from this file.

That skill owns the full build flow: application package creation, `setup.sql`, `manifest.yml`, SPCS containers, Streamlit, event sharing, and versioning. Return here after the build completes for Phases 3–6 (testing, security scan, functional review, listing).

Keep these Marketplace-specific constraints in scope during the build — they gate the functional review:
- Apply the Phase 1 design rules above (core functionality on Snowflake, recommended `manifest_version: 2`, accepted auth methods) and the Enforced Requirements table at the bottom.
- **Critical:** shared content **cannot reference objects from other databases**. Copy data into the package as tables, not views pointing at external databases; the provider's source database does not exist in the consumer's account.
- If the app uses Cortex AI, declare the `SNOWFLAKE.CORTEX_USER` database role in `manifest.yml` (see Key Technical Concepts) rather than a manual GRANT.
- Once a test version exists, continue to Phase 3 to install and verify from a separate consumer account.

### Phase 3: Test Your Application

**This is the most common failure point.** Your provider account has owner-level privileges that mask permission and dependency errors. You must test from a separate consumer account.

**Best practice:** Create a brand new Snowflake account in a **different region** from your provider account, in a **different organization**. This most accurately simulates an external consumer.

Test all four scenarios before submitting:

| | Internal Org | External Org |
|---|---|---|
| Same region | ✓ | ✓ |
| Different region | ✓ | ✓ |

**Pre-submission checklist:**
- [ ] App installs without errors (no setup script errors or initial privilege issues)
- [ ] README is complete with exact post-install configuration steps
- [ ] If app requires credentials, README explains how consumers obtain and use them — and you have **non-expiring test credentials** ready to provide at submission
- [ ] App uses all privileges it requests from the consumer; no privilege errors during operation
- [ ] If using Streamlit + account/object-level privileges, Permissions SDK is used to request them

> If you share your app with a trial account for testing, trial account limitations may prevent you from testing the full consumer experience.

### Phase 4: Pass the Security Scan

Before submitting for functional review, the app must pass the automated security scan.

**Trigger the scan:**
```sql
ALTER APPLICATION PACKAGE <package_name> SET DISTRIBUTION = EXTERNAL;
```
> Do NOT set DISTRIBUTION = EXTERNAL during active development — it triggers a scan on every version/patch. Only set it when ready for review.

**Check scan status:**
- Snowsight: **Projects → App Packages → [your app] → Security Scan Status column**
- SQL: `SHOW VERSIONS IN APPLICATION PACKAGE <package_name>;` — check the `review_status` column

**If REJECTED:** Snowflake conducts a manual review (approx. 3 business days). You can appeal a CVE-based rejection by opening a severity 4 support ticket with a reachability analysis and remediation plan.

**SPCS apps:** If you see error `093197 Account is not allowed to create application package versions or patches with Snowpark Container Services for EXTERNAL distribution`, your account hasn't been approved for container publishing yet. Complete the [SPCS security questionnaire](https://docs.google.com/forms/d/1XLjbcSrp689kXEvVELa6KbEUOPfsJIirSTG5pGQDMZE) to begin the approval process.

### Phase 5: Submit for Functional Review

1. In Snowsight: **Marketplace → Provider Studio → + Create listing**
2. Under **Add data product**, attach the application package version that passed the security scan
3. Complete all listing fields and select **Submit for approval**

**What to include at submission:**
- Non-expiring test credentials (API key, OAuth token, etc.)
- Sample data if the app doesn't generate its own
- Any configuration values needed during setup (Account ID, External URL, etc.)
- A step-by-step guide for testing the main feature

### Phase 6: The Functional Review

After submission:
1. **Assignment** — A reviewer from Marketplace Ops is assigned within **24 hours**
2. **Review** — The reviewer installs, configures, and tests the app from the perspective of a new consumer
3. **Communication** — Any questions or issues are raised via support case (snowflake@support.com) to the contacts in your Marketplace Profile. Ensure those emails are current.
4. **Decision:**
   - **Approved** — You'll be notified by email and can publish the listing
   - **Rejected** — You'll receive an email detailing all required changes. Fix the issues, create a new version or patch (which triggers a new security scan), and resubmit

> Reviews can take **up to 2 weeks**. Do not open a support ticket to ask for status unless the 2-week window has passed.

### Key Technical Concepts

**Privileges & Permissions SDK**
All account-level privileges must be declared in `manifest.yml` AND requested via Snowsight or the [Python Permission SDK](https://docs.snowflake.com/en/developer-guide/native-apps/requesting-permission-sdk-ref). For `manifest_version: 1`, if the app uses Streamlit and requires account-level or object-level privileges, the Permissions SDK is required.

**Using Cortex AI Features**
If your app uses any Snowflake Cortex AI functions, the `SNOWFLAKE.CORTEX_USER` database role must be declared in your `manifest.yml` — **not** instructed as a manual GRANT in the README. As of January 2026, the Snowflake database role is manifest-supported.

Add the following to your `manifest.yml`:
```yaml
snowflake_database:
  roles:
  - cortex_user:
      description: to utilize AI functions
```

This allows consumers to grant the Cortex database role via the **Permissions tab in Snowsight**, providing a streamlined and consistent experience. Apps that instruct consumers to manually run `GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO APPLICATION <app_name>` will be flagged during functional review.

**Consuming AI Products (CKEs, Cortex Search, Agents) in a Native App**

A Native App can offer a conversational or RAG experience by creating its own **Cortex Agents** and **Snowflake-managed MCP servers** (`CREATE AGENT`, `CREATE MCP SERVER`) that wrap app-owned Cortex Search services, semantic views, UDFs, and procedures. It can also consume a **Cortex Knowledge Extension (CKE)**, a Cortex Search Service shared as a Marketplace listing (including Snowflake-provided CKEs), that the *consumer* has installed.

Key rules:
- **Restricted Caller's Rights (RCR):** App-created agents cannot access consumer data or a consumer-installed CKE unless the consumer admin runs `GRANT CALLER ... TO APPLICATION`. The app gets implicit caller grants only on objects it **owns**.
- **A CKE cannot be bundled inside the app.** Shared app content can't reference objects in other databases, and a CKE is a separately-installed listing. Pattern: the consumer installs the CKE (or a Snowflake-provided one), grants the app caller access to its Cortex Search Service, and the app's agent references it as a `CORTEX_SEARCH_SERVICE_QUERY` tool (or via an agent `tool_resources` entry).
- **App-created Snowflake-managed MCP servers** may expose only **app-owned** tools and cannot include the `SYSTEM_EXECUTE_SQL` tool. This prevents the app from being used to run arbitrary SQL in the consumer's account.
- Use **partially-qualified identifiers** (e.g. `core.my_semantic_view`) in agent specs, since the app database name is only known at install time, and prefer `orchestration: auto` over a fixed model name (a specific model may not exist in the consumer's region).
- Requires the consumer account to have **Cortex Agents and Snowflake CoWork enabled**.

Build these with the canonical **`native-app-provider`** skill and the **`cortex-agent`** sub-skill. See [Use Cortex Agents and MCP servers in an app](https://docs.snowflake.com/en/developer-guide/native-apps/agents-mcp-servers) and [Cortex Knowledge Extensions](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-knowledge-extensions/cke-overview).

**Caller's Rights vs Owner's Rights**
Stored procedures default to owner's rights (app's privileges). Use `EXECUTE AS CALLER` for procedures that should run with the consumer's privileges. See [Restricted caller's rights](https://docs.snowflake.com/en/developer-guide/native-apps/restricted-callers-rights).

**Event Sharing (Logging & Telemetry)**
Apps can emit log messages and trace events to provider-side event tables. Mandatory event definitions should be minimal. See [Event sharing](https://docs.snowflake.com/en/developer-guide/native-apps/event-about).

**Custom Billing Events**
Custom Event Billing lets a Native App charge consumers for specific usage (per procedure call, per row processed, or a custom event you define), on top of any per-query charge or monthly fee. It has two sides that must match: the app emits events from a stored procedure via `SYSTEM$CREATE_BILLING_EVENT` / `SYSTEM$CREATE_BILLING_EVENTS`, and the listing's usage-based pricing plan lists each event `class` with its billing quantity. Only Native App listings can use billable events (plain data listings cannot). For the full provider setup, code patterns, system-function reference, listing configuration, billing-behavior rules, and testing steps, see [`references/custom-event-billing.md`](references/custom-event-billing.md).

**Trial Listings**
Use `SYSTEM$IS_LISTING_TRIAL()` in secure views, UDFs, or Streamlit apps to limit functionality for trial consumers. See [Prepare to offer a limited trial listing](https://docs.snowflake.com/en/collaboration/provider-listings-preparing).

### Enforced Requirements

| # | Requirement | Key Check |
|---|------------|-----------|
| 1 | Immediate utility | App delivers usable functionality after install + minimal config; no shell apps |
| 2 | Standalone | Core functionality runs on Snowflake; no forced cross-selling or pass-through to external services |
| 3 | Data-centric | Leverages Snowflake data (provider's share, Marketplace dataset, or consumer data) |
| 4 | Transparent | All privileges in manifest; requested via Snowsight or Permission SDK |
| 5 | README required | Must include: description, config steps, stored procs/UDFs, privileges, example SQL |
| 6 | marketplace.yml | All resource requirements listed; app creates them at install |
| 7 | Cortex role | If using Cortex AI, declare `SNOWFLAKE.CORTEX_USER` database role in manifest (not as a manual GRANT instruction) |
| 8 | Auth methods | Username/password deprecated; key pair: providers generate and share only the public key; PAT and OAuth also accepted |

### References
- [Custom Event Billing for Native Apps (setup, code, listing config)](references/custom-event-billing.md)
- [Native Apps Framework overview](https://docs.snowflake.com/en/developer-guide/native-apps/native-apps-about)
- [App package](https://docs.snowflake.com/en/developer-guide/native-apps/creating-app-package)
- [Manifest reference](https://docs.snowflake.com/en/developer-guide/native-apps/manifest-reference)
- [Setup script](https://docs.snowflake.com/en/developer-guide/native-apps/creating-setup-script)
- [Adding Streamlit](https://docs.snowflake.com/en/developer-guide/native-apps/adding-streamlit)
- [Requesting privileges](https://docs.snowflake.com/en/developer-guide/native-apps/requesting-about)
- [Event sharing](https://docs.snowflake.com/en/developer-guide/native-apps/event-about)
- [SPCS in Native Apps](https://docs.snowflake.com/en/developer-guide/native-apps/container-services)
- [Security overview](https://docs.snowflake.com/en/developer-guide/native-apps/security-overview)
- [Publishing an app](https://docs.snowflake.com/en/developer-guide/native-apps/ui-provider-publishing-app-package)
- [Listing requirements for apps](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps#native-applications)
- [Limitations](https://docs.snowflake.com/en/developer-guide/native-apps/limitations)
