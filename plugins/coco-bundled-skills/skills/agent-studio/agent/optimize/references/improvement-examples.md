# Instruction Improvement Examples

Used in Phase 4. Draft a section per pattern, iterate wording, then apply via the parent skill's **Apply instruction edit** (never a partial spec).

## Percentage / proportion

```
## Proportion and percentage calculations

When the question asks for a percent, proportion, or share:
- Primary answer is the percentage
- Include context: "67.4% (1.2M of 1.8M total credits)"
- Compute (numerator / NULLIF(denominator, 0)) * 100
- For "highest proportion", sort by percentage, not the raw numerator
- If the denominator is 0, say you cannot calculate the percentage
- If the percentage is over 100%, re-check the query
```

## Tool routing

```
## Tool selection

Identify which tool has the data before answering.

Product names that look similar are different tools — do not collapse them.
When two tools could apply, ask one clarifying question.
Some questions need more than one tool: query each, then combine.
```

Rewrite the product/tool names to match **this** agent's `tools[]` and `tool_resources`. The Streamlit / ML examples in older docs are not generic rules.

## Iterate, then apply

1. Name the pattern and the questions it covers.
2. Show expected vs actual for one question.
3. Draft the section. Ask what to change.
4. Show how the revised text handles each failed question in the pattern.
5. Combine approved sections with the existing instructions (critical rules first).
6. Apply with the parent **Apply instruction edit** — complete YAML, tools preserved, `agent-save` only.

Do not accept the first draft and immediately save.

## Comparison after re-eval

```
Baseline:      mean AC 0.31   4 pass / 2 partial / 7 fail
After update:  mean AC 0.77   10 pass / 1 partial / 2 fail

Fixed: Q1, Q4, Q5, Q7, Q9, Q10
Regressions: none
Still failing: Q2, Q8
```

If mean AC is still under 0.70, analyze what is left and draft another round.
