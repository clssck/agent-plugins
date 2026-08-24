---
name: get-marketplace-listing-details
"description": "Present a focused, recommendation-first write-up of ONE Snowflake Marketplace listing (data share, native app, connected app, private/targeted, or request-only): why it fits the user's need, how it's delivered, how they get access, and how its data/capabilities solve the problem. Invoke whenever the user asks you to describe, summarize, write up, explain, review, or give a recommendation on a single listing referenced by title or global name — e.g. \"tell me about GZ2FQZ711TU\", \"what's in the Consumer Pricing listing\", \"should I get this listing\". ALWAYS invoke it even when the listing metadata is already in the conversation or the user pasted the SYSTEM$BULK_GET_LISTINGS or data-dictionary payload: this skill governs how to SHAPE and present that data, so pre-supplied data does NOT make it optional — a raw metadata dump or generic overview is the wrong output. Do NOT use for marketplace search results spanning multiple listings — use `marketplace-listing-formatting` instead."
---

# Skill: get-marketplace-listing-details

Present a **tight, recommendation-first** view of a single marketplace listing. The response answers four questions and nothing more:

1. **Why is this a fit?** — ties the listing to what the user was asking about **and** the specific data already in their Snowflake account.
2. **How is it delivered?** — secure share, native app, or connected app.
3. **How does the user get access?** — free, trial, paid, or by request.
4. **How does it solve the problem?** — concrete tables/columns (from the data dictionary) or capabilities, mapped to the user's need.

**Do not** produce the old kitchen-sink detail view (long More-details tables, certifications, coverage, regions, provider bios, multiple SQL examples). Those bury the recommendation. Keep the output short and decision-oriented.

## Output contract — read this first

Everything below (retrieval, parsing, field references) only decides **what goes inside** the response. The **shape never changes.** Every response — data share, native app, connected app, request-only, or private listing — is exactly this template and nothing else:

```
# {listing title}

**Why this is a fit**

{1–3 sentences tying the listing to the user's goal}

| | |
|---|---|
| Delivery | {Secure share | Native App | Integrated SaaS | By Request} |
| Access | {one access label} |

**How it solves your problem**

{concrete tables/columns or capabilities, mapped to the need}

### Get this listing

{the install card from the marketplace-install-formatting skill if it is available, else the marketplace URL}
```

**Four parts, in this exact order, nothing before or after:** the `#` title, `**Why this is a fit**`, the 2-row Delivery/Access table, `**How it solves your problem**`, and `### Get this listing`.

**The user will almost always list what they want** — *"what it is, who's behind it, why it's useful, how I'd use it, what they offer."* **Those are not section headings.** Fold every one of those sub-questions *into* the four parts above. Emitting any heading that mirrors the user's phrasing is a **failure of this skill** — never produce `Overview`, `What It Is`, `Who It's From` / `Who's Behind It` / `About the Provider`, `Why It's Useful`, `How It Works` / `How You'd Use It`, `What They Offer`, `Key Details`, `Additional Details`, `Additional Resources`, `Geographic Coverage`, `Next Steps`, `How to Get Started`, `Bottom Line`, or `Summary`.

This holds **even when the user has already pasted the full listing metadata and asks for a "detailed write-up."** That is not license to reproduce a marketing overview — reshape the payload into the four parts. If you catch yourself opening with "here's a comprehensive overview" or writing `##` overview headings, stop and rewrite to the template.

## When to use

- The user references **one** listing by title (e.g. "Consumer pricing data") or by global name (e.g. `GZ2FQZ711TU`).
- The user wants an overview or a "should I get this?" recommendation about a listing.

**Do NOT** use this skill when:

- The user is browsing or searching across multiple listings — use `marketplace-listing-formatting` instead.
- It is unclear which specific listing is meant — ask for clarification first (see Prerequisites).

## Prerequisites

This skill has **two required inputs**: the listing's global name **and** the user's problem/prompt. The output is a contextual recommendation, so both are mandatory — without the problem, "Why this is a fit" and "How it solves your problem" degrade into generic marketing copy, which defeats the skill. If either input is missing after the checks below, **ask the user for it and stop** rather than producing a generic view.

