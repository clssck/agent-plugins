# Write Mode Workflow

## 1. Understand the Decision

Ask ONE message covering all fields; NEVER split across turns:

1. **Decision topic** — what and why (required)
2. **Options considered** — with known pros/cons (required, minimum 2 unless mandated)
3. **Chosen option** and why, or "undecided" (required)
4. **Decision drivers** (optional)
5. **Confluence pages** — titles, URLs, search terms (optional)
6. **Jira tickets** — keys (optional)
7. **External references** — URLs (optional)
8. **Status** — proposed, accepted, rejected, deprecated, superseded
9. **Deciders** (optional; omit the line when none supplied)

- Only a topic supplied: proceed, ask ONE follow-up for options and chosen option.
- A Jira key or title in the request: treat as field 1, fetch the ticket, then one follow-up.
- Atlassian unavailable: still collect refs; record them as Links.

### Status rules

| Input | Status | Decision Outcome |
|---|---|---|
| Decision made, no status given | `accepted` | Chosen option + justification |
| "Undecided" or evaluation pending | `proposed` | "No option chosen yet; pending [evaluation/owner]". NEVER invent a choice. |
| User gives status | As given | As supplied |

## 2. Fetch Atlassian Context

Per Jira ticket: fetch with the available Atlassian Jira tool; extract problem context, acceptance criteria, linked issues, decision comments.

Per Confluence page: resolve tiny URLs per [atlassian-integration.md](atlassian-integration.md); search by title via Atlassian tools or the search-company-knowledge skill; fetch by page ID. Extract context, constraints, prior decisions.

- List each fetched page title and ticket summary; ask the user to confirm.
- Unresolved link: say "I could not resolve [link]. Provide the page title or numeric ID."
- Search Confluence for existing standards on the topic. Surface an enterprise standard as context and a factor in the analysis.
- Fetch the Sanofi Architecture Manifesto through Atlassian tools. If unavailable, use the principle list in [adr.template.md](../assets/adr.template.md) and say the live source was unavailable.
- Present a consolidated summary and confirm before continuing.

| Atlassian access | User gave refs | Behavior |
|:-:|:-:|:--|
| Yes | Yes | Fetch all, summarize, confirm |
| Yes | No | Skip step |
| No | Yes | Inform user, record as Links, ask for manual summary |
| No | No | Skip step |

## 3. Gather Remaining Context

Ask once, only for what is missing: options, decision, status, deciders, drivers. Skip when already sufficient. Clarify a vague topic here.

## 4. Determine File Name

1. Scan `docs/adr/` for the next number.
2. Match existing formatting conventions.
3. Kebab-case slug from the title: `ADR-NNN-slug.md`.
4. Create `docs/adr/` if missing.

## 5. Write the ADR

Use [adr.template.md](../assets/adr.template.md). Include required sections; include optional ones only with supporting input.

- Technical Story from Jira keys.
- Links: Jira, Confluence, external references.
- Technically infeasible option → Options Ruled Out.
- Variable-priced infrastructure → Cost Annex per [cost-analysis.md](cost-analysis.md).
- Mandated single option: follow SKILL.md "Single Mandated Option".

## 6. Confirm

Show the file path, a short summary of the decision, and next steps (team review, link from code).
