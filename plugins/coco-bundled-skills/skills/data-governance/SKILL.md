---
name: data-governance
description: "**[REQUIRED]** for Snowflake data-governance tasks involving sensitive data, data policies, access/compliance evidence, stewardship, governance maturity, observability maturity, policy recommendations, or exact intent-driven governance triggers. Do not answer governance-risk tasks from general knowledge; route through this control-plane skill to the canonical owner."
---

# Data Governance

Use this skill as the Snowflake governance control plane. Its job is to identify the user's governance intent, route to the canonical owner, and avoid answering access, classification, policy, stewardship, maturity, or compliance tasks from general knowledge.

This router owns activation, precedence, ambiguity handling, exact product triggers, and workflow handoff. Implementation detail belongs in the owning workflow.

Keep user-facing replies in product terms: do not paste internal file paths (e.g. `workflows/...`, `SKILL.md`) or harness/internal state into the visible reply — summarize what you found or are doing instead. Briefly telling the user what you're doing (e.g. "let me check your account") is fine.

For exact UI slash-commands, the first user-facing response should be the UI workflow's product-facing acknowledgement and next question — do not open with the universal intake questions.

For `/data-governance Create a new <policy type> policy for me`, parse `<policy type>` from the command and do not ask the user to choose a type again. The visible first reply should be equivalent to: `<Policy type> policy it is. What should we name the policy? Provide the fully qualified name as <database>.<schema>.<policy_name>.`

## Routing Precedence

Apply these rules in order:

1. **Exact UI policy slash-commands** → load `workflows/data-policy.md` plus the matching UI workflow. Follow the UI contract exclusively. Do not ask the universal intake questions.
   - `/data-governance Create a new <policy type> policy for me`
   - `/data-governance Edit the <POLICY_KIND> POLICY named <POLICY_NAME> located at <DB>.<SCHEMA>.`
   - Category-seeded UI command `/data-governance Create a data policy for categories <CAT1>, <CAT2>, ... [source=classification-wizard]` is handled inside `workflows/data-policy.md` and requires the `[source=classification-wizard]` sentinel.
2. **Exact policy-recommendations slash-command** → load `workflows/policy-recommendations.md` only for `/data-governance Identify policy gaps and recommend remediation actions for my account [within <PATH>]`.
3. **Exact intent-driven governance triggers** → load `workflows/intent-driven-governance/SKILL.md` only for the exact trigger phrases listed below.
4. **Sensitive-data discovery** → load `workflows/sensitive-data-classification.md`.
5. **Protection-control design or policy audit** → load `workflows/data-policy.md`.
6. **Access review plus stewardship / ownership / contacts** → load `workflows/access-review-and-stewardship.md` when the request combines who-can-access, inherited grants, access evidence, and owner/steward accountability. For contact assignment only, load `workflows/object-contacts.md`.
7. **Governance posture / roadmap** → load `workflows/governance-maturity-score.md`.
8. **Observability posture / monitoring signal** → load `workflows/observability-maturity-score.md`.
9. **Catalog, access, grants, users, roles, object dependencies, query history, MFA, compliance, or unclear governance/corpus evidence** → consult `workflows/horizon-catalog-index.md`, then load the relevant section of `workflows/horizon-catalog.md`.

If a request spans multiple owners, sequence the canonical owners instead of duplicating logic. For example, “find PII and create a masking policy” starts with classification, then hands protection design to data-policy.

## Exact Trigger Gates

### Intent-Driven Governance

Load `workflows/intent-driven-governance/SKILL.md` only when the current user request contains one of these exact case-insensitive trigger phrases or command shapes:

- `intent driven governance`
- `intent-driven governance`
- `governance intent workspace`
- `restore governance version vNNN`
- `revert governance to vNNN`
- `rollback governance to vNNN`

Do not route ordinary governance, policy creation, classification, access-audit, stewardship, maturity-score, or drift wording to intent-driven governance unless one of those exact triggers is present in the current request.

### Policy Recommendations

Load `workflows/policy-recommendations.md` only when the user's first message is the exact UI slash-command:

```text
/data-governance Identify policy gaps and recommend remediation actions for my account [within <PATH>]
```

Do not route general phrasing like `policy gap`, `what should I protect`, or `which tables need protection` to policy recommendations. Without the exact UI command, use the normal decision tree.

## Canonical Ownership

