# Prompt Quality Scoring Dimensions

The prompt quality scorer evaluates any LLM prompt across 9 dimensions via `SNOWFLAKE.CORTEX.COMPLETE`. Scores are produced by an LLM applying a structured heuristic rubric. Because an LLM executes the rules, scores may vary slightly across calls, but the rubric ensures consistent evaluation criteria. The agent builds a scoring meta-prompt embedding these rules and the user's prompt, then asks the LLM to apply each sub-criterion and return structured JSON.

## Overall Score Formula

```
overall_score = round(1 + sum(dimension_scores))
```

- **Base**: 1 (every non-empty prompt gets at least 1)
- **9 dimensions x 0-1 each** = up to +9
- **Range**: 1-10

| Score | Interpretation |
|---|---|
| 1-3 | Poor — missing most fundamentals |
| 4-5 | Needs work — has basics but significant gaps |
| 6-7 | Good — solid prompt with room to improve |
| 8-9 | Very good — well-crafted, minor improvements possible |
| 10 | Excellent — hits all dimensions fully |

## Dimensions

### 1. Structure (0-1)

*Is the prompt well-organized and appropriately sized?*

| Sub-criterion | Points | Detection |
|---|---|---|
| Section delimiters | +0.33 | XML tags, markdown headers (`##`), numbered sections, triple-backtick blocks |
| Paragraph separation | +0.33 | 2+ paragraph breaks (`\n\n`) |
| Appropriate length | +0.34 | Between 100 and 50,000 characters |

### 2. Role Clarity (0-1)

*Does the prompt define who the LLM should be?*

| Sub-criterion | Points | Detection |
|---|---|---|
| Has role definition | +0.5 | "You are a/an...", "Act as...", "As a...", "Your role is..." |
| Role is domain-specific | +0.5 | Role sentence contains domain-specific nouns. "Snowflake DMF expert" = full; "helpful assistant" = only 0.5 total |

### 3. Task Specification (0-1)

*Does the prompt clearly state what to do?*

| Sub-criterion | Points | Detection |
|---|---|---|
| Imperative instructions | +0.33 | Action verbs: Analyze, Generate, Create, Summarize, Extract, Classify, Compare |
| Clear deliverable | +0.33 | Output words: return, output, respond with, provide, recommend |
| No vague language | +0.34 | Zero instances of "try to", "maybe", "if possible", "do your best", "feel free". Each instance deducts 0.08 |

### 4. Output Specification (0-1)

*Does the prompt tell the LLM what format to produce?*

| Sub-criterion | Points | Detection |
|---|---|---|
| Format mentioned | +0.5 | "JSON", "markdown", "CSV", "list", "table", "bullet points", "XML", "YAML" |
| Output constraints | +0.5 | Size/shape: "up to N", "maximum N", "no more than", "in N sentences", or structural schema (field names, types) |

### 5. Context & Grounding (0-1)

*Does the prompt provide concrete data or domain context?*

| Sub-criterion | Points | Detection |
|---|---|---|
| Has data/context section | +0.5 | Placeholders (`{variable}`, `{{template}}`), data blocks, context section headers |
| Domain-specific content | +0.5 | Domain terminology beyond generic stop words |

### 6. Safety & Guardrails (0-1)

*Does the prompt set boundaries on what the LLM should NOT do?*

| Sub-criterion | Points | Detection |
|---|---|---|
| Negative constraints | +0.5 | "Do not", "Never", "Avoid", "Must not", "Don't" |
| Edge case / fallback handling | +0.5 | "If... then", "In case of", "When there is no", "If unknown", "Otherwise", "If you cannot" |

### 7. Examples (0-1)

*Does the prompt demonstrate expected input/output?*

| Sub-criterion | Points | Detection |
|---|---|---|
| Has positive examples | +0.5 | "Example:", "For instance:", "Sample output:", structured example blocks (JSON/code) |
| Has negative examples | +0.5 | "Incorrect example", "Do NOT return", "Example of WRONG", CORRECT vs INCORRECT contrast |

### 8. Reasoning Guidance (0-1)

*Does the prompt guide the LLM's thinking process?*

| Sub-criterion | Points | Detection |
|---|---|---|
| Chain-of-thought | +0.5 | "step by step", "think through", "let's reason", "break down", "first... then..." |
| Instruction priority/hierarchy | +0.5 | "Top Priority", "High Priority", "Secondary", "most important", "in order of importance", numbered priority lists |

### 9. Completeness (0-1)

*Does the prompt reinforce critical rules and cover its bases?*

| Sub-criterion | Points | Detection |
|---|---|---|
| Emphasis / reinforcement | +0.5 | Emphasis markers ("Important:", "Critical:", "MUST", "Note:") or key phrases restated across sections |
| Fallback / summary section | +0.5 | Recap at the end: "Critical requirements:", "Summary:", "Remember:", "Key points:" |

## Architecture

Scoring is performed via a single `SNOWFLAKE.CORTEX.COMPLETE` call (default model: `claude-sonnet-4-6`). The agent constructs a scoring meta-prompt that embeds all 9 dimension definitions, sub-criteria, and point values, then asks the LLM to evaluate the user's prompt against each rule and return the structured JSON result. Because the scoring is LLM-based, results are non-deterministic — scores may vary slightly across calls, but the structured rubric provides consistent evaluation criteria. See `workflows/prompt-quality.md` for the full meta-prompt template.

## JSON Response Format

```json
{
  "overall_score": 9,
  "dimensions": {
    "structure": { "score": 1.0, "detail": "Markdown headers, paragraph separation, good length" },
    "role_clarity": { "score": 1.0, "detail": "Domain-specific role: 'Snowflake DMF expert'" },
    "task_specification": { "score": 1.0, "detail": "Clear action verbs, no vague language" },
    "output_specification": { "score": 1.0, "detail": "JSON format with field-level schema" },
    "context_grounding": { "score": 1.0, "detail": "Rich data profile with column stats" },
    "safety_guardrails": { "score": 1.0, "detail": "'DO NOT recommend', edge case handling" },
    "examples": { "score": 0.5, "detail": "Has positive examples; no negative examples" },
    "reasoning_guidance": { "score": 0.5, "detail": "Has priority hierarchy; no chain-of-thought" },
    "completeness": { "score": 1.0, "detail": "'Critical requirements' section restates key rules" }
  },
  "suggestions": [
    "Add a negative example showing an INCORRECT response",
    "Add chain-of-thought guidance ('Think step by step: first...')"
  ]
}
```
