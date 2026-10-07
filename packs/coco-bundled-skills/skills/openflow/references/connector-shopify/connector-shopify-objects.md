---
name: openflow-connector-shopify-objects
description: Object Definitions Override reference for the Openflow Shopify connector — full field reference, the JSON Schema asset, and the field-verification procedure for adding or customizing Shopify objects. Loaded from connector-shopify.md when authoring overrides.
---

# Shopify — Object Definitions Override

Loaded from [`connector-shopify.md`](../connector-shopify.md) when adding or customizing Shopify objects via the `Object Definitions Override` parameter. Contains the full field reference, the JSON
Schema (as an asset), the field-verification procedure, and worked examples.

## Adding New Objects (Object Definitions Override)

Any Shopify Admin GraphQL query-root object can be synced without a code release by adding a definition to the `Object Definitions Override` parameter (a JSON **array**) and listing its `apiType` in
`Objects to Sync`.

> **CRITICAL — Preview and confirm before applying.** Before updating the `Object Definitions Override` parameter:
>
> 1. **Show a formatted preview** of the complete new definition JSON to the user and wait for explicit confirmation before applying. Never apply without user approval.
> 2. **Clarify ambiguous data types.** If there is any uncertainty about `gidTypeName`, `promotedColumns` types, field types, or any other data type choice, ask the user for clarification before
     proceeding. Do not guess.
> 3. **Validate the JSON.** The value must be a syntactically valid JSON **array**. Invalid JSON (or a non-array top-level value) fails
     > validation on the `StandardShopifyObjectRegistryService`, which leaves the controller services unable to enable and **the connector fails to start**. Always verify the JSON before saving the
     > parameter:
>
> ```bash
> # Validate that override.json parses AND is a top-level array (exit code 0 = valid)
> python3 -c "import json, sys; d = json.load(open('override.json')); sys.exit(0 if isinstance(d, list) else 1)"
>
> # Or with jq (reads the file directly)
> jq -e 'type == "array"' override.json
> ```
>
> Only apply the parameter after this check passes. After updating it, re-enable the registry and GraphQL services and confirm they reach `ENABLED` (a validation failure surfaces as an INVALID service
> with the JSON error in its bulletin).

### Resolution order (highest wins)

1. **Override** — entries in `Object Definitions Override` (matching `apiType` replaces a bundled entry; new `apiType` is added).
2. **Bundled catalogue** — `shopify-objects-2026-04.json` in the NAR.
3. **Introspection** — live API discovery (only if `Enable Introspection` is true).

### Building `graphqlFields` safely (verify against the Admin GraphQL reference)

> **Never invent or guess fields, type names, or GID types.** Every entry in `graphqlFields` must be a real field on the object's GraphQL type for the configured `Shopify API Version`. A made-up
> field, a wrong argument, or a
> field copied from Shopify's **REST** API makes the entire query fail and the object never syncs. **The REST Admin API is a different API — its (snake_case) field names are not valid here and must
never be used or mixed in.** This is a hard rule: do not hallucinate.
>
> **Shopify deprecates and renames types across API versions.** An LLM's training data is always stale relative to the current API. Never rely on base-model memory for GraphQL type names, field names,
> or `gidTypeName` values — always fetch and verify against the official docs or the live QueryRoot for the configured version. For example, `OnlineStorePage` was deprecated in 2024-10 and replaced by
`Page`.

When generating or editing `graphqlFields`, consult the official **Admin GraphQL** reference for the target version (or the Shopify dev docs / MCP). **One page is never enough** — for any object you
must check **at least** both the query page and the object page, then recurse into every nested type:

