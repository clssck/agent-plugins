#!/usr/bin/env bun
// Keeps this repository self-contained. In order:
//   1. pin    – move every upstream in sources.json to the latest commit of its ref
//   2. fetch  – copy each upstream into upstream/<name>/ at its pinned commit
//   3. rules  – render rule-sources/<pack>/*.md into packs/<pack>/rules/
//   4. check  – fail if anything in packs/ or upstream/ would not load in OMP
//   5. readme – regenerate README.md (the workflow only; pass --readme to do it locally)
// Run by .github/workflows/sync-upstreams.yml; set GITHUB_TOKEN when running locally.
// `--local` runs only rules and check: no network, no token. A local run leaves README.md to the workflow.

import { YAML } from "bun";
import { cp, mkdir, mkdtemp, readdir, rename, rm, stat } from "node:fs/promises";
import * as path from "node:path";

interface Upstream {
	name: string;
	repo: string;
	ref: string;
	sha: string;
	description: string;
	/** Upstream path → pack path, e.g. `{ "skills": "skills" }`. */
	include: Record<string, string>;
}

interface Sources {
	repository: string;
	description: string;
	upstreams: Upstream[];
}

interface Commit {
	sha: string;
	date: string;
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
	upstream?: Upstream;
	/** Upstream packs: pack path → upstream path of each copied entry, as recorded by fetch. */
	origins?: Record<string, string>;
	/** A pack under packs/ that ships an ATTRIBUTION file: vendored here rather than written here. */
	attribution: boolean;
	skills: Item[];
	rules: Item[];
	agents: Item[];
	commands: Item[];
	extensions: number;
}

