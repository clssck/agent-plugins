import { afterEach, describe, expect, test } from "bun:test";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { adaptCompatibility, planCompatibility } from "./compatibility";

const temporaryDirectories: string[] = [];

async function fixture(files: Record<string, string>): Promise<string> {
	const root = await mkdtemp(path.join(tmpdir(), "agent-plugins-compat-"));
	temporaryDirectories.push(root);
	for (const [relative, contents] of Object.entries(files)) {
		const file = path.join(root, relative);
		await mkdir(path.dirname(file), { recursive: true });
		await writeFile(file, contents);
	}
	return root;
}

afterEach(async () => {
	await Promise.all(temporaryDirectories.splice(0).map((directory) => rm(directory, { recursive: true, force: true })));
});

describe("CoCo OMP compatibility", () => {
	test("converts structured choices to the OMP ask schema and is idempotent", async () => {
		const root = await fixture({
			"skills/access/SKILL.md": `---
name: access
description: Access workflow
---

# Access

\`\`\`python
AskUserQuestion(
    questions=[{
        "id": "approval",
        "header": "Approval",
        "question": "Proceed?",
        "multiSelect": false,
        "options": [
            {"label": "Yes", "description": "Continue"},
            {"label": "No", "description": "Stop"}
        ]
    }]
)
\`\`\`
`,
		});

		const result = await adaptCompatibility(root);
		expect(result.errors).toEqual([]);
		expect(result.changed).toEqual(["skills/access/SKILL.md"]);
		const contents = await readFile(path.join(root, "skills/access/SKILL.md"), "utf8");
		expect(contents).toContain('ask(\n    i="Collecting user decision",');
		expect(contents).toContain('"id": "approval"');
		expect(contents.match(/"id": "approval"/g)).toHaveLength(1);
		expect(contents).not.toContain('"id": "selection"');
		expect(contents).toContain('"multi": false');
		expect(contents).not.toContain("AskUserQuestion");
		expect(contents).not.toContain("multiSelect");
		expect(contents).toContain("only an explicit user response grants approval");
		expect(contents).toContain("automatic/default selection does not");
		expect((await planCompatibility(root)).changed).toEqual([]);
	});

	test("adds unique ids to multi-question and implicit ask payloads", async () => {
		const root = await fixture({
			"skills/questions/SKILL.md": `---
name: questions
description: Questions
---

ASK the user:

{
  "questions": [
    {
      "question": "First?",
      "multiSelect": false,
      "options": [{"label": "A"}]
    },
    {
      "question": "Second?",
      "multiSelect": true,
      "options": [{"label": "B"}]
    }
  ]
}
`,
		});

		const result = await adaptCompatibility(root);
		expect(result.errors).toEqual([]);
		const contents = await readFile(path.join(root, "skills/questions/SKILL.md"), "utf8");
		expect(contents).toContain('"id": "selection_1"');
		expect(contents).toContain('"id": "selection_2"');
		expect(contents).toContain('"multi": true');
		expect(contents).not.toContain("multiSelect");
		expect((await planCompatibility(root)).changed).toEqual([]);
	});

	test("maps supported skill loads to OMP skill URLs", async () => {
		const root = await fixture({
			"skills/marketplace-search/SKILL.md": `---\nname: marketplace-search\ndescription: Search\n---\n\nCall \`skill(command="marketplace-search")\`, then skill().\n`,
			"skills/event-table/SKILL.md": `---\nname: event-table\ndescription: Events\n---\n\nskill(command="dt-alerting")\n`,
			"skills/migration/SKILL.md": `---\nname: migration\ndescription: Migrate\n---\n\nskill("snowflake-notebooks")\n`,
			"skills/ai-data-share/create_agent.md": `Load the cortex-agent skill with read skill://cortex-agent/SKILL.md.\n`,
		});

		const result = await adaptCompatibility(root);
		expect(result.errors).toEqual([]);
		expect(await readFile(path.join(root, "skills/marketplace-search/SKILL.md"), "utf8")).toContain(
			"read skill://marketplace-search/SKILL.md",
		);
		expect(await readFile(path.join(root, "skills/event-table/SKILL.md"), "utf8")).toContain(
			"read skill://dynamic-tables/dt-alerting/SKILL.md",
		);
		expect(await readFile(path.join(root, "skills/migration/SKILL.md"), "utf8")).toContain(
			"read skill://snowflake-notebooks/SKILL.md",
		);
		const createAgent = await readFile(path.join(root, "skills/ai-data-share/create_agent.md"), "utf8");
		expect(createAgent).toContain("read skill://agent-studio/agent/creation/SKILL.md");
		expect(createAgent).toContain("agent-studio agent creation skill");
		expect(createAgent).not.toContain("cortex-agent");
	});

	test("does not mistake task calls for ask calls and rejects legacy task fields", async () => {
		const root = await fixture({
			"skills/delegation/SKILL.md": [
				"---",
				"name: delegation",
				"description: Delegate work",
				"---",
				"",
				"```python",
				"task(",
				'    i="Collecting user decision",',
				'    subagent_type="general-purpose",',
				'    description="Fix a cell",',
				'    prompt="Fix it"',
				")",
				"",
				"job = BatchInferenceTask(",
				'    i="Collecting user decision",',
				'    "batch"',
				")",
				"```",
			].join("\n"),
		});

		const result = await adaptCompatibility(root);
		expect(result.errors).toEqual(["skills/delegation/SKILL.md: unsupported task subagent_type field"]);
		const contents = await readFile(path.join(root, "skills/delegation/SKILL.md"), "utf8");
		expect(contents).toContain('task(\n    subagent_type="general-purpose"');
		expect(contents).toContain('BatchInferenceTask(\n    "batch"');
		expect(contents).not.toContain('i="Collecting user decision"');
	});

	test("rejects positional ask interfaces", async () => {
		const root = await fixture({
			"skills/approval/SKILL.md": [
				"---",
				"name: approval",
				"description: Approval",
				"---",
				"",
				"ask(",
				'    i="Collecting user decision",',
				'    "Proceed?",',
				'    choices=["yes", "no"],',
				")",
			].join("\n"),
		});

		const result = await adaptCompatibility(root);
		expect(result.errors).toContain("skills/approval/SKILL.md: ask call does not use OMP's questions schema");
	});

	test("gates external capabilities without inventing a fallback", async () => {
		const root = await fixture({
			"skills/sql/SKILL.md": `---\nname: sql\ndescription: SQL\n---\n\nUse \`cortex agent-studio\`, \`nipyapi\`, or \`snowflake.connector\`; run the query with \`snowflake_sql_execute\`.\n`,
		});

		await adaptCompatibility(root);
		const contents = await readFile(path.join(root, "skills/sql/SKILL.md"), "utf8");
		expect(contents).toContain(
			"external capabilities not built into OMP: `cortex CLI`, `nipyapi`, `snowflake.connector`, `snowflake_sql_execute`",
		);
		expect(contents).toContain("blocked: missing <capability>");
		expect(contents).toContain("never substitute an unrelated shell command or claim execution");
		expect(contents).not.toContain("`sql_execute`");
	});

	test("detects executable cortex CLI commands without gating names, paths, or URLs", async () => {
		const root = await fixture({
			"skills/cli/SKILL.md": `---\nname: cli\ndescription: CLI\n---\n\nRun \`cortex search object \"table\"\`.\n`,
			"skills/docs/SKILL.md": `---\nname: docs\ndescription: Docs\n---\n\nSee https://docs.snowflake.com/en/user-guide/snowflake-cortex/example, ~/.snowflake/cortex/config, and cortex-agent.\n`,
		});

		const result = await adaptCompatibility(root);
		expect(result.errors).toEqual([]);
		const cli = await readFile(path.join(root, "skills/cli/SKILL.md"), "utf8");
		const docs = await readFile(path.join(root, "skills/docs/SKILL.md"), "utf8");
		expect(cli).toContain("`cortex CLI`");
		expect(docs).not.toContain("cortex CLI");
		expect(docs).not.toContain("omp-compat:start");
	});

	test("rejects instructions that treat ask as a turn boundary", async () => {
		const root = await fixture({
			"skills/status/SKILL.md": `---\nname: status\ndescription: Status\n---\n\nPresent status, then end your turn with \`ask\`.\n`,
		});

		const result = await adaptCompatibility(root);
		expect(result.errors).toContain(
			"skills/status/SKILL.md: OMP ask returns in the same turn; it is not a turn boundary",
		);
	});

	test("de-links missing Markdown references and preserves unrelated text", async () => {
		const source = `---\nname: docs\ndescription: Docs\n---\n\nRead [missing](references/missing.md).\n\n\`SELECT 'AskUserQuestionnaire';\`\n`;
		const root = await fixture({ "skills/docs/SKILL.md": source });

		await adaptCompatibility(root);
		const contents = await readFile(path.join(root, "skills/docs/SKILL.md"), "utf8");
		expect(contents).toContain("missing *(reference not included in this pack)*");
		expect(contents).toContain("`SELECT 'AskUserQuestionnaire';`");
	});

	test("rewrites known cross-language fixer delegation to OMP task batches", async () => {
		const file = "skills/spark-migration/snowpark-connect/migrate-pyspark-to-snowpark-connect/agents/fixer.md";
		const root = await fixture({
			[file]: [
				"task(",
				'     subagent_type="general-purpose",',
				'     description="Fix single Scala cell",',
				'     prompt="<content of migrate-spark-scala-to-snowpark-connect/agents/fixer.md>\\n\\n"',
				'            "CELL_MODE=true\\n"',
				'            "CELL_SOURCE=<cell.source>\\n"',
				"            \"CELL_ISSUES=<subset of analysis.json matching this cell AND language=='scala'>\\n\"",
				"   )",
			].join("\n"),
		});

		const result = await adaptCompatibility(root);
		expect(result.errors).toEqual([]);
		const contents = await readFile(path.join(root, file), "utf8");
		expect(contents).toContain('context="Fix one cross-language notebook cell');
		expect(contents).toContain('"agent": "task"');
		expect(contents).toContain('"solutionSpace":');
		expect(contents).not.toContain("subagent_type");
	});

	test("rejects bare and unsupported question payloads", async () => {
		const root = await fixture({
			"skills/example/SKILL.md": `---\nname: example\ndescription: Example\n---\n\nAsk:\n{\n  "questions": [{\n    "question": "Unwrapped?",\n    "options": [{"label": "Yes"}, {"label": "No"}]\n  }]\n}\n\nask(\n  i="Collecting user decision",\n  questions=[{\n    "id": "name",\n    "question": "Name?",\n    "type": "text",\n    "defaultValue": "demo",\n    "options": [{"label": "Demo"}, {"label": "Production"}]\n  }]\n)\n`,
		});

		const result = await adaptCompatibility(root);
		expect(result.errors).toContain("skills/example/SKILL.md: bare questions payload is not wrapped in ask(...)");
		expect(result.errors).toContain("skills/example/SKILL.md: unsupported ask type/defaultValue field");
	});

	test("preserves Cortex Code's own tool reference without treating it as OMP instructions", async () => {
		const source = `---\nname: cortex-code-guide\ndescription: Cortex Code reference\n---\n\n| ask_user_question | Supports text input |\n| web_fetch | Fetch a URL |\n`;
		const root = await fixture({ "skills/cortex-code-guide/SKILL.md": source });

		const result = await adaptCompatibility(root);
		expect(result.errors).toEqual([]);
		expect(result.changed).toEqual([]);
		expect(await readFile(path.join(root, "skills/cortex-code-guide/SKILL.md"), "utf8")).toBe(source);
	});

	test("rejects unknown skill-command interfaces", async () => {
		const root = await fixture({
			"skills/example/SKILL.md": `---\nname: example\ndescription: Example\n---\n\nskill(command="unknown-skill")\n`,
		});

		const result = await adaptCompatibility(root);
		expect(result.errors).toEqual(["skills/example/SKILL.md: unsupported skill(command=...) invocation"]);
	});
	test("normalizes compact asks and preserves ids declared after question keys", async () => {
		const root = await fixture({
			"skills/choices/SKILL.md": `---\nname: choices\ndescription: Choices\n---\n\nask_question(questions=[{"question": "First?", "options": [{"label": "A"}]}, {"question": "Second?", "id": "custom", "options": [{"label": "B"}]}])\n`,
		});

		const result = await adaptCompatibility(root);
		expect(result.errors).toEqual([]);
		const contents = await readFile(path.join(root, "skills/choices/SKILL.md"), "utf8");
		expect(contents).toContain('i="Collecting user decision"');
		expect(contents).toContain('"id": "selection_1"');
		expect(contents.match(/"id": "custom"/g)).toHaveLength(1);
		expect(contents).not.toContain("ask_question");
	});

	test("does not mutate ordinary ask functions or add an approval notice", async () => {
		const source = `---\nname: helper\ndescription: Helper\n---\n\n\`\`\`python\ndef ask(session, question):\n    return session.send(question)\n\nllm.ask(\n    prompt,\n)\n\`\`\`\n`;
		const root = await fixture({ "skills/helper/SKILL.md": source });

		const result = await adaptCompatibility(root);
		expect(result.errors).toEqual([]);
		expect(await readFile(path.join(root, "skills/helper/SKILL.md"), "utf8")).toBe(source);
	});

	test("rejects implicit question payloads with unsupported top-level fields", async () => {
		const root = await fixture({
			"skills/questions/SKILL.md": `---\nname: questions\ndescription: Questions\n---\n\nASK the user:\n{\n  "questions": [\n    {"question": "Proceed?", "options": [{"label": "Yes"}]}\n  ],\n  "timeout": 30\n}\n`,
		});

		const result = await adaptCompatibility(root);
		expect(result.errors).toContain("skills/questions/SKILL.md: implicit question payload was not adapted");
		const contents = await readFile(path.join(root, "skills/questions/SKILL.md"), "utf8");
		expect(contents).toContain('"timeout": 30');
		expect(contents).not.toContain("timeout=30");
	});

	test("scopes ask-field lint to question objects", async () => {
		const root = await fixture({
			"skills/fields/SKILL.md": `---\nname: fields\ndescription: Fields\n---\n\nask(\n  i="Choosing a view",\n  questions=[{\n    "id": "view",\n    "question": "Pick the 'type': view or table?",\n    "options": [{"label": "View"}]\n  }]\n)\n\nExample output: {"type": "object", "defaultValue": 1}\n`,
		});

		const result = await adaptCompatibility(root);
		expect(result.errors).toEqual([]);
	});

	test("gates the full external capability vocabulary", async () => {
		const root = await fixture({
			"skills/external/SKILL.md": `---\nname: external\ndescription: External\n---\n\nRun \`cortex ctx message list\`, then use get_page_context, bash_output, open_file, snowsight_navigate, publish_report, kill_agent, snowflake_multi_cortex_analyst, and snowflake_connections_list.\n`,
		});

		const result = await adaptCompatibility(root);
		expect(result.errors).toEqual([]);
		const contents = await readFile(path.join(root, "skills/external/SKILL.md"), "utf8");
		for (const capability of [
			"bash_output",
			"cortex CLI",
			"get_page_context",
			"kill_agent",
			"open_file",
			"publish_report",
			"snowsight_navigate",
			"snowflake_connections_list",
			"snowflake_multi_cortex_analyst",
		]) {
			expect(contents).toContain(`\`${capability}\``);
		}
	});

	test("converts namespaced dollar routes without extending the skill URI", async () => {
		const root = await fixture({
			"skills/sf-solutions/SKILL.md": `---\nname: sf-solutions\ndescription: Solutions\n---\n\nRun \`$sf-solutions:predictive-maintenance teardown\`. SQL uses $sf-solutionsRole.\n`,
		});

		const result = await adaptCompatibility(root);
		expect(result.errors).toEqual([]);
		const contents = await readFile(path.join(root, "skills/sf-solutions/SKILL.md"), "utf8");
		expect(contents).toContain("skill://sf-solutions/SKILL.md predictive-maintenance teardown");
		expect(contents).not.toContain("SKILL.md:predictive-maintenance");
		expect(contents).toContain("$sf-solutionsRole");
	});

	test("removes foreign skill tools and avoids isolated task worktrees", async () => {
		const ontology = "skills/ontology-stack-builder/SKILL.md";
		const fixer = "skills/spark-migration/snowpark-connect/migrate-pyspark-to-snowpark-connect/agents/fixer.md";
		const root = await fixture({
			[ontology]: `---\nname: ontology-stack-builder\ndescription: Ontology\ntools:\n  - ask\n  - skill\n---\n`,
			[fixer]: [
				"task(",
				'     subagent_type="general-purpose",',
				'     description="Fix single Scala cell",',
				'     prompt="<content of migrate-spark-scala-to-snowpark-connect/agents/fixer.md>\\n\\n"',
				'            "CELL_MODE=true\\n"',
				'            "CELL_SOURCE=<cell.source>\\n"',
				"            \"CELL_ISSUES=<subset of analysis.json matching this cell AND language=='scala'>\\n\"",
				"   )",
			].join("\n"),
		});

		const result = await adaptCompatibility(root);
		expect(result.errors).toEqual([]);
		expect(await readFile(path.join(root, ontology), "utf8")).not.toContain("  - skill");
		expect(await readFile(path.join(root, fixer), "utf8")).not.toContain('"isolated": true');
	});

	test("rejects stale file-specific rewrites and broader ask turn-boundary wording", async () => {
		const root = await fixture({
			"skills/ai-data-share/create_agent.md": "No known compatibility source or target remains.\n",
			"skills/status/SKILL.md": `---\nname: status\ndescription: Status\n---\n\nThe \`ask\` call is a hard turn boundary.\n`,
		});

		const result = await adaptCompatibility(root);
		expect(result.errors).toContain("skills/ai-data-share/create_agent.md: compatibility rewrite 1 did not match");
		expect(result.errors).toContain(
			"skills/status/SKILL.md: OMP ask returns in the same turn; it is not a turn boundary",
		);
	});
});

