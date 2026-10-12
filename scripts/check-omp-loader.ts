#!/usr/bin/env bun
/**
 * Validate every pack with OMP's real extension-package loaders from an oh-my-pi checkout.
 *
 * Usage: OMP_ROOT=/path/to/oh-my-pi bun scripts/check-omp-loader.ts
 *
 * The check runs the omp-plugins provider in explicit-only mode for skills, commands,
 * rules, and tools; parses task agents with OMP's fatal agent parser; and imports/binds every
 * declared extension. Repository expectations must match OMP by name and file with no warnings.
 */

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

interface LoadedItem {
	name: string;
	path: string;
}

interface CapabilityLoadResult<T> {
	items: T[];
	warnings: string[];
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
	parseAgent(
		filePath: string,
		content: string,
		source: "user",
		level: "fatal",
	): { name: string };
};
const extensionLoader = (await import(path.join(AGENT_SRC, "extensibility/extensions/loader.ts"))) as {
	loadExtensions(
		paths: string[],
		cwd: string,
	): Promise<{ extensions: unknown[]; errors: Array<{ path: string; error: string }> }>;
};
const utils = (await import(path.join(OMP_ROOT, "packages/utils/src/frontmatter.ts"))) as {
	parseFrontmatter(content: string, options?: { source?: unknown; level?: "off" | "warn" | "fatal" }): unknown;
};

const sources = await Bun.file(path.join(ROOT, "sources.json")).json();
const repositoryErrors: string[] = [];
const packs = await check(sources, repositoryErrors);
const problems = repositoryErrors.map(error => "repository check: " + error);
const packRoots = packs.map(pack => path.join(ROOT, pack.dir));
const extensionRoots: ExtensionRoots = {
	explicit: packRoots,
	mode: "explicit-only",
	configured: [],
	configuredLevel: "user",
};

const surfaces = [
	{ id: "skills", label: "skills", select: (pack: (typeof packs)[number]) => pack.skills, strictFrontmatter: true },
	{ id: "slash-commands", label: "commands", select: (pack: (typeof packs)[number]) => pack.commands, strictFrontmatter: false },
	{ id: "rules", label: "rules", select: (pack: (typeof packs)[number]) => pack.rules, strictFrontmatter: false },
	{ id: "tools", label: "tools", select: (pack: (typeof packs)[number]) => pack.tools, strictFrontmatter: false },
] as const;
const totals: string[] = [];

for (const surface of surfaces) {
	const result = await capability.loadCapability<LoadedItem>(surface.id, {
		cwd: ROOT,
		providers: ["omp-plugins"],
		extensionRoots,
	});
	for (const warning of result.warnings) problems.push("OMP " + surface.label + " warning: " + warning);

	const discovered = new Map(result.items.map(item => [path.resolve(item.path), item]));
	let expectedCount = 0;
	for (const pack of packs) {
		for (const item of surface.select(pack)) {
			expectedCount++;
			const absolute = path.resolve(ROOT, pack.dir, item.file);
			const found = discovered.get(absolute);
			if (!found) {
				problems.push(pack.name + ": " + item.file + " expected as \"" + item.name + "\" but OMP did not discover it");
				continue;
			}
			if (found.name !== item.name) {
				problems.push(
					pack.name + ": " + item.file + " expected as \"" + item.name + "\" but OMP named it \"" + found.name + "\"",
				);
			}
			discovered.delete(absolute);
			if (surface.strictFrontmatter) {
				try {
					utils.parseFrontmatter(await Bun.file(absolute).text(), { source: absolute, level: "fatal" });
				} catch (error) {
					problems.push(pack.name + ": " + item.file + " frontmatter only loads via OMP's lenient fallback: " + String(error));
				}
			}
		}
	}
	for (const item of discovered.values()) {
		problems.push("OMP discovered unexpected " + surface.label + " item \"" + item.name + "\" at " + item.path);
	}
	totals.push(expectedCount + " " + (expectedCount === 1 ? surface.label.slice(0, -1) : surface.label));
}
const packsByName = new Map(packs.map(pack => [pack.name, pack]));
for (const pack of packs) {
	const dependencyNames = Object.keys(pack.skillReferences.requires ?? {});
	const dependencyPacks = dependencyNames.map(name => packsByName.get(name)!);
	const roots = [pack, ...dependencyPacks].map(item => path.join(ROOT, item.dir));
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
		const discovered = new Map(result.items.map(item => [path.resolve(item.path), item]));
		for (const item of surface.select(pack)) {
			const absolute = path.resolve(ROOT, pack.dir, item.file);
			const found = discovered.get(absolute);
			if (!found) {
				problems.push(pack.name + ": " + item.file + " was not discovered from its declared dependency closure");
			} else if (found.name !== item.name) {
				problems.push(pack.name + ": " + item.file + " loaded as \"" + found.name + "\" from its declared dependency closure");
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
				problems.push(pack.name + ": " + item.file + " expected as \"" + item.name + "\" but OMP named it \"" + parsed.name + "\"");
			}
		} catch (error) {
			problems.push(pack.name + ": OMP rejected agent " + item.file + ": " + String(error));
		}
	}
}
totals.push(agentCount + " " + (agentCount === 1 ? "agent" : "agents"));

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
