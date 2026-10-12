#!/usr/bin/env bun

import { readdir, readFile, stat, writeFile } from "node:fs/promises";
import * as path from "node:path";

export type CompatibilityProfile = "coco";

export const COMPATIBILITY_VERSION = 2;
export const COMPATIBILITY_PROFILE: CompatibilityProfile = "coco";

const MARKER_START = "<!-- omp-compat:start -->";
const MARKER_END = "<!-- omp-compat:end -->";
const COMPATIBILITY_BLOCK = /\n?<!-- omp-compat:start -->[\s\S]*?<!-- omp-compat:end -->\n*/g;
const EXTERNAL_CAPABILITIES = new Set([
	"agent_output",
	"bash_output",
	"execute_sql",
	"get_page_context",
	"kill_agent",
	"list_teammates",
	"nipyapi",
	"notebook_action",
	"open_file",
	"publish_report",
	"read_active_pane",
	"semantic_studio",
	"send_message",
	"snowsight_navigate",
	"snowflake_connections_list",
	"snowflake_multi_cortex_analyst",
	"snowflake_object_search",
	"snowflake_product_docs",
	"snowflake_sql_execute",
	"spawn_teammate",
	"sql_execute",
	"task_create",
	"task_update",
	"team_create",
	"team_delete",
	"visualize_data",
	"wait_agent",
]);
const CORTEX_CLI_SUBCOMMANDS = new Set([
	"agent-studio",
	"agents",
	"ai-function-studio",
	"analyst",
	"artifact",
	"automation",
	"browser",
	"code",
	"connection",
	"connections",
	"conversation",
	"conversations",
	"ctx",
	"env",
	"extension",
	"lineage",
	"memory",
	"plugin",
	"resume",
	"search",
	"secret",
	"semantic-views",
	"sense",
	"skill",
	"ws",
]);
const CORTEX_CLI_COMMAND = /(?:^[ \t>$]*|[`(;&|]\s*|\$\(\s*)cortex[ \t]+([a-z][\w-]*)(?=[ \t]+\S|[ \t]*(?:`|$))/gm;
const SKILL_TARGETS: Record<string, string> = {
	"dt-alerting": "dynamic-tables/dt-alerting",
	"marketplace-listing-formatting": "marketplace-listing-formatting",
	"marketplace-search": "marketplace-search",
	"native-app-provider": "native-app-provider",
	"snowflake-notebooks": "snowflake-notebooks",
};

