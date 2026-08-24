---
name: openflow-connector-shopify-fleet
description: Fleet/multi-shop deployment guidance for the Openflow Shopify connector — the one-connector-per-shop model, shared-vs-per-shop parameters, destination strategies, token provisioning at scale, sizing/limits, and the plan-then-apply rollout. Loaded from connector-shopify.md when deploying to many shops.
---

# Shopify — Fleet (Many-Shop) Deployment

Loaded from [`connector-shopify.md`](../connector-shopify.md) when deploying the Shopify connector across many stores.

## Deploying many shops (fleet)

Customers with tens or hundreds of Shopify stores deploy **one connector instance per shop**. A single connector instance has exactly one `Shop Domain` and one set of dev-app credentials (`Shopify Client ID` + `Shopify Client Secret`), so there is no multi-shop-in-one-connector mode — each shop is its own process group on a runtime.

### Per-shop model and what is shared vs. per-shop

| Value                                                                                                                                                            | Shared across shops                       | Per shop                                            |
|------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------|-----------------------------------------------------|
| `Shop Domain`                                                                                                                                                    | —                                         | Yes (unique)                                        |
| `Shopify Client ID`                                                                                                                                              | Usually shared (one dev app, many installs) | Only differs if you use a separate app per shop     |
| `Shopify Client Secret`                                                                                                                                          | Follows the Client ID (sensitive)         | Only differs when Client ID does                    |
| `Shopify API Version`, `Objects to Sync`, `Objects to Track for Deletes`, schedules, `Enable Introspection`, `Include Metafields`, `Object Definitions Override` | Usually the same for every shop           | Override per shop only if a store genuinely differs |
| Snowflake account / role / warehouse / auth                                                                                                                      | Yes                                       | —                                                   |
| `Destination Database` / `Destination Schema`                                                                                                                    | Depends on the destination strategy below | —                                                   |

> **Verify the parameter-context structure on the live flow before scripting a fleet.** The shipped `shopify-connector` flow exposes a single `Shopify Parameters` context. Inspect the deployed flow
> and confirm how repeated deploys bind parameter contexts; do not assume a multi-context layout.

### Destination strategy — two options

1. **Shared schema, partitioned by `SHOP_URL` (the connector's native multi-tenant design).** Point every shop's connector at the **same** `Destination Database`/`Destination Schema`. All shops write
   to the same tables; rows are keyed by the compound merge key `(ID, SHOP_URL)`, so shops don't collide. Queries filter/group by `SHOP_URL`. Simplest to operate at scale; one set of tables to manage.
2. **Per-shop schema or table suffix.** Give each shop its own schema, or suffix table names per tenant using the `shopify.shop.url.escaped` attribute emitted by `PartitionShopifyByObject` (e.g.
   `ORDERS_MY_STORE_MYSHOPIFY_COM`). Use when per-tenant isolation (separate grants, independent resets) is required. More objects to manage.

### Credentials at scale

Build **one Shopify dev app** and install it on every store you own or operate. The same `Shopify Client ID` / `Shopify Client Secret` values feed every connector instance — only `Shop Domain` differs per shop. The connector obtains and refreshes access tokens automatically from `https://<shop>.myshopify.com/admin/oauth/access_token`, so there is no per-shop token to mint or rotate in Snowflake. Store the Client Secret as a `snowflake:DB.SCHEMA.SECRET` reference (not inline). Any scope change requires **releasing a new dev-app version** and **reinstalling** on every store — plan scope changes as a fleet-wide event.

### Rate limits, sizing, and Snowflake limits

- **Shopify rate limits are per shop.** Each store has its own 1,000-point leaky bucket, so a fleet does **not** share one Shopify API budget — but every connector competes for the **runtime's**
  CPU/threads, and the initial bulk loads are heavy. Stagger first-time bulk loads and shard shops across multiple runtimes when one runtime saturates.
- **Confirm Snowflake-side limits before fanning out** (Snowpipe Streaming throughput/limits, warehouse concurrency, object counts). Don't assume one runtime absorbs hundreds of shops.
- One runtime per invocation; shard a large fleet across several runtimes (e.g. 50 shops each).

### Recommended workflow (plan-then-apply)

For repeatable fleet deploys, drive the rollout declaratively from a per-shop config (shop domain, token secret ref, objects, destination) and use a **plan-then-apply** model:

1. **Plan** — generate a written plan (e.g. a `.plan.md` next to the config) listing every shop to deploy, its parameters, and any blockers.
2. **Review & approve** — present the plan and wait for explicit human approval before making any change; never auto-apply at fleet scale.
3. **Apply serially** — deploy one shop at a time. **Journal** every state-changing step to an append-only log so a re-run after any failure resumes exactly where it left off (idempotent —
   already-deployed shops are skipped).
4. **Verify per shop** — run `verify_config` and read bulletins for each shop before moving to the next; surface failures instead of plowing ahead.
5. **Shard across runtimes** — process one runtime per invocation; split a large fleet (e.g. ~50 shops per runtime) and roll up the results.

Keep secrets out of the config — use `snowflake:DB.SCHEMA.SECRET` references (see [Credentials at scale](#credentials-at-scale)).

**Validate against the live flow before scripting.** Confirm every Shopify parameter name and how repeated deploys bind parameter contexts against the deployed `shopify-connector` flow — it ships a
single `Shopify Parameters` context, so don't assume a multi-context layout. Snowflake-side, the connector uses Snowpipe Streaming; confirm its limits and warehouse/object constraints before fanning
out to many shops.

---

Return to [`connector-shopify.md`](../connector-shopify.md).