/** What fetch records in each generated upstream package.json. */
interface SyncRecord {
	/** buildId() of the inputs the pack was built from. */
	build: string;
	/** Pack path → upstream path of every copied top-level entry. */
	origins: Record<string, string>;
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
const BUILD_FORMAT = 2;
/** Rule sources; packs/<pack>/rules/ is generated from rule-sources/<pack>/. */
const RULE_SOURCES_DIR = path.join(ROOT, "rule-sources");
/** Shared regex fragments, one per file, referenced from rule frontmatter as {{<name>}}. */
const FRAGMENTS_DIR = path.join(RULE_SOURCES_DIR, "fragments");
const FRAGMENT_REF = /\{\{([\w-]+)\}\}/g;

const token = process.env.GITHUB_TOKEN;

/** One GraphQL request; callers batch many lookups into it with aliases. */
async function graphql<T>(query: string): Promise<T> {
	if (!token) throw new Error("GITHUB_TOKEN is required: GitHub's GraphQL API has no anonymous access");
	const response = await fetch("https://api.github.com/graphql", {
		method: "POST",
		headers: { Authorization: `Bearer ${token}`, "User-Agent": "clssck-agent-plugins" },
		body: JSON.stringify({ query }),
	});
	const body = (await response.json()) as { data?: T; errors?: Array<{ message: string }> };
	if (!response.ok || body.errors?.length || !body.data) {
		throw new Error(`GitHub GraphQL ${response.status}: ${body.errors?.map(error => error.message).join("; ")}`);
	}
	return body.data;
}

/** GraphQL `repository(...)` selector; JSON string literals are valid GraphQL strings. */
function repositoryField(repo: string): string {
	const [owner, name] = repo.split("/");
	return `repository(owner: ${JSON.stringify(owner)}, name: ${JSON.stringify(name)})`;
}

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

/** Same rules as OMP's frontmatter parser: `---` on the first line, YAML until the next `\n---`. */
function frontmatter(content: string): Record<string, unknown> | undefined {
	const text = content.replace(/\r\n?/g, "\n");
	if (!text.startsWith("---")) return undefined;
	const end = text.indexOf("\n---", 3);
	if (end === -1) return undefined;
	try {
		const parsed = YAML.parse(text.slice(4, end));
		return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : undefined;
	} catch {
		return undefined;
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
	const inputs = [BUILD_FORMAT, upstream.name, upstream.repo, upstream.sha, upstream.description, Object.entries(upstream.include)];
	return new Bun.CryptoHasher("sha256").update(JSON.stringify(inputs)).digest("hex");
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
		const sync: SyncRecord = {
			build: buildId(upstream),
			origins: Object.fromEntries(Object.entries(origins).sort(([a], [b]) => a.localeCompare(b))),
		};
		const manifest = {
			name: upstream.name,
			version: `0.0.0-g${upstream.sha.slice(0, 7)}`,
			private: true,
			description: upstream.description,
			homepage: `https://github.com/${upstream.repo}/tree/${upstream.sha}`,
			repository: `https://github.com/${upstream.repo}`,
			gitHead: upstream.sha,
			sync,
			omp: {},
		};
		await Bun.write(path.join(pack, "package.json"), `${JSON.stringify(manifest, null, 2)}\n`);

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
		const current = await readJson<{ sync?: Partial<SyncRecord> }>(path.join(UPSTREAM_DIR, upstream.name, "package.json"));
		if (current?.sync?.build === buildId(upstream)) continue;
		await buildUpstream(upstream);
		console.log(`fetch  ${upstream.name} @ ${upstream.sha.slice(0, 7)}`);
	}
}

// ---------------------------------------------------------------------------
// 3. rules
// ---------------------------------------------------------------------------

/**
 * Render rule-sources/<pack>/*.md into packs/<pack>/rules/, replacing each {{name}} in the frontmatter
 * with rule-sources/fragments/<name>.regex. Conditions are YAML single-quoted, so `'` is doubled.
 * In GitHub Actions a stale generated rule is an error: the workflow commits only upstream changes.
 */
export async function renderRules(errors: string[]): Promise<void> {
	const fragments = new Map<string, string>();
	for (const entry of await entries(FRAGMENTS_DIR)) {
		if (!entry.isFile() || !entry.name.endsWith(".regex")) continue;
		const text = await Bun.file(path.join(FRAGMENTS_DIR, entry.name)).text();
		fragments.set(entry.name.slice(0, -".regex".length), text.replace(/\r?\n$/, "").replaceAll("'", "''"));
	}
	const packNames = (await entries(path.join(ROOT, "packs"))).filter(entry => entry.isDirectory()).map(entry => entry.name);
	for (const entry of await entries(RULE_SOURCES_DIR)) {
		if (entry.isDirectory() && entry.name !== "fragments" && !packNames.includes(entry.name)) {
			errors.push(`rule-sources/${entry.name}/ has no matching packs/${entry.name}/`);
		}
	}
	for (const pack of packNames) {
		const sourceDir = path.join(RULE_SOURCES_DIR, pack);
		const targetDir = path.join(ROOT, "packs", pack, "rules");
		const names = (await entries(sourceDir)).filter(entry => entry.isFile() && entry.name.endsWith(".md")).map(entry => entry.name);
		for (const name of names) {
			const source = await Bun.file(path.join(sourceDir, name)).text();
			const end = source.startsWith("---") ? source.indexOf("\n---", 3) : -1;
			if (end === -1) {
				errors.push(`rule-sources/${pack}/${name} must start with YAML frontmatter closed by ---`);
				continue;
			}
			const head = source.slice(0, end).replace(FRAGMENT_REF, (ref, key: string) => {
				const fragment = fragments.get(key);
				if (fragment === undefined) errors.push(`rule-sources/${pack}/${name}: unknown fragment ${ref}`);
				return fragment ?? ref;
			});
			const rendered = head + source.slice(end);
			const target = path.join(targetDir, name);
			const current = (await Bun.file(target).exists()) ? await Bun.file(target).text() : undefined;
			if (rendered === current) continue;
			if (process.env.GITHUB_ACTIONS) {
				errors.push(`packs/${pack}/rules/${name} is stale; run \`bun scripts/sync.ts --local\` and commit it`);
			} else {
				await Bun.write(target, rendered);
				console.log(`rendered packs/${pack}/rules/${name}`);
			}
		}
		for (const entry of await entries(targetDir)) {
			if (!names.includes(entry.name)) errors.push(`packs/${pack}/rules/${entry.name} has no source; rules are edited in rule-sources/${pack}/`);
		}
	}
}

// ---------------------------------------------------------------------------
// 4. check
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

async function inspectPack(dir: string, upstream: Upstream | undefined, errors: string[]): Promise<Pack | undefined> {
	const packDir = path.join(ROOT, dir);
	const manifest = await readJson<{ name?: string; version?: string; sync?: Partial<SyncRecord>; omp?: { extensions?: string[] } }>(
		path.join(packDir, "package.json"),
	);
	if (!manifest) {
		errors.push(`${dir}: missing package.json`);
		return undefined;
	}
	const label = manifest.name ?? dir;
	if (manifest.name !== path.basename(dir)) errors.push(`${dir}: package.json name must be "${path.basename(dir)}"`);
	if (!manifest.version) errors.push(`${label}: package.json has no version`);
	if (typeof manifest.omp !== "object") errors.push(`${label}: package.json needs an "omp" object, or OMP ignores the pack`);

	const skills: Item[] = [];
	for (const entry of await entries(path.join(packDir, "skills"))) {
		if (!entry.isDirectory()) continue;
		const file = path.posix.join("skills", entry.name, "SKILL.md");
		const handle = Bun.file(path.join(packDir, file));
		if (!(await handle.exists())) continue;
		const meta = frontmatter(await handle.text());
		if (!meta) errors.push(`${label}: ${file} must start with YAML frontmatter`);
		else if (!meta.description) errors.push(`${label}: ${file} has no description, so OMP skips it`);
		else if (meta.enabled === false) continue;
		else {
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
		if (!meta?.name || !meta.description) errors.push(`${label}: ${file} needs name and description in its frontmatter`);
		agents.push(item(file, meta?.name));
	}
	const rules = (await flatMarkdown(packDir, "rules", /\.mdc?$/, errors, label)).map(file => item(file));
	const commands = (await flatMarkdown(packDir, "commands", /\.md$/, errors, label)).map(file => item(file));
	const extensions = manifest.omp?.extensions ?? [];
	for (const extension of extensions) {
		if (!(await Bun.file(path.join(packDir, extension)).exists())) errors.push(`${label}: extension ${extension} does not exist`);
	}

	return {
		name: label,
		dir,
		version: typeof manifest.version === "string" ? manifest.version : "",
		upstream,
		origins: manifest.sync?.origins,
		attribution: !upstream && (await Bun.file(path.join(packDir, "ATTRIBUTION")).exists()),
		skills,
		rules,
		agents,
		commands,
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

	// OMP keeps one skill per name; a second pack defining it is silently shadowed.
	const owners = new Map<string, string>();
	for (const pack of packs) {
		for (const skill of pack.skills) {
			const owner = owners.get(skill.name);
			if (owner) errors.push(`skill "${skill.name}" is defined by both ${owner} and ${pack.name}`);
			else owners.set(skill.name, pack.name);
		}
	}

	failOn(errors);
	return packs.sort((a, b) => a.name.localeCompare(b.name));
}

function failOn(errors: string[]): void {
	if (errors.length === 0) return;
	console.error(`${errors.length} problem(s) would stop packs from loading in OMP:`);
	for (const error of errors) console.error(`  - ${error}`);
	process.exit(1);
}

// ---------------------------------------------------------------------------
// 5. readme
// ---------------------------------------------------------------------------

/** Newest commit touching each file and directory under packs/ and upstream/, from one pass over history (newest first). */
function localLastCommits(): Map<string, Commit> {
	const log = Bun.spawnSync(["git", "log", "--format=%x00%H %cI", "--name-only", "--", "packs", "upstream"], { cwd: ROOT });
	const latest = new Map<string, Commit>();
	for (const block of log.stdout.toString().split("\0").slice(1)) {
		const [header, ...files] = block.trim().split("\n");
		const [sha, date] = header.split(" ");
		for (const file of files) {
			if (!latest.has(file)) latest.set(file, { sha, date });
			// Ancestors of an already-dated directory were dated by the same, newer commit.
			for (let dir = path.posix.dirname(file); dir !== "." && !latest.has(dir); dir = path.posix.dirname(dir)) {
				latest.set(dir, { sha, date });
			}
		}
	}
	return latest;
}

/** Newest commit touching each upstream skill at its pin, keyed by `<pack>/<skill dir>`, in one request. */
async function upstreamLastCommits(packs: Pack[]): Promise<Map<string, Commit>> {
	const lookups: Array<{ key: string; alias: string }> = [];
	const fields = packs.flatMap((pack, p) => {
		if (!pack.upstream || pack.skills.length === 0) return [];
		const upstream = pack.upstream;
		const histories = pack.skills.map((skill, s) => {
			const dir = path.posix.dirname(skill.file);
			lookups.push({ key: `${pack.name}/${dir}`, alias: `${p}.${s}` });
			return `s${s}: history(first: 1, path: ${JSON.stringify(upstreamPath(pack, dir))}) { nodes { oid committedDate } }`;
		});
		return [`p${p}: ${repositoryField(upstream.repo)} { object(oid: ${JSON.stringify(upstream.sha)}) { ... on Commit { ${histories.join(" ")} } } }`];
	});
	if (fields.length === 0) return new Map();
	type History = { nodes: Array<{ oid: string; committedDate: string }> };
	const data = await graphql<Record<string, { object: Record<string, History> | null } | null>>(`query { ${fields.join("\n")} }`);
	const commits = new Map<string, Commit>();
	for (const { key, alias } of lookups) {
		const [p, s] = alias.split(".");
		const node = data[`p${p}`]?.object?.[`s${s}`]?.nodes[0];
		if (node) commits.set(key, { sha: node.oid, date: node.committedDate });
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
	return Object.entries({ skills: pack.skills.length, rules: pack.rules.length, agents: pack.agents.length, commands: pack.commands.length, extensions: pack.extensions })
		.filter(([, count]) => count > 0)
		.map(([kind, count]) => `${count} ${count === 1 ? kind.slice(0, -1) : kind}`)
		.join(", ");
}

export async function renderReadme(sources: Sources, packs: Pack[]): Promise<string> {
	const localCommits = localLastCommits();
	const upstreamCommits = await upstreamLastCommits(packs);
	const repo = sources.repository;
	const stamp = (commit: Commit | undefined, at: string): string =>
		commit
			? `[${new Date(commit.date).toISOString().slice(0, 16).replace("T", " ")} UTC](https://github.com/${at}/commit/${commit.sha})`
			: "—";
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
		return { at: repo, url: `https://github.com/${repo}/blob/${commit?.sha ?? "main"}/${pack.dir}/${item.file}`, commit };
	};
	const section = (kind: string, pick: (pack: Pack) => Item[]): string[] => {
		const rows = packs
			.flatMap(pack => pick(pack).map(item => ({ pack, item })))
			.sort((a, b) => `${a.pack.name}/${a.item.name}`.localeCompare(`${b.pack.name}/${b.item.name}`))
			.map(({ pack, item }) => {
				const link = source(pack, item);
				return `| [${item.name}](${link.url}) | \`${pack.name}\` | \`${pack.version}\` | [${link.at}](https://github.com/${link.at}) | ${stamp(link.commit, link.at)} |`;
			});
		if (rows.length === 0) return [];
		return [`## ${kind}`, "", `| ${kind.slice(0, -1)} | Pack | Version | Source | Last updated |`, "| --- | --- | --- | --- | --- |", ...rows, ""];
	};
	const authored = packs.filter(pack => !pack.upstream && !pack.attribution).map(pack => `\`${pack.name}\``).join(", ");
	const packRows = packs.map(pack => {
		const at = pack.upstream ? pack.upstream.repo : repo;
		const target = pack.upstream
			? `[${pack.upstream.repo}@${pack.upstream.sha.slice(0, 7)}](https://github.com/${pack.upstream.repo}/tree/${pack.upstream.sha})`
			: pack.attribution
				? `vendored, see [ATTRIBUTION](./${pack.dir}/ATTRIBUTION)`
				: "this repo";
		return `| \`${pack.name}\` | \`${pack.version}\` | ${target} | ${describeContents(pack)} | ${stamp(localCommits.get(pack.dir), at)} |`;
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
		"omp plugin link $AP/upstream/emilkowalski-skills",
		"```",
		"",
		"`omp plugin upgrade agent-plugins` pulls the latest commit; linked packs follow automatically because they point into omp's copy. `omp plugin disable <name>` / `enable <name>` toggles a pack, `omp plugin uninstall <name>` removes it, and `/extensions` toggles individual skills, rules, and agents.",
		"",
		"Packs that load are not guaranteed to work with your host: the vendored CoCo and Snowflake skills reference CoCo tools, the `cortex` CLI, and host path variables. When those are unavailable, stop and say so; NEVER improvise a substitute.",
		"",
		"Maintainer docs: [CONTRIBUTING.md](./CONTRIBUTING.md).",
		"",
		"## Packs",
		"",
		"| Pack | Version | Source | Contents | Last updated |",
		"| --- | --- | --- | --- | --- |",
		...packRows,
		"",
		...section("Skills", pack => pack.skills),
		...section("Rules", pack => pack.rules),
		...section("Agents", pack => pack.agents),
		...section("Commands", pack => pack.commands),
		"## License",
		"",
		`The root [LICENSE](./LICENSE) covers what is written here: ${authored} under \`packs/\`, \`rule-sources/\`, and \`scripts/\`. Vendored packs and \`upstream/\` copies carry the license files their upstreams ship. Third-party adaptations and attributions are listed in [\`licenses/\`](./licenses/README.md).`,
		"",
	].join("\n");
}


// ---------------------------------------------------------------------------

if (import.meta.main) {
	const sources = (await Bun.file(SOURCES_PATH).json()) as Sources;
	const local = process.argv.includes("--local");
	if (!local) {
		await pin(sources);
		await fetchUpstreams(sources);
	}
	const errors: string[] = [];
	await renderRules(errors);
	const packs = await check(sources, errors);
	if (process.env.GITHUB_ACTIONS || process.argv.includes("--readme")) {
		const readme = await renderReadme(sources, packs);
		if (readme !== (await Bun.file(README_PATH).text())) {
			await Bun.write(README_PATH, readme);
			console.log("readme updated");
		}
	} else {
		console.log("readme: written by the workflow; pass --readme to update it locally");
	}
	console.log(`${packs.length} packs, ${packs.reduce((total, pack) => total + pack.skills.length, 0)} skills: all load in OMP`);
}
