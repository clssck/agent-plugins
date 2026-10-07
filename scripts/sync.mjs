#!/usr/bin/env node
// Re-pin every upstream in sources.json to the head of its ref and regenerate README.md.
// Run by the daily workflow; also safe to run locally (set GITHUB_TOKEN to avoid rate limits).

import { execFileSync } from "node:child_process";
import { readdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, posix, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourcesPath = join(root, "sources.json");
const readmePath = join(root, "README.md");
const packsDir = join(root, "packs");
const token = process.env.GITHUB_TOKEN;
const headers = {
  Accept: "application/vnd.github+json",
  "X-GitHub-Api-Version": "2022-11-28",
  "User-Agent": "clssck-agent-plugins",
  ...(token ? { Authorization: `Bearer ${token}` } : {}),
};

// OMP's extension-package provider scans exactly one level: `skills/<name>/SKILL.md`.
const LOADED_SKILL = /^skills\/[^/]+\/SKILL\.md$/;

async function githubJson(path) {
  const response = await fetch(`https://api.github.com${path}`, { headers });
  if (!response.ok) throw new Error(`GitHub ${response.status} for ${path}: ${await response.text()}`);
  return response.json();
}

async function lastCommit(repo, sha, directory) {
  const query = new URLSearchParams({ sha, per_page: "1", path: directory });
  const [commit] = await githubJson(`/repos/${repo}/commits?${query}`);
  if (!commit) return null;
  return { sha: commit.sha, date: commit.commit.committer?.date ?? commit.commit.author?.date };
}

function formatUtc(value) {
  return `${new Date(value).toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true }).catch(error => {
    if (error?.code === "ENOENT") return [];
    throw error;
  });
  const files = [];
  for (const entry of entries) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...(await walk(path)));
    else files.push(path);
  }
  return files;
}

const toPosix = path => path.split(sep).join(posix.sep);

async function countFiles(directory, pattern) {
  return (await walk(directory)).filter(file => pattern.test(file)).length;
}

// ---------------------------------------------------------------------------
// Re-pin upstreams
// ---------------------------------------------------------------------------

const sourcesText = await readFile(sourcesPath, "utf8");
const sources = JSON.parse(sourcesText);
for (const upstream of sources.upstreams) {
  const head = await githubJson(`/repos/${upstream.repo}/commits/${encodeURIComponent(upstream.ref)}`);
  if (head.sha !== upstream.sha) {
    console.log(`${upstream.name}: ${upstream.sha.slice(0, 7)} -> ${head.sha.slice(0, 7)}`);
    upstream.sha = head.sha;
  }
}
const renderedSources = `${JSON.stringify(sources, null, 2)}\n`;
if (renderedSources !== sourcesText) await writeFile(sourcesPath, renderedSources);

// ---------------------------------------------------------------------------
// Collect skills
// ---------------------------------------------------------------------------

const headSha = process.env.GITHUB_SHA ?? execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim();
const rows = [];
const packs = [];

for (const entry of (await readdir(packsDir, { withFileTypes: true })).filter(e => e.isDirectory())) {
  const packDir = join(packsDir, entry.name);
  const manifest = JSON.parse(await readFile(join(packDir, "package.json"), "utf8"));
  const skillFiles = (await readdir(join(packDir, "skills"), { withFileTypes: true }).catch(() => []))
    .filter(child => child.isDirectory())
    .map(child => join(packDir, "skills", child.name, "SKILL.md"));
  const loadedSkillFiles = [];
  for (const file of skillFiles) if (await readFile(file).then(() => true, () => false)) loadedSkillFiles.push(file);
  packs.push({
    name: manifest.name,
    path: `packs/${entry.name}`,
    source: "this repo",
    contents: {
      skills: loadedSkillFiles.length,
      rules: await countFiles(join(packDir, "rules"), /\.mdc?$/),
      agents: await countFiles(join(packDir, "agents"), /\.md$/),
      commands: await countFiles(join(packDir, "commands"), /\.md$/),
      extensions: manifest.omp?.extensions?.length ?? 0,
    },
  });
  for (const file of loadedSkillFiles) {
    const skillPath = toPosix(relative(root, file));
    rows.push({ name: posix.basename(posix.dirname(skillPath)), pack: manifest.name, repo: sources.repository, sha: headSha, skillPath });
  }
}

for (const upstream of sources.upstreams) {
  const tree = await githubJson(`/repos/${upstream.repo}/git/trees/${upstream.sha}?recursive=1`);
  if (tree.truncated) throw new Error(`${upstream.repo}: tree listing truncated`);
  // OMP loads only `skills/<name>/SKILL.md` from a pack; skills nested deeper are reference material.
  const destination = path =>
    Object.entries(upstream.include)
      .filter(([from]) => path.startsWith(`${from}/`))
      .map(([from, to]) => `${to}${path.slice(from.length)}`)[0];
  const skillPaths = tree.tree
    .filter(item => item.type === "blob" && LOADED_SKILL.test(destination(item.path) ?? ""))
    .map(item => item.path);
  packs.push({
    name: upstream.name,
    path: `upstream/${upstream.name}`,
    source: `[${upstream.repo}@${upstream.sha.slice(0, 7)}](https://github.com/${upstream.repo}/tree/${upstream.sha})`,
    contents: { skills: skillPaths.length },
  });
  for (const skillPath of skillPaths) {
    rows.push({ name: posix.basename(posix.dirname(skillPath)), pack: upstream.name, repo: upstream.repo, sha: upstream.sha, skillPath });
  }
}