1. **The query page** — `https://shopify.dev/docs/api/admin-graphql/<version>/queries/<queryName>`. This is the source of truth for the **query root**: that it exists, which **arguments** it accepts (
   `first`, `sortKey`, the `query` filter, `reverse`, and any required args → `requiredQueryArgs`), the valid **`…SortKeys`** enum values, and the **access scope the query requires**. To find or
   confirm the exact query-root name to use as `apiType` — and to see which top-level queries exist at all — browse the index of every available query on the **QueryRoot** page:
   `https://shopify.dev/docs/api/admin-graphql/<version>/objects/QueryRoot` (e.g. [latest](https://shopify.dev/docs/api/admin-graphql/latest/objects/QueryRoot)). `apiType` must match a query-root
   field name exactly.
2. **The object page** — `https://shopify.dev/docs/api/admin-graphql/<version>/objects/<Type>`. This lists the **fields** on the returned type, each field's **arguments**, **deprecations**, type, and
   any field-level scope notes.
3. **Each nested type's object page** — for every nested object or connection you select into, open *its* object page too, recursively, and apply the same checks. A parent object page does not
   document its children's fields.

Example — to build `orders` you must check at least:

- Query: [`.../queries/orders`](https://shopify.dev/docs/api/admin-graphql/latest/queries/orders) (args, sort keys, required scope)
- Object: [`.../objects/Order`](https://shopify.dev/docs/api/admin-graphql/latest/objects/Order) (Order fields)
- Plus the object page for **every nested type you select**, e.g. `LineItem`, `MoneyBag`/`MoneyV2`, `MailingAddress`, `Fulfillment`, `Customer`, … — and so on for anything nested inside those.

For every field confirm:

1. **It exists** on that GraphQL type for the configured API version (versions add and remove fields).
2. **It is not deprecated.** Avoid deprecated fields — they may be removed in a later version, and some require a write scope just to read (
   see [Fields that require a write scope to read](#fields-that-require-a-write-scope-to-read)). Prefer the documented replacement.
3. **Arguments are correct.** If a field requires arguments, supply them inline (e.g. `metafield(key: "custom.x") { value }`, a connection `lineItems(first: 250) { ... }`). A field that requires an
   argument but is queried without it fails. Confirm field arguments on the field's own object page and query-root arguments on the query page.
4. **The selection shape matches the field kind.** Scalars/enums take no sub-selection; objects and connections need `{ ... }` (connections use `(first: N) { edges { node { ... } } }`, or the array
   form). Decide inline vs. child table — see [Child tables](connector-shopify-objects-examples.md#3-child-tables-edges-and-array-connections).
5. **Granted scopes permit it.** The query page states the read scope the query root requires (see also [Configure Admin API Scopes](../connector-shopify.md#step-2-configure-admin-api-scopes)); some
   fields additionally
   require a write scope to read; full `orders` history needs `read_all_orders`. Confirm the app's granted scopes cover both the object and the specific fields selected.

Also respect these query constraints while building the selection:

- Bulk queries allow at most **5 connections** total and **2 levels** of nesting (a `metafields` connection counts toward the 5).
- `sortKeys` must be valid values from the type's `…SortKeys` enum — a wrong value fails the whole bulk operation (omit if unsure).
- **Bulk API is lenient about non-existent fields; incremental queries are not.** The Bulk API silently ignores fields that don't exist on a type (returning `null`), so a bulk load can succeed even
  with an invalid field name. However, the paginated incremental query (used by `GetShopifyIncremental`) performs strict GraphQL validation and will fail with `Field 'X' doesn't exist on type 'Y'`.
  This means a definition can appear to work during initial bulk load but break on the first incremental sync. **Always verify field names against the current API version docs for both the bulk and
  incremental paths.**
- `incrementalField` must be (a) a real timestamp field on the type **and** (b) accepted as a filter field by the query root's `query:` argument. (b) is the rule that bites: the connector uses `incrementalField` to build the Shopify `query: "<field>:>'<watermark>'"` filter, and Shopify rejects unsupported filter fields with `Invalid search field: <name>`. Verify by looking up the query root's `query:` argument doc in the Admin GraphQL reference (or test once via the API explorer). If the timestamp exists on the type but the query root won't filter on it, set `supportsIncremental: false` and `refreshStrategy: "FULL_PERIODIC"`.

**If anything is unclear — whether a field exists, which arguments it takes, which scope it needs, or which object/API version the user means — stop and ask the user to confirm rather than guessing.**
After building a definition, [validate the JSON](#adding-new-objects-object-definitions-override), then run `verify_config` and a small test sync and read bulletins (
see [Validate Data Flow](../connector-shopify.md#validate-data-flow)) to confirm Shopify accepts the query before relying on it.

### ShopifyObjectDefinition fields

| Field                    | Type                       | Required           | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
|--------------------------|----------------------------|--------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `apiType`                | string                     | Yes                | GraphQL query-root field name, e.g. `fulfillmentOrders`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `tableName`              | string                     | Yes                | Snowflake table name, e.g. `FULFILLMENT_ORDERS`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `graphqlFields`          | string[]                   | Yes                | Complete GraphQL selection set, including embedded child connections.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `gidTypeName`            | string                     | Recommended        | The **resource type segment** from the Shopify GID (`gid://shopify/{gidTypeName}/{id}`). This may differ from both the `apiType` (query-root name) and the GraphQL object type name — types get renamed/unified across API versions. **Never guess from memory — always verify** by checking the `id` field in a sample API response or the current object page in the Admin GraphQL docs for the configured `Shopify API Version`. Used to route records during partitioning and for delete cascades. Required in practice for objects with child tables or deletes. |
| `supportsIncremental`    | boolean                    | No (`true`)        | Set `false` for full-periodic objects.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `supportsBulk`           | boolean                    | No (`true`)        |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `incrementalField`       | string                     | No (auto)          | `updatedAt`, `processedAt`, etc. `null` → auto-discovered from `graphqlFields`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `sortKeys`               | string[]                   | No                 | UPPER_SNAKE_CASE, e.g. `["UPDATED_AT","CREATED_AT"]`. A wrong sort key fails the whole bulk operation — omit if unsure.                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `sortKeyStyle`           | string                     | No (`ENUM`)        | `STRING` only for `metaobjects`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `refreshStrategy`        | string                     | No (`INCREMENTAL`) | `INCREMENTAL`, `FULL_PERIODIC`, or `PARENT_PIGGYBACKED`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `additionalGidTypeNames` | string[]                   | No                 | Extra GID type names that also route to this table. **Required for union-type queries** (e.g. `discountNodes` returns `DiscountCodeNode` and `DiscountAutomaticNode` — both must be registered). See [Union types](#union-types-and-gid-routing) and [example](connector-shopify-objects-examples.md#6-other-useful-cases).                                                                                                                                                                                                                                                                                |
| `supportsDeletes`        | boolean                    | No (`false`)       | Whether the Events API fires destroy events for this type.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `ignoredFields`          | string[]                   | No                 | Top-level `graphqlFields` entries to drop from queries (matched by leading field/alias name only — see note below).                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `requiredQueryArgs`      | object                     | No                 | Fixed GraphQL args appended to every query for the object, e.g. `metaobjects` require `{"type": "\"my_type\""}`. See the [requiredQueryArgs example](connector-shopify-objects-examples.md#6-other-useful-cases).                                                                                                                                                                                                                                                                                                                                                                                          |
| `promotedColumns`        | PromotedColumnDefinition[] | No                 | Promote nested values into dedicated top-level columns.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `childFields`            | ChildFieldDefinition[]     | No                 | Child connections extracted into their own tables.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |

> **Discounts:** prefer the unified `discountNodes` query root (uses `additionalGidTypeNames` for `DiscountCodeNode` + `DiscountAutomaticNode` routing) — it supports `query: "updated_at:>..."`. The per-subtype query roots `codeDiscountNodes` and `automaticDiscountNodes` do **not** accept `updated_at` as a filter; if you split them out, set `supportsIncremental: false` + `refreshStrategy: "FULL_PERIODIC"`.

#### Fields that require a write scope to read

Some Admin GraphQL fields require a **write** scope to be *read*. For example, as of the 2025-12 API the customer marketing-URL fields require `write_customers` (per the Shopify
changelog [Customer marketing URL fields now require write access](https://shopify.dev/changelog/customer-marketing-url-fields-now-require-write-access)): `Customer.unsubscribeUrl` (deprecated),
`CustomerEmailAddress.marketingUnsubscribeUrl` / `openTrackingUrl`, and `CustomerPhoneNumber.marketingUnsubscribeUrl`. If the app lacks the required write scope, the Shopify API returns an *
*error for that field**, which fails the query (and the object's sync) rather than just omitting the field.

Since the connector only needs read access, the fix is to **not request the field** — choose based on whether it is a top-level entry or a nested sub-field:

- **Top-level field** (a direct entry in `graphqlFields`, e.g. the deprecated `unsubscribeUrl`): remove it from `graphqlFields`, or add its name to `ignoredFields`.
- **Nested field** (inside another entry's sub-selection, e.g. `marketingUnsubscribeUrl` within `defaultEmailAddress { ... }`): `ignoredFields` does **not** help — it matches only the leading name of
  each top-level `graphqlFields` entry and never descends into sub-selections. You must edit the parent entry's sub-selection in `graphqlFields` to drop the offending field (or remove the whole parent
  entry).

Either way, supply the corrected definition via `Object Definitions Override` (validate the JSON first — see the callout above). Alternatively, grant the required write scope on the dev app if you
genuinely need the field — remember to **Release** a new version and **Reinstall** on the store for the new scope to take effect.

### PromotedColumnDefinition

```json
{
  "name": "TOTAL_PRICE",
  "path": "$.totalPriceSet.shopMoney.amount",
  "type": "money"
}
```

| `type`      | Snowflake      | Notes                                 |
|-------------|----------------|---------------------------------------|
| `id`        | `NUMBER(38,0)` | Strips the `gid://shopify/*/` prefix. |
| `gid`       | `VARCHAR`      | Full GID string.                      |
| `timestamp` | `TIMESTAMP_TZ` | ISO-8601.                             |
| `date`      | `DATE`         |                                       |
| `money`     | `NUMBER(38,4)` | Amount string → numeric.              |
| `float`     | `FLOAT`        |                                       |
| `string`    | `VARCHAR`      |                                       |
| `boolean`   | `BOOLEAN`      |                                       |
| `integer`   | `NUMBER(38,0)` |                                       |
| `json`      | `VARIANT`      | Sub-object stored as VARIANT.         |

### ChildFieldDefinition

```json
{
  "fieldName": "lineItems",
  "tableName": "ORDER_LINE_ITEMS",
  "gidTypeName": "LineItem",
  "connectionType": "edges",
  "pageSize": 250,
  "graphqlFields": [
    "id",
    "quantity",
    "sku"
  ],
  "promotedColumns": []
}
```

| Field             | Default | Notes                                                                                                                         |
|-------------------|---------|-------------------------------------------------------------------------------------------------------------------------------|
| `fieldName`       | —       | Field/alias name in the parent selection.                                                                                     |
| `tableName`       | —       | Target Snowflake child table.                                                                                                 |
| `gidTypeName`     | —       | GID type for the child records.                                                                                               |
| `connectionType`  | `edges` | `edges` = GraphQL edges/node; `array` = plain JSON array.                                                                     |
| `pageSize`        | `250`   | `first: N` on **incremental** child queries. Default and **max 250** — Shopify's hard limit for `first:` on regular queries; a larger value is rejected with `first cannot exceed 250`. (The JSON Schema enforces ≤ 250.) |
| `graphqlFields`   | —       | Optional explicit child selection set; if omitted, parsed from the matching connection entry in the parent's `graphqlFields`. |
| `promotedColumns` | —       | Promoted columns for the child table.                                                                                         |

### Union types and GID routing

When a query returns a **union type** (e.g. `discountNodes` returns the `Discount` union with concrete types `DiscountAutomaticBasic`, `DiscountCodeBasic`, etc.), the records in the Bulk API response
carry GID types corresponding to the **wrapper node types** (e.g. `DiscountCodeNode`, `DiscountAutomaticNode`), NOT the concrete inner union members and NOT the query-root name.

**The `PartitionShopifyByObject` processor routes records by their GID type.** If the GID type is not registered (in `gidTypeName` or `additionalGidTypeNames`), records are routed to failure with:

```
No schema definition found for GID type 'X' — N record(s) routed to 'failure'
```

**To correctly route union-type queries:**

1. **Run a test bulk first** (or check the Shopify docs) to discover what GID types actually appear in the response. Do NOT guess — union wrappers often have surprising GID types (e.g.
   `DiscountCodeNode` and `DiscountAutomaticNode`, not `DiscountNode`).
2. **Set `gidTypeName`** to one of the concrete GID types (e.g. `DiscountCodeNode`).
3. **Set `additionalGidTypeNames`** to an array of all OTHER GID types that should route to the same table (e.g. `["DiscountAutomaticNode"]`).
4. **Use inline fragments** in `graphqlFields` for the union field (e.g. `discount { ... on DiscountCodeBasic { title status } ... on DiscountAutomaticBasic { title status } }`). The Shopify Bulk API
   supports inline fragments; the connector passes them through verbatim.

**Example — `discountNodes`:**

```json
{
  "apiType": "discountNodes",
  "tableName": "DISCOUNTS",
  "gidTypeName": "DiscountCodeNode",
  "additionalGidTypeNames": [
    "DiscountAutomaticNode"
  ],
  "graphqlFields": [
    "id",
    "discount { ... on DiscountCodeBasic { title status startsAt endsAt createdAt updatedAt } ... on DiscountAutomaticBasic { title status startsAt endsAt createdAt updatedAt } }"
  ]
}
```

**Common mistake:** Setting `gidTypeName` to the query-root name (e.g. `DiscountNode`) or the GraphQL union type name (e.g. `Discount`) — neither appears in the actual GID. Always verify from real API
responses.

**`promotedColumns` paths on union objects:** the JSON root after partitioning is the **wrapper node** (e.g. `{ id, discount: { … } }`), not the inner union member. Promoted-column `path` must include the wrapper field: `$.discount.title`, not `$.title`. A wrong path creates the column with all NULLs and no error.

---

### JSON Schema (validate the override)

The JSON Schema (Draft 2020-12) for the override is shipped as an asset: [`assets/shopify-object-definitions.schema.json`](assets/shopify-object-definitions.schema.json). It covers the fields the
connector consumes; unknown keys are ignored (`additionalProperties` is open, so extra fields like `displayName` are accepted but inert). Validate the `Object Definitions Override` value against it
with any Draft 2020-12 validator:

```bash
jsonschema -i override.json assets/shopify-object-definitions.schema.json
```

The schema enforces the structural rules the connector relies on (required `apiType`/`tableName`/`graphqlFields`; valid enum values for `type`, `connectionType`, `refreshStrategy`, `sortKeyStyle`;
`requiredQueryArgs` value shapes; `pageSize` ≤ 250). It does **not** — and cannot — verify that field names exist in Shopify's schema or that scopes are granted; for that, follow [Building
`graphqlFields` safely](#building-graphqlfields-safely-verify-against-the-admin-graphql-reference).

### Examples by case

For worked examples — minimal new objects, promoted columns, child tables, GraphQL aliases, metafields, miscellaneous patterns, and multi-object arrays — **Load** [`connector-shopify-objects-examples.md`](connector-shopify-objects-examples.md).

---
