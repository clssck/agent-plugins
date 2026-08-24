---
description: "Review who can access sensitive objects and who is accountable for them. Use for access review, inherited role analysis, direct vs indirect grants, access evidence, broad-role findings, object-contact/stewardship coverage, or requests that combine access and ownership."
---

# Access Review And Stewardship

Use this workflow when the user asks who can access sensitive data, how access is inherited, who has actually used access, or who owns/stewards the objects.

## Goal

Produce a reviewable access-and-stewardship artifact. Do not change grants, roles, contacts, or ownership without explicit approval.

## Required Sequence

1. **Confirm or infer scope**
   - If the user gives exact objects, use them.
   - If the user gives business scope such as “customer profile and support data,” identify candidate databases/schemas/tables first (via the catalog evidence workflow), then ask the user to confirm the exact `<database>.<schema>.<object>` targets before recommending changes.

2. **Explain access evidence layers**
   - Direct privileges are not enough.
   - Inherited access must traverse role hierarchy with recursive `SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES` plus user membership from `SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS`.
   - Actual access/usage evidence should use `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY` or `QUERY_HISTORY` when available; if account-usage latency makes it unavailable, use an explicitly labeled fixture or recent evidence table and say so.

3. **Review stewardship coverage**
   - Check object contacts, owner/steward records, or governance contact evidence.
   - Separate assigned contacts from gaps.
   - Treat missing owners/stewards as a recommendation, not an automatic change.

4. **Produce review package**
   - Access matrix: object, direct role, inherited role path, users if available, privilege.
   - Usage evidence: recent queries/access, role count, query count, or clearly labeled unavailable/latent evidence.
   - Stewardship report: assigned owner/steward/contact and gaps.
   - Recommendations: broad roles to review, missing contacts to assign, and exact SQL/commands only as approval-ready proposals.

## Approval Boundary

Never execute `GRANT`, `REVOKE`, `ALTER ... SET CONTACT`, ownership transfer, or contact assignment without explicit approval. If proposing SQL, label it as review-only until approved.

## Evidence Sourcing

Do not re-implement catalog SQL here. Route each evidence layer to its canonical owner via `workflows/horizon-catalog-index.md`, then load the relevant section of `workflows/horizon-catalog.md`:

- **Inherited role paths**: use the *Access And Grants* section's recursive `GRANTS_TO_ROLES` + `GRANTS_TO_USERS` pattern. Never treat direct grants as final proof of transitive access.
- **Actual usage evidence**: use the *Access History And Usage Evidence* section (`ACCESS_HISTORY` / `QUERY_HISTORY` with `LATERAL FLATTEN`). If account-usage latency makes this unavailable, say so explicitly rather than guessing.
- **Stewardship coverage**: use object-contact / owner evidence from catalog metadata or `workflows/object-contacts.md`.

If the customer supplies or you discover a low-latency evidence table in their own schema (for example a pre-aggregated query-evidence or contact table), you may use it, but label it as customer-supplied evidence rather than a required source. Do not hardcode specific database, schema, or object names into this workflow.

## Handoffs

- If the user asks to assign or manage contacts, hand off to `workflows/object-contacts.md` after the review package.
- If the access review reveals missing masking or policy coverage, hand off to `workflows/data-policy.md` or `workflows/policy-recommendations.md` only after summarizing the evidence.
- If the user asks for broad governance posture, hand off to `workflows/governance-maturity-score.md` with this review as evidence.