describe("OMP host workflow adaptation", () => {
	test("skill authoring chooses OMP locations and preserves later workflow steps", async () => {
		const root = await fixture({
			"skills/skill-development/SKILL.md":
				"---\nname: skill-development\ndescription: Create Cortex Code skills\n---\n# Skill Development\n## Strong Skill Domains\nCortex Code has **native tooling and deep integration** for these domains\n",
			"skills/skill-development/create-from-scratch/SKILL.md":
				"# Create\n### Step 3: Choose Location\nOtherwise: `.cortex/skills/demo`\n### Step 4: Write SKILL.md\nKeep this implementation step.\n",
			"skills/skill-development/summarize-session/SKILL.md":
				"# Capture\n3. **Location**:\n - `.snowflake/cortex/skills/demo`\n### Step 5: Generate Skill\nKeep parameters.\n",
			"skills/skill-development/audit-skill/SKILL.md": "Ask for skill path or name. Search `.cortex/skills/`.\n",
			"skills/skill-development/compile-skill/SKILL.md":
				"Ask for `<skill-name>`. Resolve to a SKILL.md in this order:\n1. `.cortex/skills/`\nRead the SKILL.md. Keep the executor requirements.\n",
		});
		expect((await adaptCompatibility(root)).errors).toEqual([]);
		for (const name of ["create-from-scratch", "summarize-session"]) {
			const output = await readFile(path.join(root, `skills/skill-development/${name}/SKILL.md`), "utf8");
			expect(output).toContain("`.omp/skills/<name>/SKILL.md`");
			expect(output).toContain("`~/.omp/agent/skills/<name>/SKILL.md`");
			expect(output).not.toContain("Otherwise:");
		}
		expect(await readFile(path.join(root, "skills/skill-development/create-from-scratch/SKILL.md"), "utf8")).toContain(
			"Keep this implementation step.",
		);
		expect(await readFile(path.join(root, "skills/skill-development/compile-skill/SKILL.md"), "utf8")).toContain(
			"Keep the executor requirements.",
		);
		expect((await planCompatibility(root)).changed).toEqual([]);
	});
	test("skill creation, capture, audit, refactor, compile, and guidance agree on Decisions semantics", async () => {
		const root = await fixture({
			"skills/skill-development/create-from-scratch/SKILL.md": [
				"# Create",
				"### Step 3: Choose Location",
				"Otherwise: `.cortex/skills/demo`",
				"### Step 4: Write SKILL.md",
				"**⚠️ STOP**: [Checkpoint]",
				"## Stopping Points",
				"- ✋ After Step X",
				"## Output",
				"[What skill produces]",
				"",
			].join("\n"),
			"skills/skill-development/summarize-session/SKILL.md": [
				"# Capture",
				"3. **Location**:",
				" - `.snowflake/cortex/skills/demo`",
				"### Step 5: Generate Skill",
				"Write SKILL.md with:",
				"- Stopping points",
				"## Stopping Points",
				"- ✋ Step 1: Summary validated",
				"## Output",
				"Skill.",
				"",
			].join("\n"),
			"skills/skill-development/audit-skill/SKILL.md": [
				"# Audit",
				"Ask for skill path or name. Search `.cortex/skills/`.",
				"| Stopping points | 🔴 |",
				"| ⚠️ checkpoints marked | 🔴 |",
				"| Consequential actions match user authorization | 🔴 |",
				"**⚠️ STOP**: Present report.",
				"## Stopping Points",
				"- ✋ LINT Step 3: Present report",
				"## Output",
				"Report.",
				"",
			].join("\n"),
			"skills/skill-development/refactor-skill/SKILL.md": [
				"# Refactor",
				"**⚠️ STOP**: Present assessment and recommended level.",
				"### Step 5: Verify",
				"**⚠️ STOP**: Present refactored structure for approval.",
				"## Stopping Points",
				"",
				"- ✋ Step 1: After assessment, before refactoring",
				"- ✋ Step 5: Refactored structure approval",
				"## Output",
				"Refactored.",
				"",
			].join("\n"),
			"skills/skill-development/compile-skill/SKILL.md": [
				"# Compile",
				"**STOP** — present the eval table.",
				"## Stopping Points",
				"",
				"- After Step 3: approve bucketed clusters and proposed intents.",
				"- After Step 5: review coverage table.",
				"- After Step 6: review eval table against pre-registered thresholds.",
				"## Output",
				"Compiled.",
				"",
			].join("\n"),
			"skills/skill-development/SKILL_BEST_PRACTICES.md": [
				"# Best Practices",
				"4. **User checkpoints**: Where to pause for user input",
				"### Mandatory Stopping Points",
				"Mark where the workflow MUST pause:",
				"**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until user responds.",
				"### Approval Gates",
				"Before making changes, get explicit approval:",
				"**⚠️ MANDATORY CHECKPOINT**: Before applying changes:",
				'Wait for explicit approval (e.g., "approved", "looks good", "proceed").',
				"NEVER proceed without user confirmation.",
				"## Stopping Points",
				"- ✋ After diagnosis if ground truth needed",
				"- ✋ After analysis for approval",
				"**Resume rule:** Upon user approval, proceed directly to next step without re-asking.",
				"### 2. ❌ Missing Stopping Points",
				"**⚠️ MANDATORY CHECKPOINT**: Present changes to user for approval before applying.",
				"## Stopping Points",
				"[Where to pause for user input]",
				"| F8 | No stopping points | Medium | Agent chains without approval |",
				"- [ ] Mandatory stopping points marked with ⚠️",
				"- [ ] No chaining actions without user approval",
				"",
			].join("\n"),
		});
		expect((await adaptCompatibility(root)).errors).toEqual([]);
		const best = await readFile(path.join(root, "skills/skill-development/SKILL_BEST_PRACTICES.md"), "utf8");

		for (const name of ["create-from-scratch", "summarize-session", "audit-skill", "refactor-skill", "compile-skill"]) {
			const output = await readFile(path.join(root, "skills/skill-development", name, "SKILL.md"), "utf8");
			expect(output, name).toContain("## Decisions");
			expect(output, name).not.toContain("## Stopping Points");
			expect(output, name).not.toContain("⚠️ STOP");
		}
		const summarize = await readFile(path.join(root, "skills/skill-development/summarize-session/SKILL.md"), "utf8");
		expect(summarize).toContain("- Decisions and authorization boundaries");
		expect(summarize).not.toContain("- Stopping points");
		const audit = await readFile(path.join(root, "skills/skill-development/audit-skill/SKILL.md"), "utf8");
		expect(audit).toContain("| Decisions and authorization boundaries | 🟡 |");
		expect(audit).not.toContain("| Stopping points |");
		expect(audit).not.toContain("checkpoints marked");
		const compile = await readFile(path.join(root, "skills/skill-development/compile-skill/SKILL.md"), "utf8");
		expect(compile).toContain("**Gate** — present the eval table.");
		expect(best).toContain("### Decision Points");
		expect(best).toContain("### Authorization Boundaries");
		expect(best).toContain("### 2. ❌ No Authorization Boundary");
		expect(best).toContain("| F8 | No authorization boundary | Medium | Consequential actions ignore scope |");
		expect(best).toContain("- [ ] Consequential actions match the user's authorization");
		expect(best).not.toContain("Mandatory Stopping Points");
		expect(best).not.toContain("MANDATORY STOPPING POINT");
		expect(best).not.toContain("Approval Gates");
		expect(best).not.toContain("Missing Stopping Points");
		expect((await planCompatibility(root)).changed).toEqual([]);
	});
	test("CoCo team integration becomes manual-only while preserving capability gates", async () => {
		const root = await fixture({
			"skills/team-workflow/SKILL.md":
				"---\nname: team-workflow\ndescription: HIGHEST PRIORITY team workflow\n---\nCall team_create and spawn_teammate.\n",
		});
		expect((await adaptCompatibility(root)).errors).toEqual([]);
		const output = await readFile(path.join(root, "skills/team-workflow/SKILL.md"), "utf8");
		expect(output).toContain("disable-model-invocation: true");
		expect(output).not.toContain("HIGHEST PRIORITY");
		expect(output).toContain("blocked: missing <capability>");
		expect((await planCompatibility(root)).changed).toEqual([]);
	});
});
