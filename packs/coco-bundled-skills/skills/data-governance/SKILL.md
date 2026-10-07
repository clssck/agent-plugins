---
name: data-governance
description: "**[REQUIRED]** for Snowflake requests about controlling, protecting, or governing data. Use for sensitive-data discovery or classification; policies, tags, and other protection controls; access or compliance evidence; ownership and stewardship; governance or observability maturity; and policy recommendations. Invoke when users want to find or label sensitive data, prevent exposure, inspect where a policy is attached, determine whether tags follow derived or cloned objects, understand what survives clone, swap, or rename operations, assess coverage across a schema or database, or remediate missing controls. Also use for customer language such as lock it down, restrict, hide, redact, mask, confidential, restricted or tiered data, people below should not see it, finding who can access data or who accessed it, or cleaning up roles. Cover grants, privileges, permissions, role hierarchy and inheritance, least privilege, service-account or agent/app scoping, offboarding, access revocation, excessive access, and insufficient privileges. Do not answer governance-risk tasks from general knowledge. Route incorrect, missing, stale, duplicate, or inconsistent values to data-quality. Route origin, provenance, dependencies, blast radius, and what-will-break questions to lineage. Keep data-governance as coordinator when quality or lineage supplies evidence for a broader governance outcome."
---

# Data Governance

Use this skill as the Snowflake governance control plane. Determine the requested outcome and execution shape, then load the canonical owner. Keep implementation detail in the owning workflow and do not answer governance-risk tasks from general knowledge.

Keep user-facing replies in product terms. Do not expose internal paths, skill files, harness state, or routing labels.

## Precedence

Apply these rules in order:

1. Preserve exact product-command contracts before semantic routing.
   - `/data-governance Create a new <policy type> policy for me` → load `workflows/data-policy.md` and its matching UI workflow. Parse `<policy type>` and ask for the fully qualified policy name; do not ask for the type again.
   - `/data-governance Edit the <POLICY_KIND> POLICY named <POLICY_NAME> located at <DB>.<SCHEMA>.` → load `workflows/data-policy.md` and its matching UI workflow.
   - `/data-governance Create a data policy for categories <CAT1>, <CAT2>, ... [source=classification-wizard]` → load `workflows/data-policy.md`; preserve the source sentinel.
   - `/data-governance Identify policy gaps and recommend remediation actions for my account [within <PATH>]` → load `workflows/policy-recommendations.md`. This owner is reserved for the exact first-message command.
2. Requests containing the exact case-insensitive phrases `intent driven governance`, `intent-driven governance`, or `governance intent workspace`, or the command shapes `restore governance version vNNN`, `revert governance to vNNN`, or `rollback governance to vNNN` → load `workflows/intent-driven-governance/SKILL.md`. Do not use this workflow for ordinary governance requests without one of these triggers.
3. Determine the requested governance domain and load its canonical owner from the routing table.

## Routing

| Request | Canonical owner |
|---|---|
| Discover, classify, or report sensitive data | `workflows/sensitive-data-classification.md` |
| Inspect, design, audit, create, change, or remove a protection control | `workflows/data-policy.md` |
| Determine access, grants, inheritance, users, roles, activity, dependencies, compliance evidence, or other account facts | `workflows/horizon-catalog-index.md`, then the relevant part of `workflows/horizon-catalog.md` |
| Combine access evidence with owner or steward accountability | `workflows/access-review-and-stewardship.md` |
| Assign or report ownership, contacts, or stewardship only | `workflows/object-contacts.md` |
| Assess governance posture, gaps, priorities, or roadmap | `workflows/governance-maturity-score.md` |
| Assess observability posture or monitoring coverage | `workflows/observability-maturity-score.md` |

If a request spans multiple owners, sequence the canonical owners instead of moving it to intent-driven governance. Start with the workflow that produces evidence needed by the next workflow.

## Boundaries

- Incorrect, missing, stale, duplicate, or inconsistent values and failing checks → use `data-quality` first.
- Origin, provenance, upstream/downstream dependencies, blast radius, or what-will-break questions → use `lineage`.
- If quality or lineage is evidence for a broader governance outcome, retain governance coordination and delegate only the supporting analysis.

## Invariants

- Exact product commands use their contracted acknowledgement and next question; do not replace them with generic intake.
- Read-only work may proceed according to the selected workflow. Any mutation must follow that workflow's preview, approval, and stopping rules.
- Ask one targeted question only when the desired outcome or scope cannot be inferred. Do not present a workflow menu by default.
- Follow the selected workflow completely. For catalog SQL, load the index and selected slice, use recursive grants and `LATERAL FLATTEN` rather than direct array indexing, and exclude disabled/deleted users from MFA compliance.
