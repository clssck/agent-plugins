# Failure Analysis

Used in Phases 3 and 4. Discover patterns from the scored questions; do not force preset buckets.

## Per-question

For each Fail and Partial (`answer_correctness` buckets in the parent skill):

- What did the agent return vs the expected answer?
- Which tool ran (if any), and which type (`cortex_analyst_text_to_sql`, `cortex_search`, `web_search`, generic)?
- Why did it fail?

If the tool is `cortex_analyst_text_to_sql` **and** the generated SQL is wrong (filters, joins, missing columns, date logic): stop treating it as an instruction bug. Mark it Category B and move on.

## Discover patterns

**Don't:** "This is a tool-selection error" as a default label.

**Do:** group by the actual shared cause.

```
9 failures, 4 patterns:

1. Percentage vs absolute (Q4, Q9, Q11)
   Asked for percent/proportion; got raw counts.
   Instructions never say to compute a ratio.

2. Wrong tool (Q7, Q12)
   Q7 asked about "Streamlit Open Source" but used the "Streamlit in Snowflake" tool.

3. Time period (Q1, Q10)
   Relative ranges ("last week", "first half") interpreted inconsistently.

4. Missing validation (Q5, Q13)
   No check that the queried window actually covers the asked period.
```

Routing smells to look for: wrong semantic view, no clarification when two tools fit, no multi-tool plan, similar product names collapsed into one tool.

## Category A vs B

| Category A — agent instructions | Category B — semantic view |
|---------------------------------|----------------------------|
| Wrong tool chosen | Analyst SQL is wrong |
| Response shape / units | Missing column, table, or join |
| Missing clarification | Bad filter or date logic in the model |
| Intent misread | A VQR is steering SQL the wrong way |
| Multi-tool coordination | |

Present both counts and ask what to fix first:

```
Failures: 9
  Agent-level (A): Q2, Q5, Q8, Q11, Q13
  Semantic view (B): Q1, Q4, Q7, Q10
    Q1: "last week" = calendar week vs rolling 7 days
    Q4: no column for the percentage
    Q7: wrong table joined
    Q10: VQR pattern misleads SQL

A) Agent-level first
B) Semantic views first
C) Both in parallel (best if different owners)
```

## Category B next step

**Same team:** load `../../../semantic-view/SKILL.md`. Pass the view FQN (from `tool_resources` on the working spec), the failing questions, and expected vs actual SQL. After the view is updated, re-eval — same dataset is fine; mention which questions were Category B when you compare.

**Different team:** write a handoff with view FQN, question, expected vs actual SQL, root cause, suggested fix. Pause this optimize loop until those changes are deployed.
