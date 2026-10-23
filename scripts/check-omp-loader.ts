#!/usr/bin/env bun
/**
 * Local smoke test: validate every pack with OMP's extension-package loaders from an explicit oh-my-pi checkout.
 *
 * Usage: OMP_ROOT=/path/to/oh-my-pi bun scripts/check-omp-loader.ts
 *
 * The check runs the omp-plugins provider in explicit-only mode for skills, commands,
 * rules, and tools; parses task agents with OMP's fatal agent parser; and imports/binds every
 * declared extension. Repository expectations must match the host by name and file with no warnings.

 */

import * as fs from "node:fs/promises";
import * as path from "node:path";
import { check } from "./sync";

const ROOT = path.resolve(import.meta.dir, "..");
const ompRootInput = process.env.OMP_ROOT ?? process.argv[2];
if (!ompRootInput) {
	console.error("OMP_ROOT is required (env var or first argument): path to an oh-my-pi checkout");
	process.exit(2);
}
const OMP_ROOT = path.resolve(ompRootInput);
const AGENT_SRC = path.join(OMP_ROOT, "packages/coding-agent/src");

// Refuse any checkout that is not the reviewed commit before a single host module is loaded.
const lock: unknown = await Bun.file(path.join(ROOT, "omp-source-lock.json")).json();
const expectedCommit = lock && typeof lock === "object" && "reviewedCommit" in lock ? lock.reviewedCommit : undefined;
if (typeof expectedCommit !== "string" || !/^[0-9a-f]{40}$/.test(expectedCommit)) {
	console.error("omp-source-lock.json reviewedCommit must be a full 40-character SHA");
	process.exit(2);
}
function git(...args: string[]): string | undefined {
	const result = Bun.spawnSync(["git", "-C", OMP_ROOT, ...args], { stdout: "pipe", stderr: "pipe" });
	return result.exitCode === 0 ? result.stdout.toString().trim() : undefined;
}
const toplevel = git("rev-parse", "--show-toplevel");
if (!toplevel || (await fs.realpath(toplevel)) !== (await fs.realpath(OMP_ROOT).catch(() => OMP_ROOT))) {
	console.error("OMP_ROOT is not the root of a Git checkout: " + OMP_ROOT);
	process.exit(2);
}
const actualCommit = git("rev-parse", "HEAD");
if (actualCommit !== expectedCommit) {
	console.error("OMP_ROOT is not at the reviewed commit; refusing to load host modules from " + OMP_ROOT);
	console.error("  expected: " + expectedCommit);
	console.error("  actual:   " + (actualCommit ?? "unreadable"));
	process.exit(1);
}

interface LoadedItem {
	name: string;
	path: string;
	/** Present on rules: OMP's normalized regex condition strings. */
	condition?: string[];
}

interface CapabilityLoadResult<T> {
	items: T[];
	warnings: string[];
}
interface SlashCommandTemplate {
	name: string;
	description: string;
	content: string;
	source: string;
}

interface ExtensionRoots {
	explicit: readonly string[];
	mode: "explicit-only";
	configured: readonly string[];
	configuredLevel: "user";
}

// Dynamic imports: OMP_ROOT selects the checkout at runtime, so static specifiers cannot work.
await import(path.join(AGENT_SRC, "discovery/omp-plugins.ts"));
const capability = (await import(path.join(AGENT_SRC, "capability/index.ts"))) as {
	loadCapability<T>(
		id: string,
		options: { cwd: string; providers: string[]; extensionRoots: ExtensionRoots },
	): Promise<CapabilityLoadResult<T>>;
};
const taskAgents = (await import(path.join(AGENT_SRC, "task/agents.ts"))) as {
	parseAgent(filePath: string, content: string, source: "user", level: "fatal"): { name: string };
};
const extensionLoader = (await import(path.join(AGENT_SRC, "extensibility/extensions/loader.ts"))) as {
	loadExtensions(
		paths: string[],
		cwd: string,
	): Promise<{ extensions: unknown[]; errors: Array<{ path: string; error: string }> }>;
};
const customToolLoader = await import(path.join(AGENT_SRC, "extensibility/custom-tools/loader.ts"));
const ruleRuntime = await import(path.join(AGENT_SRC, "export/ttsr.ts"));
const slashCommands = (await import(path.join(AGENT_SRC, "extensibility/slash-commands.ts"))) as {
	expandSlashCommand(text: string, fileCommands: SlashCommandTemplate[]): string;
};
const utils = (await import(path.join(OMP_ROOT, "packages/utils/src/frontmatter.ts"))) as {
	parseFrontmatter(
		content: string,
		options?: { source?: unknown; level?: "off" | "warn" | "fatal" },
	): { frontmatter: Record<string, unknown>; body: string };
};
const ruleCapability = (await import(path.join(AGENT_SRC, "capability/rule.ts"))) as {
	compileRuleCondition(pattern: string): RegExp;
};

