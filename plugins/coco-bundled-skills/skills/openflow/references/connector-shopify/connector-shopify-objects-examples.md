---
name: openflow-connector-shopify-objects-examples
description: Worked examples for the Shopify connector Object Definitions Override — 7 cases covering minimal objects, promoted columns, child tables, GraphQL aliases, metafields, miscellaneous patterns (no-incremental, non-default timestamp, requiredQueryArgs, additionalGidTypeNames, customizing built-ins), and multi-object arrays. Loaded from connector-shopify-objects.md.
---

# Shopify — Object Definitions Override: Examples

Loaded from [`connector-shopify-objects.md`](connector-shopify-objects.md). Each example below is a single definition. The parameter value is a JSON **array** — wrap one or more definitions in `[ ... ]` and [validate the JSON](connector-shopify-objects.md#adding-new-objects-object-definitions-override)
before saving. After changing the parameter, re-enable the registry/GraphQL services and add the `apiType` to `Objects to Sync`.

> **Override replaces, it does not merge.** A definition whose `apiType` matches a bundled object **replaces the bundled entry wholesale** — it does not patch individual fields. To customize a
> built-in object (e.g. `orders`, `products`), copy its full definition and edit it; otherwise you lose every field/child/column you didn't repeat. New `apiType` values are simply added.

## 1. Simple case (minimal new object)

Set `Object Definitions Override` to:

```json
[
  {
    "apiType": "fulfillmentOrders",
    "tableName": "FULFILLMENT_ORDERS",
    "gidTypeName": "FulfillmentOrder",
    "supportsIncremental": true,
    "supportsBulk": true,
    "incrementalField": "updatedAt",
    "sortKeys": [
      "UPDATED_AT"
    ],
    "graphqlFields": [
      "id",
      "createdAt",
      "updatedAt",
      "status",
      "requestStatus"
    ],
    "promotedColumns": [],
    "childFields": []
  }
]
```

The minimal valid definition needs only `apiType`, `tableName`, and `graphqlFields` (with a timestamp field present for auto-discovery to infer the incremental field).

## 2. Promoting columns (simple and nested)

By default the connector lands the raw record (plus base columns); `promotedColumns` lift specific values into dedicated, typed top-level columns. A `path` may be a **top-level** scalar (`$.title`) or
a **nested** JSON path (`$.priceRangeV2.minVariantPrice.amount`). Every path you promote must also be present in `graphqlFields`.

```json
{
  "apiType": "products",
  "tableName": "PRODUCTS",
  "gidTypeName": "Product",
  "graphqlFields": [
    "id",
    "title",
    "status",
    "createdAt",
    "updatedAt",
    "priceRangeV2 { minVariantPrice { amount currencyCode } }",
    "variantsCount { count }"
  ],
  "promotedColumns": [
    {
      "name": "TITLE",
      "path": "$.title",
      "type": "string"
    },
    {
      "name": "MIN_VARIANT_PRICE",
      "path": "$.priceRangeV2.minVariantPrice.amount",
      "type": "money"
    },
    {
      "name": "VARIANTS_COUNT",
      "path": "$.variantsCount.count",
      "type": "integer"
    }
  ]
}
```

`type` controls the Snowflake column type (`id`, `gid`, `timestamp`, `date`, `money`, `float`, `string`, `boolean`, `integer`, `json` — see [PromotedColumnDefinition](connector-shopify-objects.md#promotedcolumndefinition)).

> **Union-typed queries:** the JSON root is the **wrapper node** that gets partitioned (e.g. `{ id, codeDiscount: { … } }` for `codeDiscountNodes`), not the inner union member. Promoted-column `path` values must include the wrapper field, e.g. `$.codeDiscount.title` — not `$.title`. A column promoted with the wrong path is created but stays NULL with no runtime error. Confirm by inspecting a sample bulk JSONL record before applying the override.

## 3. Child tables (edges and array connections)

A nested connection is split into its own Snowflake table, with each child row carrying `__PARENT_ID` (the parent's GID). The child's **field selection lives inside the parent's `graphqlFields`**
connection string; the `childFields` entry just declares routing (target table, GID type, connection type, page size). You may instead set an explicit `graphqlFields` on the child to override that
parent-derived selection.

```json
{
  "apiType": "orders",
  "tableName": "ORDERS",
  "gidTypeName": "Order",
  "graphqlFields": [
    "id",
    "name",
    "createdAt",
    "updatedAt",
    "lineItems(first: 250) { edges { cursor node { id name quantity sku } } }",
    "fulfillments { id status createdAt }"
  ],
  "childFields": [
    {
      "fieldName": "lineItems",
      "tableName": "ORDER_LINE_ITEMS",
      "gidTypeName": "LineItem",
      "connectionType": "edges",
      "pageSize": 250
    },
    {
      "fieldName": "fulfillments",
      "tableName": "ORDER_FULFILLMENTS",
      "gidTypeName": "Fulfillment",
      "connectionType": "array",
      "pageSize": 10
    }
  ]
}
```

- `connectionType: "edges"` — a GraphQL `edges { node }` connection (selection uses `edges { ... node { ... } }`).
- `connectionType: "array"` — a plain JSON list field (selection is a bare `{ ... }`, no `edges`/`node`).
- The Bulk API allows at most **5 connections** per query and **2 levels** of nesting; child connections and `metafields` all count toward the 5.

## 4. Labelling fields with GraphQL aliases

A GraphQL alias (`label: realField`) renames a field in the response — useful to give a column a friendlier name or to expose a single nested value. Aliases pass through verbatim because the connector
concatenates `graphqlFields` as-is.

```json
{
  "apiType": "customers",
  "tableName": "CUSTOMERS",
  "gidTypeName": "Customer",
  "graphqlFields": [
    "id",
    "createdAt",
    "updatedAt",
    "primaryEmail: email",
    "addresses: addressesV2(first: 250) { edges { cursor node { id address1 city country } } }"
  ],
  "childFields": [
    {
      "fieldName": "addresses",
      "tableName": "CUSTOMER_ADDRESSES",
      "gidTypeName": "MailingAddress",
      "connectionType": "edges",
      "pageSize": 250
    }
  ]
}
```

**Key rule:** when you alias a connection, the `childFields` `fieldName` must match the **alias** (`addresses`), not the underlying field (`addressesV2`) — child routing keys off the response key,
which is the alias. Set `gidTypeName` to the GID type of the connection's nodes (confirm it in the Admin API reference).

## 5. Metafields

> **Metafields are expensive — fetch only what you need.** Pulling all metafields (the `metafields(first: N)` connection / the `Include Metafields` parameter) **significantly increases query cost and
response size**, and the connection counts toward the Bulk API's 5-connection limit. On stores with many metafields this is a common cause of slow syncs and throttling. **Prefer querying the specific
metafields you need by key** (cheap, predictable) over bulk-fetching them all.

**Preferred — query specific metafields by key via alias.** Alias `metafield(key: "namespace.key")` to a friendly name and promote its `.value` into a typed column (this is the pattern shown in
the [official docs](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/shopify/object-definitions)). This adds **no** extra connection and fetches only the keys you list:

```json
{
  "apiType": "products",
  "tableName": "PRODUCTS",
  "gidTypeName": "Product",
  "graphqlFields": [
    "id",
    "title",
    "updatedAt",
    "care_instructions: metafield(key: \"custom.care_instructions\") { value }",
    "fabric_type: metafield(key: \"custom.fabric_type\") { value }"
  ],
  "promotedColumns": [
    {
      "name": "CARE_INSTRUCTIONS",
      "path": "$.care_instructions.value",
      "type": "string"
    },
    {
      "name": "FABRIC_TYPE",
      "path": "$.fabric_type.value",
      "type": "string"
    }
  ]
}
```

**Bulk (all metafields) — use only when you genuinely need every metafield.** Set the `Include Metafields` parameter to `true` (or add a `metafields(first: N)` connection to `graphqlFields`). This is
the expensive path:

- It **significantly increases query cost and response size** and consumes one of the **5** allowed nested connections — keep `first` as low as you can, and avoid combining it with many other child
  connections on the same object.
- When `Include Metafields` is `false` (the default) the connector strips any `metafields` selection from the query (it is treated as an ignored field), so nothing is fetched even if the definition
  includes it. The by-key alias approach above does **not** require this parameter.
- If you need all metafields in their own Snowflake table, add a `childFields` entry for the `metafields` connection — the mechanics are identical to any child connection (
  see [Child tables](#3-child-tables-edges-and-array-connections), e.g. `orders` → `lineItems` or `products` → `options`).
- The bulk metafields selection is driven by what's in `graphqlFields` plus the `Include Metafields` parameter.

## 6. Other useful cases

**Object with no incremental field** — for objects that have no usable `updated_at` query filter, set `supportsIncremental: false` (the registry marks these `FULL_PERIODIC`). The object is
**bulk-loaded once** and is not incrementally updated; to pull fresh data, reset its state so the bulk re-runs (see [Reset an Object](../connector-shopify.md#reset-replication-for-one-object)):

```json
{
  "apiType": "locations",
  "tableName": "LOCATIONS",
  "gidTypeName": "Location",
  "supportsIncremental": false,
  "refreshStrategy": "FULL_PERIODIC",
  "graphqlFields": [
    "id",
    "name",
    "isActive",
    "createdAt",
    "updatedAt"
  ]
}
```

**Incremental on a non-default timestamp** — for objects whose change field isn't `updatedAt`, set `incrementalField` explicitly (e.g. `processedAt`):

```json
{
  "apiType": "tenderTransactions",
  "tableName": "TENDER_TRANSACTIONS",
  "gidTypeName": "TenderTransaction",
  "incrementalField": "processedAt",
  "graphqlFields": [
    "id",
    "processedAt",
    "test",
    "paymentMethod",
    "amount { amount currencyCode }"
  ]
}
```

**Required query arguments (`requiredQueryArgs`)** — some query roots require a fixed argument the connector does not set on its own. `requiredQueryArgs` appends `key: value` to every query for the
object (bulk and incremental). The canonical case is `metaobjects`, whose query **requires** a `type` argument — and each metaobject type is its own definition (distinct `type` and `tableName`):

```json
{
  "apiType": "metaobjects",
  "tableName": "METAOBJECTS_BOOK_REVIEW",
  "gidTypeName": "Metaobject",
  "sortKeyStyle": "STRING",
  "requiredQueryArgs": {
    "type": "\"book_review\""
  },
  "graphqlFields": [
    "id",
    "handle",
    "displayName",
    "type",
    "updatedAt",
    "fields { key value type }"
  ]
}
```

This builds `metaobjects(..., type: "book_review")`. **Value format** (validated before the query is built — an invalid value fails the build):

- boolean — `"reverse": "true"`
- integer — `"someCount": "5"`
- `UPPER_SNAKE` enum (bare, unquoted in the query) — `"type": "SALES_CHANNEL"` → `type: SALES_CHANNEL`
- quoted string (escape the quotes in JSON) — `"type": "\"book_review\""` → `type: "book_review"`

Keys must be valid GraphQL identifiers. `metaobjects` also uses string sort keys, hence `sortKeyStyle: STRING`. Confirm which arguments a query requires (and whether it supports incremental filtering)
in the Admin API reference.

**Multiple GID types routing to one table (`additionalGidTypeNames`)** — `PartitionShopifyByObject` routes each record to a table by its **GID type** (`gid://shopify/<Type>/<id>`). When a query
returns the same logical resource under more than one GID type — typically a GraphQL **interface** with concrete subtypes — list the extra types in `additionalGidTypeNames` so every record resolves to
the same table. Without it, records carrying an unlisted GID type are sent to the `unmatched` relationship. This is exactly why the bundled `catalogs` object maps the `Catalog` interface's subtypes:

```json
{
  "apiType": "catalogs",
  "tableName": "CATALOGS",
  "gidTypeName": "Catalog",
  "additionalGidTypeNames": [
    "MarketCatalog",
    "AppCatalog"
  ],
  "supportsIncremental": false,
  "graphqlFields": [
    "id",
    "title",
    "status"
  ]
}
```

Records with `gid://shopify/MarketCatalog/...` or `gid://shopify/AppCatalog/...` now land in `CATALOGS` alongside `gid://shopify/Catalog/...`. `ChildFieldDefinition` accepts the same
`additionalGidTypeNames` for child connections whose nodes are polymorphic.

**Customize a built-in object** — because an override replaces the bundled entry by `apiType`, copy the built-in definition and edit it: add a `promotedColumns` entry, add a child table, or set
`ignoredFields` to drop a field you cannot read (see [Fields that require a write scope to read](connector-shopify-objects.md#fields-that-require-a-write-scope-to-read)). Remember to keep the rest of the definition intact — the
override does not merge.

> **When to override vs. when to use a SQL view.** A bundled-entry override is the right tool when you need to **change what is fetched** — add a new `graphqlField`, change `incrementalField`, add a child table, add `additionalGidTypeNames`, or set `ignoredFields`. For anything that is **just a different shape of already-fetched data** (a flat column from a `VARIANT` path, a coalesced field, a typed cast), prefer a Snowflake **view** on the bundled table — it avoids re-declaring 60+ fields and stays compatible across connector upgrades. Reserve overrides for cases where SQL can't do the job.

## 7. Multiple objects in one override (it is one array)

The `Object Definitions Override` parameter holds **one JSON array** containing **every** definition you want — you do not set one object per parameter. Combine brand-new objects and customizations of
built-ins in the same array: an entry whose `apiType` is new is **added**, an entry whose `apiType` matches a bundled object **replaces** it.

```json
[
  {
    "apiType": "metaobjects",
    "tableName": "METAOBJECTS_BOOK_REVIEW",
    "gidTypeName": "Metaobject",
    "sortKeyStyle": "STRING",
    "requiredQueryArgs": {
      "type": "\"book_review\""
    },
    "graphqlFields": [
      "id",
      "handle",
      "type",
      "updatedAt",
      "fields { key value type }"
    ]
  },
  {
    "apiType": "locations",
    "tableName": "LOCATIONS",
    "gidTypeName": "Location",
    "supportsIncremental": false,
    "refreshStrategy": "FULL_PERIODIC",
    "graphqlFields": [
      "id",
      "name",
      "isActive",
      "createdAt",
      "updatedAt"
    ]
  }
]
```

Here `metaobjects` is **added** (it is not in the bundled catalogue) and `locations` **replaces** the bundled `locations` entry — both in a single array, which is the entire parameter value. List each
object's `apiType` in `Objects to Sync` as well.

---

Return to [`connector-shopify-objects.md`](connector-shopify-objects.md).
