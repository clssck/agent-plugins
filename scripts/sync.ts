#!/usr/bin/env bun
// Keeps this repository self-contained. In order:
//   1. pin    – move every upstream in sources.json to the latest commit of its ref
//   2. fetch  – copy each upstream into upstream/<name>/ at its pinned commit
//   3. check  – fail on repository-contract problems in packs/ or upstream/ (static: it does not run OMP;
//               scripts/check-omp-loader.ts loads every pack with OMP's own loaders)
//   4. readme – regenerate README.md (the workflow only; pass --readme to do it locally)
// Run by .github/workflows/sync-upstreams.yml; set GITHUB_TOKEN when running locally.
// `--local` runs only check: no network, no token. A local run leaves README.md to the workflow.

import { YAML } from "bun";
import { cp, mkdir, mkdtemp, open, readdir, rename, rm, stat } from "node:fs/promises";
import * as path from "node:path";
import {
	adaptCompatibility,
	COMPATIBILITY_PROFILE,
	COMPATIBILITY_VERSION,
	lintCompatibility,
	type CompatibilityProfile,
} from "./compatibility";
import { githubGraphql as graphql, githubRepositoryField as repositoryField } from "./github";

interface OmpSkillReferences {
	requires?: Record<string, string[]>;
	optional?: string[];
}
interface Upstream {
	name: string;
	repo: string;
	ref: string;
	sha: string;
	description: string;
	/** Upstream path → pack path, e.g. `{ "skills": "skills" }`. */
	include: Record<string, string>;
	/** Versioned local transformation applied after copying, without modifying the source repository. */
	compatibility?: CompatibilityProfile;
	/** Cross-pack and optional skill:// targets used by this pack. */
	skillReferences?: OmpSkillReferences;
}

interface Sources {
	repository: string;
	description: string;
	upstreams: Upstream[];
}

/** A commit and the GitHub repository that owns it; links are built only from this pair. */
export interface Commit {
	repository: string;
	sha: string;
	date: string;
}

/** Last-updated commits for README rows: this repository's history and upstream histories at their pins. */
export interface ReadmeCommits {
	/** Repository path under packs/ or upstream/ → newest local commit touching it. */
	local: Map<string, Commit>;
	/** `<pack>/<skill dir>` → newest upstream commit touching that skill at the pin. */
	upstream: Map<string, Commit>;
}

interface Item {
	name: string;
	/** Path of the file relative to the pack root. */
	file: string;
}

interface Pack {
	name: string;
	/** Directory relative to the repository root, e.g. `packs/clssck-core`. */
	dir: string;
	/** The pack's `package.json` version. */
	version: string;
	/** GitHub owner/repository parsed from package.json repository. */
	repository?: string;
	upstream?: Upstream;
	/** Upstream packs: pack path → upstream path of each copied entry, as recorded by fetch. */
	origins?: Record<string, string>;
	/** A pack under packs/ that ships an ATTRIBUTION file: vendored here rather than written here. */
	attribution: boolean;
	/** Declared cross-pack and optional skill:// targets. */
	skillReferences: OmpSkillReferences;
	skills: Item[];
	rules: Item[];
	agents: Item[];
	commands: Item[];
	tools: Item[];
	extensions: number;
}

/** What fetch records in each generated upstream package.json. */
interface SyncRecord {
	/** buildId() of the inputs the pack was built from. */
	build: string;
	/** Pack path → upstream path of every copied top-level entry. */
	origins: Record<string, string>;
	compatibility?: { profile: CompatibilityProfile; version: number };
	/** generatedTreeDigest() of the finished pack; the one value the digest itself excludes. */
	tree?: string;
}

const ROOT = path.resolve(import.meta.dir, "..");
const SOURCES_PATH = path.join(ROOT, "sources.json");
const README_PATH = path.join(ROOT, "README.md");
const UPSTREAM_DIR = path.join(ROOT, "upstream");
const SKIPPED_NAMES: Record<string, true> = { ".DS_Store": true, ".git": true, __pycache__: true };
const LICENSE_FILE = /^(licen[cs]e|copying|notice)(\.|$)/i;
/** Prefix of fetch's staging directories inside upstream/; leftovers from an interrupted run are removed. */
const STAGING_PREFIX = ".sync-";
/** Bump whenever buildUpstream's output changes for an unchanged sources.json entry, so every pack is rebuilt. */
const BUILD_FORMAT = 8;
/** Generated packs contain source and prompt assets, never individual files larger than this. */
const MAX_GENERATED_FILE_BYTES = 16 * 1024 * 1024;

async function readJson<T>(file: string): Promise<T | undefined> {
	const handle = Bun.file(file);
	return (await handle.exists()) ? ((await handle.json()) as T) : undefined;
}

async function entries(dir: string) {
	try {
		return (await readdir(dir, { withFileTypes: true })).filter(entry => !entry.name.startsWith("."));
	} catch (error) {
		if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
		throw error;
	}
}

const PLAIN_SCALAR_KEY_VALUE = /^(\s*[A-Za-z_][\w-]*:\s+)(\S.*?)(\s*)$/;
const FLOW_OR_EXPLICIT_VALUE_START = new Set(['"', "'", "[", "{", "|", ">", "!", "&", "*", "#"]);

function quoteAmbiguousPlainScalars(metadata: string): string | undefined {
	let changed = false;
	const lines = metadata.split("\n").map(line => {
		const match = line.match(PLAIN_SCALAR_KEY_VALUE);
		if (!match) return line;
		const [, prefix, rawValue, suffix] = match;
		const value = rawValue.trimEnd();
		if (!value.includes(": ") || FLOW_OR_EXPLICIT_VALUE_START.has(value[0])) return line;
		changed = true;
		return prefix + JSON.stringify(value) + suffix;
	});
	return changed ? lines.join("\n") : undefined;
}

function parseYamlRecord(metadata: string): Record<string, unknown> | undefined {
	const parsed = YAML.parse(metadata.replaceAll("\t", "  "));
	return parsed && typeof parsed === "object" && !Array.isArray(parsed)
		? (parsed as Record<string, unknown>)
		: undefined;
}

