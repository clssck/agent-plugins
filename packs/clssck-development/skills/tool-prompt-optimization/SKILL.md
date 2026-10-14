---
name: tool-prompt-optimization
description: "Author, audit, trim, or review the description prompts an agent reads to learn its tools (function/tool docs, MCP tool descriptions). Two halves: (1) measure how much of a tool prompt is already inferable from the tool's name + JSON parameter schema, to prune redundancy with evidence; (2) authoring rules for what belongs in a tool prompt vs what stays in code. Use when writing a tool description, deciding what schema field descriptions already cover, testing schema-vs-prompt overlap before deleting prompt lines, or cutting a bloated tool doc. Prompt voice, tags, RFC keywords — system-prompts; re-encoding mechanics — semantic-compression."
---

# Tool Prompt Optimization

A tool prompt is read cold, next to a wire schema the model already sees. Content reconstructible from `(name, JSON schema, blank outline)` is a *prune candidate*, never an automatic delete. Probe that overlap for evidence: ask models to predict the prompt body from those inputs. Lines recovered reliably across samples and models → candidates. Lines no model recovers → load-bearing, keep.

This skill owns tool-prompt content: what ships, what stays in code, how to measure. Voice, tags, and RFC 2119 vocabulary → `system-prompts`. Re-encoding the survivors → `semantic-compression`. Decide *what* with this skill, then *how it reads* with those two.

## Run probe

