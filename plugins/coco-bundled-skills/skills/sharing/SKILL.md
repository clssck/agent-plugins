---
name: sharing
description: "Router for Snowflake sharing and collaboration. Routes to Secure Data Sharing, Declarative Sharing, Native Apps, or Data Clean Rooms. Asks up to 2 questions when intent is ambiguous, then loads the target sub-skill. This skill should supersede invocation of product-specific skills unless the product is named explicitly — in particular, open-ended or comparison requests (alternatives, options, 'which should I use', 'manifests or native apps') must come here, not to a product skill. Triggers: share, sharing, listing, data product, how do I share, what's the best way to share, compare sharing options, alternative to a share, alternatives to sharing, what are my options for sharing, which sharing option, not sure how to share, manifests or native apps."
tools: ["ask_user_question"]
---

# Sharing

This skill routes users to the correct Snowflake sharing or collaboration construct. It asks up to 2 questions to pick the right sub-skill, then hands off immediately with context.

## Feature Boundaries

Each category is mutually exclusive — route to exactly one.

| Feature | What It Is |
|---------|-----------|
| **Secure Data Sharing** | Read-only sharing via `CREATE SHARE`. Consumer gets live SQL access to tables and views. Includes direct shares (private) and Marketplace listings (public). Does NOT include versioning, code objects, or bundled business logic. |
| **Declarative Sharing** | Data-as-a-product via `APPLICATION PACKAGE` with `TYPE=DATA`. Bundles data with code objects: notebooks, UDFs, stored procedures, Cortex Agents, semantic views. Consumer installs once (no setup script or privilege dialogs). Consumer's private data is NOT accessible. |
| **Native Apps** | Application installs and runs in the consumer's account. Supports Streamlit UIs, SPCS containers, consumer data access via References (`SYSTEM$REFERENCE`), and bi-directional data flows. Consumer can grant access to their private data. Does NOT involve joint analysis with partners. |
| **Data Clean Rooms** | Partners contribute data for one or more runners to analyze via approved templates and code. Runners can see templates and code specs but not the underlying staged code files. Only results are returned. Roles: Owner, Data Provider, Analysis Runner. Not for delivering packaged products or applications. |

### Bi-directional Disambiguation

| Scenario | Route To | Why |
|----------|----------|-----|
| Partners exchange data back and forth, no analysis | Two Secure Data Shares | Just data, no code or analysis |
| Provider ships app, consumer grants data back | Native Apps | Provider's code installs in consumer account; consumer grants access via References |
| Partners contribute data, runner executes approved analysis | Data Clean Rooms | Approved templates and code run on providers' data; providers approve what runners can execute |

## Routing Table

Scan the user's full request and match against the unambiguous triggers below. If no clear match, use the Decision Guide.

| Intent | Unambiguous Triggers | Target Skill |
|--------|---------------------|--------------|
| **Secure Data Sharing** | "secure data sharing", "SDS" | Invoke skill: `data-sharing` |
| **Declarative Sharing** | "declarative sharing", "declarative native app" | Invoke skill: `declarative-sharing` |
| **Native Apps** | "native app", "native app framework", "native app provider" | Invoke skill: `native-app-provider` |
| **Data Clean Rooms** | "clean room", "DCR", "DCR collaboration", "multi-party" | Invoke skill: `data-cleanrooms` |

> **Ambiguous triggers:** "share notebook", "share UDF", "share stored proc", "share workspace", "create listing" — these fall through to the Decision Guide. The right construct depends on whether the consumer needs to access their own data.

---

## Decision Guide

If the Routing Table gives a clear match, load that sub-skill immediately. Otherwise, ask the questions below in order. Always ask Q1 first, then Q2.

**IMPORTANT: Infer before asking.** Before presenting any question, check if the user's prompt already answers it. Ask the user to confirm what you inferred.

For example:
- "share with my partner account" or "another Snowflake account" → Q1 is cross-account (skip Q1)
- "give my analyst role access" or "within my account" → Q1 is same account → RBAC, stop
- "query my tables directly" or "full SQL access" → Q2 = A → SDS
- "run queries together" or "joint analysis" or "partner contributes data" or "approved templates" → Q2 = B → DCR
- "share my notebook" or "share my UDF" or "share my agent" without consumer data access → Q2 = C → Declarative
- "they need to run it on their own data" or "access consumer data" → Q2 = D → Native Apps