function fallbackFrontmatter(metadata: string): Record<string, unknown> | undefined {
	const result: Record<string, unknown> = {};
	for (const line of metadata.split("\n")) {
		const match = line.match(/^([\w-]+):\s*(.*)$/);
		if (!match) continue;
		const raw = match[2].trim();
		let value: unknown = raw;
		if (raw.length > 0) {
			try {
				const parsed = YAML.parse(raw);
				if (parsed !== null && (typeof parsed !== "object" || Array.isArray(parsed))) value = parsed;
			} catch {
				// Match OMP: preserve an individually malformed value as its raw string.
			}
		}
		result[match[1]] = value;
	}
	return Object.keys(result).length > 0 ? result : undefined;
}

/** Same lenient frontmatter rules as OMP: comments, tabs, ambiguous scalars, then key/value fallback. */
function frontmatter(content: string): Record<string, unknown> | undefined {
	const text = content.replace(/\r\n?/g, "\n").replace(/<!--[\s\S]*?-->/g, "");
	if (!text.startsWith("---")) return undefined;
	const end = text.indexOf("\n---", 3);
	if (end === -1) return undefined;
	const metadata = text.slice(4, end);
	try {
		return parseYamlRecord(metadata);
	} catch {
		const quoted = quoteAmbiguousPlainScalars(metadata);
		if (quoted) {
			try {
				return parseYamlRecord(quoted);
			} catch {
				// Fall through to OMP's simple key/value recovery.
			}
		}
		return fallbackFrontmatter(metadata);
	}
}

// ---------------------------------------------------------------------------
// 1. pin
// ---------------------------------------------------------------------------

async function pin(sources: Sources): Promise<void> {
	const fields = sources.upstreams.map(
		(upstream, i) => `u${i}: ${repositoryField(upstream.repo)} { object(expression: ${JSON.stringify(upstream.ref)}) { oid } }`,
	);
	const heads = await graphql<Record<string, { object: { oid: string } | null } | null>>(`query { ${fields.join("\n")} }`);
	sources.upstreams.forEach((upstream, i) => {
		const head = heads[`u${i}`]?.object?.oid;
		if (!head) throw new Error(`${upstream.name}: ${upstream.repo} has no ref "${upstream.ref}"`);
		if (head === upstream.sha) return;
		console.log(`pin    ${upstream.name}: ${upstream.sha.slice(0, 7)} -> ${head.slice(0, 7)}`);
		upstream.sha = head;
	});
	await Bun.write(SOURCES_PATH, `${JSON.stringify(sources, null, 2)}\n`);
}

// ---------------------------------------------------------------------------
// 2. fetch
// ---------------------------------------------------------------------------

async function extractTarball(repo: string, sha: string, destination: string): Promise<void> {
	const response = await fetch(`https://codeload.github.com/${repo}/tar.gz/${sha}`);
	if (!response.ok) throw new Error(`Download failed for ${repo}@${sha}: HTTP ${response.status}`);
	const tar = Bun.spawn(["tar", "-xzf", "-", "-C", destination, "--strip-components=1"], {
		stdin: response,
		stderr: "pipe",
	});
	if ((await tar.exited) !== 0) throw new Error(`tar failed for ${repo}@${sha}: ${await new Response(tar.stderr).text()}`);
}

/** Hash of everything that shapes a generated pack; fetch rebuilds a pack whenever it changes. */
export function buildId(upstream: Upstream): string {
	const inputs = [
		BUILD_FORMAT,
		upstream.name,
		upstream.repo,
		upstream.sha,
		upstream.description,
		Object.entries(upstream.include),
		upstream.compatibility,
		upstream.skillReferences,
		upstream.compatibility ? COMPATIBILITY_VERSION : undefined,
	];
	return new Bun.CryptoHasher("sha256").update(JSON.stringify(inputs)).digest("hex");
}

type GeneratedManifest = Record<string, unknown> & { sync?: Record<string, unknown> };

/** The exact bytes fetch writes for a generated package.json. */
function serializeManifest(manifest: unknown): string {
	return `${JSON.stringify(manifest, null, 2)}\n`;
}

/** Stream one held regular-file descriptor, bounded even if the file grows after its initial stat. */
async function consumeGeneratedFile(
	absolute: string,
	relative: string,
	consume: (chunk: Uint8Array) => void,
): Promise<"100644" | "100755"> {
	const handle = await open(absolute, "r");
	try {
		const info = await handle.stat();
		if (!info.isFile()) {
			throw new Error(`generated trees hold only regular files and directories; found ${relative} (not a regular file)`);
		}
		if (info.size > MAX_GENERATED_FILE_BYTES) {
			throw new Error(`generated file exceeds 16 MiB limit: ${relative} (${info.size} bytes)`);
		}
		let bytes = 0;
		for await (const chunk of handle.createReadStream({ autoClose: false })) {
			const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
			bytes += buffer.length;
			if (bytes > MAX_GENERATED_FILE_BYTES) {
				throw new Error(`generated file exceeds 16 MiB limit: ${relative} (${bytes} bytes)`);
			}
			consume(buffer);
		}
		if (bytes !== info.size) throw new Error(`generated file changed while hashing: ${relative}`);
		return info.mode & 0o111 ? "100755" : "100644";
	} finally {
		await handle.close();
	}
}

/** Read the one generated file that must be parsed, under the same streaming size policy. */
async function readGeneratedText(absolute: string, relative: string): Promise<{ mode: "100644" | "100755"; text: string }> {
	const decoder = new TextDecoder();
	const chunks: string[] = [];
	const mode = await consumeGeneratedFile(absolute, relative, chunk => {
		const text = decoder.decode(chunk, { stream: true });
		if (text) chunks.push(text);
	});
	const final = decoder.decode();
	if (final) chunks.push(final);
	return { mode, text: chunks.join("") };
}

