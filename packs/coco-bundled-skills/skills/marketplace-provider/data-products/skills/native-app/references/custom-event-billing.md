# Custom Event Billing for Native Apps

Custom Event Billing lets a Native App charge consumers for specific types of usage inside the app (for example, per procedure call, per row processed, or a custom event you define). It is a usage-based pricing option that you can combine with a per-query charge and a monthly fee.

> **Only Native App listings can use billable events.** Data listings (plain data shares) cannot. If a provider wants event-based charging, the data product must be a Native App.

## How it works: two sides that must match

Custom Event Billing has two halves, and they must line up exactly:

1. **App code emits billable events.** Your app calls the `SYSTEM$CREATE_BILLING_EVENT` (or `SYSTEM$CREATE_BILLING_EVENTS`) system function from inside a stored procedure. Each event carries a `class` and a base charge.
2. **The listing defines the price.** In Provider Studio you add a Custom Event Billing pricing plan and list each billable event `Class` with its `Billing Quantity`.

> **The `class` and `billing_quantity` you configure on the listing must exactly match the `class` and the quantity used to calculate `base_charge` in your app code.** You are paid only for the events you added to the listing, even if the app emits other event types.

---

## Step 1: Emit billable events from app code

Create stored procedures that call the billing system function, and add those procedures to your app's setup script. You can write them in JavaScript, Python, or Java.

> The system function can only be called from a **stored procedure created by the provider, running inside an app installed in a consumer account**. It cannot be called from outside a procedure, from a UDF or table function, or from a row access policy. You cannot test its output from the provider account.

### Helper function

All the JavaScript examples below use this helper (define it once, in the same procedure/schema the emitting procedures use):

```sql
CREATE OR REPLACE PROCEDURE <schema_name>.custom_event_billing()
RETURNS NULL
LANGUAGE JAVASCRIPT
AS
$$
  function createBillingEvent(className, subclassName, startTimestampVal, timestampVal, baseCharge, objects, additionalInfo) {
    try {
      var res = snowflake.createStatement({
        sqlText: `SELECT SYSTEM$CREATE_BILLING_EVENT('${className}',
                                                     '${subclassName}',
                                                     ${startTimestampVal},
                                                     ${timestampVal},
                                                     ${baseCharge},
                                                     '${objects}',
                                                     '${additionalInfo}')`
      }).execute();
      res.next();
      return res.getColumnValue(1);
    } catch(err) {
      return err.message;
    }
  }
$$;
```

> Pass arguments by string concatenation as shown, not by bind variables. This avoids data-type mismatches between the procedure language and SQL.

### The four common billing patterns

**Pattern 1: Per procedure call.** Charge a fixed amount each time the consumer calls a procedure.

```javascript
var event_ts = Date.now();
var billing_quantity = 1.0;
var base_charge = billing_quantity;
var objects = "[ \"db_1.public.procedure_1\" ]";
createBillingEvent("PROCEDURE_CALL", "", event_ts, event_ts, base_charge, objects, "");
```

**Pattern 2: Rows consumed.** Charge based on rows read by the app.

```javascript
var res = snowflake.execute({sqlText: "select i from db_1.public.t1"});
res.next();
var event_ts = Date.now();
var billing_quantity = 2.5;
var base_charge = res.getRowcount() * billing_quantity;
var objects = "[ \"db_1.public.t1\" ]";
createBillingEvent("ROWS_CONSUMED", "", event_ts, event_ts, base_charge, objects, "");
```

**Pattern 3: Rows ingested / changed.** Charge based on rows inserted plus updated by a MERGE.

```javascript
var merge_query = "MERGE INTO target_table USING source_table ON target_table.i = source_table.i \
    WHEN MATCHED THEN UPDATE SET target_table.j = source_table.j \
    WHEN NOT MATCHED THEN INSERT (i, j) VALUES (source_table.i, source_table.j)";
res = snowflake.execute({sqlText: merge_query});
res.next();
var numRowsIngested = res.getColumnValue(1) + res.getColumnValue(2); // inserted + updated
var event_ts = Date.now();
var billing_quantity = 2.5;
var base_charge = numRowsIngested * billing_quantity;
var objects = "[ \"db_1.public.target_table\" ]";
createBillingEvent("ROWS_CHANGED", "", event_ts, event_ts, base_charge, objects, "");
```

