---
name: marketplace-search
description: >-
  Search the Snowflake Marketplace (public, internal, or both) for
  datasets, data shares, Native Apps, and Connected Apps.

  **MANDATORY.** Call `skill(command="marketplace-search")` before any
  marketplace search — even if you already know the query or loaded this
  skill earlier. If you are about to type `cortex search marketplace`, you
  must have called skill() first: going straight to bash skips the
  query-construction and presentation rules and is a defect. Re-invoke once
  per distinct marketplace need, not for the search you are already running.

  Use when the user wants to find, use, or obtain a third-party or internal
  data product, app, connector, or data share: bare brand names, data
  categories ("weather data", "ESG and sustainability data", "where can I find
  email data"), risk,
  compliance and firmographic profiles ("best source of AML risk data"),
  connectors and apps ("Salesforce connector", "managed MCP servers", "MCP
  servers in Snowflake"),
  availability asks ("is there a connector for X"), marketplace exploration
  ("most downloaded listing"), alternate-source and best-source asks,
  catalog-shaped asks that name a vendor, and intra-org listings ("internal
  listings for HR data", "what is my org publishing for this topic"). The
  word "external" in a query (e.g. "external job-boards") is enough by
  itself. Prefer over-firing over
  missing a marketplace opportunity.

  **Bare tokens.** A bare recognizable product, vendor, fund, or brand name
  alone is enough — "Tomorrow.io", "Fishbowl", "DV360", "Citadel", "Maximo"
  — including single lowercase words, fragments, and catalog-shaped framings
  like "what's the snowflake database for salesforce cases?" or "find me a
  table about X". Invoke in the same turn; do not wait to see whether the
  internal catalog has it. If you cannot tell whether a token names a
  company or product, assume it does and search. The only exclusion is a
  token that reads as a person's given + family name ("give details for
  daniel spark") or an opaque identifier with no brand reading — a
  data-domain word next to a vendor ("Person data from Maximo") is not a
  person name.

  **A catalog miss is not an answer.** `cortex search object` returning
  nothing is not evidence the data is unavailable. Before you say "I don't
  have that data", "no objects found", or "you'll need to bring your own
  data", search the marketplace. An active Snowflake connection is not a
  reason to treat an ask as catalog-only. When a query names a third-party
  brand, product, or external source, run both searches in the same turn.

  **Mid-conversation.** If the user is about to build against an external
  source, search the marketplace first — once per data need. This applies
  even if they named an external source or connector, since the same data is
  frequently available as a listing; surrounding workflow or sandbox context
  does not cancel the signal. Once that topic has been searched, a source
  chosen, or they are iterating on integration code, do not re-pitch
  unprompted. Always fire on an explicit search request, and re-fire when
  they ask for more options or pivot to a new data topic.

  Do not use for: a listing referenced by global name or exact title (use
  get-marketplace-listing-details); formatting results already in hand;
  Snowflake product docs or how-tos (use cortex search docs); specific-value
  or identifier lookups ("what is the [metric/ID] for [entity]", "what is
  the SM ID for…"); named-mechanism integration how-tos ("how to use MCP to
  connect to Salesforce"); educational deep-dives; org-specific business
  conventions such as a fiscal month calendar or internal cost centres
  (unless a vendor is named, e.g. Workday); or a data need already resolved
  earlier in the conversation. Industry-standard code sets and public
  reference data — CPT, NAICS, postcode-to-lat/long — do fire.
---

# Skill: marketplace-search

Wrapper around the `cortex search marketplace` CLI subcommand that searches the Snowflake Marketplace for listings matching a user's data or product need, then surfaces the results so the user can pick one to install or inspect further.

> **PRESENTATION CONTRACT (read before you present anything):** As soon as the search returns, and *before* you draft any results prose, check your available-skills list for `marketplace-listing-formatting`. **If it is there, delegating to it is MANDATORY** — call `skill(command="marketplace-listing-formatting")` and let *that* skill format the results into its rich listing widget, NOT a hand-written list of names/URLs. Writing your own markdown list of listings while that skill sits available is a defect, even if the list looks clean. That skill owns the exact widget format; invoking it is the only way to render the widget correctly, so do **not** attempt to reproduce any listing markup yourself. Only when that skill is genuinely absent from your list do you fall back to the manual name+URL format. Full rules in **Step 6**.

## Workflow

### Step 1 — Resolve marketplace source

Before building the query, detect the user's intent and resolve a `--marketplace-type` value:

| User signal | `--marketplace-type` |
|---|---|
| "internal", "intra-org", "my org", "our listings", "we share" | `internal` |
| "public", "external", "third-party", "Snowflake Marketplace" | `public` |
| Named third-party brand, vendor, or external service with no intra-org signal (e.g. "Salesforce", "Tomorrow.io", "find a HubSpot connector") | `public` |
| Intra-org signal + third-party brand (e.g. "is Salesforce available as an internal listing in my org?") — brand is the search subject, not a source signal; intra-org intent takes precedence | `internal` |
| Explicit request for both sources (e.g. "show me both internal and public listings for <X>") | `all` |
| Ambiguous / no signal and no third-party reference | `all` |

When ambiguous, default to `all` — missing an internal listing is equally bad as missing a public one.

### Step 2 — Build the search query

Translate the user's intent into a short free-text query (typically 1–5 words). Prefer concrete nouns over verbose phrasing.

| User intent                                          | Good query                  |
|------------------------------------------------------|-----------------------------|
| "Do you have weather data for the US?"               | `weather`                   |
| "I need consumer credit card transaction data"       | `credit card transactions`  |
| "Find demographic data by ZIP code"                  | `demographics zip code`     |
| "Is there a Salesforce connector?"                   | `Salesforce`                |
| "I want B2B company firmographics"                   | `B2B firmographics`         |

If the user's request mentions **multiple distinct data needs** (e.g. "weather and stock prices"), run the search **once per need** rather than concatenating them — you'll get more relevant results.


| User intent                                          | Good query                         |
|------------------------------------------------------|------------------------------------|
| "I need to connect HubSpot, Salesforce, and Gong?"   | `hubspot`, `salesforce`, `gong`    |


### Step 3 — Restrict to the user's region (applied by default)

Always scope results to the user's current Snowflake region **by default** using
the `cloudRegion` filter key — apply it *before* considering any of the optional
refinements in Step 4. A listing that isn't offered in the user's region can't be
installed without cross-region replication, so surfacing out-of-region listings
as if they were readily available is misleading. This is the one filter key you
add **without** an explicit user request; it is AND-ed with any optional Step 4
keys in the same `--filter` object.

**Determine the region.** Query it with the available SQL execution tool (for
example `sql_execute` / `snowflake_sql_execute` / `snow sql`
in other runners):

```sql
SELECT CURRENT_REGION();
```

Map the result to a `cloudRegion` value: `CURRENT_REGION()` returns either a bare
region (e.g. `AWS_US_WEST_2`) or a region-group–qualified value (e.g.
`PUBLIC.AWS_US_WEST_2`). Strip any leading `<region_group>.` prefix and pass the
region name in the `--filter` object — `--help` documents the key and format
(e.g. `["AWS_US_WEST_2"]`) but does not enumerate every region:

```
--filter='{"cloudRegion":["AWS_US_WEST_2"]}'
```

**When to skip the region filter (opt-out):**

- The user asks to search across regions or include out-of-region listings
  ("search all regions", "any region", "include listings not available in my
  region", "I can replicate cross-region", "ignore region"). Omit `cloudRegion`.
- The user names a specific *different* region — use that region's `cloudRegion`
  value instead of the current one (no need to query `CURRENT_REGION()`).
- `SELECT CURRENT_REGION()` errors or is unavailable — **don't block the
  search.** Run it without the region filter and note that results aren't
  region-scoped.

If a region-scoped search returns zero or very few results, re-run without the
`cloudRegion` key before concluding nothing exists — the listing may only be
available cross-region. If it then appears, tell the user it isn't offered in
their region and would require cross-region replication.

### Step 4 — Optionally refine with `--sort` and `--filter`

Run 
```
cortex search marketplace --help
```

to understand the `--sort` and `--filter` parameters. 

`--sort` and `--filter` are **optional refinements**. The free-text query is the
primary tool — reach for these only when the user's request maps cleanly to one
of them. **Default to omitting both.** When in doubt, leave them off: an
unnecessary filter silently hides relevant listings, and the wrong sort buries
the best semantic match. (The `cloudRegion` region key is the one exception —
Step 3 already applies it by **default**, not on request; everything below is
about the *additional* refinements you layer on top of that region scope.)

**`--sort`** — only set it when the user expresses an explicit ordering
preference. Otherwise omit it (the server uses `mostRelevant`, which is almost
always what you want for a query-driven search).

| User signal | `--sort` |
|---|---|
| "most popular", "most used", "top", "trending" | `mostPopular` |
| "newest", "latest", "most recent", "just published" | `mostRecent` |
| "alphabetical", "by name", "A to Z" | `title` |
| No ordering language (most cases) | omit (defaults to `mostRelevant`) |

**`--filter`** — use **sparingly**. A filter is a hard constraint: any listing
that doesn't match is dropped entirely, so an over-eager filter will 
turn good results into zero results. Only add a key when the
user states a clear, hard requirement that maps to a supported filter key. Do
**not** infer filters from soft or topical language — topical intent belongs in
the **query string**, not the filter. Prefer one or two narrow keys over a
broad filter object.

Apply a filter key only when the user's requirement is unambiguous, e.g.:

| User requirement | `--filter` (JSON object string) |
|---|---|
| "only free data", "no paid listings" | `'{"pricing":["free","freeToTry"]}'` |
| "HIPAA / SOC2 compliant" | `'{"complianceBadge":["HIPAA", "SOC2"]}'` |
| "in the AWS us-west-2 region" | `'{"cloudRegion":["AWS_US_WEST_2"]}'` |
| "MCD-eligible", "Marketplace Capacity Drawdown", "capacity-drawdown listings" | `'{"providerMcdLocationGroups":["<group>"]}'` (populate from `SYSTEM$GET_MCD_ELIGIBILITY()` — see below) |

The `category` and `businessNeed` filter keys exist, but they are **NOT** for
ordinary topical queries. Search is a semantic ranker: the topic *is* the
ranking signal, so a plain need like "weather data" or "weather patterns in Lake
Tahoe" should go entirely in the **query string** (`weather`, `weather lake tahoe`) 
with **no** category filter. A `category`/`businessNeed` filter only
includes/excludes — it does not rank — so using it for a normal topical request
both discards relevance ranking and risks dropping well-matched but mis-tagged
listings. Reach for these keys only in two narrow cases, and always **in
addition to** (never as a replacement for) the specific query terms:

- **Cross-domain disambiguation** — the query word is polysemous and dragging in
  unrelated results (e.g. "mercury" the planet/element/metric, "apple" the
  brand/fruit). Add a `category`/`businessNeed` facet to pin the domain.
- **Explicit browse intent** — the user wants to enumerate a whole domain or
  use-case rather than match a specific need ("what weather data is available",
  "listings for fraud-detection use cases").

When you do use them: `category` matches the product's domain (`'{"category":["WEATHER"]}'`),
while `businessNeed` matches the problem/workflow the user wants to solve
(`'{"businessNeed":["Fraud Detection"]}'`). Pass names (case-insensitive) or
numeric IDs; see the "FILTER CONTRACT" section of `--help` for the allowed names.

**`providerMcdLocationGroups` (MCD / Marketplace Capacity Drawdown)** — use this
key when the user wants listings they can acquire under **Marketplace Capacity
Drawdown (MCD)**: drawing down against an existing Snowflake capacity commitment
instead of paying separately. Triggers: "MCD", "Marketplace Capacity Drawdown",
"capacity drawdown", "listings I can put toward my capacity / credit commitment",
"MCD-eligible listings". A listing is MCD-eligible when its provider MCD location
group overlaps one of the **caller's** consumer MCD location groups, so fetch the
caller's groups first with the available SQL execution tool:

```sql
SELECT SYSTEM$GET_MCD_ELIGIBILITY();
```

Parse the consumer MCD location group identifiers from the result and pass them
as the `providerMcdLocationGroups` array — values are OR-ed, so a listing matches
if it shares at least one group:

```
--filter='{"providerMcdLocationGroups":["<group_a>","<group_b>"]}'
```

If `SYSTEM$GET_MCD_ELIGIBILITY()` returns no groups, the caller isn't
MCD-eligible — tell the user rather than passing an empty array (`[]` is the
default and applies no filter, silently returning everything).

If `SYSTEM$GET_MCD_ELIGIBILITY()` errors or is unavailable — **don't block the
search.** Proceed without the `providerMcdLocationGroups` filter and tell the
user the eligibility check couldn't be completed.

Rules of thumb for `--filter`:

- The value is a single JSON object string. Keys are AND-ed; array values within
  one key are OR-ed.
- Do **not** set `includePrivateListings` / `includeIntraOrgListings` — those are
  controlled by `--marketplace-type` (Step 1).
- For the full list of supported keys, allowed values, and category /
  business-need names, consult `cortex search marketplace --help` (the
  "FILTER CONTRACT" section) rather than guessing key names or values.
- If a filtered search returns zero or very few results, **re-run without the
  filter** (or with fewer keys) before telling the user nothing exists — the
  filter, not the data, is usually the cause.

### Step 5 — Run the search

**First decide the scope: marketplace-only, or marketplace + catalog?**

Before running anything, classify the request — this decides whether the catalog
search runs at all:

- **Marketplace-only → run ONLY `cortex search marketplace`. Do NOT run
  `cortex search object`.** Choose this when the user explicitly scopes the
  request to the marketplace or to third-party/external sourcing. Signals: any
  mention of "the marketplace" / "the Snowflake Marketplace" (e.g. "...on the
  marketplace", "...in the Marketplace", "search the marketplace for..."),
  "third party" / "3rd party" (data / provider / solution), "external provider
  / source". **An explicit marketplace mention ALWAYS wins — even when the topic
  by itself would be a dual-surface example.** For instance "Do you have weather
  data on the marketplace?" is marketplace-only (skip the catalog), even though a
  bare "weather data" with no marketplace mention would be dual-surface. The user
  has already told you they want acquired data, so a catalog search is off-target
  noise — **skip it.**
- **Dual-surface (default for brand-less data needs) → run BOTH `cortex search
  object` and `cortex search marketplace`.** Choose this for a generic
  data-discovery / acquisition need with no marketplace or third-party scoping,
  e.g. "I'm looking for weather data", "find healthcare data", "where can I get
  demographic data".

Decide from the user's words, not the topic's vibe. The marketplace-only path
requires an explicit scoping signal (a marketplace mention, "third party" / "3rd
party", or an external provider). A topic merely being commonly sold by data
vendors is **not** a marketplace-only signal on its own — without an explicit
qualifier, treat it as the dual-surface default (the user may hold a first-party
version or an already-licensed vendor feed internally). The word "external" on
its own is likewise **contextual**, not a marketplace-only signal: "external
data" usually just means data the user doesn't have yet → dual-surface; treat it
as marketplace-only only when paired with explicit marketplace / third-party /
provider sourcing language.

**Search the internal catalog — dual-surface case ONLY (skip entirely for marketplace-only)**

```bash
cortex search object "<query>"
```

Run it in the same turn as the marketplace search. `cortex search object` has no
`--sort` / `--filter` options, so pass only the text query. The catalog covers
data the user may already have internally; the marketplace covers data they'd
need to acquire — present both sets so the user sees the full picture.

The command prints a JSON envelope on stdout:

```json
{
  "query": "weather",
  "results": "Found 50 object(s):\n\n1. ...\n2. ..."
}
```

The `results` string is a numbered, human-readable list. For each object, extract
at minimum its fully qualified name (`DATABASE.SCHEMA.OBJECT`) and type
(`TABLE`, `VIEW`, etc.); a column list or comment may also be present and is
useful context when presenting.

**Search the marketplace**

Invoke the CLI through the available shell tool:

```bash
cortex search marketplace "<query>" --marketplace-type=<public|internal|all> [--sort=<field>] [--filter='<json-object>']
```

Conventions:

- Pass the `--marketplace-type` value resolved in Step 1.
- Include the `cloudRegion` filter from Step 3 by default (unless the user
  opted out). Add any other `--sort` / `--filter` keys only when Step 4 says
  they apply; otherwise omit them and let the server defaults stand.
- Default `--max-results=15` is fine for most queries; only raise it (cap is server-side) if the user asks for a broader sweep.
- **Always quote the query** so multi-word queries are passed as a single argument. Likewise, **single-quote the `--filter` JSON** so the braces and inner double quotes survive the shell.
- Do not pass `--connection` unless the user has named a specific saved connection; the CLI uses the active one by default.

The command prints a JSON envelope on stdout:

```json
{
  "query": "<query>",
  "results": "Found N marketplace result(s):\n\n1. ...\n2. ..."
}
```

The `results` string is a numbered, human-readable list. For each match, extract at minimum:

- **Listing title** (human-readable name).
- **Global name** — an alphanumeric `GZ...` identifier. This is the listing's id.
- **Listing URL** — `https://app.snowflake.com/marketplace/listing/<global_name>`. If the URL is not literally in the output, construct it from the global name.

The response will also include the listing subtitle, description, provider name, provider description which can be used when presenting the results.

**These returned fields are the ceiling for what you may claim.** `cortex search marketplace` returns only the fields above — title, global name, subtitle, description, provider name, provider description. It does **not** return the listing's tables/columns, geographic or temporal coverage, refresh/update cadence, row counts, price or pricing tier, compliance certifications, or the specific third-party integrations it supports. Anything at that level of detail lives on the listing page or comes from `get-marketplace-listing-details` — it is **not** in your search results, so you cannot know it here. Treat the returned subtitle/description as the outer bound of what you can assert about a listing.

### Step 6 — Present results

If you searched the internal catalog, you **MUST present those results before the marketplace results**, under a clear heading (e.g. `## In your account (catalog)`). For each object, show its fully qualified name `DATABASE.SCHEMA.OBJECT` and type, plus a one-line description from the comment/columns if available:

```
- **DATABASE.SCHEMA.OBJECT** (TABLE) — <optional one-line description / key columns>
```

If the catalog search returned no objects, say so briefly (one line) and move on to the marketplace results — do not omit the marketplace section just because the catalog was empty.

For the results from the marketplace search, first decide **how** to present them. There are two mutually exclusive modes, and you MUST resolve the mode **before writing any results prose**:

**MANDATORY FIRST ACTION — check for `marketplace-listing-formatting` and delegate to it.** Before you type a single listing, scan your **available-skills list** for `marketplace-listing-formatting` (that list — not your memory — is the source of truth for what exists). **If it is present, you MUST call `skill(command="marketplace-listing-formatting")` and format the results per its rules. This is not optional and not a "nicety" you can skip because a hand-written list would also work** — that skill produces the rich listing widget the client renders into listing cards, and it is the single source of truth for that widget's exact format. Because only that skill knows the correct format, invoking it is the sole way to render the widget — do **not** hand-craft any listing markup yourself; markup you write from memory will be malformed. Delegating is the default, expected behavior; presenting the results yourself while that skill sits available in your list is a defect. When unsure whether it's available, invoke it anyway. In this mode the **widget carries the listing metadata**, so you do **NOT** also hand-write a name+URL list or restate per-listing descriptions / URLs / IDs — that skill forbids the duplication (it produces a doubled display). A short recommendation after the tag is welcome; ground it per the rule below.

**Fallback (manual name + URL list) — ONLY when `marketplace-listing-formatting` is genuinely absent from your available-skills list.** Do not reach for this path just because presenting the results inline feels faster — it is the last resort, used solely when the formatting skill does not exist in your environment. When it applies, present the results yourself as the name + URL list described next.

In this fallback mode, every response **MUST give each listing its URL at least once** — the URL is the actionable artifact the user clicks to inspect or install, so a listing the user can't get to is not useful. Include the URL at the listing's **primary mention** (where you introduce or present it); you don't need to repeat it on every later reference to the same listing. This holds **even when you summarize, rank, recommend, or show only a shortlist**: any listing you put in front of the user must be reachable via its `https://app.snowflake.com/marketplace/listing/<global_name>` URL somewhere in the response. Don't present a shortlist of titles or providers with no URLs at all.

Use a consistent one-listing-per-line format, e.g.:

```
- **<Listing title>** — https://app.snowflake.com/marketplace/listing/<global_name>
  <optional one-line description / provider / why it fits>
```

You may add a description, provider info, or a recommendation tailored to the conversation — but **build it only from the returned fields** (title, subtitle, description, provider name/description). A recommendation is where hallucination creeps in: the pull is to justify "why this fits" with concrete-sounding specifics the search never gave you. Keep the recommendation to *why the returned description matches the user's stated need* — do not invent or infer the attributes the search doesn't return (tables/columns, coverage/geography, update frequency, row counts, price/pricing tier, compliance badges, supported integrations). If a listing's subtitle says "US weather," say "US weather"; do not upgrade it to "hourly station-level US weather back to 1990" — that specificity isn't in the output. Likewise, do **not** write "example usage" SQL here: you don't have the real table or column names, so any query you'd write would be fabricated.

**Every listing you name anywhere in the response — especially in a closing "I recommend you start with X" / "your best bet is X" line — must be one the search actually returned, referenced by its exact returned title.** The recommendation is the single highest-risk spot for this: after presenting the results it's tempting to name the "best" provider from memory (a brand you happen to know), but if that name isn't in the search output it's a fabrication — the user clicks expecting it and it doesn't exist. Recommend *by pointing back to an entry you already presented* — in fallback mode reuse the same title and its `https://app.snowflake.com/marketplace/listing/<global_name>` URL; in `marketplace-listing-formatting` mode the widget already carries the URL, so name it by title alone (don't paste a URL, ID, or re-listed metadata). Never introduce a name in the recommendation that didn't appear verbatim in the results. Before sending, scan your own response: if any listing name isn't one the search returned, remove it. If none of the returned listings is a strong fit, say that plainly — do not reach for a better-known name that wasn't returned.

When the user needs that deeper detail to decide, don't guess it — point them to the listing URL or offer a full write-up via `get-marketplace-listing-details` (which actually fetches the listing's metadata and data dictionary). Grounding the recommendation in what came back, and deferring the rest, is strictly better than a confident but invented pitch. If an optional field is missing, omit it; but the name and URL are always available (construct the URL from the global name if it isn't printed literally).

When `--marketplace-type=all`, the CLI already labels results by source in the output (`## Snowflake Marketplace Results` and `## Internal (Intra-Org) Marketplace Results`). Preserve these section headers when presenting results to the user. (In `marketplace-listing-formatting` mode, let that skill render one listing widget per section, per its rules.)

**Before you send the response, run this final check — you are not done until it passes:**

1. Is `marketplace-listing-formatting` in your available-skills list? If **yes**, did you actually call `skill(command="marketplace-listing-formatting")` and let it render the results into its listing widget? If it's available and you instead hand-wrote a list of names/URLs (or tried to write the widget markup yourself), **STOP — that response is wrong.** Go back and delegate before sending. (Only skip when that skill is genuinely absent from the list, or the user explicitly asked for plain text.)
2. Every listing you named — including in any closing recommendation — appeared verbatim in the search output (no invented titles or better-known brands the search didn't return).
3. You did not assert attributes the search doesn't return (tables/columns, coverage, cadence, pricing, compliance, integrations) or write "example usage" SQL.

If `cortex search marketplace` returns "No marketplace listings found" or zero matches:
- If you passed `--filter`, **re-run without it (or with fewer keys) first** — an over-restrictive filter is the most common cause of empty results.
- For `--marketplace-type=internal`: suggest both (1) rephrasing the query and (2) re-running with `--marketplace-type=all` or `--marketplace-type=public` — the data may exist on the public marketplace even if the org hasn't published it internally.
- For `--marketplace-type=public` or `--marketplace-type=all`: suggest one or two alternative query phrasings (a synonym, a broader category) before giving up.

## Troubleshooting

- **`Marketplace search failed: ...`** — surface the error verbatim. Common causes: no active Snowflake connection (run `cortex connections list` to inspect), expired session token, or transient network issue. Ask the user how to proceed rather than retrying the same query blindly.
- **`Object search failed: ...` (the `cortex search object` catalog search errors, in the dual-surface case)** — surface the error verbatim; same common causes as a marketplace failure (no active connection, expired session, transient network). Because the catalog search is the *secondary* surface, do not let its failure block the run: still report the marketplace results, and note that the internal-catalog search could not be completed (offer to retry it). Do not retry the same command blindly.
- **`Connection '<name>' not found`** — the `--connection` flag was passed but does not match any saved connection. Drop the flag (so the active connection is used) or have the user run `cortex connections set <name>` first.
- **`results` is empty / "No marketplace listings found"** — treat the same as the zero-match case in Step 6: tell the user, then suggest reformulated queries.
- **`cortex: command not found`** — the Cortex Code CLI is not installed on this machine. Tell the user; DO NOT attempt to install it silently.

## CRITICAL - Anti-patterns

- Do not default to `--marketplace-type=internal` or `=all` when the user's intent is clearly public/third-party. Use `internal` or `all` only when the user's message signals intra-org intent or is ambiguous between both sources.
- NEVER use `cortex search object --types=marketplace`. 
- Do NOT run `cortex search object` when the user explicitly scoped the request to the marketplace or to third-party / external sourcing ("...in the Marketplace", "Snowflake Marketplace", "third party" / "3rd party", "external provider"). Those are marketplace-only — running a catalog search is off-target. The dual-surface catalog search is for brand-less data needs with no such scoping (e.g. "I'm looking for weather data").
- NEVER run marketplace-only (skipping `cortex search object`) for a brand-less need that carries **no** marketplace, third-party, or external-sourcing signal — a plain "I'm looking for weather data" / "find healthcare data" / "find me demographic data" is **dual-surface**, so running only `cortex search marketplace` is a defect. A topic merely *sounding* like something data vendors sell (weather, healthcare, demographics, firmographics) is NOT a marketplace-only signal; the user may already hold it internally, so you MUST also run `cortex search object` in the same turn. **This rule fires only when the request is BOTH brand-less AND has no scoping signal — it never overrides the marketplace-only rule above.** The moment the message contains "marketplace", "third party" / "3rd party", "external provider/source", or names a specific vendor/brand, it is marketplace-only and you must NOT run `cortex search object` — e.g. "I need **third party** consumer spending data" is marketplace-only despite the generic topic, because "third party" is an explicit sourcing signal. When unsure whether a signal is present, dual-surface is the safe default; but an explicit third-party/marketplace/external word is never ambiguous.
- NEVER re-run the same query just because the first attempt found something the user did not ask for — refine the query string instead.
- Do NOT add `--filter` (or `--sort`) speculatively. Topical intent belongs in the query string, not a filter — filters are hard constraints that drop non-matching listings, so apply a key only for an explicit, hard user requirement. The lone exception is `cloudRegion`, which Step 3 applies by default to scope to the user's current region (drop it only when the user opts out of region-scoping).
- NEVER invent listing titles, providers, URLs, or descriptions that did not appear in the search output. If a field is missing, omit it.
- NEVER name a listing in a recommendation / "start with X" / summary line that did not appear in the search output. Every listing referenced *anywhere* in the response — including the closing recommendation — must map to an entry the search actually returned (same title + URL). Recommending a better-known brand you weren't handed back is a fabrication, even if it's a real product; scan the finished response and drop any name the search didn't return.
- NEVER assert listing **attributes the search does not return** — tables/columns, coverage/geography, update cadence, row counts, price or pricing tier, compliance certifications, or supported integrations. These aren't in the results, so stating them is a hallucination even when it sounds plausible. Keep recommendations to why the returned subtitle/description fits the need, and route deeper questions to the listing URL or `get-marketplace-listing-details`. Do not write "example usage" SQL — you don't have real column names.
- NEVER present the marketplace results yourself as a name+URL list, table, or bullet list when `marketplace-listing-formatting` is in your available-skills list. Its presence makes delegation **mandatory**: call `skill(command="marketplace-listing-formatting")` and let it render the listing widget. Skipping the skill because your own inline list "looks fine" is the single most common defect here — a well-formatted hand-written list is still wrong when the formatting skill exists, because it produces no widget. Only fall back to the manual name+URL list when that skill is genuinely not in your available-skills list. Check the list rather than assuming it's absent from memory.
- NEVER hand-write the listing widget markup yourself — not as a substitute for invoking `marketplace-listing-formatting`, and not "to save a step." That skill is the only source of the correct widget format; markup you produce from memory will be malformed or use the wrong shape, and it silently breaks the client rendering. The widget only appears in the response as the *output of invoking that skill* — if you didn't call `skill(command="marketplace-listing-formatting")`, there should be no widget markup in your response at all (use the name+URL fallback instead).
- In the fallback (no `marketplace-listing-formatting`) mode, NEVER present a shortlist of listings as bare names or providers with no URLs. Curating to a "top picks" set or describing options in prose is fine, but each listing must be reachable via its `https://app.snowflake.com/marketplace/listing/<global_name>` URL at its primary mention (you needn't repeat the URL on every later reference) — a name with no URL anywhere forces the user to go hunting and defeats the point of the search. This is easy to slip on deep in a long conversation, where the temptation is to summarize providers by name; include the URLs anyway.
- NEVER skip the search and answer "the marketplace might have it" — actually run the command and report what came back.
- NEVER run `cortex search marketplace` directly from bash without **first** calling `skill(command="marketplace-search")` in the same turn. The `skill` call is the mandatory entry point even when you already know the exact query you want to run — going straight to the CLI skips the query-construction and result-presentation rules and is a defect.
- When a NEW marketplace need arises later in a conversation — a different data topic, or an explicit "search again / show me other options" request — re-invoke `skill(command="marketplace-search")` before searching. Do NOT skip the wrapper and go straight to the CLI just because you loaded the skill earlier and the `cortex search marketplace` command is still in your context. This is the most common multi-turn defect: the wrapper is loaded once on the first search, then later distinct searches run from bash directly. (You don't need to re-invoke for the same search you're already executing — the rule is one `skill()` entry per distinct need, not per CLI call.)
