---
name: openflow-connector-shopify-discover
description: Pre-override discovery recipe for the Shopify connector — run a single GraphQL probe to classify candidate query roots as present, empty, scope-missing, or API-not-available before deciding what to add to Objects to Sync or Object Definitions Override. Loaded from connector-shopify.md.
---

# Shopify — Object Discovery

Loaded from [`connector-shopify.md`](../connector-shopify.md) when a user asks what objects exist in their shop before writing an `Object Definitions Override`.

## Discover what's in the shop before writing an override

Run a single GraphQL query against the shop's Admin API to classify candidate query roots before choosing what to add to `Objects to Sync` or `Object Definitions Override`. This avoids writing a definition for an object that is empty, scope-blocked, or unavailable in the configured API version.

### Probe query

Save the query below to a file (e.g. `probe.graphql`), then run:

```bash
curl -X POST \
  https://<shop>.myshopify.com/admin/api/<version>/graphql.json \
  -H 'Content-Type: application/json' \
  -H 'X-Shopify-Access-Token: <token>' \
  -d "{\"query\": \"$(cat probe.graphql | tr -d '\n' | sed 's/"/\\"/g')\"}"
```

Where `<token>` is a short-lived Admin API token you fetch from the OAuth2 token endpoint using the same dev-app credentials the connector uses:

```bash
curl -X POST https://<shop>.myshopify.com/admin/oauth/access_token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'grant_type=client_credentials&client_id=<client_id>&client_secret=<client_secret>'
# → { "access_token": "shpat_...", "scope": "..." }
```

Pass the returned `access_token` value in the `X-Shopify-Access-Token` header — same wire format the connector uses.

Or inline for a single root (e.g. to spot-check one object):

```bash
curl -X POST \
  https://<shop>.myshopify.com/admin/api/2026-04/graphql.json \
  -H 'Content-Type: application/json' \
  -H 'X-Shopify-Access-Token: <token>' \
  -d '{"query": "{ orders(first: 1) { edges { node { id } } } }"}'
```

Expand or trim the root list to match the objects you are considering.

```graphql
{
  orders(first: 1)            { edges { node { id } } }
  draftOrders(first: 1)       { edges { node { id } } }
  products(first: 1)          { edges { node { id } } }
  customers(first: 1)         { edges { node { id } } }
  inventoryItems(first: 1)    { edges { node { id } } }
  collections(first: 1)       { edges { node { id } } }
  fulfillmentOrders(first: 1, assignedLocationIds: []) { edges { node { id } } }
  marketingEvents(first: 1)   { edges { node { id } } }
  giftCards(first: 1)         { edges { node { id } } }
  markets(first: 1)           { edges { node { id } } }
  discountNodes(first: 1)     { edges { node { id } } }
  catalogs(first: 1)          { edges { node { id } } }
  metaobjects(first: 1, type: "") { edges { node { id } } }
  pages(first: 1)             { edges { node { id } } }
  blogs(first: 1)             { edges { node { id } } }
}
```

### Interpreting the response

| Response for a root | Classification | What to do |
|---------------------|---------------|------------|
| Returns `edges` with nodes | **Present** — data exists | Safe to add to `Objects to Sync` |
| Returns `edges: []` | **Empty** — object type exists, no records yet | Safe to add; bulk load will complete immediately |
| Error: `Access denied for <field>` | **Scope-missing** — the app lacks the required read scope | Add the scope in the dev app **Access** section, **Release** a new version, and **Reinstall** on the store |
| Error: `Field '<field>' doesn't exist on type 'QueryRoot'` | **API-not-available** — query root absent in this API version | Change the configured API version, or the object isn't supported |

### Also check incremental support

Before finalizing a definition, confirm the query root accepts `updated_at` as a `query:` filter — this is required for incremental sync and is separate from whether the field exists on the returned type:

```graphql
{
  <queryRoot>(first: 1, query: "updated_at:>'2020-01-01'") { edges { node { id } } }
}
```

- If it returns results or `edges: []` — incremental is supported; use `refreshStrategy: "INCREMENTAL"` (default).
- If it errors with `Invalid search field: updated_at` — the query root does not support `query:` filtering on this field; set `supportsIncremental: false` and `refreshStrategy: "FULL_PERIODIC"`.

See [connector-shopify-objects.md](connector-shopify-objects.md#incrementalfield) and [troubleshooting](connector-shopify-troubleshooting.md#incremental-fails-with-invalid-search-field-name) for details.

---

Return to [`connector-shopify.md`](../connector-shopify.md).