const FILE_REWRITES: Record<string, ReadonlyArray<readonly [string, string]>> = {
	"skills/ai-data-share/create_agent.md": [
		["skill://cortex-agent/SKILL.md", "skill://agent-studio/agent/creation/SKILL.md"],
		["cortex-agent", "agent-studio agent creation"],
	],
	"skills/business-ontology/workflow/sv-ingest/SKILL.md": [
		["../workflow/SKILL.md", "../SKILL.md"],
		["`../workflow`", "`..`"],
	],
	"skills/dynamic-tables/dbt-to-dt/SKILL.md": [
		["../../references/incremental-operators.md", "../references/incremental-operators.md"],
	],
	"skills/iceberg/catalog-integration/shared/verify/SKILL.md": [
		["../shared/next-steps/SKILL.md", "../next-steps/SKILL.md"],
	],
	"skills/machine-learning/ml-lineage/SKILL.md": [
		["../../data-governance/lineage/SKILL.md", "skill://lineage/SKILL.md"],
	],
	"skills/spark-migration/snowpark-connect/migrate-pyspark-to-snowpark-connect/agents/fixer.md": [
		[
			String.raw`task(
     subagent_type="general-purpose",
     description="Fix single Scala cell",
     prompt="<content of migrate-spark-scala-to-snowpark-connect/agents/fixer.md>\n\n"
            "CELL_MODE=true\n"
            "CELL_SOURCE=<cell.source>\n"
            "CELL_ISSUES=<subset of analysis.json matching this cell AND language=='scala'>\n"
   )`,
			String.raw`task(
     context="Fix one cross-language notebook cell with the sibling fixer's instructions.",
     tasks=[{
       "name": "fix-single-scala-cell",
       "agent": "task",
       "task": "<content of migrate-spark-scala-to-snowpark-connect/agents/fixer.md>\n\n"
               "CELL_MODE=true\n"
               "CELL_SOURCE=<cell.source>\n"
               "CELL_ISSUES=<subset of analysis.json matching this cell AND language=='scala'>\n",
       "solutionSpace": "Transform only the provided Scala cell; preserve every other cell and return only the transformed source."
     }]
   )`,
		],
	],
	"skills/ontology-stack-builder/SKILL.md": [["  - ask\n  - skill\n", "  - ask\n"]],
	"skills/spark-migration/snowpark-connect/migrate-spark-scala-to-snowpark-connect/agents/fixer.md": [
		[
			String.raw`task(
     subagent_type="general-purpose",
     description="Fix single Python cell",
     prompt="<content of migrate-pyspark-to-snowpark-connect/agents/fixer.md>\n\n"
            "CELL_MODE=true\n"
            "CELL_SOURCE=<cell.source>\n"
            "CELL_ISSUES=<subset of analysis.json matching this cell AND language=='python'>\n"
   )`,
			String.raw`task(
     context="Fix one cross-language notebook cell with the sibling fixer's instructions.",
     tasks=[{
       "name": "fix-single-python-cell",
       "agent": "task",
       "task": "<content of migrate-pyspark-to-snowpark-connect/agents/fixer.md>\n\n"
               "CELL_MODE=true\n"
               "CELL_SOURCE=<cell.source>\n"
               "CELL_ISSUES=<subset of analysis.json matching this cell AND language=='python'>\n",
       "solutionSpace": "Transform only the provided Python cell; preserve every other cell and return only the transformed source."
     }]
   )`,
		],
	],
};

const GLOBAL_REWRITES: ReadonlyArray<readonly [string, string]> = [
	["../../../cortex-agent/create-cortex-agent/TOOL_CREATION.md", "skill://agent-studio/agent/edit/SKILL.md"],
	["../../../cortex-agent/create-cortex-agent/ADHOC_TESTING.md", "skill://agent-studio/agent/test/SKILL.md"],
	["../../../sql/references/sql-authoring-rules.md", "skill://cortex-ai-function-studio/references/ai-function-rules.md"],
	["../../sql/references/sql-authoring-rules.md", "skill://cortex-ai-function-studio/references/ai-function-rules.md"],
];

export interface CompatibilityPlan {
	changed: string[];
	errors: string[];
}

async function exists(file: string): Promise<boolean> {
	try {
		await stat(file);
		return true;
	} catch (error) {
		if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
		throw error;
	}
}

async function markdownFiles(dir: string): Promise<string[]> {
	if (!(await exists(dir))) return [];
	const files: string[] = [];
	for (const entry of await readdir(dir, { withFileTypes: true })) {
		const file = path.join(dir, entry.name);
		if (entry.isDirectory()) files.push(...(await markdownFiles(file)));
		else if (entry.isFile() && entry.name.endsWith(".md")) files.push(file);
	}
	return files;
}

function replaceAll(contents: string, from: string, to: string): string {
	return contents.includes(from) ? contents.split(from).join(to) : contents;
}

function isCortexCodeGuide(relativeFile: string): boolean {
	return relativeFile.split(path.sep).join("/").startsWith("skills/cortex-code-guide/");
}

function skillTarget(name: string, skillNames: ReadonlySet<string>): string | undefined {
	return SKILL_TARGETS[name] ?? (skillNames.has(name) ? name : undefined);
}

function skillUri(name: string, skillNames: ReadonlySet<string>): string | undefined {
	const target = skillTarget(name, skillNames);
	return target ? `skill://${target}/SKILL.md` : undefined;
}

function delimiterDelta(line: string, opening: string, closing: string): number {
	let delta = 0;
	let quote: string | undefined;
	let escaped = false;
	for (const character of line) {
		if (escaped) {
			escaped = false;
			continue;
		}
		if (character === "\\" && quote) {
			escaped = true;
			continue;
		}
		if (quote) {
			if (character === quote) quote = undefined;
			continue;
		}
		if (character === '"' || character === "'") {
			quote = character;
			continue;
		}
		if (character === opening) delta++;
		else if (character === closing) delta--;
	}
	return delta;
}