### Identify the listing

This skill needs the **global name** of the listing (an alphanumeric string like `GZ2FQZ711TU`), not just the human-readable title.

If the user gave only a title, search the conversation context for the matching global name. If you cannot find one, **ask the user** — do not guess.

### Identify the user's problem

This skill also needs to know **what the user is trying to do** — the prompt or goal the listing should address.

Look for it in the current conversation: the request that led here, the analysis they're building, the data they're trying to enrich, or the question they asked. If no problem or goal is recoverable from context, **ask the user** what they're trying to accomplish before continuing — do not fall back to a generic, context-free overview.

### Fetch the listing

Run **Query A** (always) and, **for data-share listings**, **Query B**. These are the **only** SQL queries this skill executes for retrieval. Every field below is read from the parsed JSON in your own reasoning — do **not** wrap Query A in `PARSE_JSON(...)` / `FLATTEN(...)` / `TABLE(...)` or re-run `SYSTEM$BULK_GET_LISTINGS` to extract sub-fields; the data is already in the result.

**Query A — `SYSTEM$BULK_GET_LISTINGS`** (source of truth for title, description, business needs, monetization/pricing, type detection, fulfillment, consumer state, and `metadata.usage`):

```sql
SELECT SYSTEM$BULK_GET_LISTINGS(
  'SNOWFLAKE_DATA_MARKETPLACE',
  '{"listingGlobalEntityIds":["<global_name>"]}'
);
```