/** Content digest and mode for one generated file; package.json excludes only its own recorded tree digest. */
async function digestGeneratedFile(absolute: string, relative: string): Promise<{ hash: string; mode: "100644" | "100755" }> {
	const hasher = new Bun.CryptoHasher("sha256");
	if (relative === "package.json") {
		const { mode, text } = await readGeneratedText(absolute, relative);
		const manifest = JSON.parse(text) as GeneratedManifest;
		if (manifest.sync) delete manifest.sync.tree;
		hasher.update(serializeManifest(manifest));
		return { hash: hasher.digest("hex"), mode };
	}
	const mode = await consumeGeneratedFile(absolute, relative, chunk => hasher.update(chunk));
	return { hash: hasher.digest("hex"), mode };
}

/**
 * Deterministic digest of a generated upstream tree: every regular file's POSIX path, executable bit, and
 * content hash, in code-unit path order. Individual files are capped at 16 MiB and streamed. package.json
 * is hashed in its generated serialization without `sync.tree`, so the digest can live inside the tree it
 * covers. Symlinks and other non-regular entries are rejected, never hashed or shipped.
 */
export async function generatedTreeDigest(dir: string): Promise<string> {
	const files: string[] = [];
	const rejected: string[] = [];
	const walk = async (relative: string): Promise<void> => {
		for (const entry of await readdir(path.join(dir, relative), { withFileTypes: true })) {
			const child = relative ? `${relative}/${entry.name}` : entry.name;
			if (entry.isDirectory()) await walk(child);
			else if (entry.isFile()) files.push(child);
			else rejected.push(`${child} (${entry.isSymbolicLink() ? "symlink" : "not a regular file"})`);
		}
	};
	await walk("");
	if (rejected.length > 0) {
		throw new Error(`generated trees hold only regular files and directories; found ${rejected.sort().join(", ")}`);
	}
	files.sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
	const tree = new Bun.CryptoHasher("sha256");
	for (const file of files) {
		const { hash, mode } = await digestGeneratedFile(path.join(dir, file), file);
		tree.update(`${mode} ${hash} ${file}\0`);
	}
	return `sha256:${tree.digest("hex")}`;
}

/** Record generatedTreeDigest() as `sync.tree` in dir/package.json; the last write fetch makes to a pack. */
export async function stampGeneratedTree(dir: string): Promise<void> {
	const file = path.join(dir, "package.json");
	const manifest = JSON.parse((await readGeneratedText(file, "package.json")).text) as GeneratedManifest;
	manifest.sync = { ...manifest.sync, tree: await generatedTreeDigest(dir) };
	await Bun.write(file, serializeManifest(manifest));
}

/** Why a generated upstream tree differs from what fetch wrote; empty when it is intact. */
export async function generatedTreeProblems(dir: string): Promise<string[]> {
	const file = path.join(dir, "package.json");
	const handle = Bun.file(file);
	if (!(await handle.exists())) return ["missing package.json"];
	let text: string;
	try {
		text = (await readGeneratedText(file, "package.json")).text;
	} catch (error) {
		return [(error as Error).message];
	}
	let manifest: GeneratedManifest;
	try {
		manifest = JSON.parse(text) as GeneratedManifest;
	} catch {
		return ["package.json is not valid JSON"];
	}
	const problems: string[] = [];
	if (text !== serializeManifest(manifest)) problems.push("package.json is not in the form fetch writes");
	let actual: string;
	try {
		actual = await generatedTreeDigest(dir);
	} catch (error) {
		return [...problems, (error as Error).message];
	}
	const recorded = manifest.sync?.tree;
	if (typeof recorded !== "string") problems.push("package.json has no sync.tree digest; rebuild it from sources.json");
	else if (recorded !== actual) {
		problems.push(`generated tree was modified (sync.tree ${recorded}, contents ${actual}); rebuild it from sources.json instead of editing it`);
	}
	return problems;
}

/**
 * Move `staged` onto `target`, parking the previous `target` at `backup` (same filesystem) until the
 * move succeeds and putting it back if it fails. Replaces in place: `omp plugin link` points at `target`.
 */
export async function replaceDir(staged: string, target: string, backup: string): Promise<void> {
	let hadPrevious = true;
	await rename(target, backup).catch((error: NodeJS.ErrnoException) => {
		if (error.code !== "ENOENT") throw error;
		hadPrevious = false;
	});
	try {
		await rename(staged, target);
	} catch (error) {
		if (hadPrevious) await rename(backup, target);
		throw error;
	}
}