**Pattern 4: Monthly active rows.** Charge only for rows inserted or updated for the first time in a calendar month (the same shape works for unique users or unique load locations).

```javascript
var monthly_active_rows_query = "SELECT count(*) FROM source_table \
    WHERE source_table.i NOT IN (SELECT i FROM target_table \
    WHERE updated_on >= DATE_TRUNC('MONTH', CURRENT_TIMESTAMP))";
res = snowflake.execute({sqlText: monthly_active_rows_query});
res.next();
var monthlyActiveRows = parseInt(res.getColumnValue(1));
// ...run the MERGE that also sets updated_on = current_timestamp...
var event_ts = Date.now();
var billing_quantity = 0.02;
var base_charge = monthlyActiveRows * billing_quantity;
var objects = "[ \"db_1.public.target_table\" ]";
createBillingEvent("MONTHLY_ACTIVE_ROWS", "", event_ts, event_ts, base_charge, objects, "");
```

### Snowpark Python example (rows consumed)

```sql
CREATE OR REPLACE PROCEDURE app_schema.billing_event_rows()
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python')
  HANDLER = 'run'
  EXECUTE AS OWNER
  AS $$
import time

def createBillingEvent(session, class_name, subclass_name, start_ts, ts, base_charge, objects, additional_info):
    session.sql(f"SELECT SYSTEM$CREATE_BILLING_EVENT('{class_name}', '{subclass_name}', {start_ts}, {ts}, {base_charge}, '{objects}', '{additional_info}')").collect()
    return "Success"

def run(session):
    res = session.sql("select i from db_1.public.t1").collect()
    billing_quantity = 2.5
    charge = len(res) * billing_quantity
    now_ms = int(time.time() * 1000)
    return createBillingEvent(session, 'ROWS_CONSUMED', '', now_ms, now_ms, charge, '["billing_event_rows"]', '')
$$;
```

---

## System function reference

| | `SYSTEM$CREATE_BILLING_EVENT` | `SYSTEM$CREATE_BILLING_EVENTS` |
|---|---|---|
| Purpose | Emit a single billable event | Emit a batch of events (JSON array) |
| When to use | Low-frequency events | When you would exceed the single-event rate limit |
| Batch limit | One event | Up to **100 events** per call; payload up to **9,000 characters** |

**Parameters** (same fields either way): `class`, `subclass`, `start_timestamp`, `timestamp`, `base_charge`, `objects`, `additional_info`.

Key rules:
- **`class`** identifies the event. Must start with a letter or underscore; contain only letters, underscores, digits, and `$`; be at most **64 characters**; and must not start with `SNOWFLAKE_` (reserved). Stored and compared case-insensitively. An emitted event is only billed if its class matches a class configured on the listing.
- **`subclass`** is optional and **visible only to the provider**, never to consumers. Use it to sub-categorize events for your own reporting. Same naming rules as `class`.
- **`base_charge`** is in US dollars: greater than 0, less than 99,999.99, at most two decimal places. **Negative charges and credits are not supported.**
- **`start_timestamp` / `timestamp`** are Unix epoch times in milliseconds (UTC). Use `start_timestamp` to charge for a time range; otherwise set both to the same value.
- **`objects`** is a JSON string array of fully qualified object names (max 4 KB). **`additional_info`** is a JSON key-value string (max 4 KB).

**Best practice: batch events on a schedule.** Rather than calling the API inline on every action, have your app accumulate events and emit them periodically (for example, from a scheduled task) using the batch function. This stays within the rate limits and reduces the chance of dropped events.

---

## Step 2: Configure billable events on a usage-based pricing plan

Before you configure pricing, your app must already emit billable events, and you must know each `class` and the `billing_quantity` used to compute its `base_charge`.

