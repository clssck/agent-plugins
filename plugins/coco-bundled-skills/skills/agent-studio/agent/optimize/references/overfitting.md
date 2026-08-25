# Overfitting and Generalization

Used in Phases 5 and 6. Judge production impact, not string matches.

## What to look for

- Years, dates, or windows copied from eval questions
- Company / account names used as the rule rather than an example
- Numeric thresholds that only fit eval-data scale
- Fixed result counts ("always show top 10")
- Absolute ranges that will be wrong for a larger or smaller customer

## Reason about risk

**Don't:** "Found '2025' — that's overfitting."

**Do:**

```
Line 107: "First half of 2025" = Jan 1–June 30, 2025.

In production, users will ask about other years. "First half" should mean
Jan 1–June 30 of the year they named (or the current year if they did not).
```

## Priority

| Priority | Meaning |
|----------|---------|
| Critical | Will fail for ordinary production questions |
| Medium | Fails in some realistic scenarios |
| Low | Nicety |

## Generalization patterns

**Time periods** — define H1/H2, quarters, and "last N days/months" relative to a reference date. Ask when the window is ambiguous. Put exact dates in tool inputs.

**Entity names** — "Short names (2–4 characters) can match unrelated entities; confirm or use a stronger identifier." One eval company can be an example, not the only case.

**Thresholds** — prefer relative comparisons ("SIS credits are typically orders of magnitude smaller than total credits") over hardcoded bands from the eval warehouse.

**Result counts** — vary by question type (one winner → 3–5; "high X" → 10–20; "all" → full list plus a count).

## After generalizing

Re-eval the same dataset. Generalization must not regress a question that the Phase 4 instructions already fixed. If it does, the wording was too broad — tighten and re-eval.

```
Optimization journey

                Mean AC   Instruction chars
Baseline        0.31      4,067
Updated         0.77      12,637
Generalized     0.84      14,420

Q1  fail → pass → pass   (fixed in update)
Q2  fail → fail → pass   (fixed in generalization)
```