export async function buildUpstream(upstream: Upstream): Promise<void> {
	// Stage inside upstream/: rename() cannot cross filesystems, so staging in tmpdir() could fail after the old pack was gone.
	const scratch = await mkdtemp(path.join(UPSTREAM_DIR, `${STAGING_PREFIX}${upstream.name}-`));
	try {
		const checkout = path.join(scratch, "checkout");
		const pack = path.join(scratch, "pack");
		await mkdir(checkout);
		await mkdir(pack);
		await extractTarball(upstream.repo, upstream.sha, checkout);

		// Includes may share a destination; copying entry by entry records where each one came from
		// and refuses to merge two includes into, or over, the same path.
		const origins: Record<string, string> = {};
		const claim = (to: string, from: string) => {
			for (const [taken, origin] of Object.entries(origins)) {
				if (to === taken || to.startsWith(`${taken}/`) || taken.startsWith(`${to}/`)) {
					throw new Error(`${upstream.name}: "${from}" and "${origin}" both map to "${to}" in the pack`);
				}
			}
			origins[to] = from;
		};
		const keep = (source: string) => !SKIPPED_NAMES[path.basename(source)];
		for (const [from, to] of Object.entries(upstream.include)) {
			const source = path.join(checkout, from);
			if (!(await stat(source).catch(() => undefined))?.isDirectory()) {
				throw new Error(`${upstream.name}: "${from}" is not a directory at ${upstream.sha}`);
			}
			for (const name of await readdir(source)) {
				if (SKIPPED_NAMES[name]) continue;
				claim(path.posix.join(to, name), path.posix.join(from, name));
				await cp(path.join(source, name), path.join(pack, to, name), { recursive: true, filter: keep });
			}
		}
		for (const entry of await entries(checkout)) {
			if (!entry.isFile() || !LICENSE_FILE.test(entry.name)) continue;
			claim(entry.name, entry.name);
			await cp(path.join(checkout, entry.name), path.join(pack, entry.name));
		}
		if (upstream.compatibility) {
			if (upstream.compatibility !== COMPATIBILITY_PROFILE) {
				throw new Error(`${upstream.name}: unknown compatibility profile "${upstream.compatibility}"`);
			}
			const result = await adaptCompatibility(pack);
			if (result.errors.length > 0) throw new Error(`${upstream.name}: ${result.errors.join("; ")}`);
		}
		const sync: SyncRecord = {
			build: buildId(upstream),
			origins: Object.fromEntries(Object.entries(origins).sort(([a], [b]) => a.localeCompare(b))),
			...(upstream.compatibility
				? { compatibility: { profile: upstream.compatibility, version: COMPATIBILITY_VERSION } }
				: {}),
		};
		const manifest = {
			name: upstream.name,
			version: `${upstream.compatibility ? "0.0.1" : "0.0.0"}-g${upstream.sha.slice(0, 7)}`,
			private: true,
			description: upstream.description,
			homepage: `https://github.com/${upstream.repo}/tree/${upstream.sha}`,
			repository: `https://github.com/${upstream.repo}`,
			gitHead: upstream.sha,
			sync,
			...(upstream.skillReferences ? { ompSkillReferences: upstream.skillReferences } : {}),
			...(upstream.compatibility
				? { ompCompatibility: { profile: upstream.compatibility, version: COMPATIBILITY_VERSION } }
				: {}),
			omp: {},
		};
		await Bun.write(path.join(pack, "package.json"), serializeManifest(manifest));
		await stampGeneratedTree(pack).catch((error: Error) => {
			throw new Error(`${upstream.name}: ${error.message}`);
		});

		await replaceDir(pack, path.join(UPSTREAM_DIR, upstream.name), path.join(scratch, "previous"));
	} finally {
		await rm(scratch, { recursive: true, force: true });
	}
}

export async function fetchUpstreams(sources: Sources): Promise<void> {
	await mkdir(UPSTREAM_DIR, { recursive: true });
	// upstream/ is generated: anything not listed in sources.json goes, including staging left by an interrupted run.
	const listed = new Set(sources.upstreams.map(upstream => upstream.name));
	for (const name of await readdir(UPSTREAM_DIR)) {
		if (listed.has(name)) continue;
		await rm(path.join(UPSTREAM_DIR, name), { recursive: true, force: true });
		console.log(`remove upstream/${name}`);
	}
	for (const upstream of sources.upstreams) {
		const target = path.join(UPSTREAM_DIR, upstream.name);
		const current = await readJson<{ sync?: Partial<SyncRecord> }>(path.join(target, "package.json"));
		// A pack whose tree no longer matches its digest was edited by hand; rebuild it.
		if (current?.sync?.build === buildId(upstream) && (await generatedTreeProblems(target)).length === 0) continue;
		await buildUpstream(upstream);
		console.log(`fetch  ${upstream.name} @ ${upstream.sha.slice(0, 7)}`);
	}
}


// ---------------------------------------------------------------------------
// 3. check
// ---------------------------------------------------------------------------

/** OMP scans rules/, agents/, and commands/ one level deep; nested files are silently ignored. */
async function flatMarkdown(packDir: string, sub: string, pattern: RegExp, errors: string[], label: string) {
	const files: string[] = [];
	for (const entry of await entries(path.join(packDir, sub))) {
		if (entry.isDirectory()) errors.push(`${label}: ${sub}/${entry.name}/ is nested; OMP only loads ${sub}/*.md`);
		else if (pattern.test(entry.name)) files.push(path.join(sub, entry.name));
	}
	return files;
}

interface SkillOwner {
	pack: string;
	baseDir: string;
}

async function nestedMarkdownFiles(dir: string): Promise<string[]> {
	const files: string[] = [];
	for (const entry of await entries(dir)) {
		const file = path.join(dir, entry.name);
		if (entry.isDirectory()) files.push(...(await nestedMarkdownFiles(file)));
		else if (entry.isFile() && entry.name.endsWith(".md")) files.push(file);
	}
	return files;
}

function normalizedSkillReferences(pack: Pack, errors: string[]): OmpSkillReferences {
	const value = pack.skillReferences as unknown;
	if (!value || typeof value !== "object" || Array.isArray(value)) {
		errors.push(`${pack.name}: ompSkillReferences must be an object`);
		return {};
	}
	const raw = value as Record<string, unknown>;
	for (const key of Object.keys(raw)) {
		if (key !== "requires" && key !== "optional") errors.push(`${pack.name}: unknown ompSkillReferences field "${key}"`);
	}
	const references: OmpSkillReferences = {};
	if (raw.requires !== undefined) {
		if (!raw.requires || typeof raw.requires !== "object" || Array.isArray(raw.requires)) {
			errors.push(`${pack.name}: ompSkillReferences.requires must map pack names to skill-name arrays`);
		} else {
			const requires: Record<string, string[]> = {};
			for (const [provider, targets] of Object.entries(raw.requires as Record<string, unknown>)) {
				if (!Array.isArray(targets) || targets.some(target => typeof target !== "string" || !/^[a-z0-9][a-z0-9_-]*$/.test(target))) {
					errors.push(`${pack.name}: ompSkillReferences.requires.${provider} must be a skill-name array`);
					continue;
				}
				requires[provider] = [...new Set(targets as string[])];
				if (requires[provider].length !== targets.length) {
					errors.push(`${pack.name}: ompSkillReferences.requires.${provider} contains duplicates`);
				}
			}
			references.requires = requires;
		}
	}
	if (raw.optional !== undefined) {
		if (!Array.isArray(raw.optional) || raw.optional.some(target => typeof target !== "string" || !/^[a-z0-9][a-z0-9_-]*$/.test(target))) {
			errors.push(`${pack.name}: ompSkillReferences.optional must be a skill-name array`);
		} else {
			const optional = [...new Set(raw.optional as string[])];
			references.optional = optional;
			if (optional.length !== raw.optional.length) {
				errors.push(`${pack.name}: ompSkillReferences.optional contains duplicates`);
			}
		}
	}
	return references;
}

