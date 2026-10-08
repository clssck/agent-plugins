#!/usr/bin/env bun
// Keeps this repository self-contained. In order:
//   1. pin    – move every upstream in sources.json to the latest commit of its ref
//   2. fetch  – copy each upstream into upstream/<name>/ at its pinned commit
//   3. check  – fail if anything in packs/ or upstream/ would not load in OMP
//   4. readme – regenerate README.md
// Run by .github/workflows/sync-upstreams.yml; set GITHUB_TOKEN when running locally.

import { YAML } from "bun";
import { cp, mkdir, mkdtemp, readdir, rename, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
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

interface Skill {
	name: string;
	/** Path of SKILL.md relative to the pack root. */
	file: string;
}

interface Pack {
	name: string;
	/** Directory relative to the repository root, e.g. `packs/bro`. */
	dir: string;
	upstream?: Upstream;
	skills: Skill[];
	counts: Record<"rules" | "agents" | "commands" | "extensions", number>;
}

const ROOT = path.resolve(import.meta.dir, "..");
const SOURCES_PATH = path.join(ROOT, "sources.json");
const README_PATH = path.join(ROOT, "README.md");
const UPSTREAM_DIR = path.join(ROOT, "upstream");
const SKIPPED_NAMES: Record<string, true> = { ".DS_Store": true, ".git": true, __pycache__: true };
const LICENSE_FILE = /^(licen[cs]e|copying|notice)(\.|$)/i;

const token = process.env.GITHUB_TOKEN;

async function github<T>(endpoint: string): Promise<T> {
	const response = await fetch(`https://api.github.com${endpoint}`, {
		headers: {
			Accept: "application/vnd.github+json",
			"X-GitHub-Api-Version": "2022-11-28",
			"User-Agent": "clssck-agent-plugins",
			...(token ? { Authorization: `Bearer ${token}` } : {}),
		},
	});
	if (!response.ok) throw new Error(`GitHub ${response.status} for ${endpoint}: ${await response.text()}`);
	return (await response.json()) as T;
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
	for (const upstream of sources.upstreams) {
		const head = await github<{ sha: string }>(`/repos/${upstream.repo}/commits/${encodeURIComponent(upstream.ref)}`);
		if (head.sha === upstream.sha) continue;
		console.log(`pin    ${upstream.name}: ${upstream.sha.slice(0, 7)} -> ${head.sha.slice(0, 7)}`);
		upstream.sha = head.sha;
	}
	await Bun.write(SOURCES_PATH, `${JSON.stringify(sources, null, 2)}\n`);
}

// ---------------------------------------------------------------------------
// 2. fetch
// ---------------------------------------------------------------------------

async function extractTarball(repo: string, sha: string, destination: string): Promise<void> {
	const response = await fetch(`https://codeload.github.com/${repo}/tar.gz/${sha}`);
	if (!response.ok) throw new Error(`Download failed for ${repo}@${sha}: HTTP ${response.status}`);
	const tar = Bun.spawn(["tar", "-xzf", "-", "-C", destination, "--strip-components=1"], {
		stdin: await response.arrayBuffer(),
		stderr: "pipe",
	});
	if ((await tar.exited) !== 0) throw new Error(`tar failed for ${repo}@${sha}: ${await new Response(tar.stderr).text()}`);
}

async function buildUpstream(upstream: Upstream): Promise<void> {
	const scratch = await mkdtemp(path.join(tmpdir(), `agent-plugins-${upstream.name}-`));
	try {
		const checkout = path.join(scratch, "checkout");
		const pack = path.join(scratch, "pack");
		await mkdir(checkout);
		await mkdir(pack);
		await extractTarball(upstream.repo, upstream.sha, checkout);

		const keep = (source: string) => !SKIPPED_NAMES[path.basename(source)];
		for (const [from, to] of Object.entries(upstream.include)) {
			const source = path.join(checkout, from);
			if (!(await stat(source).catch(() => undefined))?.isDirectory()) {
				throw new Error(`${upstream.name}: "${from}" is not a directory at ${upstream.sha}`);
			}
			await cp(source, path.join(pack, to), { recursive: true, filter: keep });
		}
		for (const entry of await entries(checkout)) {
			if (entry.isFile() && LICENSE_FILE.test(entry.name)) await cp(path.join(checkout, entry.name), path.join(pack, entry.name));
		}
		const manifest = {
			name: upstream.name,
			version: `0.0.0-g${upstream.sha.slice(0, 7)}`,
			private: true,
			description: upstream.description,
			homepage: `https://github.com/${upstream.repo}/tree/${upstream.sha}`,
			repository: `https://github.com/${upstream.repo}`,
			gitHead: upstream.sha,
			omp: {},
		};
		await Bun.write(path.join(pack, "package.json"), `${JSON.stringify(manifest, null, 2)}\n`);

		// Replace in place: `omp plugin link` points at this directory path.
		const target = path.join(UPSTREAM_DIR, upstream.name);
		await rm(target, { recursive: true, force: true });
		await rename(pack, target);
	} finally {
		await rm(scratch, { recursive: true, force: true });
	}
}

async function fetchUpstreams(sources: Sources): Promise<void> {
	await mkdir(UPSTREAM_DIR, { recursive: true });
	for (const upstream of sources.upstreams) {
		const current = await readJson<{ gitHead?: string }>(path.join(UPSTREAM_DIR, upstream.name, "package.json"));
		if (current?.gitHead === upstream.sha) continue;
		await buildUpstream(upstream);
		console.log(`fetch  ${upstream.name} @ ${upstream.sha.slice(0, 7)}`);
	}
	// upstream/ is generated: anything not listed in sources.json goes.
	const listed = new Set(sources.upstreams.map(upstream => upstream.name));
	for (const entry of await entries(UPSTREAM_DIR)) {
		if (listed.has(entry.name)) continue;
		await rm(path.join(UPSTREAM_DIR, entry.name), { recursive: true, force: true });
		console.log(`remove upstream/${entry.name}`);
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

async function inspectPack(dir: string, upstream: Upstream | undefined, errors: string[]): Promise<Pack | undefined> {
	const packDir = path.join(ROOT, dir);
	const manifest = await readJson<{ name?: string; version?: string; omp?: { extensions?: string[] } }>(
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

	const skills: Skill[] = [];
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

	const agents = await flatMarkdown(packDir, "agents", /\.md$/, errors, label);
	for (const file of agents) {
		const meta = frontmatter(await Bun.file(path.join(packDir, file)).text());
		if (!meta?.name || !meta.description) errors.push(`${label}: ${file} needs name and description in its frontmatter`);
	}
	const rules = await flatMarkdown(packDir, "rules", /\.mdc?$/, errors, label);
	const commands = await flatMarkdown(packDir, "commands", /\.md$/, errors, label);
	const extensions = manifest.omp?.extensions ?? [];
	for (const extension of extensions) {
		if (!(await Bun.file(path.join(packDir, extension)).exists())) errors.push(`${label}: extension ${extension} does not exist`);
	}

	return {
		name: label,
		dir,
		upstream,
		skills,
		counts: { rules: rules.length, agents: agents.length, commands: commands.length, extensions: extensions.length },
	};
}

async function check(sources: Sources): Promise<Pack[]> {
	const errors: string[] = [];
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

	if (errors.length > 0) {
		console.error(`${errors.length} problem(s) would stop packs from loading in OMP:`);
		for (const error of errors) console.error(`  - ${error}`);
		process.exit(1);
	}
	return packs.sort((a, b) => a.name.localeCompare(b.name));
}

// ---------------------------------------------------------------------------
// 4. readme
// ---------------------------------------------------------------------------

function localLastCommit(file: string): Commit | undefined {
	const result = Bun.spawnSync(["git", "log", "-1", "--format=%H %cI", "--", file], { cwd: ROOT });
	const [sha, date] = result.stdout.toString().trim().split(" ");
	return sha && date ? { sha, date } : undefined;
}

async function upstreamLastCommit(repo: string, sha: string, dir: string): Promise<Commit | undefined> {
	const query = new URLSearchParams({ sha, path: dir, per_page: "1" });
	const [commit] = await github<Array<{ sha: string; commit: { committer: { date: string } } }>>(
		`/repos/${repo}/commits?${query}`,
	);
	return commit && { sha: commit.sha, date: commit.commit.committer.date };
}

/** Map a path inside an upstream pack back to its path in the upstream repository. */
function upstreamPath(upstream: Upstream, packPath: string): string {
	for (const [from, to] of Object.entries(upstream.include)) {
		if (packPath === to || packPath.startsWith(`${to}/`)) return `${from}${packPath.slice(to.length)}`;
	}
	throw new Error(`${upstream.name}: ${packPath} is outside every include mapping`);
}

function describeContents(pack: Pack): string {
	return Object.entries({ skills: pack.skills.length, ...pack.counts })
		.filter(([, count]) => count > 0)
		.map(([kind, count]) => `${count} ${count === 1 ? kind.slice(0, -1) : kind}`)
		.join(", ");
}

async function renderReadme(sources: Sources, packs: Pack[]): Promise<string> {
	const rows: string[] = [];
	// Sequential: a burst of parallel commit queries trips GitHub's secondary rate limit.
	for (const pack of packs) {
		for (const skill of pack.skills) {
			const dir = path.posix.dirname(skill.file);
			let repo: string;
			let skillUrl: string;
			let commit: Commit | undefined;
			if (pack.upstream) {
				const source = upstreamPath(pack.upstream, dir);
				repo = pack.upstream.repo;
				commit = await upstreamLastCommit(repo, pack.upstream.sha, source);
				skillUrl = `https://github.com/${repo}/blob/${pack.upstream.sha}/${source}/SKILL.md`;
			} else {
				repo = sources.repository;
				commit = localLastCommit(path.posix.join(pack.dir, dir));
				// Link at the skill's own last commit so unrelated commits don't rewrite the row.
				skillUrl = `https://github.com/${repo}/blob/${commit?.sha ?? "main"}/${pack.dir}/${skill.file}`;
			}
			const updated = commit
				? `[${new Date(commit.date).toISOString().slice(0, 16).replace("T", " ")} UTC](https://github.com/${repo}/commit/${commit.sha})`
				: "not committed yet";
			rows.push(`| [${skill.name}](${skillUrl}) | \`${pack.name}\` | [${repo}](https://github.com/${repo}) | ${updated} |`);
		}
	}
	rows.sort((a, b) => a.localeCompare(b));
	const skillCount = packs.reduce((total, pack) => total + pack.skills.length, 0);

	return [
		"<!-- Generated by scripts/sync.ts. Do not edit manually. -->",
		"",
		"# Agent Plugins",
		"",
		sources.description,
		"",
		"Every directory in `packs/` (written here) and `upstream/` (copied from other repositories) is an OMP extension package: a `package.json` with an `omp` field, plus any of `skills/`, `rules/`, `agents/`, `commands/`, `hooks/`, `tools/`, `prompts/`, and `.mcp.json`. Linked packs appear under **OMP Extension Packages** in `/extensions`.",
		"",
		"## Install",
		"",
		"```bash",
		"git clone https://github.com/clssck/agent-plugins ~/Projects/agent-plugins",
		"cd ~/Projects/agent-plugins",
		"omp plugin link packs/clssck-core      # link each pack you want",
		"omp plugin link upstream/emilkowalski-skills",
		"```",
		"",
		"Links point at the clone, so `git pull` updates everything. `omp plugin disable <name>` / `enable <name>` toggles a pack, `omp plugin uninstall <name>` removes it, and `/extensions` toggles individual skills, rules, and agents.",
		"",
		"## Packs",
		"",
		"| Pack | Link | Source | Contents |",
		"| --- | --- | --- | --- |",
		...packs.map(pack => {
			const source = pack.upstream
				? `[${pack.upstream.repo}@${pack.upstream.sha.slice(0, 7)}](https://github.com/${pack.upstream.repo}/tree/${pack.upstream.sha})`
				: "this repo";
			return `| \`${pack.name}\` | \`omp plugin link ${pack.dir}\` | ${source} | ${describeContents(pack)} |`;
		}),
		"",
		"## Skills",
		"",
		`${skillCount} skills across ${packs.filter(pack => pack.skills.length > 0).length} packs. “Last updated” is the newest commit that touched the skill's directory.`,
		"",
		"| Skill | Pack | Repository | Last updated |",
		"| --- | --- | --- | --- |",
		...rows,
		"",
		"## Maintenance",
		"",
		"[`.github/workflows/sync-upstreams.yml`](./.github/workflows/sync-upstreams.yml) runs [`scripts/sync.ts`](./scripts/sync.ts) daily at 06:17 UTC and on pushes that change `packs/`, `sources.json`, or `scripts/`. It moves every upstream in [`sources.json`](./sources.json) to the latest commit of its branch, copies it into `upstream/`, regenerates this README, and commits the result. The run fails, and commits nothing, if any skill, rule, agent, or command would not load in OMP or two packs define the same skill.",
		"",
		"To run it locally: `GITHUB_TOKEN=$(gh auth token) bun scripts/sync.ts`.",
		"",
		"### Add an upstream",
		"",
		"Append to `upstreams` in `sources.json`: `name` (the pack name), `repo` (`owner/name`), `ref` (branch), `sha` (any commit; the sync moves it), `description`, and `include`, which maps upstream paths to pack paths (usually `{ \"skills\": \"skills\" }`). Push, and the workflow does the rest.",
		"",
		"### Add a pack of your own",
		"",
		"Create `packs/<name>/package.json` with `name` (matching the directory), `version`, and `\"omp\": {}` (list TypeScript extension modules under `omp.extensions`). Add `skills/<skill>/SKILL.md`, `rules/*.md`, `agents/*.md`, or `commands/*.md` as needed; OMP does not look inside subdirectories of `rules/`, `agents/`, or `commands/`.",
		"",
	].join("\n");
}

// ---------------------------------------------------------------------------

const sources = (await Bun.file(SOURCES_PATH).json()) as Sources;
await pin(sources);
await fetchUpstreams(sources);
const packs = await check(sources);
const readme = await renderReadme(sources, packs);
if (readme !== (await Bun.file(README_PATH).text())) {
	await Bun.write(README_PATH, readme);
	console.log("readme updated");
}
console.log(`${packs.length} packs, ${packs.reduce((total, pack) => total + pack.skills.length, 0)} skills: all load in OMP`);
