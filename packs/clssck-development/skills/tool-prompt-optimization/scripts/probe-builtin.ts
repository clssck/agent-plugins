#!/usr/bin/env bun
/**
 * OPTIONAL OMP-host adapter for the schema -> prompt inference probe.
 *
 * Runs only inside an OMP checkout (or install) whose packages resolve from the current
 * working directory. Instead of hand-writing a tool's JSON schema + outline, point it at a
 * live host tool name. It resolves the tool (direct constructor for the availability-gated
 * `github` tool, else the BUILTIN_TOOLS/HIDDEN_TOOLS factory map), pulls the EXACT wire
 * schema the model sees (`toolWireSchema`) and the rendered description (`tool.description`),
 * derives an outline (first-line summary, section headers/tags, bodies collapsed to `...`),
 * then runs the generic `probe()`.
 * Outside OMP, use probe.ts with a hand-supplied schema and template.
 *
 * Usage:
 *   bun probe-builtin.ts --tool <name> [--no-summary] [--show]
 *     --tool <name>      host tool name (e.g. read). Required.
 *     --no-summary       ablation: also drop the first-line summary (section names remain).
 *     --show             print resolved schema + outline + real prompt and exit. Offline:
 *                        needs no model selection and makes no model calls.
 *     --model <provider/id> / --samples <n> / --max-tokens <n> / --json
 *                        shared with probe.ts; --model (or CLSSCK_PROBE_MODELS) is required
 *                        unless --show is set.
 *     --help             print usage and exit 0
 *   Invalid arguments print the error + usage and exit 2 before any tool is resolved.
 */
import type * as PiAi from "@oh-my-pi/pi-ai";
import type * as OmpSettings from "@oh-my-pi/pi-coding-agent/config/settings";
import type * as OmpTools from "@oh-my-pi/pi-coding-agent/tools";
import type { Tool, ToolFactory, ToolSession } from "@oh-my-pi/pi-coding-agent/tools";
import {
	exitOnUsageError,
	PROBE_FLAGS,
	PROBE_FLAGS_USAGE,
	type ProbeSettings,
	parseCli,
	printRun,
	probe,
	resolveProbeSettings,
	UsageError,
} from "./probe.ts";

interface OmpHost {
	toolWireSchema: typeof PiAi.toolWireSchema;
	Settings: typeof OmpSettings.Settings;
	BUILTIN_TOOLS: typeof OmpTools.BUILTIN_TOOLS;
	HIDDEN_TOOLS: typeof OmpTools.HIDDEN_TOOLS;
	GithubTool: typeof OmpTools.GithubTool;
}

const USAGE = [
	"usage: bun probe-builtin.ts --tool <name> [--no-summary] [--show] [--model <provider/id>] [options]",
	"  --tool <name>           host tool name (required)",
	"  --no-summary            also drop the first-line summary (section names remain)",
	"  --show                  print schema, outline, real prompt; offline, no model needed",
	PROBE_FLAGS_USAGE,
].join("\n");

const OPEN_TAG = /^<[a-z_][\w-]*>$/i;
const CLOSE_TAG = /^<\/[a-z_][\w-]*>$/i;
const MD_HEADER = /^#{1,6}\s/;

/** Keep the first line plus every section header/tag; collapse body runs to `...`. */
function deriveOutline(description: string, dropSummary: boolean): string {
	const lines = description.split("\n");
	const isHeader = (line: string): boolean => {
		const trimmed = line.trim();
		return OPEN_TAG.test(trimmed) || CLOSE_TAG.test(trimmed) || MD_HEADER.test(line);
	};

	let i = 0;
	while (i < lines.length && lines[i].trim() === "") i++;
	const summary: string[] = [];
	if (i < lines.length && !isHeader(lines[i])) {
		summary.push(lines[i]);
		i++;
	}

	const parts: string[] = [];
	if (!dropSummary && summary.length > 0) parts.push(summary.join("\n").trim());
	let pendingBody = false;
	for (; i < lines.length; i++) {
		const line = lines[i];
		const trimmed = line.trim();
		if (OPEN_TAG.test(trimmed) || MD_HEADER.test(line)) {
			parts.push("", line);
			pendingBody = false;
		} else if (CLOSE_TAG.test(trimmed)) {
			parts.push(line);
			pendingBody = false;
		} else if (trimmed !== "" && !pendingBody) {
			parts.push("...");
			pendingBody = true;
		}
	}
	return parts.join("\n").trim();
}

/**
 * Host packages resolve from the working directory (the OMP checkout), so the specifiers
 * are runtime-selected and static imports cannot work. Loaded only after arguments validate.
 */