function adaptImplicitAskPayloads(contents: string): string {
	const lines = contents.split("\n");
	const output: string[] = [];
	for (let index = 0; index < lines.length; index++) {
		const prompt = lines[index];
		if (!/^\s*ASK the user:\s*$/.test(prompt)) {
			output.push(prompt);
			continue;
		}
		let start = index + 1;
		while (start < lines.length && !lines[start].trim()) start++;
		if (lines[start]?.trim() !== "{") {
			output.push(prompt);
			continue;
		}
		let depth = 0;
		let end = start;
		for (; end < lines.length; end++) {
			depth += delimiterDelta(lines[end], "{", "}");
			if (depth === 0) break;
		}
		const payload = lines.slice(start + 1, end);
		const questions = payload.findIndex(line => /^\s*["']questions["']\s*:\s*\[\s*$/.test(line));
		let arrayDepth = 0;
		let arrayEnd = -1;
		for (let payloadIndex = questions; payloadIndex >= 0 && payloadIndex < payload.length; payloadIndex++) {
			arrayDepth += delimiterDelta(payload[payloadIndex], "[", "]");
			if (arrayDepth === 0) {
				arrayEnd = payloadIndex;
				break;
			}
		}
		const hasOtherFields =
			questions < 0 ||
			arrayEnd < 0 ||
			payload.slice(0, questions).some(line => line.trim()) ||
			payload.slice(arrayEnd + 1).some(line => line.trim());
		if (depth !== 0 || hasOtherFields) {
			output.push(prompt);
			continue;
		}
		const indent = lines[start].match(/^\s*/)?.[0] ?? "";
		const questionIndent = payload[questions].match(/^\s*/)?.[0] ?? `${indent}  `;
		output.push(`${indent}Use OMP \`ask\`:`, "", `${indent}ask(`, `${indent}  i="Collecting user decision",`);
		output.push(`${questionIndent}questions=[`);
		const questionLines = payload.slice(questions + 1, arrayEnd + 1);
		questionLines[questionLines.length - 1] = questionLines.at(-1)!.replace(/],\s*$/, "]");
		output.push(...questionLines, `${indent})`);
		index = end;
	}
	return output.join("\n");
}

interface AskCall {
	start: number;
	open: number;
	end: number;
	name: string;
	indent: string;
}

function closingParenthesis(contents: string, open: number): number | undefined {
	let depth = 0;
	let quote: string | undefined;
	let escaped = false;
	for (let index = open; index < contents.length; index++) {
		const character = contents[index];
		if (escaped) {
			escaped = false;
			continue;
		}
		if (character === "\\" && quote) {
			escaped = true;
			continue;
		}
		if (quote) {
			if (character === quote) quote = undefined;
			continue;
		}
		if (character === '"' || character === "'" || character === "\`") {
			quote = character;
			continue;
		}
		if (character === "(") depth++;
		else if (character === ")" && --depth === 0) return index;
	}
	return undefined;
}

function askCalls(contents: string): AskCall[] {
	const calls: AskCall[] = [];
	const pattern = /^([ \t]*(?:[A-Za-z_][\w]*[ \t]*=[ \t]*)?)(AskUserQuestion|ask_user_question|ask_question|ask)[ \t]*\(/gm;
	for (const match of contents.matchAll(pattern)) {
		const open = (match.index ?? 0) + match[0].length - 1;
		const end = closingParenthesis(contents, open);
		if (end === undefined) continue;
		calls.push({
			start: (match.index ?? 0) + match[1].length,
			open,
			end,
			name: match[2],
			indent: match[0].match(/^[ \t]*/)?.[0] ?? "",
		});
	}
	return calls;
}

function hasQuestionsField(body: string): boolean {
	return /(?:^|[\s,{])(?:["']questions["']|questions)\s*[:=]/m.test(body);
}

interface ObjectSpan {
	start: number;
	end: number;
}

function objectSpans(contents: string): ObjectSpan[] {
	const spans: ObjectSpan[] = [];
	const starts: number[] = [];
	let quote: string | undefined;
	let escaped = false;
	for (let index = 0; index < contents.length; index++) {
		const character = contents[index];
		if (escaped) {
			escaped = false;
			continue;
		}
		if (character === "\\" && quote) {
			escaped = true;
			continue;
		}
		if (quote) {
			if (character === quote) quote = undefined;
			continue;
		}
		if (character === '"' || character === "'") {
			quote = character;
			continue;
		}
		if (character === "{") starts.push(index);
		else if (character === "}" && starts.length > 0) spans.push({ start: starts.pop()!, end: index });
	}
	return spans;
}

function propertyMatches(contents: string, property: string): RegExpMatchArray[] {
	const pattern = new RegExp(`(?:^|[{,])([\\t \\r\\n]*)["']${property}["']\\s*:`, "gm");
	return [...contents.matchAll(pattern)];
}

function normalizeQuestionIds(body: string): string {
	const spans = objectSpans(body);
	const questionObjects = new Map<number, { span: ObjectSpan; key: number }>();
	for (const match of propertyMatches(body, "question")) {
		const key = (match.index ?? 0) + match[0].search(/["']question["']/);
		const span = spans
			.filter(candidate => candidate.start < key && candidate.end > key)
			.sort((a, b) => a.end - a.start - (b.end - b.start))[0];
		if (span) questionObjects.set(span.start, { span, key });
	}
	const questions = [...questionObjects.values()].sort((a, b) => a.span.start - b.span.start);
	const usedIds = new Set(
		[...body.matchAll(/(?:^|[{,])\s*["']id["']\s*:\s*["']([^"']+)["']/gm)].map(match => match[1]),
	);
	const inserts: Array<{ at: number; text: string }> = [];
	let generated = 0;
	for (const question of questions) {
		const object = body.slice(question.span.start, question.span.end + 1);
		if (/(?:^|[{,])\s*["']id["']\s*:/m.test(object)) continue;
		let id = questions.length === 1 ? "selection" : `selection_${++generated}`;
		while (usedIds.has(id)) id = `selection_${++generated}`;
		usedIds.add(id);
		const lineStart = body.lastIndexOf("\n", question.key) + 1;
		const beforeKey = body.slice(lineStart, question.key);
		const text = beforeKey.trim() ? `"id": "${id}", ` : `"id": "${id}",\n${beforeKey}`;
		inserts.push({ at: question.key, text });
	}
	let normalized = body;
	for (const insert of inserts.sort((a, b) => b.at - a.at)) {
		normalized = normalized.slice(0, insert.at) + insert.text + normalized.slice(insert.at);
	}
	return normalized;
}

function normalizeAskBody(rawBody: string, indent: string): string {
	let body = rawBody.replace(/(["'])multiSelect\1\s*:/g, '"multi":');
	body = body.replace(/^(\s*)["']questions["']\s*:/m, "$1questions=");
	body = normalizeQuestionIds(body);
	if (/^\s*i\s*=/m.test(body)) return body;
	const multiline = body.match(/^([ \t]*\n)([ \t]*)/);
	if (multiline) {
		return `${multiline[1]}${multiline[2]}i="Collecting user decision",\n${body.slice(multiline[1].length)}`;
	}
	return `\n${indent}  i="Collecting user decision",\n${indent}  ${body.trim()}\n${indent}`;
}

function adaptAsk(contents: string): string {
	let adapted = contents.replace(
		/(^[ \t]*(?:[A-Za-z_][\w]*[ \t]*=[ \t]*)?(?:task|BatchInferenceTask)\(\s*\n)[ \t]*i="Collecting user decision",\s*\n/gm,
		"$1",
	);
	adapted = adaptImplicitAskPayloads(adapted).replace(/\bmultiSelect\b/g, "multi");
	const calls = askCalls(adapted);
	for (const call of calls.reverse()) {
		const rawBody = adapted.slice(call.open + 1, call.end);
		const body = hasQuestionsField(rawBody) ? normalizeAskBody(rawBody, call.indent) : rawBody;
		adapted = adapted.slice(0, call.start) + `ask(${body})` + adapted.slice(call.end + 1);
	}
	return adapted.replace(/\b(?:AskUserQuestion|ask_user_question|ask_question)\b/g, "ask");
}

function adaptSkillCalls(contents: string, relativeFile: string, skillNames: ReadonlySet<string>): string {
	let adapted = contents.replace(
		/skill\s*\(\s*command\s*[:=]\s*(["'])([a-z0-9][a-z0-9_-]*)\1\s*\)/gi,
		(whole, _quote: string, name: string) => {
			const uri = skillUri(name, skillNames);
			return uri ? `read ${uri}` : whole;
		},
	);
	adapted = adapted.replace(/skill\s*\(\s*(["'])([a-z0-9][a-z0-9_-]*)\1\s*\)/gi, (whole, _quote: string, name: string) => {
		const uri = skillUri(name, skillNames);
		return uri ? `read ${uri}` : whole;
	});
	adapted = adapted.replace(
		/\b(skill:\/\/[a-z0-9][a-z0-9_-]*(?:\/[a-z0-9._-]+)*\/SKILL\.md):(<[^>\n]+>|[a-z0-9][a-z0-9-]*)/gi,
		"$1 $2",
	);
	const topLevelSkill = relativeFile.split(path.sep)[1];
	if (topLevelSkill) adapted = adapted.replace(/skill\s*\(\s*\)/gi, `read skill://${topLevelSkill}/SKILL.md`);
	return adapted.replace(
		/\$([a-z][a-z0-9_-]*)(?::(<[^>\n]+>|[a-z0-9][a-z0-9-]*))?(?![A-Za-z0-9_-])/g,
		(whole, name: string, argument: string | undefined) => {
			const uri = skillUri(name, skillNames);
			return uri ? (argument ? `${uri} ${argument}` : uri) : whole;
		},
	);
}

function adaptAliases(contents: string, relativeFile: string, skillNames: ReadonlySet<string>): string {
	if (isCortexCodeGuide(relativeFile)) return contents;
	let adapted = adaptAsk(contents);
	adapted = adaptSkillCalls(adapted, relativeFile, skillNames);
	adapted = adapted.replace(/\bWebFetch\b/g, "read");
	adapted = adapted.replace(/\bweb_fetch\b/g, "read");
	return adapted;
}

function adaptKnownReferences(contents: string, relativeFile: string): string {
	let adapted = contents;
	for (const [from, to] of GLOBAL_REWRITES) adapted = replaceAll(adapted, from, to);
	for (const [from, to] of FILE_REWRITES[relativeFile] ?? []) adapted = replaceAll(adapted, from, to);
	return adapted;
}

function isLocalMarkdownTarget(target: string): boolean {
	if (/^(?:[a-z][a-z0-9+.-]*:|#|\/)/i.test(target)) return false;
	const pathname = target.split("#", 1)[0]!.split("?", 1)[0]!;
	return pathname.toLowerCase().endsWith(".md") && !pathname.includes("<") && !pathname.includes("{");
}

async function deLinkMissingReferences(contents: string, file: string): Promise<string> {
	const pattern = /(?<!!)\[([^\]]+)\]\(([^)\s]+)(?:\s+["'][^)]*["'])?\)/g;
	let result = "";
	let offset = 0;
	for (const match of contents.matchAll(pattern)) {
		const index = match.index ?? 0;
		const [whole, label, target] = match;
		if (!isLocalMarkdownTarget(target)) continue;
		const relativeTarget = decodeURIComponent(target.split("#", 1)[0]!.split("?", 1)[0]!);
		if (await exists(path.resolve(path.dirname(file), relativeTarget))) continue;
		result += contents.slice(offset, index);
		result += `${label} *(reference not included in this pack)*`;
		offset = index + whole.length;
	}
	return offset === 0 ? contents : result + contents.slice(offset);
}

function hasCortexCliCommand(contents: string): boolean {
	for (const match of contents.matchAll(CORTEX_CLI_COMMAND)) {
		if (CORTEX_CLI_SUBCOMMANDS.has(match[1])) return true;
	}
	return false;
}

function externalCapabilities(contents: string): string[] {
	const found = new Set<string>();
	for (const token of contents.matchAll(/\b[a-z][a-z0-9_]*\b/g)) {
		if (EXTERNAL_CAPABILITIES.has(token[0])) found.add(token[0]);
	}
	if (hasCortexCliCommand(contents)) found.add("cortex CLI");
	if (/\bsnowflake\.connector\b/.test(contents)) found.add("snowflake.connector");
	return [...found].sort();
}

function compatibilityBlock(contents: string, relativeFile: string): string | undefined {
	if (isCortexCodeGuide(relativeFile)) return undefined;
	const notes: string[] = [];
	if (askCalls(contents).some(call => hasQuestionsField(contents.slice(call.open + 1, call.end)))) {
		notes.push(
			"- Choices use OMP's \`ask\` tool. At approval gates, only an explicit user response grants approval; timeout, cancellation, or an automatic/default selection does not.",
		);
	}
	const capabilities = externalCapabilities(contents);
	if (capabilities.length > 0) {
		notes.push(
			`- Selected paths may require external capabilities not built into OMP: ${capabilities.map(name => `\`${name}\``).join(", ")}. Before using one, verify a configured tool providing that capability is available and authenticated. If the selected path requires an unavailable capability, stop and report \`blocked: missing <capability>\`; never substitute an unrelated shell command or claim execution.`,
		);
	}
	if (notes.length === 0) return undefined;
	return `${MARKER_START}\n> **OMP compatibility**\n>\n${notes.map(note => `> ${note}`).join("\n")}\n${MARKER_END}`;
}

function stripCompatibilityBlock(contents: string): string {
	return contents.replace(COMPATIBILITY_BLOCK, "\n");
}

function insertCompatibilityBlock(contents: string, block: string | undefined): string {
	if (!block) return contents;
	let split = 0;
	if (contents.startsWith("---\n")) {
		const closing = contents.indexOf("\n---\n", 4);
		if (closing >= 0) split = closing + 5;
	}
	const head = contents.slice(0, split).replace(/\n+$/, "");
	const tail = contents.slice(split).replace(/^\n+/, "");
	return head ? `${head}\n\n${block}\n\n${tail}` : `${block}\n\n${tail}`;
}

function hasPositiveLine(contents: string, pattern: RegExp): boolean {
	const lines = contents.split("\n");
	for (let index = 0; index < lines.length; index++) {
		if (!pattern.test(lines[index])) continue;
		const context = `${lines[index - 1] ?? ""} ${lines[index]}`;
		if (/\b(?:do not|don't|never|no separate|unsupported|instead of|not supported|not a registered|were? replaced)\b/i.test(context)) continue;
		return true;
	}
	return false;
}

function lintContents(contents: string, relativeFile: string, skillNames: ReadonlySet<string>): string[] {
	const errors: string[] = [];
	const cocoReference = isCortexCodeGuide(relativeFile);
	if (!cocoReference && /\b(?:AskUserQuestion|ask_user_question|ask_question)\b/.test(contents)) {
		errors.push(`${relativeFile}: unsupported user-question tool name`);
	}
	if (!cocoReference && /\bmultiSelect\b/.test(contents)) {
		errors.push(`${relativeFile}: unsupported ask multiSelect field`);
	}
	if (
		!cocoReference &&
		/\bASK the user:\s*(?:\n\s*)?\{[\s\S]{0,2000}?["']questions["']\s*:/.test(contents)
	) {
		errors.push(`${relativeFile}: implicit question payload was not adapted`);
	}
	if (!cocoReference && /^\s*\{\s*\n\s*["']questions["']\s*:\s*\[/m.test(contents)) {
		errors.push(`${relativeFile}: bare questions payload is not wrapped in ask(...)`);
	}
	if (
		!cocoReference &&
		/(?:final tool call of (?:this|the) turn MUST be|(?:end|stop|finish)(?:\s+\w+){0,3}\s+turn with|turn (?:must )?ends? with)\s+\`?ask\`?|\`?ask\`?(?: call)? is a hard turn boundary/i.test(
			contents,
		)
	) {
		errors.push(`${relativeFile}: OMP ask returns in the same turn; it is not a turn boundary`);
	}

	const calls = cocoReference ? [] : askCalls(contents);
	for (const call of calls) {
		const body = contents.slice(call.open + 1, call.end);
		if (!hasQuestionsField(body)) {
			errors.push(`${relativeFile}: ask call does not use OMP's questions schema`);
			continue;
		}
		const questions = propertyMatches(body, "question").length;
		const ids = [...body.matchAll(/(?:^|[{,])\s*["']id["']\s*:\s*["']([^"']+)["']/gm)].map(id => id[1]);
		if (questions === 0 || questions !== ids.length || new Set(ids).size !== ids.length) {
			errors.push(`${relativeFile}: every ask question needs a unique id`);
		}
		if (!/^\s*i\s*=/m.test(body)) errors.push(`${relativeFile}: ask call has no intent`);
		if (/(?:^|[{,])\s*["'](?:defaultValue|type)["']\s*:/m.test(body)) {
			errors.push(`${relativeFile}: unsupported ask type/defaultValue field`);
		}
		if (/(?:^|[{,])\s*["']options["']\s*:\s*\[\s*["']/m.test(body)) {
			errors.push(`${relativeFile}: ask options must be objects with labels`);
		}
		if (/["']label["']\s*:\s*["'](?:Other(?: \(type your own\))?|Something else)["']/i.test(body)) {
			errors.push(`${relativeFile}: ask must not supply OMP's automatic Other option`);
		}
		if (/["']label["']\s*:\s*["'][^"'\n]*\(recommended\)/i.test(body)) {
			errors.push(`${relativeFile}: ask recommendation belongs in the recommended index`);
		}
	}
	if (!cocoReference && /\bskill\s*\(\s*command\s*[:=]/i.test(contents)) {
		errors.push(`${relativeFile}: unsupported skill(command=...) invocation`);
	}
	if (
		!cocoReference &&
		hasPositiveLine(contents, /\bskill\s*\(\s*["'][a-z0-9][a-z0-9_-]*["']\s*\)/i)
	) {
		errors.push(`${relativeFile}: unsupported positional skill invocation`);
	}
	if (
		!cocoReference &&
		hasPositiveLine(
			contents,
			/(?:\b(?:use|using|invoke|call|load|run|via)\s+(?:the\s+)?[\`']?skill[\`']?\s+(?:tool|call|command)\b|\bthe\s+[\`']skill[\`']\s+(?:tool|call|command)\b)/i,
		)
	) {
		errors.push(`${relativeFile}: unsupported skill-tool prose`);
	}
	if (!cocoReference) {
		const frontmatterEnd = contents.startsWith("---\n") ? contents.indexOf("\n---\n", 4) : -1;
		const metadata = frontmatterEnd >= 0 ? contents.slice(4, frontmatterEnd) : "";
		if (/^\s*-\s*skill\s*$/m.test(metadata) || /^tools:\s*[^\n]*\bskill\b/m.test(metadata)) {
			errors.push(`${relativeFile}: unsupported skill tool in frontmatter`);
		}
		for (const match of contents.matchAll(/\$([a-z][a-z0-9_-]*)\b/g)) {
			if (skillTarget(match[1], skillNames)) {
				errors.push(`${relativeFile}: Cortex Code $skill routing was not converted to skill://`);
				break;
			}
		}
	}
	if (!cocoReference && /\b(?:WebFetch|web_fetch)\b/.test(contents)) {
		errors.push(`${relativeFile}: unsupported web-fetch tool name`);
	}
	if (!cocoReference && /\bsystem_todo_write\b/.test(contents)) {
		errors.push(`${relativeFile}: unsupported todo tool name`);
	}
	if (!cocoReference && /\bsubagent_type\b/.test(contents)) {
		errors.push(`${relativeFile}: unsupported task subagent_type field`);
	}
	for (const [index, [, expected]] of (FILE_REWRITES[relativeFile] ?? []).entries()) {
		if (!contents.includes(expected)) errors.push(`${relativeFile}: compatibility rewrite ${index + 1} did not match`);
	}
	const hasAsk = calls.some(call => hasQuestionsField(contents.slice(call.open + 1, call.end)));
	if (!cocoReference && hasAsk && !contents.includes(MARKER_START)) {
		errors.push(`${relativeFile}: missing OMP ask approval invariant`);
	}
	if (!cocoReference && externalCapabilities(contents).length > 0 && !contents.includes(MARKER_START)) {
		errors.push(`${relativeFile}: missing external-capability gate`);
	}
	return errors;
}

interface CompatibilityInputs {
	files: string[];
	skillNames: Set<string>;
}

async function compatibilityInputs(packDir: string): Promise<CompatibilityInputs> {
	const skillsDir = path.join(packDir, "skills");
	const skillNames = new Set<string>();
	for (const entry of await readdir(skillsDir, { withFileTypes: true })) {
		if (!entry.isDirectory() && !entry.isSymbolicLink()) continue;
		const skillFile = path.join(skillsDir, entry.name, "SKILL.md");
		if (!(await exists(skillFile))) continue;
		skillNames.add(entry.name);
		const declared = (await readFile(skillFile, "utf8")).match(/^name:\s*["']?([a-z0-9][a-z0-9_-]*)/im)?.[1];
		if (declared) skillNames.add(declared);
	}
	return {
		files: [
			...(await markdownFiles(skillsDir)),
			...(await markdownFiles(path.join(packDir, "commands"))),
		].sort(),
		skillNames,
	};
}

async function adaptedContents(
	packDir: string,
	file: string,
	skillNames: ReadonlySet<string>,
): Promise<string> {
	const relativeFile = path.relative(packDir, file);
	let contents = stripCompatibilityBlock(await readFile(file, "utf8"));
	contents = adaptAliases(contents, relativeFile, skillNames);
	contents = adaptKnownReferences(contents, relativeFile);
	contents = await deLinkMissingReferences(contents, file);
	return insertCompatibilityBlock(contents, compatibilityBlock(contents, relativeFile));
}

export async function planCompatibility(packDir: string): Promise<CompatibilityPlan> {
	const { files, skillNames } = await compatibilityInputs(packDir);
	const changed: string[] = [];
	const errors: string[] = [];
	for (const file of files) {
		const relativeFile = path.relative(packDir, file);
		const current = await readFile(file, "utf8");
		const adapted = await adaptedContents(packDir, file, skillNames);
		if (current !== adapted) changed.push(relativeFile);
		errors.push(...lintContents(adapted, relativeFile, skillNames));
	}
	return { changed, errors };
}

export async function adaptCompatibility(packDir: string): Promise<CompatibilityPlan> {
	const { files, skillNames } = await compatibilityInputs(packDir);
	const changed: string[] = [];
	const errors: string[] = [];
	for (const file of files) {
		const relativeFile = path.relative(packDir, file);
		const current = await readFile(file, "utf8");
		const adapted = await adaptedContents(packDir, file, skillNames);
		if (current !== adapted) {
			await writeFile(file, adapted);
			changed.push(relativeFile);
		}
		errors.push(...lintContents(adapted, relativeFile, skillNames));
	}
	return { changed, errors };
}

export async function lintCompatibility(packDir: string): Promise<string[]> {
	const plan = await planCompatibility(packDir);
	return [
		...plan.changed.map(file => `${file}: OMP compatibility output is stale`),
		...plan.errors,
	];
}

if (import.meta.main) {
	const write = process.argv.includes("--write");
	const packDirs = process.argv.slice(2).filter(argument => argument !== "--write");
	if (packDirs.length === 0) {
		console.error("usage: bun scripts/compatibility.ts [--write] <pack-dir>...");
		process.exit(2);
	}
	let failed = false;
	for (const argument of packDirs) {
		const packDir = path.resolve(argument);
		const result = write ? await adaptCompatibility(packDir) : await planCompatibility(packDir);
		for (const file of result.changed) console.log(`${write ? "adapted" : "stale"}: ${path.join(argument, file)}`);
		for (const error of result.errors) console.error(error);
		if (result.errors.length > 0 || (!write && result.changed.length > 0)) failed = true;
	}
	if (failed) process.exit(1);
}
