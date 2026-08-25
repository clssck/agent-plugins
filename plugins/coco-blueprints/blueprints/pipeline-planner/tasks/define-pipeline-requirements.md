# Define Pipeline Requirements

## Summary
Gather requirements about source data, freshness, logic type, triggers, consumers, constraints, and technology preference.

## Personas
- Data Engineer
- Data Architect

## Details
## **What You Will Accomplish**

- Identify where your source data lives
- Define how fresh your output needs to be
- Characterize your transformation logic
- Determine how the pipeline gets triggered
- Identify downstream consumers
- Select any hard constraints
- State any technology preference

## **Steps in This Task**

| Step | Title | Purpose | Conditional |
|------|-------|---------|-------------|
| B.0 | Source Data Identification | Where does your data come from? | Path B |
| B.1 | Freshness Requirements | How current must the output be? | Path B |
| B.2 | Transformation Logic | What kind of code are you writing? | Path B |
| B.3 | Trigger Model | Who/what decides when it runs? | Path B (conditional display) |
| B.4 | Downstream Consumers | What uses the output? | Path B |
| B.5 | Constraints | Hard constraints that affect technology choice | Path B |
| B.6 | Technology Preference | Override or tiebreaker | Path B |