async function loadHost(): Promise<OmpHost> {
	const ai = (await import(Bun.resolveSync("@oh-my-pi/pi-ai", process.cwd()))) as typeof PiAi;
	const settings = (await import(
		Bun.resolveSync("@oh-my-pi/pi-coding-agent/config/settings", process.cwd())
	)) as typeof OmpSettings;
	const tools = (await import(Bun.resolveSync("@oh-my-pi/pi-coding-agent/tools", process.cwd()))) as typeof OmpTools;
	return {
		toolWireSchema: ai.toolWireSchema,
		Settings: settings.Settings,
		BUILTIN_TOOLS: tools.BUILTIN_TOOLS,
		HIDDEN_TOOLS: tools.HIDDEN_TOOLS,
		GithubTool: tools.GithubTool,
	};
}

async function resolveTool(host: OmpHost, name: string): Promise<Tool> {
	await host.Settings.init({ inMemory: true, cwd: process.cwd() });
	const settings = host.Settings.isolated({});
	// We only read `.parameters` / `.description`, never `execute`. The factory map
	// bypasses the settings allowlist (`isToolAllowed`), and github is constructed directly
	// below to bypass its `gh` availability gate.
	const session = {
		cwd: process.cwd(),
		hasUI: false,
		getSessionFile: () => null,
		getSessionSpawns: () => "*",
		settings,
		taskDepth: 0,
	} as ToolSession;
	// `github` maps to `createIf`, which gates on the gh CLI. Direct construction keeps this
	// metadata-only probe gh-independent. Everything else goes through the factory map.
	const direct: Record<string, (s: ToolSession) => Tool> = {
		github: s => new host.GithubTool(s),
	};
	const key = name.toLowerCase();
	const directCtor = direct[key];
	if (directCtor) return directCtor(session);
	const factories: Record<string, ToolFactory> = { ...host.BUILTIN_TOOLS, ...host.HIDDEN_TOOLS };
	const factory = factories[key];
	if (!factory) {
		const names = Object.keys(factories).sort().join(", ");
		throw new Error(`unknown host tool "${name}". available: ${names}`);
	}
	const tool = await factory(session);
	if (!tool) {
		throw new Error(`tool "${name}" did not construct here — blocked by an availability gate (e.g. ssh, or a memory backend that isn't configured). Fall back to the manual probe.ts --schema/--template path.`);
	}
	return tool;
}

async function main(): Promise<void> {
	let toolName: string;
	let dropSummary: boolean;
	let show: boolean;
	let settings: ProbeSettings | undefined;
	try {
		const values = parseCli(Bun.argv.slice(2), {
			tool: { type: "string" },
			"no-summary": { type: "boolean" },
			show: { type: "boolean" },
			...PROBE_FLAGS,
		});
		if (values.help) {
			console.log(USAGE);
			return;
		}
		if (!values.tool) throw new UsageError("--tool is required");
		toolName = values.tool;
		dropSummary = values["no-summary"] === true;
		show = values.show === true;
		const parsedSettings = resolveProbeSettings(values, process.env, !show);
		settings = show ? undefined : parsedSettings;
	} catch (err) {
		return exitOnUsageError(err, USAGE);
	}

	const host = await loadHost();
	const tool = await resolveTool(host, toolName);
	const schema = host.toolWireSchema(tool);
	const realPrompt = tool.description ?? "";
	const outline = deriveOutline(realPrompt, dropSummary);
	if (!show && (outline === "" || outline === realPrompt.trim())) {
		console.error(
			`error: ${tool.name}: derived outline ${outline === "" ? "is empty" : "equals the real prompt"}; ` +
				"use probe.ts with a hand-written template",
		);
		process.exit(2);
	}

	if (show || !settings) {
		console.log(`# tool: ${tool.name}\n\n## wire schema\n\`\`\`json\n${JSON.stringify(schema, null, 2)}\n\`\`\`\n`);
		console.log(`## derived outline\n${outline}\n`);
		console.log(`## real prompt (${Buffer.byteLength(realPrompt)} bytes)\n${realPrompt}`);
		return;
	}

	const run = await probe({
		schema,
		template: outline,
		name: tool.name,
		models: settings.models,
		samples: settings.samples,
		maxTokens: settings.maxTokens,
	});

	if (settings.json) {
		console.log(JSON.stringify({ ...run, realPrompt }, null, 2));
		return;
	}

	printRun(run);
	console.log(`\n############ REAL PROMPT (${tool.name}) ############\n${realPrompt}`);
}

if (import.meta.main) {
	await main();
}
