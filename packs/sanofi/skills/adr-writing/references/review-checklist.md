# ADR Review Checklist

Assign each item **Pass**, **Fail**, **Partial**, or **N/A**. N/A applies to genuinely optional items when the ADR omits the section because no relevant information exists.

## Structure

| # | Check | Criteria |
| - | ----- | -------- |
| S1 | Status field present | One of: proposed, accepted, rejected, deprecated, superseded |
| S2 | Date field present | Valid YYYY-MM-DD date |
| S3 | Deciders listed | Named person or role; N/A if the ADR omits Deciders and none was supplied |
| S4 | Context and Problem Statement | 2-3 sentences, a question where possible |
| S5 | Decision Drivers | Table with Driver and Description; N/A if omitted for lack of input |
| S6 | Drivers weighted | Explicit priority (recommended, never Fail) |
| S7 | Minimum 2 options | At least 2 considered options, OR a documented single mandated option with the constraint in Context |
| S8 | Pros and cons per option | Each option has both; mandated single option may state only the constraint |
| S9 | Decision Outcome | Chosen option with justification; `proposed` ADRs state pending evaluation instead |
| S10 | Rejection rationale | Each non-chosen option explains why; N/A for a mandated single option |
| S11 | Consequences | Positive and negative listed; N/A if omitted |
| S12 | Links | Related ADRs, tickets, docs; N/A if none exist |
| S13 | Architecture Manifesto Alignment | Relevant principles mapped with verdict |

## Content Quality

| # | Check | Criteria |
| - | ----- | -------- |
| C1 | Specific problem | Constraints, requirements, or metrics |
| C2 | Factual pros/cons | Evidence, not opinion |
| C3 | Claims referenced | Platform capability claims cite documentation |
| C4 | Cost data sourced | API, pricing page, or quote; consistent model |
| C5 | No scope creep | One decision per ADR |
| C6 | Migration path | Addressed when changing an existing system |
| C7 | Rollback | What happens if the decision fails |
| C8 | Validation criteria | How success is measured |

## Completeness

| # | Check | Criteria |
| - | ----- | -------- |
| X1 | No placeholders | No "[TODO]" or "[TBD]" |
| X2 | No orphan options | Every listed option has a detail section |
| X3 | Current-state data | Problem grounded in numbers or incidents |
| X4 | Future ADRs scoped | Out-of-scope concerns listed for follow-up |
