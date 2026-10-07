---
name: openflow-connector-shopify-troubleshooting
description: Symptom-based troubleshooting for the Openflow Shopify connector — HTTP 401 on OAuth2 auth, ACCESS_DENIED on an object (missing scope vs. protected customer data), UnknownHostException on the token endpoint, UnresolvedAddressException on the GCS bulk download, missing/empty data, access-denied on a single field, the 60-day order window, invalid Object Definitions Override, bulk-operation failures, duplicate or missing records, deletes not appearing, and throttling. Loaded from connector-shopify.md when diagnosing a failure.
---

# Shopify — Troubleshooting

Loaded from [`connector-shopify.md`](../connector-shopify.md) when diagnosing a Shopify connector failure. To re-snapshot an object, see [Reset replication for one object](../connector-shopify.md#reset-replication-for-one-object).

## Troubleshooting

### A table never appears / object is empty

1. Confirm the `apiType` is in `Objects to Sync` and is spelled correctly (case-insensitive, but must match a catalogue/override/introspection type).
2. Confirm the Shopify app has the matching **read scope** (e.g. `read_orders`). A missing scope yields access errors or empty results for that type only.
3. If it is a custom object, confirm the `Object Definitions Override` JSON is a valid array and the service was re-enabled.
4. If introspection is relied upon, confirm `Enable Introspection` is `true`.

### HTTP 401 Unauthorized from Shopify

Bulletin: `Shopify authentication failed (HTTP 401). Verify the Access Token or the configured OAuth2 Access Token Provider credentials and Authorization Server URL.` Sometimes surfaces as `[API] Invalid API key or access token (unrecognized login or wrong password)`. Check the following in order:

1. Confirm `Shopify Client ID` and `Shopify Client Secret` match the values in the dev app's **Settings → Credentials**.
2. Confirm the dev app has been **Released** (unreleased apps cannot authenticate).
3. Confirm the app is **Installed** on the store. If it was uninstalled at any point, tokens are revoked — reinstall, then re-enable the controller service so it fetches a fresh token.
4. Confirm the `StandardOauth2AccessTokenProvider` controller service is `ENABLED` and its `Authorization Server URL` resolves to `https://<Shop Domain>/admin/oauth/access_token`.

### `UnknownHostException` on the OAuth2 token request (SPCS)

Bulletin: `OAuth2 access token request failed` caused by `java.net.UnknownHostException: <shop>.myshopify.com`. The runtime can't reach Shopify to obtain a token — the EAI is missing, or the execute-as role lacks `USAGE` on it, or the network rule does not include `<shop>.myshopify.com:443`. Fix the EAI as described in the connector setup, restart the runtime binding if needed, then re-enable the controller services. **Load** `references/platform-eai.md` for the create/grant procedure.

### `UnresolvedAddressException` when downloading bulk results

Bulletin on `GetShopifyBulk` mentions `storage.googleapis.com` with `java.net.ConnectException` or `java.nio.channels.UnresolvedAddressException`. Shopify returned a signed Google Cloud Storage URL for the bulk output but the runtime cannot reach GCS. The EAI network rule must list **both** hosts:

```sql
ALTER NETWORK RULE openflow_<runtime_name>_shopify_network_rule
  SET VALUE_LIST = (
    '<shop>.myshopify.com:443',
    'storage.googleapis.com:443'
  );
```

Update the network rule and reattach the EAI to the runtime. The error will retry naturally on the next scheduled cycle.

### GraphQL `ACCESS_DENIED` on an object type

Distinct from a single-field access denial — this rejects the whole query. Two variants:

- **Missing read scope**: error text `Access denied for <object> field.` The app doesn't have the corresponding read scope. Add the scope in the dev app **Access** section, **Release** a new version, and **Install** it on the store. Then restart / re-enable the controller service.
- **Protected customer data not approved**: error text `This app is not approved to access the <Object> object.` The object exposes customer PII and requires Shopify's protected-customer-data approval. Submit a request from the app's **API access** settings. Bulk/incremental for that object stays broken until approval lands.

If the error is on a single field rather than the whole object, see the next section.

### A query fails with an access-denied error on one field

A few Admin GraphQL fields require a **write** scope to be read (e.g. the customer marketing-URL fields require `write_customers`). When the app lacks that scope, Shopify errors on the field and the
whole object's query fails. Remove the field from the object's `graphqlFields` (or, for a top-level entry, add its name to `ignoredFields`) via `Object Definitions Override` — for nested fields you
must edit the sub-selection, since `ignoredFields` matches top-level entries only.
See [Fields that require a write scope to read](connector-shopify-objects.md#fields-that-require-a-write-scope-to-read). Only grant the write
scope if you actually need the field (and remember: you must **Release** a new dev-app version and **Reinstall** on the store after changing scopes for the new permissions to take effect).

### Orders are missing older history (only ~60 days present)

Expected when the app lacks `read_all_orders` (see the [Critical](../connector-shopify.md#critical-read-first) note). Grant `read_all_orders` alongside `read_orders`, then [reset the `orders` object](../connector-shopify.md#reset-replication-for-one-object) so the bulk re-runs with full history.

### Connector will not start / Object Registry service is INVALID

Almost always an invalid `Object Definitions Override`. The value must be valid JSON and a top-level **array**. Check the `StandardShopifyObjectRegistryService` bulletin for the parse error (e.g. "
Invalid JSON" or "Must be a JSON array of object definitions"), fix the JSON (validate with `python3 -m json.tool` or `jq -e 'type=="array"'`), re-apply, and re-enable the service.

### Bulk operation fails immediately

- **Wrong sort key**: an unsupported `sortKeys` value fails the entire bulk operation. Remove the sort key from the object definition (omitting is safe) or correct it.
- **"A bulk operation is already in progress"**: Shopify allows only one bulk operation per shop at a time. Wait for the in-flight operation to finish; the processor retries on the next cycle. If it
  never clears, another app or connector on the **same shop** may be holding the bulk slot — check for other integrations running bulk operations.
- **Too many / too deep connections**: the Bulk API allows at most **5 connections** and **2 levels** of nesting. Reduce or flatten child connections, or disable `Include Metafields` (it consumes one).
- **Bulk operation stuck (no progress for a long time)**: very large datasets take time, but if a bulk operation shows no progress for an extended period it may be wedged. Narrow the volume with a
  `Date Filter` on `GetShopifyBulk`, or reset the object (below) and let it resubmit.

### Duplicate or missing records in Snowflake

- **Duplicates right after the initial load** are expected during the bulk→incremental handoff and are harmless — the merge deduplicates on the compound key `(ID, SHOP_URL)`, so the target converges.
  No action needed.
- **Records missing / not updating**: the incremental watermark may have advanced past them. Inspect per-object state (high watermark), and if it is
  wrong, [reset the object](../connector-shopify.md#reset-replication-for-one-object) to re-run bulk. For orders specifically, also confirm the 60-day window is not the cause (see below).

### Incremental routes to retry / failure

- `Fail If No Initial Load = true` routes to `failure`/`retry` until the bulk load for that type completes. This is expected on first run — let bulk finish.

### Incremental fails with `Invalid search field: <name>`

Bulletins on `GetShopifyIncremental` show e.g. `Invalid search field: updated_at`. Means the object's `incrementalField` exists on the **returned type** but is **not accepted as a filter** by the query root's `query:` argument. Bulk loads succeed (no `query:` arg), but incremental polling fails on every cycle and the high watermark never advances.

Fix: in the object's `Object Definitions Override` entry, set `supportsIncremental: false` and `refreshStrategy: "FULL_PERIODIC"`. The object will bulk-load once and refresh only on reset (same lifecycle as `blogs`, `locations`, `markets`, etc.). Cycle the `StandardShopifyObjectRegistryService` after editing the override JSON.

Common offenders: `codeDiscountNodes`, `automaticDiscountNodes` (use the unified `discountNodes` query root if you need incremental — see [Object Definitions](connector-shopify-objects.md#union-types-and-gid-routing)).

### Schema changed in Shopify

Schema evolution is not supported. After source fields change, [reset the object](../connector-shopify.md#reset-replication-for-one-object) to re-snapshot with the new schema.

### Deletes are not appearing in Snowflake

1. The type must have `supportsDeletes = true` (see the catalogue table). `orders` and `inventoryItems` do not emit destroy events.
2. The type must be listed in `Objects to Track for Deletes`.
3. The initial bulk load for that type must be complete.
4. Events younger than `Safety Buffer` (default 5 min) are intentionally deferred.
5. Delete polling yields when API credits are below `Rate Limit Threshold` (default 500) — check bulletins for "below threshold — yielding" messages during heavy sync.

### `first cannot exceed 250`

A regular (incremental) query set `first:` above Shopify's hard limit of **250** — either the top-level `Page Size` parameter or a child connection's `pageSize`. Full error: *"first cannot exceed 250. To query larger amounts of data with fewer limits, bulk operations should be used instead."* Fix: set `Page Size` / `pageSize` to ≤ 250 (the `Object Definitions Override` JSON Schema already caps `pageSize` at 250). For parents with more than 250 children, the initial **bulk** load captures the full set — in a bulk query Shopify **ignores** the `first` argument and returns all records ([docs](https://shopify.dev/docs/api/usage/bulk-operations/queries)); incremental still caps each run at `pageSize`.

### Sustained throttling

High-volume stores with many objects can stay rate-limited. Increase `Sync Schedule` / `Deletes Schedule` intervals, reduce `Objects to Sync`, or disable `Include Metafields` to cut query cost.

### StandardPrivateKeyService INVALID on SPCS / SNOWFLAKE_MANAGED

The `StandardPrivateKeyService` controller is only used for BYOC `KEY_PAIR` authentication. On SPCS, and on BYOC with `SNOWFLAKE_MANAGED`, it is unused and may show `INVALID`.

**Impact:** None — the connector works correctly.

**Workaround:** Ignore (recommended). Deleting it causes local modifications to the flow.

---

Return to [`connector-shopify.md`](../connector-shopify.md).