Custom Event Billing is a form of **usage-based pricing**: you declare each billable event on a usage-based pricing plan for the listing, optionally alongside a per-query charge and a monthly fee. You can set this up in Snowsight (Provider Studio, on the listing's pricing plan) or with a pricing plan manifest (YAML). The `monetization-offers` skill owns the end-to-end pricing-plan and offer authoring flow; this doc covers only the billable-event specifics.

In a pricing plan manifest, declare each billable event under `billing_events`:

```yaml
pricing_model: USAGE_BASED
billing_events:
  - class: PROCEDURE_CALL          # must exactly match the class your app emits
    display_name: Procedure Call    # consumer-facing label
    billing_quantity: 1.0           # must match the billing_quantity in your app code
    billing_unit: call              # unit label to display
    description: Charge per procedure call
  - class: ROWS_CONSUMED
    display_name: Rows Consumed
    billing_quantity: 0.01
    billing_unit: row
    description: Charge per row read by the app
usage_details:
  max_fee: 500.0                    # Maximum Monthly Charge cap (required for dynamic charges)
```

Rules that must hold (Snowsight or manifest):
- Each `class` must **exactly match** the class your app emits, and `billing_quantity` must match the value used to compute `base_charge`. You are paid only for events declared on the listing, even if the app emits others.
- Up to **eight (8)** billable event classes per listing.
- The plan must set a **Maximum Monthly Charge** cap.
- Trials are **required** for listings offered publicly on the Marketplace.

> **Testing tip:** for validation you only need a **private** offer shared to a consumer account in your own org (see the testing section below); you do not need to publish publicly.

---

## Billing behavior FAQs

Common questions consumers and providers ask about how the charges actually land:

- **Is the first query free if I allow free queries?** No. The **first query in each calendar month is always charged**, even within a free-query allotment. A free-query count applies only after that first query.
- **Is the monthly fee prorated?** No. The monthly fee is a fixed price and is **not prorated**. It is **not charged in a month with no usage** (no query, or for SPCS apps no compute pool run).
- **How is the monthly fee triggered for SPCS apps?** For a Native App with Snowpark Container Services, the one-time monthly fee is triggered when the **compute pool runs**, not by a query. If the compute pool never runs and no query executes that month, there is no monthly fee.
- **When does a usage-based charge stop?** Once the **Maximum Monthly Charge** cap is reached, further usage that month is free.
- **Are events from my own organization billed?** No. **Intra-org usage is not billed by default**, to allow testing. To charge consumer accounts within your own organization, [contact Snowflake Support](https://docs.snowflake.com/en/user-guide/contacting-support) to enable it.
- **Can I change the price of an existing subscription plan?** No. Price changes to existing subscription pricing are **not supported**. Create a **new listing** instead.
- **Can consumers get access before paying (NET 30-style)?** Yes, for **subscription-based paid private listings**, enable **early access** so a consumer can use the listing before payment. The provider communicates the payment terms (for example, NET 30). Snowflake recommends early access only for paid private listings.
- **Does a discount apply automatically to billing events?** No. A discount on an offer is **not** automatically applied to `SYSTEM$CREATE_BILLING_EVENT` charges. The app must read the discount (`SHOW OFFERS IN LISTING <listing>;`), compute the discounted amount, and emit the final discounted `base_charge`. See the monetization-offers skill's Discount Limitation section.

---

## Test and validate before you publish

You cannot test billing from the provider account. Test from a consumer account:

1. Update your app package: add the emitting procedures to the setup script, update the package, and add a new version or patch. The exact version command depends on whether release channels are enabled on the package (`REGISTER VERSION` + release channel when enabled, `ADD VERSION` when not); app-package versioning and publishing are owned by the `native-app-provider` skill.
2. Create a **private listing**, add the Custom Event Billing pricing plan, and share it with a consumer account in your organization.
3. Sign in to that consumer account, install the app, set a payment method (you will **not** be charged for intra-org usage), and call the procedures. A return of `Success` means the code works.
4. Validate the charges by querying the shared usage view from the consumer account (allow ~2 days for latency):

```sql
SELECT listing_global_name, listing_display_name, charge_type, charge
FROM SNOWFLAKE.DATA_SHARING_USAGE.MARKETPLACE_PAID_USAGE_DAILY
WHERE charge_type = 'MONETIZABLE_BILLING_EVENTS'
  AND provider_account_name = <account_name>
  AND provider_organization_name = <organization_name>;
```

Providers can also see Custom Event Billing usage in their standard monetization usage reports.

---

## References
- [Add billable events to an application package](https://docs.snowflake.com/en/developer-guide/native-apps/adding-custom-event-billing)
- [Paid listings pricing models](https://docs.snowflake.com/en/collaboration/provider-listings-pricing-model)
- [SYSTEM$CREATE_BILLING_EVENT](https://docs.snowflake.com/en/sql-reference/functions/system_create_billing_event)
- [SYSTEM$CREATE_BILLING_EVENTS](https://docs.snowflake.com/en/sql-reference/functions/system_create_billing_events)
