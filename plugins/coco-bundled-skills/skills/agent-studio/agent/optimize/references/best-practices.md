# Optimize Loop — Assistant Guidelines

Applies to every phase.

## Analysis

Discover patterns from the scored questions. Do not start from a fixed taxonomy (tool selection / metric confusion / …) and shove rows into it.

## Improvements

Write instructions that a production agent can follow: concrete rules, worked shapes, what to do on zero or tiny denominators. "When the user asks for X, do Y" with no detail is not an improvement.

## Overfitting

If a rule only works because an eval question used 2025, AMD, or a 1000-credit cutoff, generalize it before calling the agent production-ready. Accuracy on the eval set is not enough.

## Talking to the user

Be specific about the next action ("I'll read the spec for TEMP.NVYTLA.SALES_AGENT", "Q4 asked for a percent and got a raw count").

Ask at decision points: categorization, which pattern to fix first, wording, whether to save the spec, whether to publish a clone onto the original.

Do the analysis yourself; present findings. Do not ask the user to classify failures or to run CLI commands.

## Escalate

Ask when requirements are ambiguous, when domain knowledge is needed for an expected answer, or when a change that helps Q4 may hurt Q7.

Do not ask for permission to run read-only steps (agent-read, SHOW, eval status). Do ask before `agent-save`, `agent-deploy`, `agent-publish`, or any clone → original copy.

## Common misses

- Saving the first instruction draft
- Shipping after a score jump without an overfitting pass
- Labeling a Category B SQL bug as an instruction bug
- Updating instructions with a partial YAML and stripping `tools`
