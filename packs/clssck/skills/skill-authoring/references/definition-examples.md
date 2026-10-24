# Definition Examples

Seven patterns from bundled OMP definitions: what to borrow and where to adapt it. Links open upstream source; verify runtime details against the version in `omp-source-lock.json`. Re-state each pattern in the target definition's own terms; NEVER paste the host prompt around it.

| Example | Primitive | Borrow |
|---|---|---|
| Agent acceptance criteria | agent | all-must-hold report gate |
| Agent coverage | agent | reviewed and deferred scope as output |
| Skill dry-run | skill | inspect exact inputs before spending |
| Skill declared loss | skill | claim ledger checked after rewrite |
| Rule correction table | rule | situation → remedy table |
| Command named outcomes | command | closed status vocabulary |
| Tool state-shaped usage | tool | per-state input contract |

## Agent acceptance criteria

Source: [reviewer.md](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/prompts/agents/reviewer.md)

**Pattern:** a finding is reportable only when every listed criterion holds: provable impact on named code paths, actionable fix, unintentional, introduced by the patch, no unstated assumption about code or author intent, rigor proportionate to the rest of the codebase. A second block forces a consumer-side check: any value crossing a function or module boundary is traced to its dispatch point, and a silent drop is a defect.

**Adapt:** rewrite the criteria for the agent's domain. Do not copy the host's frontmatter `tools`, model, spawn settings, or incremental-`yield` procedure unless the caller supports that contract.

## Agent coverage

Source: [security-reviewer.md](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/prompts/agents/security-reviewer.md)

**Pattern:** coverage is part of the output. `reviewed_paths` lists what was read; `deferred` lists what was skipped, each with a `reason`. Every candidate is traced from attacker-controlled source to broken control or dangerous sink. An empty findings list is a valid result when the agent states what it reviewed.

**Adapt:** any review agent MAY use the coverage fields; they are not host-only. An `output` schema alone does not force structured output: the agent needs `structured: true` or a caller/session that enables structured results. Otherwise the prose MUST describe the coverage report without relying on the schema. See [task settings](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/task/settings.ts) and [structured subagent handling](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/task/structured-subagent.ts).

## Skill dry-run