[`probe.ts`](skill://tool-prompt-optimization/scripts/probe.ts) is generic: any tool, any schema. You supply the schema, the outline, and the models. Model calls use the OMP host model layer, so run it from a working directory where `@oh-my-pi/pi-ai` and `@oh-my-pi/pi-catalog` resolve; credentials are whatever the host resolves for the provider you select.

```bash
bun "$(realpath skill://tool-prompt-optimization/scripts/probe.ts)" \
  --schema schema.json --template outline.md --name search_files \
  --model <provider/id> --model <provider/id> --samples 3
```

| Flag | Rule |
|---|---|
| `--schema`, `--template` | Required. File path, else inline value. |
| `--model` | Required unless `CLSSCK_PROBE_MODELS` is set. Repeatable; commas allowed; `provider/id`. Flag wins over env. |
| `--samples` | Integer 1..20, default 3. |
| `--max-tokens` | Integer 1..32000, default 1200. |
| `--name` | Tool name shown to the model; default `the tool`. |
| `--json` / `--help` | Machine output / usage, exit 0. |

- **Validation:** bad flags, unknown flags, missing models, out-of-range numbers → error + usage, exit 2, before any model call. No default panel exists: you choose models and own the spend.
- **Panel:** use at least two unrelated models; agreement across them is the signal. One model = noise.
- **Programmatic:** `import { probe } from "./probe.ts"` → `probe({ schema, template, models, samples?, name?, maxTokens? })` → `{ prompt, results: [{ model, samples: [{ text, stopReason, usage, error }] }] }`. `models` is required.

### OMP-host adapter (optional)

[`probe-builtin.ts`](skill://tool-prompt-optimization/scripts/probe-builtin.ts) works only inside an OMP checkout. It instantiates a live host tool and reads the exact wire schema (`toolWireSchema`) and rendered description (`tool.description`), derives the outline, then calls the generic probe. Anywhere else, use `probe.ts` with hand-supplied inputs; it still calls models through the OMP host model layer, so `@oh-my-pi/pi-ai` and `@oh-my-pi/pi-catalog` MUST resolve from the working directory.

```bash
bun "$(realpath skill://tool-prompt-optimization/scripts/probe-builtin.ts)" --tool <name> --show
bun "$(realpath skill://tool-prompt-optimization/scripts/probe-builtin.ts)" --tool <name> [--no-summary] --model <provider/id>
```

- `--show`: prints resolved schema, derived outline, real prompt; offline, needs no model, makes no model call. Run it first.
- `--no-summary`: also drops the first-line summary. Section names still reach the model.
- `--model`, `--samples`, `--max-tokens`, `--json`: same rules as `probe.ts`. Output ends with the real prompt for in-place diff.
- Factory-map resolution bypasses the host's tool allowlist. `github` is built directly and skips its CLI-availability gate; any other tool that fails to construct needs the manual `probe.ts` path.

## Inputs

**Schema:** the wire schema the model actually sees, never a hand sketch. Include `required` and `additionalProperties: false`; omitting them makes usage look looser than it is. Export it from the host (the adapter does) or copy the serialized request.

**Outline:** the real prompt's structure with every body blanked: first-line summary, then each section tag containing `...`. The adapter refuses a prompt whose outline would equal the prompt itself (no sections) or come out empty.

```
Search files by name or content under a directory.

<instruction>
...
</instruction>

<output>
...
</output>

<critical>
...
</critical>
```

## Interpret

Bucket each line of the real prompt:

| Bucket | Lines |
|---|---|
| **Prune candidate** | Stable across samples **and** models; restates the schema: parameter names/types, `required`, example values already in field descriptions, stated clamp ranges. |
| **Keep** | No model recovers it: defaults and their direction (`gitignore: true` does not say "respects gitignore"); routing and escalation ("NEVER shell out to `find` → use this tool"); exact output shape (ordering, grouping, truncation, URIs); WRONG/RIGHT anti-patterns; constraints invisible to types (embedded-DSL grammar, trailing delimiters). |

One sample is noise. Stable cross-model overlap only nominates a line; history clears it.

Worked read, for a `search_files(pattern, path?, glob?, limit?)` schema: models restate "`pattern`: text or regex to find; `path`: directory, default current" → prune after check. They never produce "results grouped by file, newest first; truncated output carries a handle for the full list" or "NEVER pipe to `grep`" → keep.

## Before every deletion

- **Version history:** MUST read the history of each cut line (blame, commit message, linked issue). Many lines are incident scar tissue: a hallucinated flag, a shell-out, a repo-root scan. Keep scar tissue. Inferability is necessary, NEVER sufficient.
- **Memorization ≠ inference:** a model may recite a public tool's prompt from training. Host-specific names and URI schemes absent from the schema are recitation; discount them.
- **Outline leaks:** summary and section names hint. For schema-alone inference run a second pass with `--no-summary`; for generic section names too, hand `probe.ts` a template with renamed tags. Content surviving only the summary is summary-inferable, not schema-inferable.
- **Verdict:** models typically recover schema-covered parameter mechanics and generic usage; they do not recover defaults, output shape, routing, anti-patterns, or domain grammar. Self-documenting flag tools prune heavily; DSL and capability tools barely. Treat that as a hypothesis for your tool, not a result: the probe decides.

## Authoring

Tool prompts teach when to choose the tool, its input shape, and agent-owned failures. They are not API docs. Engine internals, recovery heuristics, fallback chains, performance tuning: code.

### Surface, not machinery

Agents choose from prose, not source: tell WHEN/WHY, NEVER internal HOW.

|Tool|Teach|Omit|
|---|---|---|
|file reader|every source it covers (file, directory, archive, URL) so the agent skips `cat`/`curl`/`tar`|chunker, binary sniffer, cache layer|
|language-server client|"MUST use it whenever a language server is available — safer than text search"|wire protocol, server lifecycle, capability negotiation|
|structural search/replace|metavariable syntax + workflow: loosest existence check first, narrow paths|AST engine, query compilation, grammar selection|
|line-anchored editor|patch grammar (anchors, ops, payloads, ranges) + successful edit shapes|hash internals, fuzz tolerance, recovery helpers; the agent sees only "resolved your typo" or "anchor stale, re-read"|

If a detail cannot change an agent decision, it does NOT belong. Each sentence MUST shift a call.

### Anatomy

1. **One-line purpose** in agent vocabulary: "compact, line-anchored edit format", not "wraps libfoo with X".
2. **Input grammar:** operators, parameters, selectors; verbatim emitted syntax.
3. **Worked examples:** 3–8 common shapes; an example is the explanation, never narrate twice.
4. **Agent-owned failures:** stale anchor, missing payload prefix, fabricated identifier; omit silently recovered failures.
5. **Anti-patterns:** WRONG/RIGHT pairs from real retries, never imagined ones.
6. **`<critical>` recap:** 3–6 load-bearing lines for agents that skip the body. Tool prompts are short, so one recap at the end suffices; the start-and-end rule is for long system prompts.

### Exclude

- Implementation file/function names, module layout.
- Recovery, retry, normalization, caching, fuzzy matching.
- Performance (`O(n)`) unless it changes strategy.
- Telemetry, logging, debug flags, env vars the agent cannot set.
- Version history, deprecated parameters, "previously this worked differently".
- Cross-tool plumbing ("calls `read` under the hood") unless coordination is required.

### Examples drive the contract

- Mechanical syntax: one correct example beats three grammar paragraphs.
- The model anchors output format on the latest example: canonical shape last.
- Adjacent WRONG/RIGHT removes a retry class.
- Examples MUST be runnable, not pseudo-code: JSON tool → JSON example; custom grammar → real anchors, prefixes, line numbers.

```
WRONG  search_files({"pattern": "TODO", "path": "src", "limit": "ten"})
RIGHT  search_files({"pattern": "TODO", "path": "src", "limit": 10})
```
