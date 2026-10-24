# Cost Analysis

Applies when an ADR involves infrastructure, cloud services, or tooling with variable pricing: write mode (Cost Annex) and review mode (cost verification).

## Methodology

1. **Identify cost-bearing components.** Per considered option, list every service, license, or resource that incurs cost.

2. **Research pricing per component.** Find the vendor's official pricing page or API. Use `read` on the URL or `web_search`; `bash` with `curl` only for pricing APIs. Cite source URL and retrieval date (pricing pages change without notice). State billing units (e.g., SQS bills send, receive, and delete requests, not messages), region, free tier, batching, retries, and shared costs excluded from the comparison.

3. **Build comparison tables** across configurations (instance sizes, worker counts, number of environments). Each row SHOULD trace to a cited source.

4. **Model multi-scenario projections** (e.g., 5, 10, 15 teams) to show how costs scale. Choose scenarios matching the ADR's decision drivers.

5. **Provide wide-format and long-format tables:** wide for readability, long (one row per option and scenario) as chart-ready data.

6. **Supply chart data and intent** if the user intends to publish to Confluence: keep the long-format table in the ADR, and state the intended visualization (e.g., grouped bar chart, x = scenario, y = monthly cost in USD, one series per option). NEVER write Confluence wiki markup or macro syntax here; the `atl` skill owns the chart representation and publishing.

## Source Requirements

- Every cost figure MUST cite its origin (pricing page URL, API query, or vendor quote).
- Pricing API available → SHOULD prefer it over static page scraping.
- No public pricing (e.g., enterprise-negotiated rates) → note the figure as "estimate — confirm with vendor" and flag it in the review.
