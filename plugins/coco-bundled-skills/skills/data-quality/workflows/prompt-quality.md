---
parent_skill: data-quality
---

# Workflow: Prompt Quality Scoring

Score any LLM prompt across 9 dimensions using Cortex Complete. The agent builds a scoring meta-prompt that embeds the dimension rubric and asks the LLM to evaluate the prompt against structured criteria. Scores may vary slightly across calls. No DMFs, no schema, no table setup required — just a prompt string.

## Trigger Phrases

- "Score my prompt"
- "How good is this prompt?"
- "Prompt quality check"
- "Rate my prompt"
- "Prompt score"

## Execution Steps

### Step 1: Get the Prompt

Extract the prompt text from the user's message. If no prompt is provided inline, ask for it.

### Step 2: Build the Scoring Meta-Prompt

Load `reference/prompt-scoring-dimensions.md` to get the 9 dimension definitions, sub-criteria, and scoring rules. Construct a meta-prompt with:

**System message:**
```
You are a prompt quality scoring engine. Score the given LLM prompt across 9 heuristic dimensions. Apply each dimension's sub-criteria rules EXACTLY as specified — do not invent criteria. Return ONLY valid JSON, no markdown fences, no extra text.

DIMENSIONS AND SCORING RULES:

1. Structure (0-1): Section delimiters (+0.33), Paragraph separation (+0.33), Appropriate length 100-50000 chars (+0.34)
2. Role Clarity (0-1): Has role definition (+0.5), Role is domain-specific (+0.5)
3. Task Specification (0-1): Imperative instructions/action verbs (+0.33), Clear deliverable (+0.33), No vague language like "try to"/"maybe"/"if possible" (+0.34, deduct 0.08 per instance)
4. Output Specification (0-1): Format mentioned like JSON/markdown/CSV/list/table (+0.5), Output constraints like size/shape/schema (+0.5)
5. Context & Grounding (0-1): Has data/context section or placeholders (+0.5), Domain-specific content (+0.5)
6. Safety & Guardrails (0-1): Negative constraints "Do not"/"Never"/"Avoid" (+0.5), Edge case/fallback handling "If...then"/"Otherwise" (+0.5)
7. Examples (0-1): Has positive examples (+0.5), Has negative examples (+0.5)
8. Reasoning Guidance (0-1): Chain-of-thought "step by step"/"think through" (+0.5), Instruction priority/hierarchy (+0.5)
9. Completeness (0-1): Emphasis/reinforcement "Important:"/"Critical:"/"MUST" (+0.5), Fallback/summary section "Remember:"/"Key points:" (+0.5)

OVERALL SCORE FORMULA: overall_score = round(1 + sum(dimension_scores)). Range: 1-10.

Return this exact JSON structure:
{
  "overall_score": <1-10>,
  "dimensions": {
    "structure": { "score": <0.0-1.0>, "detail": "<what was found or missing>" },
    "role_clarity": { "score": <0.0-1.0>, "detail": "<what was found or missing>" },
    "task_specification": { "score": <0.0-1.0>, "detail": "<what was found or missing>" },
    "output_specification": { "score": <0.0-1.0>, "detail": "<what was found or missing>" },
    "context_grounding": { "score": <0.0-1.0>, "detail": "<what was found or missing>" },
    "safety_guardrails": { "score": <0.0-1.0>, "detail": "<what was found or missing>" },
    "examples": { "score": <0.0-1.0>, "detail": "<what was found or missing>" },
    "reasoning_guidance": { "score": <0.0-1.0>, "detail": "<what was found or missing>" },
    "completeness": { "score": <0.0-1.0>, "detail": "<what was found or missing>" }
  },
  "suggestions": ["<actionable improvement 1>", "<actionable improvement 2>", ...]
}
```

**User message:**
```
Score this prompt:

<user's prompt text>
```

### Step 3: Confirm with User

**Stopping point.** Present the scoring plan:

> "I'll score your prompt across 9 quality dimensions using Cortex Complete. This will use LLM credits. Proceed?"

Upon approval, continue.

### Step 4: Execute the Scoring Call

Execute via `templates/prompt-cortex-complete.sql`, replacing `<model>` with `claude-sonnet-4-6` (or the user's preferred model) and `<prompt>` with the constructed meta-prompt:

```sql
SELECT SNOWFLAKE.CORTEX.COMPLETE('<model>', $$<scoring_meta_prompt>$$);
```

Execute via `snowflake_sql_execute`.

### Step 5: Parse the Response

The Cortex Complete call returns a JSON object:

```json
{
  "overall_score": <1-10>,
  "dimensions": {
    "<dimension_key>": { "score": <0.0-1.0>, "detail": "<string>" },
    ...
  },
  "suggestions": ["<string>", ...]
}
```

Dimension keys: `structure`, `role_clarity`, `task_specification`, `output_specification`, `context_grounding`, `safety_guardrails`, `examples`, `reasoning_guidance`, `completeness`.

If the response contains markdown fences or extra text, strip them and extract the JSON.

### Step 6: Present Results

**Overall score with band label:**

| Score | Band |
|---|---|
| 1-3 | Poor — missing most fundamentals |
| 4-5 | Needs work — has basics but significant gaps |
| 6-7 | Good — solid prompt with room to improve |
| 8-9 | Very good — well-crafted, minor improvements possible |
| 10 | Excellent — hits all dimensions fully |

**Dimension breakdown** (sorted by score ascending so weakest dimensions appear first):

For each dimension, show:
- Dimension name
- Score displayed as X / 10
- Detail string from the response

**Strengths and gaps:**
- Strengths: dimensions with score >= 0.7
- Gaps: dimensions with score < 0.4

**Improvement suggestions:** List all suggestions from the response.

### Step 7: Offer Next Steps

After presenting results, offer:

1. **Improve the prompt** — "I can generate an improved version that addresses the gaps. Want me to rewrite it?" → Load `workflows/prompt-improve.md`
2. **Explain dimensions** — "Want details on how each dimension is scored?" → Load `reference/prompt-scoring-dimensions.md`
3. **Stop** — No further action needed.

## Output Format

```
**Overall Score: X / 10** — <band label>

**Strengths** (score >= 7/10):
- <dimension>: <score>/10 — <detail>

**Gaps** (score < 4/10):
- <dimension>: <score>/10 — <detail>

**All Dimensions** (weakest first):
| Dimension | Score | Finding |
|---|---|---|
| ... | X/10 | ... |

**Suggestions:**
1. <suggestion>
2. <suggestion>
```

## Error Handling

| Error | Action |
|---|---|
| Empty prompt | Ask user to provide a prompt |
| Cortex Complete fails | Report error; suggest checking warehouse availability or trying a different model |
| JSON parse failure | Show raw response and report the issue |