Sources: [tool-prompt-optimization](https://github.com/can1357/oh-my-pi/blob/main/.omp/skills/tool-prompt-optimization/SKILL.md), [probe-builtin.ts](https://github.com/can1357/oh-my-pi/blob/main/.omp/skills/tool-prompt-optimization/scripts/probe-builtin.ts)

**Pattern:** the skill ships a finished tool and runs it in place. `--show` prints the exact wire schema, derived outline, and real prompt, then exits before any API call. The skill sorts results into prune candidates and keepers, and inferability alone NEVER justifies a deletion.

**Adapt:** give an expensive or irreversible script a dry-run that shows its real inputs. Inspect the derived outline: it keeps everything before the first header or tag, so a headerless prompt leaks whole into the "blank" outline unless `--no-summary` is set. Do not treat the host's model panel or sample count as guarantees.

### Skill retrieval preview

Sources: [skill discovery](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/extensibility/skills.ts), [description rendering](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/extensibility/skill-descriptions.ts).

For a cold-cache retrieval trial, load authored skills with the pinned `loadSkillsFromDir`, exclude hidden skills, and apply the pure `previewSkillDescription` helper. This produces the cache-miss hint without opening a description store or calling a model.

Export `OMP_ROOT` as the checkout at `omp-source-lock.json`'s `reviewedCommit`, and `SKILLS_DIR` as the pack's skills directory. Run this read-only recipe with Bun; it is not an installed tool:

```bash
bun --eval '
if (!process.env.OMP_ROOT || !process.env.SKILLS_DIR) {
  throw new Error("Export OMP_ROOT and SKILLS_DIR first");
}
const src = `${process.env.OMP_ROOT}/packages/coding-agent/src`;
const { loadSkillsFromDir } = await import(`${src}/extensibility/skills.ts`);
const { previewSkillDescription } = await import(`${src}/extensibility/skill-descriptions.ts`);
const { skills, warnings } = await loadSkillsFromDir({
  dir: process.env.SKILLS_DIR,
  source: "omp-plugins:project",
});
if (warnings.length) throw new Error(JSON.stringify(warnings));
console.log(JSON.stringify(skills.filter(skill => skill.hide !== true).map(skill => ({
  name: skill.name,
  description: previewSkillDescription(skill.description),
})), null, 2));
'
```

Use the returned name and description in the retrieval panel; keep expected labels out of the judged state. A missing target is a discovery problem, not permission to substitute full frontmatter.

NEVER use the default `new SkillDescriptionCatalog()` for an isolated check: its constructor opens the shared user database. If catalog behavior itself is under test, pass `store: SkillDescriptionStore.open(ownedPath)` for a fresh session-owned path, await `store.close()`, and remove only that owned scratch after its process exits. An empty store still measures the cold-cache path; it does not prove cached compression or live model selection.


## Skill declared loss

Source: [semantic-compression](https://github.com/can1357/oh-my-pi/blob/main/.omp/skills/semantic-compression/SKILL.md)

**Pattern:** before rewriting, split the source into atomic claims and list every load-bearing token: identifiers, defaults with units, bounds, MUST/NEVER lines. After rewriting, name each dropped claim, default, or qualifier with the reason the text stays correct, then review the draft against that list rather than from memory.

**Adapt:** keep the ledger as a local verification artifact for the edit or its report, not as a history section inside the definition. Do not port the host's compression-ratio stop threshold or its measured token anecdotes as rules.

## Rule correction table

Source: [ts-no-any.md](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/discovery/builtin-rules/ts-no-any.md)

**Pattern:** a table maps each situation to its remedy and that remedy's limit. External data gets a schema parse. An in-process `unknown` gets a narrow type guard. A compiler gap where a runtime check would be meaningless gets an unchecked cast, assigned to a named const with a one-line reason.

**Adapt:** use the project's existing libraries. Borrow the table's shape, not unchecked code snippets; compile or run each example before porting it. The table supplies a correction after the rule fires. It does not make the rule judged; that requires a `question` field.

**Lesson:** borrow the short positive `condition` and explicit tool `scope` from [rs-box-leak.md](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/discovery/builtin-rules/rs-box-leak.md) and [ts-no-test-timers.md](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/discovery/builtin-rules/ts-no-test-timers.md). Their `interruptMode: never` suits advisory guidance, which may arrive after execution; destructive-action guards need `always` or `tool-only` to pause a matching call first. Keep exceptions in the body instead of parsing quoting, wrappers, or authorization in regex.

## Command named outcomes

Source: [fix-issues.md](https://github.com/can1357/oh-my-pi/blob/main/.omp/commands/fix-issues.md)

**Pattern:** every run ends in one closed status, `fixed | unreproduced | not-a-bug | existing-pr`, and each status names the evidence it needs: repro result, missing information, or explanation. Fields that exist only on some paths (worktree, branch, commits) are marked "if applicable".

**Adapt:** borrow the report shape, not automatic staging, commits, or a `main` assumption. The command MUST state its own authorization. Use `{{ARGUMENTS}}` for literal joined text, or `{{#each args}}` to preserve parsed argument boundaries. Raw `$ARGUMENTS` is inserted before Handlebars runs and can turn argument text into template syntax; see [slash-command rendering](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/extensibility/slash-commands.ts).

## Tool state-shaped usage

Source: [yield.md](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/prompts/tools/yield.md)

**Pattern:** the description changes with the caller's state, and each state has its own input contract:

| State | Valid call | Forbidden |
|---|---|---|
| workpool | one `key` plus exactly one of `data` or `error`, one item per call | several items in one call |
| ordinary | `data` on success or `error` on failure | both; a bare payload outside `data` |
| output schema | terminal `data` is the full schema object | data-less finalize with no sections submitted |

**Adapt:** state each mode's conditional inputs and forbidden combinations. `workPoolItems` and `hasOutputSchema` are computed by the [yield tool](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/tools/yield.ts), not pack frontmatter fields. Describe the pack's modes in plain prose.