// Sequential: a parallel burst of per-path commit queries trips GitHub's secondary rate limit.
for (const row of rows) {
  row.lastCommit = await lastCommit(row.repo, row.sha, posix.dirname(row.skillPath));
}
rows.sort((a, b) => a.name.localeCompare(b.name) || a.pack.localeCompare(b.pack));
packs.sort((a, b) => a.name.localeCompare(b.name));

// ---------------------------------------------------------------------------
// README
// ---------------------------------------------------------------------------

function describeContents(contents) {
  return Object.entries(contents)
    .filter(([, count]) => count > 0)
    .map(([kind, count]) => `${count} ${count === 1 ? kind.replace(/s$/, "") : kind}`)
    .join(", ");
}

const lines = [
  "<!-- Generated by scripts/sync.mjs. Do not edit manually. -->",
  "",
  "# Agent Plugins",
  "",
  sources.description,
  "",
  "Every directory under `packs/` and `upstream/` is an OMP extension package: a `package.json` with an `omp` field, plus any of `skills/`, `rules/`, `agents/`, `commands/`, `hooks/`, `tools/`, `prompts/`, and `.mcp.json`. OMP lists linked packs under **OMP Extension Packages** in `/extensions`.",
  "",
  "`packs/` is authored here. `upstream/` holds copies of external skill repos at the commits pinned in [`sources.json`](./sources.json), each under its own license. A daily workflow moves the pins to each upstream's latest commit, refreshes `upstream/`, and commits the result, so this repo always contains everything.",
  "",
  "## Use",
  "",
  "```bash",
  "git clone https://github.com/clssck/agent-plugins ~/Projects/agent-plugins",
  "cd ~/Projects/agent-plugins",
  "omp plugin link packs/clssck-core               # link whichever packs you want",
  "omp plugin link upstream/emilkowalski-skills",
  "```",
  "",
  "Links point at this checkout, so updating is `git pull`.",
  "",
  "Turn a pack off with `omp plugin disable <name>` (back on with `enable`) or drop it with `omp plugin uninstall <name>`. Individual skills, rules, and agents can be toggled in `/extensions`.",
  "",
  "## Packs",
  "",
  "| Pack | Link | Source | Contents |",
  "| --- | --- | --- | --- |",
  ...packs.map(pack => `| \`${pack.name}\` | \`omp plugin link ${pack.path}\` | ${pack.source} | ${describeContents(pack.contents)} |`),
  "",
  "## Skills",
  "",
  `${rows.length} skills across ${new Set(rows.map(row => row.pack)).size} packs. “Last updated” is the newest commit that touched the skill's directory at the pinned commit.`,
  "",
  "| Skill | Pack | Repository | Last updated |",
  "| --- | --- | --- | --- |",
  ...rows.map(row => {
    // Authored-pack rows link at their own last commit, not HEAD, so a bot commit doesn't rewrite them.
    const revision = row.repo === sources.repository ? (row.lastCommit?.sha ?? row.sha) : row.sha;
    const skillUrl = `https://github.com/${row.repo}/blob/${revision}/${row.skillPath}`;
    const updated = row.lastCommit
      ? `[${formatUtc(row.lastCommit.date)}](https://github.com/${row.repo}/commit/${row.lastCommit.sha})`
      : "not committed yet";
    return `| [${row.name}](${skillUrl}) | \`${row.pack}\` | [${row.repo}](https://github.com/${row.repo}) | ${updated} |`;
  }),
  "",
  "## Add an upstream",
  "",
  "Append an entry to `upstreams` in [`sources.json`](./sources.json): `name` (the pack name), `repo` (`owner/name`), `ref`, any current `sha`, a `description`, and `include`, which maps paths in the upstream repo to paths in the pack (usually `{ \"skills\": \"skills\" }`). Push it; the workflow pins it and copies it into `upstream/`. Locally: `node scripts/sync.mjs && node scripts/fetch.mjs`.",
  "",
  "## Add a pack of your own",
  "",
  "Create `packs/<name>/package.json` with `name`, `version`, and an `omp` object (`{}` is enough; list TypeScript extension modules under `omp.extensions`), then add the component directories you need.",
];
const readme = `${lines.join("\n")}\n`;
const currentReadme = await readFile(readmePath, "utf8").catch(() => "");
if (currentReadme === readme) {
  console.log("README is current.");
} else {
  await writeFile(readmePath, readme);
  console.log(`Wrote README: ${rows.length} skills across ${packs.length} packs.`);
}
