---
name: openflow-connector-oracle-licensing
description: Oracle CDC connector licensing detail — Embedded vs BYOL eligibility, licensing comparison, Embedded lifecycle and auto-conversion risk, and ORGADMIN steps to enable commercial terms and start the trial. Loaded from connector-oracle.md when the licensing decision or commercial activation needs to be worked through in detail.
---

# Oracle CDC Connector — Licensing

Loaded from [`connector-oracle.md`](../connector-oracle.md) when working through the licensing decision or ORGADMIN commercial activation.

## Scope

This reference covers:
- Embedded vs Independent (BYOL) eligibility rules
- Licensing comparison (cost, commitment, core factor)
- Embedded license lifecycle and auto-conversion risk
- ORGADMIN steps to enable Oracle Connector Terms and start the trial

For the deployment workflow and connector parameters, return to [`connector-oracle.md`](../connector-oracle.md).

---

## Licensing Decision (Resolve First)

Unlike other CDC connectors, Oracle requires a licensing decision **before** any technical work. The wrong choice can cause deployment failure or unintended financial commitments.

### Decision Tree

Ask the user:

> "Does your organization already have an Oracle GoldenGate license (or another Oracle license that includes XStream entitlements)?"
>
> - **Yes** → Independent License (BYOL)
> - **No** → Check eligibility for Embedded License below

### Eligibility Check (Embedded License)

The Embedded License is **not available** if any of the following apply:

| Restriction | Impact |
|-------------|--------|
| Public Sector (Government, Education) | Must use BYOL |
| GCP Marketplace customer | Must use BYOL |
| Third-party reseller (e.g., CDW, Optiv) | Must use BYOL |
| Legacy Snowflake pricing (non-Snowspeed) | Must use BYOL |

If eligible, the customer can proceed with Embedded License through their Snowflake Capacity.

### Licensing Comparison

| Consideration | Embedded License | Independent License (BYOL) |
|---------------|-----------------|---------------------------|
| Oracle License | Snowflake provides XStream license | Customer's existing GoldenGate/XStream license |
| Connector Fee | $70/core/month (license) + $40/core/month (S&M) = **$110/core/month** | **$0** connector fee |
| Billing | Drawn from Snowflake Capacity balance | Standard Snowflake compute/storage only |
| Trial | 60-day free trial (max 16 licensed cores) | No trial (not needed) |
| Commitment | Non-cancelable 36-month term after trial | None from Snowflake |
| Core Factor | Customer must report core count × Oracle Processor Core Factor | Not required |
| Configuration | Requires core count and multiplier in connector parameters | No billing parameters |

**Core Factor Example:** A 24-core Intel server = 24 cores × 0.5 factor = 12 Licensed Cores → 12 × $110 = $1,320/month.

### Embedded License Lifecycle (Critical)

| Phase | Timeline | What Happens |
|-------|----------|--------------|
| Trial | Days 1-60 | Free for up to 16 licensed cores |
| Auto-conversion | Day 61 | Billing starts automatically. Must cancel before Day 60 to avoid charges |
| Commitment | Months 1-36 | Non-cancelable. Full remaining balance due if Snowflake agreement terminated early |
| Post-term | Month 37+ | License fee drops to $0. S&M ($40/core/month) continues, auto-renews annually |
| S&M opt-out | After month 36 | Connector processors permanently locked when S&M expires. New license required to resume (resets 36-month term) |

**WARNING:** Advise users to set a calendar reminder for Day 55 if they want the option to cancel the trial.

---

## ORGADMIN: Enable Commercial Terms

This step must be performed by the Organization Administrator (ORGADMIN) **before** the connector can be deployed. No connector deployment or Oracle-side setup is needed first — this is purely an administrative step in Snowsight.

### Part 1: Accept Terms (Both License Types)

1. Log in to Snowsight with the **ORGADMIN** role.
2. Navigate to **Admin >> Terms**.
3. Locate **Oracle Connector Terms** in the list.
4. Click **Review & Enable**.

**Outcome:** Two things happen immediately:
- The Openflow Connector for Oracle becomes visible in the Connector Catalog.
- A new tab **Openflow for Oracle** appears in Admin >> Terms, showing a **Trial Status** card with status "Ready to Activate" (Embedded) or subscription inventory (BYOL).

### Part 2a: Start Trial (Embedded License Only)

The trial can be started immediately after accepting terms — no connector deployment is needed first. However, the connector's capture processor will not run until the trial is active.

1. Navigate to **Admin >> Terms >> Openflow for Oracle** (available immediately after Part 1).
2. Locate the **Trial Status** card (status: "Ready to Activate").
3. Click **Start Trial**.
4. Confirm: Accept the terms to start the 60-day clock.

**Note:** You can start the trial now and proceed with Oracle database prerequisites and connector deployment in parallel. The trial clock runs regardless of whether the connector is deployed.

### Part 2b: Independent License (BYOL)

No trial activation is needed. After accepting terms in Part 1, proceed directly to connector configuration.

### Part 3: Verify (Both License Types)

After the connector is deployed, configured, and connects to the source database, return to **Admin >> Terms >> Openflow for Oracle** and verify:

| UI Section | What to Verify | Success Criteria |
|------------|----------------|------------------|
| Trial Status | Countdown timer (Embedded only) | Shows "X days remaining" or "Active" |
| Cost Projections | Total Oracle database CPU cores | Core count matches source Oracle system |
| Subscription Inventory | Database instance list | Instances listed, CPU counts correct, License Status "Active" |

**Note:** Cost Projections and Subscription Inventory only populate after the connector successfully connects to the Oracle source and reports core counts.

---

Return to [`connector-oracle.md`](../connector-oracle.md).