const sources = await Bun.file(path.join(ROOT, "sources.json")).json();
const repositoryErrors: string[] = [];
const packs = await check(sources, repositoryErrors);
const problems = repositoryErrors.map((error) => "repository check: " + error);
const packRoots = packs.map((pack) => path.join(ROOT, pack.dir));
const extensionRoots: ExtensionRoots = {
	explicit: packRoots,
	mode: "explicit-only",
	configured: [],
	configuredLevel: "user",
};

const surfaces = [
	{
		id: "skills",
		label: "skills",
		select: (pack: (typeof packs)[number]) => pack.skills,
		strictFrontmatter: true,
	},
	{
		id: "slash-commands",
		label: "commands",
		select: (pack: (typeof packs)[number]) => pack.commands,
		strictFrontmatter: false,
	},
	{
		id: "rules",
		label: "rules",
		select: (pack: (typeof packs)[number]) => pack.rules,
		strictFrontmatter: false,
	},
	{
		id: "tools",
		label: "tools",
		select: (pack: (typeof packs)[number]) => pack.tools,
		strictFrontmatter: false,
	},
] as const;
const totals: string[] = [];

for (const surface of surfaces) {
	const result = await capability.loadCapability<LoadedItem>(surface.id, {
		cwd: ROOT,
		providers: ["omp-plugins"],
		extensionRoots,
	});
	for (const warning of result.warnings) problems.push("OMP " + surface.label + " warning: " + warning);

	if (surface.id === "rules") {
		for (const rule of result.items) {
			for (const [index, condition] of (rule.condition ?? []).entries()) {
				try {
					ruleCapability.compileRuleCondition(condition);
				} catch (error) {
					problems.push("OMP cannot compile rule " + rule.path + " condition[" + index + "]: " + String(error));
				}
			}
		}
	}
	const discovered = new Map(result.items.map((item) => [path.resolve(item.path), item]));
	let expectedCount = 0;
	for (const pack of packs) {
		for (const item of surface.select(pack)) {
			expectedCount++;
			const absolute = path.resolve(ROOT, pack.dir, item.file);
			const found = discovered.get(absolute);
			if (!found) {
				problems.push(pack.name + ": " + item.file + ' expected as "' + item.name + '" but OMP did not discover it');
				continue;
			}
			if (found.name !== item.name) {
				problems.push(
					pack.name + ": " + item.file + ' expected as "' + item.name + '" but OMP named it "' + found.name + '"',
				);
			}
			discovered.delete(absolute);
			if (surface.strictFrontmatter) {
				try {
					utils.parseFrontmatter(await Bun.file(absolute).text(), {
						source: absolute,
						level: "fatal",
					});
				} catch (error) {
					problems.push(
						pack.name + ": " + item.file + " frontmatter only loads via OMP's lenient fallback: " + String(error),
					);
				}
			}
		}
	}
	for (const item of discovered.values()) {
		problems.push("OMP discovered unexpected " + surface.label + ' item "' + item.name + '" at ' + item.path);
	}
	totals.push(expectedCount + " " + (expectedCount === 1 ? surface.label.slice(0, -1) : surface.label));
}
const packsByName = new Map(packs.map((pack) => [pack.name, pack]));
for (const pack of packs) {
	const dependencyNames = Object.keys(pack.skillReferences.requires ?? {});
	const dependencyPacks = dependencyNames.map((name) => packsByName.get(name)!);
	const roots = [pack, ...dependencyPacks].map((item) => path.join(ROOT, item.dir));
	const scopedRoots: ExtensionRoots = {
		explicit: roots,
		mode: "explicit-only",
		configured: [],
		configuredLevel: "user",
	};
	for (const surface of surfaces) {
		const result = await capability.loadCapability<LoadedItem>(surface.id, {
			cwd: ROOT,
			providers: ["omp-plugins"],
			extensionRoots: scopedRoots,
		});
		for (const warning of result.warnings) {
			problems.push("OMP " + pack.name + " dependency-closure " + surface.label + " warning: " + warning);
		}
		const discovered = new Map(result.items.map((item) => [path.resolve(item.path), item]));
		for (const item of surface.select(pack)) {
			const absolute = path.resolve(ROOT, pack.dir, item.file);
			const found = discovered.get(absolute);
			if (!found) {
				problems.push(pack.name + ": " + item.file + " was not discovered from its declared dependency closure");
			} else if (found.name !== item.name) {
				problems.push(
					pack.name + ": " + item.file + ' loaded as "' + found.name + '" from its declared dependency closure',
				);
			}
		}
	}
}

let agentCount = 0;
for (const pack of packs) {
	for (const item of pack.agents) {
		agentCount++;
		const absolute = path.resolve(ROOT, pack.dir, item.file);
		try {
			const parsed = taskAgents.parseAgent(absolute, await Bun.file(absolute).text(), "user", "fatal");
			if (parsed.name !== item.name) {
				problems.push(
					pack.name + ": " + item.file + ' expected as "' + item.name + '" but OMP named it "' + parsed.name + '"',
				);
			}
		} catch (error) {
			problems.push(pack.name + ": OMP rejected agent " + item.file + ": " + String(error));
		}
	}
}
totals.push(agentCount + " " + (agentCount === 1 ? "agent" : "agents"));