/** Validate skill:// links within a pack or through that pack's explicit dependency metadata. */
async function validateSkillReferences(packs: Pack[], errors: string[]): Promise<void> {
	const packByName = new Map(packs.map(pack => [pack.name, pack]));
	const references = new Map(packs.map(pack => [pack.name, normalizedSkillReferences(pack, errors)]));
	const skills = new Map<string, SkillOwner>();
	for (const pack of packs) {
		for (const skill of pack.skills) {
			skills.set(skill.name.toLowerCase(), {
				pack: pack.name,
				baseDir: path.resolve(ROOT, pack.dir, path.dirname(skill.file)),
			});
		}
	}

	for (const pack of packs) {
		const declared = references.get(pack.name)!;
		for (const [providerName, targets] of Object.entries(declared.requires ?? {})) {
			const provider = packByName.get(providerName);
			if (!provider) {
				errors.push(`${pack.name}: required skill provider "${providerName}" does not exist`);
				continue;
			}
			if (provider === pack) errors.push(`${pack.name}: must not declare itself as a required skill provider`);
			const provided = new Set(provider.skills.map(skill => skill.name.toLowerCase()));
			for (const target of targets) {
				if (!provided.has(target.toLowerCase())) {
					errors.push(`${pack.name}: required target "${target}" is not provided by ${providerName}`);
				}
			}
		}

		const usedRequired = new Set<string>();
		const usedOptional = new Set<string>();
		const optional = new Set((declared.optional ?? []).map(target => target.toLowerCase()));
		const packDir = path.join(ROOT, pack.dir);
		const files = new Set(await nestedMarkdownFiles(path.join(packDir, "skills")));
		for (const item of [...pack.agents, ...pack.commands, ...pack.rules]) files.add(path.join(packDir, item.file));
		for (const file of files) {
			const contents = await Bun.file(file).text();
			for (const match of contents.matchAll(/\bskill:\/\/([a-z0-9][a-z0-9_-]*)(\/[^\s`<>"')\]}]+)?/gi)) {
				const root = match[1]!.toLowerCase();
				const rawPath = (match[2] ?? "").replace(/[.,;:!?'"()\]}]+$/, "");
				const source = path.relative(packDir, file).split(path.sep).join("/");
				const line = contents.slice(0, match.index ?? 0).split("\n").length;
				const owner = skills.get(root);
				if (!owner) {
					if (optional.has(root)) usedOptional.add(root);
					else errors.push(`${pack.name}: ${source}:${line}: unknown skill target "${root}"`);
					continue;
				}
				if (owner.pack !== pack.name) {
					const required = new Set((declared.requires?.[owner.pack] ?? []).map(target => target.toLowerCase()));
					if (!required.has(root)) {
						errors.push(`${pack.name}: ${source}:${line}: cross-pack target "${root}" requires ompSkillReferences.requires.${owner.pack}`);
					} else {
						usedRequired.add(`${owner.pack}:${root}`);
					}
				}
				if (!rawPath || rawPath === "/") continue;
				let relativePath: string;
				try {
					relativePath = decodeURIComponent(rawPath.slice(1).split(/[?#]/, 1)[0]!);
				} catch {
					errors.push(`${pack.name}: ${source}:${line}: invalid skill URI encoding in skill://${root}${rawPath}`);
					continue;
				}
				const target = path.resolve(owner.baseDir, relativePath);
				if (target !== owner.baseDir && !target.startsWith(`${owner.baseDir}${path.sep}`)) {
					errors.push(`${pack.name}: ${source}:${line}: skill URI escapes "${root}": skill://${root}${rawPath}`);
					continue;
				}
				if (!(await stat(target).catch(() => undefined))) {
					errors.push(`${pack.name}: ${source}:${line}: skill://${root}${rawPath} does not exist in ${owner.pack}`);
				}
			}
		}
		for (const [provider, targets] of Object.entries(declared.requires ?? {})) {
			for (const target of targets) {
				if (!usedRequired.has(`${provider}:${target.toLowerCase()}`)) {
					errors.push(`${pack.name}: unused required skill reference ${provider}/${target}`);
				}
			}
		}
		for (const target of declared.optional ?? []) {
			if (!usedOptional.has(target.toLowerCase())) errors.push(`${pack.name}: unused optional skill reference ${target}`);
		}
	}
}

function githubRepository(value: unknown): string | undefined {
	if (typeof value !== "string") return undefined;
	const prefix = "https://github.com/";
	if (!value.startsWith(prefix)) return undefined;
	const path = value.slice(prefix.length);
	const slug = path.endsWith(".git") ? path.slice(0, -4) : path;
	return slug.split("/").length === 2 ? slug : undefined;
}

async function inspectPack(dir: string, upstream: Upstream | undefined, errors: string[]): Promise<Pack | undefined> {
	const packDir = path.join(ROOT, dir);
	const manifest = await readJson<{
		name?: string;
		version?: string;
		gitHead?: string;
		repository?: string;
		sync?: Partial<SyncRecord>;
		ompCompatibility?: { profile?: CompatibilityProfile; version?: number };
		ompSkillReferences?: OmpSkillReferences;
		omp?: { extensions?: string[] };
	}>(path.join(packDir, "package.json"));
	if (!manifest) {
		errors.push(`${dir}: missing package.json`);
		return undefined;
	}
	const label = manifest.name ?? dir;
	if (manifest.name !== path.basename(dir)) errors.push(`${dir}: package.json name must be "${path.basename(dir)}"`);
	if (!manifest.version) errors.push(`${label}: package.json has no version`);
	if (typeof manifest.omp !== "object") errors.push(`${label}: package.json needs an "omp" object, or OMP ignores the pack`);
	if (upstream) {
		const expectedVersion = `${upstream.compatibility ? "0.0.1" : "0.0.0"}-g${upstream.sha.slice(0, 7)}`;
		if (manifest.version !== expectedVersion) errors.push(`${label}: generated version must be ${expectedVersion}`);
		if (manifest.gitHead !== upstream.sha) errors.push(`${label}: package.json gitHead does not match sources.json`);
		if (githubRepository(manifest.repository) !== upstream.repo) {
			errors.push(`${label}: package.json repository does not match sources.json`);
		}
		if (manifest.sync?.build !== buildId(upstream)) {
			errors.push(`${label}: generated output is stale; rebuild it from sources.json`);
		}
		const syncCompatibility = manifest.sync?.compatibility;
		if (upstream.compatibility) {
			if (
				syncCompatibility?.profile !== upstream.compatibility ||
				syncCompatibility?.version !== COMPATIBILITY_VERSION
			) {
				errors.push(`${label}: sync metadata must record OMP compatibility ${upstream.compatibility}@${COMPATIBILITY_VERSION}`);
			}
		} else if (manifest.sync?.compatibility) {
			errors.push(`${label}: unexpected compatibility metadata in generated output`);
		}
		if (JSON.stringify(manifest.ompSkillReferences ?? {}) !== JSON.stringify(upstream.skillReferences ?? {})) {
			errors.push(`${label}: generated ompSkillReferences does not match sources.json`);
		}
		for (const problem of await generatedTreeProblems(packDir)) errors.push(`${label}: ${problem}`);
	}
	const compatibility = upstream?.compatibility ?? manifest.ompCompatibility?.profile;
	if (compatibility) {
		if (compatibility !== COMPATIBILITY_PROFILE) errors.push(`${label}: unknown OMP compatibility profile "${compatibility}"`);
		if (manifest.ompCompatibility?.profile !== compatibility || manifest.ompCompatibility.version !== COMPATIBILITY_VERSION) {
			errors.push(`${label}: package.json must record OMP compatibility ${compatibility}@${COMPATIBILITY_VERSION}`);
		}
		for (const error of await lintCompatibility(packDir)) errors.push(`${label}: ${error}`);
	}

	const skills: Item[] = [];
	for (const entry of await entries(path.join(packDir, "skills"))) {
		if (!entry.isDirectory() && !entry.isSymbolicLink()) continue;
		const file = path.posix.join("skills", entry.name, "SKILL.md");
		const handle = Bun.file(path.join(packDir, file));
		if (!(await handle.exists())) continue;
		const meta = frontmatter(await handle.text());
		if (!meta) errors.push(`${label}: ${file} must start with YAML frontmatter`);
		else if (meta.enabled === false) continue;
		else if (typeof meta.description !== "string" || !meta.description.trim()) {
			errors.push(`${label}: ${file} has no description, so OMP skips it`);
		} else {
			const name = typeof meta.name === "string" && meta.name.trim() ? meta.name.trim() : entry.name;
			if (/[\\/]/.test(name)) errors.push(`${label}: ${file} name "${name}" contains a path separator`);
			else skills.push({ name, file });
		}
	}

	const item = (file: string, name?: unknown): Item => ({
		name: typeof name === "string" && name.trim() ? name.trim() : path.posix.basename(file).replace(/\.[^.]+$/, ""),
		file,
	});
	const agents: Item[] = [];
	for (const file of await flatMarkdown(packDir, "agents", /\.md$/, errors, label)) {
		const meta = frontmatter(await Bun.file(path.join(packDir, file)).text());
		if (
			typeof meta?.name !== "string" ||
			!meta.name.trim() ||
			typeof meta.description !== "string" ||
			!meta.description.trim()
		) {
			errors.push(`${label}: ${file} needs non-empty name and description strings in its frontmatter`);
		}
		agents.push(item(file, meta?.name));
	}
	const rules = (await flatMarkdown(packDir, "rules", /\.mdc?$/, errors, label)).map(file => item(file));
	const commands = (await flatMarkdown(packDir, "commands", /\.md$/, errors, label)).map(file => item(file));
	const tools: Item[] = [];
	for (const entry of await entries(path.join(packDir, "tools"))) {
		if (entry.isFile()) {
			if (!/\.(ts|js|sh|bash|py)$/.test(entry.name) || /\.d\.ts$/.test(entry.name)) continue;
			tools.push(item(path.posix.join("tools", entry.name)));
			continue;
		}
		if (!entry.isDirectory()) continue;
		const file = path.posix.join("tools", entry.name, "index.ts");
		if (await Bun.file(path.join(packDir, file)).exists()) tools.push(item(file, entry.name));
	}
	const extensions = manifest.omp?.extensions ?? [];
	for (const extension of extensions) {
		if (!(await Bun.file(path.join(packDir, extension)).exists())) errors.push(`${label}: extension ${extension} does not exist`);
	}

	return {
		name: label,
		dir,
		version: typeof manifest.version === "string" ? manifest.version : "",
		repository: githubRepository(manifest.repository),
		upstream,
		origins: manifest.sync?.origins,
		attribution: !upstream && (await Bun.file(path.join(packDir, "ATTRIBUTION")).exists()),
		skillReferences: manifest.ompSkillReferences ?? {},
		skills,
		rules,
		agents,
		commands,
		tools,
		extensions: extensions.length,
	};
}

export async function check(sources: Sources, errors: string[]): Promise<Pack[]> {
	const packs: Pack[] = [];
	for (const entry of await entries(path.join(ROOT, "packs"))) {
		if (!entry.isDirectory()) continue;
		const pack = await inspectPack(path.posix.join("packs", entry.name), undefined, errors);
		if (pack) packs.push(pack);
	}
	for (const upstream of sources.upstreams) {
		const pack = await inspectPack(path.posix.join("upstream", upstream.name), upstream, errors);
		if (pack) packs.push(pack);
	}

	// Duplicate skill names are host-order dependent, so reject the ambiguous installation here.
	const owners = new Map<string, string>();
	for (const pack of packs) {
		for (const skill of pack.skills) {
			const owner = owners.get(skill.name);
			if (owner) errors.push(`skill "${skill.name}" is defined by both ${owner} and ${pack.name}`);
			else owners.set(skill.name, pack.name);
		}
	}

	await validateSkillReferences(packs, errors);

	failOn(errors);
	return packs.sort((a, b) => a.name.localeCompare(b.name));
}

function failOn(errors: string[]): void {
	if (errors.length === 0) return;
	console.error(`${errors.length} pack compatibility problem(s):`);
	for (const error of errors) console.error(`  - ${error}`);
	process.exit(1);
}

// ---------------------------------------------------------------------------
// 5. readme
// ---------------------------------------------------------------------------

/** Newest commit touching each file and directory under packs/ and upstream/, from one pass over history (newest first). */
function localLastCommits(repository: string): Map<string, Commit> {
	const log = Bun.spawnSync(["git", "log", "--format=%x00%H %cI", "--name-only", "--", "packs", "upstream"], { cwd: ROOT });
	const latest = new Map<string, Commit>();
	for (const block of log.stdout.toString().split("\0").slice(1)) {
		const [header, ...files] = block.trim().split("\n");
		const [sha, date] = header.split(" ");
		for (const file of files) {
			if (!latest.has(file)) latest.set(file, { repository, sha, date });
			// Ancestors of an already-dated directory were dated by the same, newer commit.
			for (let dir = path.posix.dirname(file); dir !== "." && !latest.has(dir); dir = path.posix.dirname(dir)) {
				latest.set(dir, { repository, sha, date });
			}
		}
	}
	return latest;
}

/** Newest commit touching each upstream skill at its pin, keyed by `<pack>/<skill dir>`, in one request. */
async function upstreamLastCommits(packs: Pack[]): Promise<Map<string, Commit>> {
	const lookups: Array<{ key: string; alias: string; repository: string }> = [];
	const fields = packs.flatMap((pack, p) => {
		if (!pack.upstream || pack.skills.length === 0) return [];
		const upstream = pack.upstream;
		const histories = pack.skills.map((skill, s) => {
			const dir = path.posix.dirname(skill.file);
			lookups.push({ key: `${pack.name}/${dir}`, alias: `${p}.${s}`, repository: upstream.repo });
			return `s${s}: history(first: 1, path: ${JSON.stringify(upstreamPath(pack, dir))}) { nodes { oid committedDate } }`;
		});
		return [`p${p}: ${repositoryField(upstream.repo)} { object(oid: ${JSON.stringify(upstream.sha)}) { ... on Commit { ${histories.join(" ")} } } }`];
	});
	if (fields.length === 0) return new Map();
	type History = { nodes: Array<{ oid: string; committedDate: string }> };
	const data = await graphql<Record<string, { object: Record<string, History> | null } | null>>(`query { ${fields.join("\n")} }`);
	const commits = new Map<string, Commit>();
	for (const { key, alias, repository } of lookups) {
		const [p, s] = alias.split(".");
		const node = data[`p${p}`]?.object?.[`s${s}`]?.nodes[0];
		if (node) commits.set(key, { repository, sha: node.oid, date: node.committedDate });
	}
	return commits;
}

/** Map a path inside an upstream pack back to its path in the upstream repository, via fetch's copy record. */
export function upstreamPath(pack: Pack, packPath: string): string {
	// Recorded entries never overlap, so at most one matches.
	for (const [to, from] of Object.entries(pack.origins ?? {})) {
		if (packPath === to || packPath.startsWith(`${to}/`)) return `${from}${packPath.slice(to.length)}`;
	}
	throw new Error(`${pack.name}: ${packPath} has no recorded upstream origin; rerun fetch`);
}

function describeContents(pack: Pack): string {
	return Object.entries({ skills: pack.skills.length, rules: pack.rules.length, agents: pack.agents.length, commands: pack.commands.length, tools: pack.tools.length, extensions: pack.extensions })
		.filter(([, count]) => count > 0)
		.map(([kind, count]) => `${count} ${count === 1 ? kind.slice(0, -1) : kind}`)
		.join(", ");
}
function describeRequirements(pack: Pack): string {
	const providers = Object.entries(pack.skillReferences.requires ?? {}).map(
		([provider, skills]) => `\`${provider}\` (${skills.map(skill => `\`${skill}\``).join(", ")})`,
	);
	return providers.length > 0 ? providers.join("; ") : "—";
}

/** Last-updated cell: the commit date, linked inside the repository that owns the commit. */
export function commitStamp(commit: Commit | undefined): string {
	return commit
		? `[${new Date(commit.date).toISOString().slice(0, 16).replace("T", " ")} UTC](https://github.com/${commit.repository}/commit/${commit.sha})`
		: "—";
}

export async function renderReadme(sources: Sources, packs: Pack[], commits?: ReadmeCommits): Promise<string> {
	const repo = sources.repository;
	const localCommits = commits?.local ?? localLastCommits(repo);
	const upstreamCommits = commits?.upstream ?? (await upstreamLastCommits(packs));
	// Link each item at its own last commit so unrelated commits don't rewrite the row.
	const source = (pack: Pack, item: Item) => {
		if (pack.upstream) {
			return {
				at: pack.upstream.repo,
				url: `https://github.com/${pack.upstream.repo}/blob/${pack.upstream.sha}/${upstreamPath(pack, item.file)}`,
				commit: upstreamCommits.get(`${pack.name}/${path.posix.dirname(item.file)}`),
			};
		}
		const commit = localCommits.get(path.posix.join(pack.dir, item.file));
		return {
			at: pack.repository ?? repo,
			url: `https://github.com/${repo}/blob/${commit?.sha ?? "main"}/${pack.dir}/${item.file}`,
			commit,
		};
	};
	const section = (kind: string, pick: (pack: Pack) => Item[]): string[] => {
		const rows = packs
			.flatMap(pack => pick(pack).map(item => ({ pack, item })))
			.sort((a, b) => `${a.pack.name}/${a.item.name}`.localeCompare(`${b.pack.name}/${b.item.name}`))
			.map(({ pack, item }) => {
				const link = source(pack, item);
				return `| [${item.name}](${link.url}) | \`${pack.name}\` | \`${pack.version}\` | [${link.at}](https://github.com/${link.at}) | ${commitStamp(link.commit)} |`;
			});
		if (rows.length === 0) return [];
		return [`## ${kind}`, "", `| ${kind.slice(0, -1)} | Pack | Version | Source | Last updated |`, "| --- | --- | --- | --- | --- |", ...rows, ""];
	};
	const authored = packs.filter(pack => !pack.upstream && !pack.attribution).map(pack => `\`${pack.name}\``).join(", ");
	const packRows = packs.map(pack => {
		const target = pack.upstream
			? `[${pack.upstream.repo}@${pack.upstream.sha.slice(0, 7)}](https://github.com/${pack.upstream.repo}/tree/${pack.upstream.sha})`
			: pack.attribution
				? pack.repository && pack.repository !== repo
					? `[${pack.repository}](https://github.com/${pack.repository}) via [ATTRIBUTION](./${pack.dir}/ATTRIBUTION)`
					: `vendored, see [ATTRIBUTION](./${pack.dir}/ATTRIBUTION)`
				: "this repo";
		// A pack row dates the pack directory in this repository, so its commit is always local.
		return `| \`${pack.name}\` | \`${pack.version}\` | ${target} | ${describeRequirements(pack)} | ${describeContents(pack)} | ${commitStamp(localCommits.get(pack.dir))} |`;
	});

	return [
		"<!-- Generated by scripts/sync.ts. Do not edit manually. -->",
		"",
		"# Agent Plugins",
		"",
		sources.description,
		"",
		"Every directory in `packs/` and `upstream/` is an OMP extension package: a `package.json` with an `omp` field, plus any of `skills/`, `rules/`, `agents/`, `commands/`, `hooks/`, `tools/`, `prompts/`, and `.mcp.json`. Linked packs appear under **OMP Extension Packages** in `/extensions`.",
		"",
		"`Version` is the pack's `package.json` version; `Last updated` is the newest commit touching the item (upstream items: at the pinned commit).",
		"",
		"## Install",
		"",
		"```bash",
		"omp plugin install github:clssck/agent-plugins   # omp keeps its own copy of this repo",
		"AP=~/.omp/plugins/node_modules/agent-plugins",
		"omp plugin link $AP/packs/clssck-core              # link each pack you want",
		"omp plugin link $AP/packs/clssck-development",
		"omp plugin link $AP/upstream/emilkowalski-skills",
		"```",
		"",
		"`omp plugin upgrade agent-plugins` pulls the latest commit; linked packs follow automatically because they point into omp's copy. The package name is required: bare `omp plugin upgrade` only upgrades marketplace packages. Run `omp plugin doctor` afterward to catch removed or renamed pack targets. Re-link only when adding, renaming, or removing a pack; routine re-links reset its enabled state and feature selection. `omp plugin disable <name>` / `enable <name>` toggles a pack, `omp plugin uninstall <name>` removes it, and `/extensions` toggles individual skills, rules, and agents.",
		"Packs are linked independently. If the catalog's \`Requires\` column names another pack, link that provider too; repository checks validate every declared cross-pack skill target.",
		"",
		"Upgrade note for existing installs: if a machine links `sanofi` without `clssck-core`, link `clssck-core` before upgrading. The `dbt-command-scope` and `dbt-test-arguments` guards moved to `clssck-core` in 1.2.0.",
		"",
		"Packs that load are not guaranteed to work with every host capability. Generated CoCo upstreams are adapted on deterministic staged copies and record pinned build provenance; committed \`packs/coco-*\` are adapted in place in this repository. In both cases source repositories and named source releases remain untouched. Foreign question, skill, task, todo, and fetch interfaces become OMP semantics; external capabilities are gated; missing links are repaired or de-linked; and \`skill://\` references are validated against pack-scoped dependency declarations. When a required capability or host path is unavailable, stop and report it; NEVER improvise a substitute.",
		"",
		"Maintainer docs: [CONTRIBUTING.md](./CONTRIBUTING.md).",
		"",
		"## Packs",
		"",
		"| Pack | Version | Source | Requires | Contents | Last updated |",
		"| --- | --- | --- | --- | --- | --- |",
		...packRows,
		"",
		...section("Skills", pack => pack.skills),
		...section("Rules", pack => pack.rules),
		...section("Agents", pack => pack.agents),
		...section("Commands", pack => pack.commands),
		...section("Tools", pack => pack.tools),
		"## License",
		"",
		`The root [LICENSE](./LICENSE) (MIT) covers all material authored in this repository: root files, \`.github/\`, configuration, \`scripts/\`, and the first-party packs ${authored} under \`packs/\`, with the third-party exceptions it documents. Vendored packs and \`upstream/\` copies carry the license files their upstreams ship. Third-party adaptations and attributions are listed in [\`licenses/\`](./licenses/README.md).`,
		"",
	].join("\n");
}


// ---------------------------------------------------------------------------

if (import.meta.main) {
	const sources = (await Bun.file(SOURCES_PATH).json()) as Sources;
	const checkOnly = process.argv.includes("--check");
	const local = process.argv.includes("--local") || checkOnly;
	if (!local) {
		await pin(sources);
		await fetchUpstreams(sources);
	}
	const errors: string[] = [];
	const packs = await check(sources, errors);
	if (!checkOnly && (process.env.GITHUB_ACTIONS || process.argv.includes("--readme"))) {
		const readme = await renderReadme(sources, packs);
		if (readme !== (await Bun.file(README_PATH).text())) {
			await Bun.write(README_PATH, readme);
			console.log("readme updated");
		}
	} else {
		console.log("readme not checked; pass --readme to regenerate it locally");
	}
	// Static contract check only; scripts/check-omp-loader.ts is what proves OMP itself loads the packs.
	console.log(
		`${packs.length} packs, ${packs.reduce((total, pack) => total + pack.skills.length, 0)} skills: repository checks passed (OMP loaders not run)`,
	);
}
