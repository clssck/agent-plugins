# Review Mode Workflow

## R1. Fetch the ADR

Source from the user's input:

- **Confluence URL:** resolve the page (including tiny URLs), fetch content via Atlassian/Confluence tools. Also fetch inline comments, footer comments, reply threads. Comment tools unavailable → note that comment review was skipped.
- **Local file path:** `read` the file.
- **Jira ticket:** fetch the ticket; look for linked Confluence pages containing the ADR.

## R2. Run the MADR Review Checklist

Evaluate against [review-checklist.md](review-checklist.md), including S13 (Architecture Manifesto Alignment). Verdicts: Pass, Fail, Partial, N/A. Optional check with validly omitted section → N/A; a documented single mandated option is not a Fail on S7/S8/S10.

Manifesto check: fetch the Architecture Manifesto page through Atlassian/Confluence tools when available; otherwise use the embedded principle list in [adr.template.md](../assets/adr.template.md) and flag the source gap.

Compare the decision and consequences against the 10 manifesto principles. Flag any principle the decision strains (e.g., a cost increase strains Principle 10 — Frugality). Present results as a table.

## R3. Fact-Check Technical Claims

Per technical claim (capabilities, limitations, pricing, compatibility):

1. Identify the vendor/technology.
2. Fetch official documentation: `read` (URL) or `web_search`.
3. Cost claims: check vendor pricing pages or APIs; recompute totals and break-even figures.
4. Compare the claim against the documentation.
5. Report: confirmed (doc reference) · refuted (doc reference) · unverifiable.

Iterative: one pass's findings may raise new questions. Continue until all significant claims are verified or flagged.

## R4. Review Comment Threads (if Confluence)

Per inline or footer thread:

1. Summarize the exchange.
2. Assess coherence: does the reply address the reviewer's question?
3. Flag threads where the reply talks past the question, deflects, or leaves the concern unresolved.
4. Draft suggested reply text for unresolved threads if the user requests it.

## R5. Produce the Review Output

Write `docs/adr/ADR-NNN-slug-review.md` (ADR's number and slug) containing:

1. **Template Compliance** — MADR checklist results.
2. **Content Quality** — strengths and gaps.
3. **Technical Accuracy** — fact-check results with documentation references.
4. **Comment Thread Analysis** — coherence assessment (Confluence source only).
5. **Comparison Table** — if the ADR compares options: color-coded summary table.
6. **Cost Analysis** — if infrastructure costs are relevant: cost annex with data from vendor pricing APIs ([cost-analysis.md](cost-analysis.md)).
7. **Recommendations** — numbered, specific, actionable improvements.

## R6. Offer Follow-Up Actions

After presenting the review, offer:

- Draft suggested text for sections needing improvement.
- Draft reply text for unresolved Confluence comment threads.
- Post the review as a footer comment on the Confluence page.
- Create a local ADR file incorporating the suggested improvements.