**Query B — `SYSTEM$GET_DATA_DICTIONARY_METADATA`** (data-share listings only — presigned URLs to JSON files describing the share's tables and columns):

```sql
SELECT SYSTEM$GET_DATA_DICTIONARY_METADATA(
  '<global_name>',
  'SNOWFLAKE_DATA_MARKETPLACE'
);
```

#### Parsing the responses

Both queries return one column whose value is a **JSON string**. Parse it in your own reasoning — do not issue more SQL to extract sub-fields.

- **Query A** parses to an **array**; read element `[0]`. Several inner fields (`metadata`, `profile`, `application_data`, `product_types`, `pricing_plan`) are themselves **JSON-encoded strings** that must be parsed a second time.
- **Query B** parses to `{presignedUrlMap: {<filename>: <url>, ...}, updatedOn: <epoch_ms>}`. Filenames typically include `<global_name>objects.json` (table list), `<global_name>dictionary_<n>.json` (columns), and `<global_name>featured.json` (featured objects). **Presigned URLs expire within ~1 hour** — fetch promptly if you fetch at all.

#### Focused field reference (Query A)

Only the fields this skill's output actually needs. Any field may be `null`/missing — defer to what the query returned.

| Field path | Use |
|---|---|
| `global_name` | Verify it matches the request; build the marketplace URL |
| `state` | If not `PUBLISHED`, surface the status before recommending |
| `metadata.title` | Listing name (the `#` heading) |
| `metadata.description`, `metadata.subtitle` | Source for "Why this is a fit" |
| `metadata.businessNeeds` | array of `{type, name?, key?, description}` — intended use cases; render `description` when `name`/`key` is opaque |
| `metadata.usage` | array of `{title, description, query, isPaid?}` — real queries; use only to learn real table/column names, not to dump multiple examples |
| `product_types` | parsed array of `{type, is_addon}` — **delivery-method detection** |
| `share_type` | `DATA` / `SECURE_VIEW` / `APPLICATION` — secondary delivery signal |
| `application_data` | parsed Native App package object (non-empty ⇒ native app) |
| `is_monetized`, `pricing_plan` | **access-type detection**; `pricing_plan` = `{type, currency, base_fee, paid_data_description, free_data_description, billing_duration, payment_type}` |
| `autofulfillment` | `false` ⇒ provider approval required — affects the "Get this listing" request/contact framing only, **not** the Delivery or Access label |
| `private`, `distribution` | `private = true` ⇒ privately shared/targeted to this account |
| `is_imported`, `is_share_imported`, `is_purchased`, `is_available_for_importing` | consumer's current relationship — affects the "Get this listing" wording |
| `provided_by_you`, `blocked`, `unpublished_by_admin_reason` | edge states to surface if set |
| `organization_profile_name`, `profile` | provider name only if you must attribute a claim — do **not** add a provider bio section |

**Never print** `profile_global_name` or `profile.profileGlobalName` (opaque internal ids like `GZ2FQZ711TI`). The listing's own `global_name` is fine.

#### Determine the delivery method

The Delivery row must show the **exact label Snowsight shows on the listing card**. Evaluate these rules **in order and stop at the first match** — this mirrors the product's `getDeliveryMethodLabel`:

1. **By Request** — a personalized / targeted listing: `private = true`. This **overrides** the product-type check below: a personalized listing is always "By Request" regardless of its underlying product type (share, app, or service).
2. Otherwise, label by the listing's **primary product type** (`product_types[0].type`, cross-checked with `share_type` / `application_data`):

| Delivery (Delivery row) | Primary product type |
|---|---|
| **Secure share** | `SHARE` / `DATA_SHARE` / `SECURE_VIEW` (or `share_type` in `DATA` / `SECURE_VIEW`) — live access to data, models, and other objects in the user's account |
| **Native App** | `NATIVE_APP` (or `share_type = APPLICATION`, or `application_data` non-empty) — securely deploys an app package in the user's account |
| **Integrated SaaS** | `SAAS_CONNECTED_APP` / `CONNECTED_APP`, `MANAGED_APP`, or `PROFESSIONAL_SERVICES` — a SaaS application that integrates tightly with Snowflake but runs outside the account |

`autofulfillment` does **not** feed the Delivery label. A bespoke or approval-gated listing that is **not** personalized still shows its product-type label — e.g. a non-personalized `DATA_SHARE` service listing is **Secure share**, not "By Request", with the request/contact flow surfaced through the "Get this listing" section. Only `private = true` produces "By Request", matching what the product renders.

If `private = true`, also prefix the "Why this is a fit" section with a one-line note that the listing is privately shared with the user's account. Only run **Query B** for **Secure share** listings (a personalized listing labeled By Request is not a Secure share for this purpose).

#### Determine the access type

The Access row must show the **exact label Snowsight shows on the listing card**. Evaluate these rules **in order and stop at the first match** — the order is load-bearing (this is the same precedence the product's `getPricingLabel` → `getMonetizationType` uses), so do not reorder or "pick the best-fitting" one:

1. **Already installed** — the consumer already has it: `is_imported`, `is_share_imported`, or `is_purchased` = `true`.
2. **Paid** — a personalized / targeted listing: `private = true`. A personalized listing is **always** "Paid" regardless of any trial-looking signal, which is why this check precedes the trial check.
3. **Free to try** — the listing exposes a free evaluation / trial / sample tier: a limited-trial (evaluation) plan is present, **or** it is monetized (`is_monetized = true`) **and** carries trial / free-sample details (`pricing_plan.free_data_description` set, or a free `metadata.attributes` tier alongside paid `metadata.paidAttributes`).
4. **Free** — not monetized: `is_monetized = false` (and none of the above matched).
5. **Paid** — monetized with no trial: `is_monetized = true` with no free tier (the fall-through when nothing above matched).

(The product also has a "Requested" state for a pending access request, but detecting it needs a separate query beyond `SYSTEM$BULK_GET_LISTINGS`, so this skill intentionally omits it — do not add it back without a reliable payload signal.)

`autofulfillment` does **not** feed this label. Provider-approval / contact-flow nuance lives on the **Delivery** row (By Request) and in the "Get this listing" framing — never fold it into the Access label. Following this precedence verbatim keeps the Access row identical to what the user sees in the product instead of a divergent, invented label.

State the label plainly. If pricing specifics are known and short (e.g. "$500/mo"), you may append them in parentheses — but keep the row to one line.

**Both rows must be *derived*, never guessed.** Delivery and Access are the two fields most prone to hallucination because they're inferred from several signals — the failure mode is emitting a confident label the payload doesn't support. Anchor each label to the specific field(s) that produced it:

- **Every price, currency, billing cadence, and `payment_type` you print must appear literally in `pricing_plan`.** Never invent a figure ("$500/mo", "billed annually") or a payment cadence that isn't in the parsed `pricing_plan` object. If `pricing_plan` is absent, state the tier label alone (e.g. "Paid") without a fabricated amount.
- **When the determining signals are missing or genuinely conflict, do not force a confident label.** Access is driven by `is_imported`/`is_purchased`, `private`, the trial signals, and `is_monetized`; Delivery by `product_types`/`share_type`, `application_data`, and `autofulfillment`. If those don't jointly point to one answer, prefer the most conservative honest statement — e.g. "Access: see listing page for terms" or "Delivery: not determinable from the listing metadata" — over guessing "Free" or "Secure share". A missing field is not evidence of "Free"/"self-service"; treat absent signals as unknown, not as a default. The user reaching the listing page with an honest "check terms there" is far better than a wrong Access label.

#### If a query fails or the listing is not live

- **Not found / invalid id / empty array** — confirm the global name with the user.
- **Insufficient privileges / not granted** (common for private & request-only) — tell the user it isn't available to their role; point them to request access via the provider.
- **`state` not `PUBLISHED`**, `blocked = true`, or `unpublished_by_admin_reason` set — surface the status; don't present it as live.
- **Query A ok, Query B fails/empty** — proceed; base "How it solves your problem" on `metadata.usage` / `metadata.description` only and say the data dictionary was unavailable. Never invent table/column names.
- **Other errors** — surface verbatim and ask how to proceed.

## Workflow

Produce the four-part template from **Output contract — read this first** above. That shape is fixed for every listing type; the steps below only decide what fills each part. The delivery mechanism changes *what goes inside* the sections, never *which sections exist* — do not fall back to an "overview" layout for apps or services, and keep the section labels verbatim. If a part would be empty or generic, tighten it — do not pad with certifications, coverage, regions, provider bios, resource-link lists, or geographic-availability sections.

**Never** make up information. Use only what the queries returned and what Step 1 enrichment confirmed.

### Step 1 — Gather the grounding

Collect the three inputs the recommendation is built on:

1. **The user's problem.** Re-read the conversation. What did they ask for / what are they trying to do? This is what "Why this is a fit" and "How it solves your problem" must speak to. This is a **required input** (see Prerequisites) — if no problem or goal is recoverable from context, ask the user and stop; do not proceed with a generic overview.
2. **The user's Snowflake context.** Use object-discovery / search tools (e.g. `snowflake_object_search`) to find databases, schemas, or tables the user already has that relate to the listing's domain. Capture 1–3 concrete objects to name in the output — this is what makes the recommendation feel specific rather than generic.
3. **The listing's real data/capabilities.**
   - **Secure share:** parse `presignedUrlMap` from Query B and, if a web-fetch tool is available, fetch `objects.json` and a `dictionary_*.json` to get real **table and column names**. `metadata.usage` queries also reveal real identifiers — cross-check before naming anything.
   - **Native / connected app:** there is no data dictionary. Rely on `metadata.description`, `metadata.businessNeeds`, `application_data` (native only), and `metadata.link` for capabilities.

### Step 2 — Write "Why this is a fit"

1–3 sentences, no filler. It must connect **the listing** to **the user's stated problem** and **name at least one specific thing from their Snowflake account** (a database/schema/table found in Step 1) that makes the listing relevant. If Step 1 found no related objects, say what the listing adds that the user appears not to have yet — but stay factual.

Bad (generic): "This listing provides valuable consumer pricing data useful for many analytics use cases."
Good (grounded): "You asked for competitor price benchmarks to enrich `RETAIL.SALES.ORDERS`. This share adds daily SKU-level pricing keyed by UPC, which joins to the `UPC` column already in your `ORDERS` table."

### Step 3 — Fill the Delivery/Access table

A 2-row table only:

| | |
|---|---|
| Delivery | {Secure share \| Native App \| Integrated SaaS \| By Request} |
| Access | {one label from the access rules} |

### Step 4 — Write "How it solves your problem"

Show the concrete substance, mapped to the need. Ground it in **both** the data dictionary (tables + key columns) **and** the listing's own metadata — `metadata.description` and `metadata.businessNeeds` — so the reader sees what the data is *and* what it's for. Depth on the data side = **tables + key columns**, not row-level data (previews generally aren't available before import).

- **Secure share:** name 2–4 representative tables from the data dictionary and, for each, list a few **key columns** (the ones relevant to the user's problem), and connect them to the relevant `metadata.businessNeeds` / `metadata.description` so the tables read as solutions, not just schema. Note where they join to the user's existing objects from Step 1. If Query B was unavailable, describe the datasets from `metadata.description` / `metadata.businessNeeds` / `metadata.usage` without fabricating identifiers. At most **one** short SQL snippet, and only if it makes the value obvious — this skill is not a query cookbook.
- **Native App:** describe the specific capabilities/functions the app adds and what they operate on, grounded in the description / `application_data`.
- **Integrated SaaS** (connected app, managed app, or professional services): describe how the SaaS product integrates (OAuth/connect flow) and what it reads/writes against the user's account. No fabricated SQL, no `CREATE APPLICATION` boilerplate.
- **By Request** (Delivery = By Request — a personalized / targeted listing): describe whatever the listing actually delivers, grounded in its metadata. "By Request" reflects that access is personalized/negotiated, **not** that there's nothing to deliver — so if the personalized listing is backed by a real share or app, describe its datasets/capabilities; if it's a bespoke engagement, describe the concrete offering and deliverables (what the engagement produces, rough timeline, how to engage) from `metadata.description` / `metadata.businessNeeds` / `customized_contact_info`. No fabricated SQL or identifiers.

### Step 5 — Get this listing

**Mandatory in every response.** The `### Get this listing` heading always appears last. Its body is the install card from `marketplace-install-formatting` whenever that skill exists in this session, and the marketplace URL only when it genuinely does not. The body is **exactly one** of the two forms below, never both:

- **Default — delegate to `marketplace-install-formatting`.** Look for it in your **available-skills list** (that list is the source of truth for what exists — do **not** decide it is unavailable from memory or assumption). If it is listed, **or if you are unsure**, invoke it (the `skill` tool with `command: "marketplace-install-formatting"`) and use **exactly** what it returns as the body of this section — nothing else (no marketplace URL, no "click to install" line, no CTA prose). It emits the install card for the listing whose global name is in scope. **You must actually invoke it: not having loaded it into context yet is NOT a reason to fall back to the URL.** `marketplace-install-formatting` is the single source of truth for the install-card tag, so never hand-write the tag or reproduce its format from memory. If you catch yourself typing a `<marketplace_listing_install .../>` tag or a raw `https://app.snowflake.com/marketplace/...` link by hand, stop: invoke the skill and let it produce the card.

- **Fallback — only when `marketplace-install-formatting` is genuinely not in your available-skills list** (e.g. you attempted to invoke it and it does not exist) — emit the marketplace URL as a clickable link:

```
https://app.snowflake.com/marketplace/listing/<global_name>
```

  This URL fallback is required for **every** listing type — connected apps, By Request, private, and monetized listings included — because the connect / request / purchase flow all live on that page. Never substitute a bare provider email, a Snowsight navigation instruction, or a `cortex search` / marketplace-search suggestion for it.

For **By Request** delivery (or any listing whose purchase runs through the provider), you may frame the surrounding sentence around requesting access / contacting the provider — but the body itself is still the install card from `marketplace-install-formatting` (when it is available) or the URL (when it is not).

### Step 6 — Self-check before sending

Fix and re-check if any fail:

1. **Only the four parts are present** — heading, "Why this is a fit", the 2-row table, "How it solves your problem", and "Get this listing". No More-details table, certifications, coverage, regions, or provider-bio subsection snuck back in.
2. **"Why this is a fit" speaks to the user's actual problem and names something specific from their Snowflake account** (or explicitly states no related object was found). It is not generic marketing copy. If no problem was in context, you should have asked for it in Prerequisites rather than reaching this step.
3. **Delivery and Access each show exactly one label** derived from the tables above, and each traces to an actual field in the payload — not a guess. Any price/currency/cadence/`payment_type` shown appears literally in `pricing_plan`. If the signals were missing or conflicting, you stated the conservative "see listing page" / "not determinable" form rather than a confident label.
4. **"How it solves your problem" is grounded** — real table/column names for shares (or an honest "data dictionary unavailable"), real capabilities for apps. No invented identifiers.
5. **No opaque profile ids** anywhere (`profile_global_name` / `profile.profileGlobalName`).
6. **No retrieval queries exposed** — no `SYSTEM$BULK_GET_LISTINGS`, `SYSTEM$GET_DATA_DICTIONARY_METADATA`, `PARSE_JSON`, or "queries run / how this was retrieved" sections. (Step 4's single value-illustrating query against the listing's real data is fine.)
7. **Get-this-listing section is last** and contains the correct single form: if `marketplace-install-formatting` is available, you **invoked** it (a `skill` tool call) and its returned install card is the entire body — no hand-written tag, no marketplace URL, no CTA prose; otherwise the body is the marketplace URL. Never both, and never a URL when the install skill is available.

## Example response shape

```
# {Listing title}

{If private: one-line note that this is privately shared with your account.}

**Why this is a fit**

{1–3 sentences connecting the listing to the user's stated problem and naming
a specific database/schema/table already in their account.}

| | |
|--|--|
| Delivery | Secure share |
| Access | Free to try |

**How it solves your problem**

{2–4 tables with their key columns (for a share) mapped to the user's need,
noting joins to the user's existing objects; or capabilities for an app. At
most one short illustrative query.}

### Get this listing

{If marketplace-install-formatting is available (preferred), invoke that skill and use
the install card it returns as the entire body. Otherwise:
https://app.snowflake.com/marketplace/listing/<global_name>}
```

The **exact same skeleton** for a non-data listing — here an Integrated SaaS
(connected app). Note the identical section labels and the absence of any
Provider / How-it-works / Resources sections:

```
# {Listing title}

**Why this is a fit**

{1–3 sentences on what the product adds for the user's goal, grounded in their
account. Attribution is at most one clause, e.g. "…from {provider}".}

| | |
|--|--|
| Delivery | Integrated SaaS |
| Access | Free to try |

**How it solves your problem**

{How the SaaS product connects (OAuth / service connection) and what it reads or
writes against the user's account, tied to their need. No fabricated SQL, no
CREATE APPLICATION boilerplate.}

### Get this listing

{If marketplace-install-formatting is available (preferred), invoke that skill and use
the install card it returns as the entire body. Otherwise:
https://app.snowflake.com/marketplace/listing/<global_name>}
```

Same skeleton for a **Native App** — note there is no `What It Is` / `Who It's
From` / `Why It's Useful` / `How You'd Use It` section; it all lives in the four
fixed parts:

```
# {Listing title}

**Why this is a fit**

{1–3 sentences on what the app adds for the user's goal, grounded in their
account. Attribution is at most one clause.}

| | |
|--|--|
| Delivery | Native App |
| Access | Free |

**How it solves your problem**

{The specific capabilities the app adds and what they operate on, grounded in
the description / application_data (privileges, reference definitions). No
fabricated SQL against the app's data.}

### Get this listing

{If marketplace-install-formatting is available (preferred), invoke that skill and use
the install card it returns as the entire body. Otherwise:
https://app.snowflake.com/marketplace/listing/<global_name>}
```

Same skeleton for a **By Request** (personalized / targeted) listing — here a
bespoke service. Do not turn it into an `Overview` / `What They Offer` /
`Who's Behind It` / `How to Get Started` write-up:

```
# {Listing title}

**Why this is a fit**

{1–3 sentences on what the engagement delivers for the user's goal, grounded in
their account. Attribution is at most one clause.}

| | |
|--|--|
| Delivery | By Request |
| Access | Paid |

**How it solves your problem**

{The concrete offering and deliverables — what the engagement produces, rough
timeline, how to engage — grounded in metadata.description / businessNeeds /
customized_contact_info. No fabricated SQL.}

### Get this listing

{If marketplace-install-formatting is available (preferred), invoke that skill and use
the install card it returns as the entire body. Otherwise:
https://app.snowflake.com/marketplace/listing/<global_name> — the request / contact
flow lives on that page.}
```
