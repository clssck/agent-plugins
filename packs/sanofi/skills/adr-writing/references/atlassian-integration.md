# Atlassian Integration — ADR-Specific

Use the Atlassian/Confluence/Jira tools available in the session. If the exact tool is not loaded, search for it, or use the search-company-knowledge and confluence-html-editor skills where they fit. NEVER assume a fixed tool name.

## Fetching an ADR from Confluence

1. Resolve the page ID (tiny URLs below).
2. Fetch the page content as markdown.
3. Fetch inline comments, footer comments, and reply threads; they hold unresolved reviewer concerns. If comments cannot be fetched, state that limitation in the review.

## Fetching Context from Jira

Extract the problem statement (description), acceptance criteria (may imply drivers), and linked Confluence pages. If Jira is unavailable, ask the user to paste the ticket.

## Confluence Tiny URLs

Tiny links look like `/wiki/x/<token>`. Order of preference:

1. Resolve via an authenticated redirect or the Atlassian page-fetch tool.
2. Decode locally (page ID = little-endian bytes, URL-safe base64 with `-` for `/` and `_` for `+`, padding and trailing zero bytes dropped):

```bash
python3 skill://adr-writing/scripts/decode_tiny_link.py "<token>"
```

   Prints a candidate page ID, or exits non-zero on an invalid token. ALWAYS verify by fetching the page and checking the title; the algorithm is documented for Data Center ([Atlassian KB](https://support.atlassian.com/confluence/kb/how-to-programmatically-generate-the-tiny-link-of-a-confluence-page/)) and may not hold for every Cloud token.
3. Search Confluence by keywords from the decision topic.
4. Ask the user for the numeric page ID.

## Fact-Checking with Vendor Documentation

1. Fetch vendor docs with `read` on the URL or `web_search`.
2. Check pricing pages or APIs for cost claims ([cost-analysis.md](cost-analysis.md)).
3. Quote text that actually appears on the page; NEVER present paraphrase as a quotation.
4. Mark claims you cannot confirm "unverified".
5. Distinguish a service's internal mechanism from what users can integrate with before calling an option infeasible.