// Exercise the actual TTSR matcher with finalized connector arguments, not a local scope approximation.
const loadedRules = await capability.loadCapability<LoadedItem>("rules", {
	cwd: ROOT,
	providers: ["omp-plugins"],
	extensionRoots,
});
const sqlRule = loadedRules.items.find((rule) => rule.name === "sql-mutation-safety");
for (const [toolName, args, expected] of [
	["bash", { command: "snow sql -q 'DROP TABLE orders'" }, true],
	["snowflake_sql_execute", { sql: "DELETE FROM orders WHERE id = 7" }, true],
	["mcp__warehouse__query", { query: "TRUNCATE TABLE orders" }, true],
	["customConnector", { statement: "UPDATE orders SET status = 'closed' WHERE id = 7" }, true],
	["mcp__warehouse__query", { query: "DELETE\nFROM orders WHERE id = 7" }, true],
	["mcp__warehouse__query", { query: "DROP\nTABLE orders" }, true],
	["mcp__warehouse__query", { query: "DELETE\tFROM orders WHERE id = 7" }, true],
	["customConnector", { statement: "UPDATE\norders\nSET status = 'closed' WHERE id = 7" }, true],
	["bash", { command: "alembic\ndowngrade -1" }, true],
	["mcp__warehouse__query", { query: "SELECT\nid FROM orders LIMIT 1" }, false],
] as const) {
	const manager = new ruleRuntime.TtsrManager({ enabled: true });
	if (!sqlRule || !manager.addRule(sqlRule)) {
		problems.push("SQL safety rule could not be registered in OMP");
		break;
	}
	const hit = manager.checkSnapshot(JSON.stringify(args), { source: "tool", toolName });
	if (hit.some((rule: LoadedItem) => rule.name === "sql-mutation-safety") !== expected) {
		problems.push("SQL safety rule mismatch for " + toolName + ": " + JSON.stringify(args));
	}
}

// Expand every shipped command through OMP's own slash-command path: user arguments must arrive as inert data,
// so template-looking text (`{{missing}}`, block helpers, `$1`, HTML) is never evaluated, escaped, or dropped.
const loadedCommands = await capability.loadCapability<LoadedItem & { content: string }>("slash-commands", {
	cwd: ROOT,
	providers: ["omp-plugins"],
	extensionRoots,
});
const inertArguments = "{{missing}} {{#if x}}y{{/if}} {{> p}} <b>&</b> $1";
let expandedCommands = 0;
for (const command of loadedCommands.items) {
	const template: SlashCommandTemplate = {
		name: command.name,
		description: "",
		content: utils.parseFrontmatter(command.content, { source: command.path, level: "warn" }).body,
		source: command.path,
	};
	let expanded: string;
	try {
		expanded = slashCommands.expandSlashCommand("/" + command.name + " " + inertArguments, [template]);
	} catch (error) {
		problems.push("OMP could not expand command /" + command.name + " with template-like arguments: " + String(error));
		continue;
	}
	expandedCommands++;
	if (!expanded.includes(inertArguments)) {
		problems.push("Command /" + command.name + " did not preserve literal arguments: " + JSON.stringify(inertArguments));
	}
}
totals.push(expandedCommands + " command expansions");

const customPaths = packs.flatMap((pack) =>
	pack.tools.map((item) => ({ path: path.resolve(ROOT, pack.dir, item.file) })),
);
const loadedCustom = await customToolLoader.loadCustomTools(customPaths, ROOT, []);
for (const error of loadedCustom.errors) problems.push("OMP custom-tool factory: " + error.path + ": " + error.error);
if (loadedCustom.tools.length !== customPaths.length)
	problems.push("OMP did not instantiate every discovered custom tool");
totals.push(loadedCustom.tools.length + " custom-tool factories; connector SQL and manual-skill runtime cases");

const extensionPaths: string[] = [];
for (const pack of packs) {
	const manifest = await Bun.file(path.join(ROOT, pack.dir, "package.json")).json();
	for (const entry of manifest.omp?.extensions ?? []) {
		extensionPaths.push(path.resolve(ROOT, pack.dir, entry));
	}
}
if (extensionPaths.length > 0) {
	const result = await extensionLoader.loadExtensions(extensionPaths, ROOT);
	for (const error of result.errors) problems.push("OMP rejected extension " + error.path + ": " + error.error);
	if (result.extensions.length !== extensionPaths.length) {
		problems.push("OMP loaded " + result.extensions.length + " of " + extensionPaths.length + " declared extensions");
	}
}
totals.push(extensionPaths.length + " " + (extensionPaths.length === 1 ? "extension" : "extensions"));

if (problems.length > 0) {
	console.error("OMP loader (" + OMP_ROOT + ") disagrees with repository expectations:");
	for (const problem of problems) console.error("  " + problem);
	process.exit(1);
}
console.log(packs.length + " packs; " + totals.join(", ") + ": all match OMP at " + OMP_ROOT + ", no warnings");
