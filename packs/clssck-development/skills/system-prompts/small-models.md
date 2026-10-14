# Small Models

Compact models (roughly ≤2B parameters, often on-device) behave as pattern-completers more than instruction-followers. Write prompts that show the pattern; enforce everything else in code.

A prompt shared across model sizes MUST be written for the smallest consumer. Larger models handle simple prompts well; compact models degrade on complex ones.

## Rules

- **One task per prompt.** Split multi-step work into separate calls. Do not combine classification, extraction, and rewriting in one prompt.
- **Examples are the spec.** Compact models copy examples more reliably than they follow prose. Where an example and an instruction conflict, assume the example wins.
- **Positive framing.** State what to produce. Negations ("don't use quotes") can prime the very token they forbid; move prohibitions into postprocessing.
- **Few constraints.** As a heuristic, keep to about five constraints at most. Past that, rules tend to displace each other. Spend the budget on output shape.
- **Executable vocabulary.** Use concrete, checkable words ("3–6 words", "one line", "lowercase"). Avoid judgment words ("concise", "appropriate", "high quality").
- **Front-load.** Put the task and output format first. Put the input last, right before the generation point.
- **No requested chain-of-thought.** Do not ask the model to reason step by step. Compact models spend their tokens on rambling and leak the reasoning into the output.

## Scaffolding over instruction

Control output shape mechanically wherever the runtime allows it:

- **Prefill** the start of the response (an opening tag, a JSON key, a list marker) so the model continues an established shape.
- **Stop sequences** end generation at the closing delimiter.
- **Token caps** sized to the expected output bound runaway generation.
- **Postprocessing** in code: trim, take the first line, strip quotes and punctuation, normalize casing, and validate against a schema or pattern. Fall back or retry when validation fails.

Every rule code can guarantee belongs in code, not in the prompt.

## Examples

- Use 2–4 input→output pairs. Output-only examples teach format but not mapping.
- Keep examples boring and representative. Unusual examples get copied verbatim or overfit.
- Vary content across pairs and keep format identical, so the model learns which parts are fixed.
- All examples positive: show correct outputs only. Never show a "bad" example the model might imitate.

## Worked example: title generation

Task: produce a short title for a user's first chat message.

```
WRONG (instruction-heavy, negation list, output-only examples):
You are a helpful assistant that generates titles. Think carefully about the
user's intent. Never use quotes. Never end with punctuation. Don't exceed six
words. Don't include the word "title". Avoid filler words.
Examples: Debug Login Timeout / Plan Kitchen Remodel

RIGHT (one task, input→output pairs, input last):
Write a 3–6 word title for the message.

Message: my login page times out after 30 seconds on staging
<title>Login page timeout on staging</title>

Message: what tiles work best for a small kitchen backsplash
<title>Small kitchen backsplash tiles</title>

Message: convert this csv of orders into monthly totals
<title>Monthly totals from orders CSV</title>

Message: {input}
<title>
```

Runtime: prefill `<title>`, stop on `</title>`, cap at a few dozen tokens. In code, take the first line, strip quotes, trailing punctuation, and stray tags, then fall back to a truncated message when the result is empty.

The dropped "Never" rules are all enforced downstream, so the prompt carries only what code cannot guarantee.