Only ask a question if the user's prompt does NOT already answer it.

**CRITICAL: Stop conditions are terminal.**
- If Q1 = same account → route to RBAC immediately. Do NOT ask Q2.
- Q2 is always terminal — each answer routes directly to a product.

---

### Q1: Who are you sharing data with?

- **Same account** — roles or users within my Snowflake account
- **Another account** — partner, customer, org, or Marketplace

**If Q1 = "Same account"** → route to **RBAC** (inline, see below) and stop. Do NOT ask Q2.

---

Before presenting Q2, give the user an overview of the available sharing constructs as a message, then present the question:

> Snowflake has four ways to share data and applications:
> - **Secure Data Sharing** — Share selected objects (tables, views, models, and more) with other accounts for live, read-only, zero-copy access—no data copied or stored in the consumer account.
> - **Data Clean Rooms** — multiple parties contribute data for joint analysis without exposing raw data to each other. One or more designated runners execute approved queries and code; only results are returned.
> - **Declarative Sharing** — your data and Snowflake objects bundled as a versioned product. Consumer installs once, then accesses everything directly. Your data only — no consumer data access. 
> - **Native Apps** — your application installs and runs inside the consumer's account. The consumer can grant your app access to their own private data. Use when your code needs to run on the consumer's side. 

### Q2: What can consumers do with what you share?

Only ask if Q1 is cross-account. Present all four options together — do not ask as sequential binary questions.

- **A — Query my live data directly** — consumer gets direct read access to allowed tables, views, or models
- **B — Run approved SQL or code that either party defines** — anyone can contribute data and code; one or more analysis runners execute post-approval
- **C — Run my code with my data only** — provider adds code and data; consumer runs it but cannot bring their own data
- **D — Run my code with either party's data** — your code runs in the consumer's account accessing both parties' data

In the `ask_user_question` picker, label each option with its product name:
- A: "Query my live data directly — Secure Data Sharing"
- B: "Approved SQL/code only — Data Clean Rooms"
- C: "My code, my data only — Declarative Sharing"
- D: "My code, either party's data — Native Apps"

**A → Secure Data Sharing** — invoke skill: `data-sharing` and stop.

**B → Data Clean Rooms** — invoke skill: `data-cleanrooms` and stop.

**C → Declarative Sharing** — invoke skill: `declarative-sharing` and stop.

**D → Native Apps** — invoke skill: `native-app-provider` and stop.

> **Note on models:** All model types are shareable. Fine-tuned and served models are queryable directly by consumers → option A (SDS). Custom ML models bundled as code objects → option C (Declarative) unless consumer data access is needed → option D (Native Apps). Do NOT tell users that any model type is unshareable.

---

## RBAC (inline — no sub-skill needed)

When Q1 = same account:

**⚠️ MANDATORY STOPPING POINT**: Ask the user for the specific database, schema, table, role, and user names before emitting any SQL.

Then emit:

```sql
GRANT USAGE ON DATABASE <database_name> TO ROLE <role_name>;
GRANT USAGE ON SCHEMA <database_name>.<schema_name> TO ROLE <role_name>;
GRANT SELECT ON TABLE <database_name>.<schema_name>.<table_name> TO ROLE <role_name>;
GRANT ROLE <role_name> TO USER <username>;
```

---

## Context Handoff

**MANDATORY: After determining the route, you MUST invoke the target skill using the `skill` tool.** Do NOT attempt to execute the next steps yourself — load the sub-skill and let it guide the workflow.

```
skill command: "<skill-name>"
```

Skill names:
- Secure Data Sharing → `data-sharing`
- Declarative Sharing → `declarative-sharing`
- Native Apps → `native-app-provider`
- Data Clean Rooms → `data-cleanrooms`

When invoking the skill, pass the answers already collected as context in your message:

```
Context from router:
- audience: [answer from Q1]
- consumer_capability: A_query_freely | B_approved_templates | C_code_my_data | D_code_either_data
```

Tell the sub-skill: "The user has already provided the above context. Skip re-asking these questions and proceed to your next step."

---

## Recovery

If the user says the routing doesn't fit:
1. Ask which aspect is wrong (audience? content type? how they access it?)
2. Loop back to that question
3. Re-route with the corrected answer — don't restart from scratch