| Shared concern | Canonical owner | Other workflows should do |
|---|---|---|
| Sensitive-data discovery | `workflows/sensitive-data-classification.md` | Route here before policy or recommendation work when sensitivity is unknown. |
| Protection control design | `workflows/data-policy.md` | Consume classification/catalog/recommendation evidence; avoid re-teaching classification or ranking gaps. |
| Policy gap prioritization | `workflows/policy-recommendations.md` | Use classification and catalog evidence; hand off to data-policy for general policy design unless applying an explicitly approved recommendation. |
| Access and catalog evidence | `workflows/horizon-catalog-index.md` then `workflows/horizon-catalog.md` | Select the catalog intent first, then provide evidence to classification, policy, recommendations, contact, or maturity workflows. |
| Access review and stewardship | `workflows/access-review-and-stewardship.md` | Use for combined access/grant inheritance and owner/steward accountability reviews; hand off to object contacts only for contact changes. |
| Stewardship and accountability | `workflows/object-contacts.md` | Provide ownership evidence to maturity and operational workflows. |
| Governance architecture and roadmap | `workflows/governance-maturity-score.md` | Summarize gaps across classification, policy, recommendations, access, and ownership. |
| Monitoring and operational signal | `workflows/observability-maturity-score.md` | Support governance maturity with monitoring evidence, not duplicate it. |
| Stateful governed change | `workflows/intent-driven-governance/SKILL.md` | Orchestrate approved changes; delegate domain-specific reasoning to canonical owners. |

## Intent Hints

Use these hints only to choose the canonical owner. Do not copy full implementation guidance into the router.

| User intent | Load |
|---|---|
| PII, sensitive data, classify, classification profile, auto-classification, custom classifier, semantic category, privacy category, GDPR/CCPA/PCI detection | `workflows/sensitive-data-classification.md` |
| Masking policy, row access policy, projection policy, aggregation policy, join policy, tokenization policy, tag-based policy, protect sensitive data, column masking, TIMESTAMP masking, policy audit | `workflows/data-policy.md` |
| Data steward, object contact, assign contact, create contact, contact report, who owns this table, who is responsible for, `SET CONTACT`, `GET_CONTACTS` | `workflows/object-contacts.md` |
| Governance maturity score, governance posture, governance assessment, governance health, governance recommendations, governance checklist | `workflows/governance-maturity-score.md` |
| Data observability score, observability maturity, DMF coverage, quality monitoring maturity, BI tool monitoring, external lineage, lineage for RCA, impact analysis readiness | `workflows/observability-maturity-score.md` |
| Access history, who has access, who accessed, permissions, role hierarchy, role inheritance, grants, users, roles, MFA, multi-factor authentication, query history, object dependencies, compliance, catalog, schema change, column metadata | `workflows/horizon-catalog-index.md` then `workflows/horizon-catalog.md` |

## Ambiguous Intent

If intent is ambiguous, ask the user to choose before loading a sub-skill:

```text
Which area can I help you with?

1. Horizon Catalog — Access history, who has access, role/grant analysis, object dependencies, compliance queries, catalog exploration
2. Data Policies — Masking policies, row access policies, projection policies
3. Sensitive Data Classification — Detect PII, set up auto-classification, create classifiers
4. Governance Maturity Score — Assess governance posture, score (0–5), recommendations
5. Observability Maturity Score — Assess data observability (DMFs, BI coverage, lineage), score (0–5), recommendations
6. Object Contacts — Assign data stewards, create contacts, generate contact reports, manage stewardship
7. Access Review & Stewardship — Combined who-can-access, inherited grants, access evidence, and owner/steward accountability
```

## Critical Catalog Invariants

These invariants prevent high-risk generic answers. Select the catalog intent in `workflows/horizon-catalog-index.md`; detailed SQL belongs in `workflows/horizon-catalog.md`.

- **Role hierarchy traversal**: For access, grants, roles, or permissions questions, do not answer from direct grants only. Use recursive `SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES` plus `SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS`; do not use `SHOW GRANTS` as the final proof of transitive access.
- **ACCESS_HISTORY JSON**: Use `LATERAL FLATTEN` for access-history JSON arrays; do not rely on direct array indexing for final answers.
- **MFA compliance checks**: Exclude disabled and dropped users. Query `SNOWFLAKE.ACCOUNT_USAGE.USERS` with `HAS_MFA = FALSE`, `DISABLED = FALSE`, and `DELETED_ON IS NULL` or equivalent filters.

## Execute The Loaded Workflow

Follow the loaded workflow completely. Each workflow owns its own templates, references, stopping points, and approval rules.

Fallback rule: if a non-catalog workflow cannot fully answer because it needs account metadata or evidence, consult `workflows/horizon-catalog-index.md` and then load the relevant part of `workflows/horizon-catalog.md` for supplemental catalog context.

## Stopping Points

- ✋ **On ambiguous intent**: Present the 7-option menu and wait for user selection before loading any sub-skill.
- ✋ **Sub-skill stopping points**: Honor the loaded workflow's mandatory stopping points.
