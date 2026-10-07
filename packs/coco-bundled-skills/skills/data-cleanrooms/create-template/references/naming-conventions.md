# Reference: Naming Conventions

Guidelines for template names, versions, and descriptions. The template creator is often different from the person who runs the template — names and descriptions must be self-explanatory.

## Name Pattern

**Convention:** `{usecase}_{variant}_{version_hint}`
**Rules:** Max 75 chars, `^[A-Za-z_][A-Za-z0-9_]{0,74}$`

### Examples by Use Case

| # | Use Case | Good Name | Bad Name |
|---|----------|-----------|----------|
| 1 | Audience Overlap | `audience_overlap_email_v1` | `test1` |
| 2 | Audience Activation | `activation_segment_email_v1` | `my_template` |
| 3 | Reach & Frequency | `reach_frequency_by_campaign_v1` | `rf` |
| 4 | Incrementality | `incrementality_lift_test_control_v1` | `inc` |
| 5 | Multi-Touch Attribution | `mta_linear_attribution_v1` | `attribution` |
| 6 | Lookalike Modeling | `lookalike_propensity_model_v1` | `ml_template` | *(code_spec, not template_spec)* |
| 7 | Identity Crosswalk | `identity_crosswalk_waterfall_v1` | `crosswalk` |

## Version Pattern

**Convention:** `YYYY_MM` or `v1`, `v2`
**Rules:** Max 20 chars, `^[A-Za-z0-9_]{1,20}$`

| Good | Bad |
|------|-----|
| `2024_01` | `2024.01` (dot not allowed) |
| `v1` | `version 1` (space not allowed) |
| `prod_v2` | `v2-beta` (hyphen not allowed) |

## Description Guidelines

**Rules:** Max 1000 chars. Explain what the template **does**, not how it works internally.

| Use Case | Good Description | Bad Description |
|----------|-----------------|-----------------|
| Overlap | "Count matching customers between advertiser and publisher datasets using hashed email, with optional regional breakdown." | "Does a JOIN." |
| Activation | "Export matched audience segment for ad targeting based on email overlap." | "Activation template." |
| Reach & Frequency | "Measure unique reach and average ad frequency per campaign across matched audiences." | "R&F." |

## Methodology Guidelines

**Rules:** Max 1000 chars. Explain the approach for data scientists and auditors.

Example:
> Performs an inner join on hashed email identifiers between provider and consumer datasets. Counts distinct matches grouped by the specified dimension. Applies a minimum count threshold to prevent small-group identification.

## Cross-Case Uniqueness

When generating specs for multiple cases in a single output, every `name` must be unique across the entire document. Common collision scenarios:

| Scenario | Problem | Fix |
|----------|---------|-----|
| Case 1 creates `audience_overlap_email_v1`, Case 10 re-shows it in a fix | Duplicate name | Case 10 should show only the version-bumped spec (`v2`) |
| Two overlap cases (e.g. Case 1 and Case 3) | Both get generic overlap name | Differentiate: `audience_overlap_email_v1` vs `standard_overlap_v1` |
| Single-account and multi-account overlap | Both named `overlap_v1` | Prefix: `single_account_overlap_v1` |

## Pushback Script

When a user provides a poor name:

**User says:** "Call it `test1`"
**Skill says:** "`test1` won't help collaborators understand what this template does. The person running this template may not be the person who created it. How about `audience_overlap_email_v1` instead?"

**If user insists:** Accept after one pushback. Their template, their choice.
