#!/usr/bin/env node

import { readFile, writeFile } from "node:fs/promises";
import { dirname, posix, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourcesPath = resolve(root, "sources.json");
const catalogPath = resolve(root, ".omp-plugin/marketplace.json");
const readmePath = resolve(root, "README.md");
const token = process.env.GITHUB_TOKEN;
const headers = {
  Accept: "application/vnd.github+json",
  "X-GitHub-Api-Version": "2022-11-28",
  "User-Agent": "clssck-agent-plugins",
  ...(token ? { Authorization: `Bearer ${token}` } : {}),
};
const repositoryCache = new Map();
const contextCache = new Map();
const blobCache = new Map();
const lastCommitCache = new Map();
const skillRecords = [];

async function githubJson(path, optional = false) {
  const response = await fetch(`https://api.github.com${path}`, { headers });
  if (optional && response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`GitHub ${response.status} for ${path}: ${await response.text()}`);
  }
  return response.json();
}

function parseGitHubRepository(value) {
  const normalized = value.includes("://") ? value : `https://github.com/${value}`;
  const url = new URL(normalized);
  if (url.hostname !== "github.com") {
    throw new Error(`Only GitHub repositories are supported: ${value}`);
  }
  const parts = url.pathname.replace(/^\/+|\/+$/g, "").replace(/\.git$/, "").split("/");
  if (parts.length !== 2 || parts.some(part => !part)) {
    throw new Error(`Expected a GitHub repository URL or owner/repo slug: ${value}`);
  }
  return `${parts[0]}/${parts[1]}`;
}

function normalizeLocalPluginPath(value) {
  if (typeof value !== "string" || !value.trim() || value.includes("\\") || value.includes("\0")) {
    throw new Error(`Expected a safe relative local plugin path, received ${JSON.stringify(value)}`);
  }
  const normalized = posix.normalize(value.trim().replace(/^\.\/+/, "")).replace(/\/+$/, "");
  if (!normalized || normalized === "." || posix.isAbsolute(normalized) || normalized.startsWith("../")) {
    throw new Error(`Local plugin path must stay inside the bazaar: ${JSON.stringify(value)}`);
  }
  return normalized;
}

function slug(value) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

function compact(object) {
  return Object.fromEntries(Object.entries(object).filter(([, value]) => value !== undefined));
}

async function repositoryMetadata(repo) {
  if (!repositoryCache.has(repo)) repositoryCache.set(repo, githubJson(`/repos/${repo}`));
  return repositoryCache.get(repo);
}

async function repositoryContext(repo, revision) {
  const metadata = await repositoryMetadata(repo);
  const ref = revision || metadata.default_branch;
  const cacheKey = `${repo}@${ref}`;
  if (!contextCache.has(cacheKey)) {
    contextCache.set(cacheKey, (async () => {
      const commit = await githubJson(`/repos/${repo}/commits/${encodeURIComponent(ref)}`);
      const tree = await githubJson(`/repos/${repo}/git/trees/${commit.sha}?recursive=1`);
      if (tree.truncated) throw new Error(`GitHub returned a truncated tree for ${repo}@${commit.sha}`);
      const files = tree.tree.filter(entry => entry.type === "blob");
      return {
        repo,
        ref,
        sha: commit.sha,
        committedAt: commit.commit.committer?.date ?? commit.commit.author?.date,
        metadata,
        files,
        fileMap: new Map(files.map(entry => [entry.path, entry])),
      };
    })());
  }
  return contextCache.get(cacheKey);
}

async function readBlob(context, sha) {
  const key = `${context.repo}:${sha}`;
  if (!blobCache.has(key)) {
    blobCache.set(key, (async () => {
      const payload = await githubJson(`/repos/${context.repo}/git/blobs/${sha}`);
      if (payload.encoding !== "base64") {
        throw new Error(`Expected a base64 blob for ${context.repo}:${sha}`);
      }
      return Buffer.from(payload.content, "base64");
    })());
  }
  return blobCache.get(key);
}

async function readJsonAt(context, path) {
  const entry = context.fileMap.get(path);
  if (!entry) return null;
  return JSON.parse((await readBlob(context, entry.sha)).toString("utf8"));
}

function parseVersion(version) {
  const match = /^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$/.exec(version ?? "");
  if (!match) throw new Error(`Expected a semantic version, received ${JSON.stringify(version)}`);
  return match.slice(1).map(part => BigInt(part));
}

function compareVersions(left, right) {
  const a = parseVersion(left);
  const b = parseVersion(right);
  for (let index = 0; index < 3; index += 1) {
    if (a[index] > b[index]) return 1;
    if (a[index] < b[index]) return -1;
  }
  return 0;
}

function resolveVersion(baseVersion, context, previousEntry) {
  if (previousEntry?.source?.sha === context.sha) return previousEntry.version;

  const [major, minor] = parseVersion(baseVersion);
  const epochSeconds = Math.floor(Date.parse(context.committedAt) / 1000);
  if (!Number.isSafeInteger(epochSeconds) || epochSeconds <= 0) {
    throw new Error(`Invalid commit timestamp for ${context.repo}: ${context.committedAt}`);
  }

  let candidate = `${major}.${minor}.${epochSeconds}`;
  if (previousEntry && compareVersions(candidate, previousEntry.version) <= 0) {
    const [previousMajor, previousMinor, previousPatch] = parseVersion(previousEntry.version);
    candidate = `${previousMajor}.${previousMinor}.${previousPatch + 1n}`;
  }
  return candidate;
}

function normalizeAuthor(author) {
  if (typeof author === "string") return { name: author };
  if (!author?.name) return undefined;
  return compact({ name: author.name, email: author.email });
}

function normalizeRepository(repository) {
  if (typeof repository === "string") return repository;
  return repository?.url;
}

function licenseName(metadata) {
  const value = metadata.license?.spdx_id;
  return value && value !== "NOASSERTION" ? value : undefined;
}

function catalogSource(context, subdirectory = "") {
  if (!subdirectory || subdirectory === ".") {
    return { source: "github", repo: context.repo, ref: context.ref, sha: context.sha };
  }
  return {
    source: "git-subdir",
    url: `https://github.com/${context.repo}.git`,
    path: subdirectory,
    ref: context.ref,
    sha: context.sha,
  };
}

function sourceIdentity(source) {
  if (typeof source === "string") return `local#${source}`;
  if (source?.source === "github") return `${source.repo}#${source.path ?? ""}`;
  if (source?.source === "git-subdir") return `${parseGitHubRepository(source.url)}#${source.path}`;
  if (source?.source === "url") return `${parseGitHubRepository(source.url)}#`;
  return null;
}

function previousEntryFor(name, context, subdirectory = "") {
  const identity = sourceIdentity(catalogSource(context, subdirectory));
  return previousCatalog.plugins.find(entry => sourceIdentity(entry.source) === identity)
    ?? previousCatalog.plugins.find(entry => entry.name === name);
}

function sourceRepositorySlug(source) {
  if (typeof source === "string") return "local";
  if (source?.source === "github") return slug(source.repo);
  if (source?.source === "git-subdir" || source?.source === "url") {
    return slug(parseGitHubRepository(source.url));
  }
  return "external";
}

const AGENT_PLUGINS_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json";

// Agent Plugins v1.0.0 fixes the manifest at `plugin.json` in the plugin root (spec §5.1) and
// forbids any other file from replacing it. Check it first, then fall back to the client-specific
// locations so upstreams that predate the standard still resolve.
async function pluginManifest(context, subdirectory = "") {
  const candidates = [
    posix.join(subdirectory, "plugin.json"),
    posix.join(subdirectory, ".omp-plugin/plugin.json"),
    posix.join(subdirectory, ".claude-plugin/plugin.json"),
    posix.join(subdirectory, "package.json"),
  ];
  for (const candidate of candidates) {
    const manifest = await readJsonAt(context, candidate);
    if (manifest) return manifest;
  }
  return null;
}

// Agent Plugins §5.5: 1-64 chars, lowercase alphanumeric plus `-` and `.`, alphanumeric at both
// ends, no `--` or `..`. OMP's marketplace naming rules are the same shape, so a name that passes
// here is valid in both layers.
const AGENT_PLUGIN_NAME = /^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/;

function assertAgentPluginManifest(manifest, where) {
  if (manifest.$schema !== AGENT_PLUGINS_SCHEMA) {
    throw new Error(`${where}: plugin.json must declare "$schema": "${AGENT_PLUGINS_SCHEMA}"`);
  }
  if (typeof manifest.name !== "string" || manifest.name.length > 64 || !AGENT_PLUGIN_NAME.test(manifest.name)) {
    throw new Error(`${where}: plugin.json "name" violates Agent Plugins §5.5: ${JSON.stringify(manifest.name)}`);
  }
  const allowed = new Set(["$schema", "name", "version", "description", "author", "homepage", "repository", "license", "keywords", "extensions"]);
  const unknown = Object.keys(manifest).filter(key => !allowed.has(key));
  if (unknown.length > 0) {
    throw new Error(`${where}: plugin.json has non-conformant top-level fields: ${unknown.join(", ")}`);
  }
}

function pluginMetadata({ entry = {}, manifest = {}, context, category, description }) {
  entry ??= {};
  manifest ??= {};
  return compact({
    description: entry.description ?? manifest.description ?? description ?? context.metadata.description,
    author: normalizeAuthor(entry.author ?? manifest.author ?? { name: context.metadata.owner.login }),
    homepage: entry.homepage ?? manifest.homepage,
    repository: entry.repository ?? normalizeRepository(manifest.repository) ?? context.metadata.html_url,
    license: entry.license ?? manifest.license ?? licenseName(context.metadata),
    category: entry.category ?? category,
    tags: entry.tags ?? entry.keywords ?? manifest.keywords,
  });
}

function findMarketplacePath(context) {
  return [".omp-plugin/marketplace.json", ".claude-plugin/marketplace.json"]
    .find(path => context.fileMap.has(path));
}

async function resolveImportedSource(parentContext, source) {
  if (typeof source === "string") {
    if (!source.startsWith("./")) throw new Error(`Invalid relative plugin source: ${source}`);
    return { context: parentContext, subdirectory: source.slice(2).replace(/\/$/, "") };
  }
  if (!source || typeof source !== "object") throw new Error("Plugin source is missing");

  if (source.source === "github") {
    return {
      context: await repositoryContext(source.repo, source.ref ?? source.sha),
      subdirectory: source.path ?? "",
    };
  }
  if (source.source === "git-subdir") {
    return {
      context: await repositoryContext(parseGitHubRepository(source.url), source.ref ?? source.sha),
      subdirectory: source.path,
    };
  }
  if (source.source === "url") {
    return {
      context: await repositoryContext(parseGitHubRepository(source.url), source.ref ?? source.sha),
      subdirectory: "",
    };
  }
  throw new Error(`Unsupported imported plugin source: ${source.source}`);
}

async function importMarketplace(context, marketplace) {
  const plugins = [];
  for (const entry of marketplace.plugins ?? []) {
    const target = await resolveImportedSource(context, entry.source);
    const manifest = await pluginManifest(target.context, target.subdirectory);
    const name = entry.name ?? manifest?.name;
    if (!name) throw new Error(`Marketplace entry in ${context.repo} has no plugin name`);
    const plugin = {
      name,
      version: resolveVersion(entry.version ?? manifest?.version ?? "1.0.0", target.context, previousEntryFor(name, target.context, target.subdirectory)),
      source: catalogSource(target.context, target.subdirectory),
      ...(entry.skills === undefined ? {} : { skills: entry.skills }),
      ...pluginMetadata({ entry, manifest, context: target.context }),
    };
    plugins.push(plugin);
    await recordPluginSkills(plugin, target.context, target.subdirectory, manifest, entry.skills);
  }
  return plugins;
}

function declaredSkillPaths(manifest) {
  if (typeof manifest?.skills === "string") return [manifest.skills];
  return Array.isArray(manifest?.skills) ? manifest.skills.filter(value => typeof value === "string") : [];
}

function pathIsInside(path, directory) {
  return directory === "" || path === directory || path.startsWith(`${directory}/`);
}

async function recordPluginSkills(
  plugin,
  context,
  subdirectory = "",
  manifest = null,
  explicitSkills,
  recordMetadata = {},
) {
  const declared = explicitSkills === undefined
    ? declaredSkillPaths(manifest)
    : typeof explicitSkills === "string"
      ? [explicitSkills]
      : explicitSkills;
  const roots = new Set();
  for (const path of declared ?? []) {
    // Trailing slashes must go: pathIsInside compares against `${directory}/`, so a root of
    // "skills/" would test startsWith("skills//") and match nothing.
    const relative = path.replace(/^\.\//, "").replace(/\/+$/, "");
    roots.add(relative === "" || relative === "." ? subdirectory : posix.normalize(posix.join(subdirectory, relative)));
  }
  // Only fall back to the conventional skills/ directory when the manifest declares nothing.
  // Seeding it unconditionally makes every plugin in a multi-plugin marketplace enumerate the
  // repository's entire skills tree, duplicating each skill once per plugin.
  if (roots.size === 0) roots.add(posix.join(subdirectory, "skills"));

  const seen = new Set();
  for (const entry of context.files.filter(file => /(^|\/)SKILL\.md$/.test(file.path))) {
    if (![...roots].some(directory => pathIsInside(entry.path, directory)) || seen.has(entry.path)) continue;
    seen.add(entry.path);
    const fallback = posix.basename(posix.dirname(entry.path));
    const frontmatter = parseSkillFrontmatter((await readBlob(context, entry.sha)).toString("utf8"), fallback);
    skillRecords.push({ plugin, context, skillPath: entry.path, name: frontmatter.name, ...recordMetadata });
  }
}

async function directRepositoryPlugin(context) {
  const manifest = await pluginManifest(context);
  const [owner, repoName] = context.repo.split("/");
  const name = slug(manifest?.name ?? `${owner}-${repoName}`);
  const plugin = {
    name,
    version: resolveVersion(manifest?.version ?? "1.0.0", context, previousEntryFor(name, context)),
    source: catalogSource(context),
    ...pluginMetadata({ manifest, context }),
  };
  await recordPluginSkills(plugin, context, "", manifest);
  return plugin;
}

async function localRepositoryPlugin(context, value) {
  const directory = normalizeLocalPluginPath(value);
  const manifest = await pluginManifest(context, directory);
  if (!manifest) {
    throw new Error(`Local plugin ${directory} has no plugin.json manifest at its plugin root`);
  }
  // Plugins this repository owns are held to the Agent Plugins standard; upstream links are not,
  // since we do not control their layout.
  assertAgentPluginManifest(manifest, `Local plugin ${directory}`);
  if (typeof manifest.version !== "string") {
    throw new Error(`Local plugin ${directory} must declare a semantic version`);
  }
  parseVersion(manifest.version);
  const rawName = manifest.name ?? posix.basename(directory);
  if (typeof rawName !== "string" || !slug(rawName)) {
    throw new Error(`Local plugin ${directory} has no valid plugin name`);
  }
  const plugin = {
    name: slug(rawName),
    version: manifest.version,
    source: `./${directory}`,
    ...pluginMetadata({ manifest, context }),
  };
  await recordPluginSkills(plugin, context, directory, manifest, undefined, { linkToLastCommit: true });
  return plugin;
}

function parseSkillFrontmatter(content, fallback) {
  const frontmatter = /^---\s*\r?\n([\s\S]*?)\r?\n---/.exec(content)?.[1] ?? "";
  const field = key => {
    const value = new RegExp(`^${key}:\\s*(.*?)\\s*$`, "m").exec(frontmatter)?.[1]?.trim();
    if (!value) return undefined;
    const quote = value[0];
    return (quote === `"` || quote === `'`) && value.at(-1) === quote ? value.slice(1, -1) : value;
  };
  const name = slug(field("name") ?? fallback);
  if (!name) throw new Error(`Could not determine a skill name for ${fallback}`);
  return { name, description: field("description") };
}

async function standaloneRepositoryPlugins(context) {
  const entries = context.files.filter(entry => /(^|\/)SKILL\.md$/.test(entry.path));
  if (entries.length === 0) throw new Error(`${context.repo} contains no discoverable SKILL.md files`);

  const plugins = [];
  for (const entry of entries) {
    const directory = posix.dirname(entry.path) === "." ? "" : posix.dirname(entry.path);
    const fallback = directory ? posix.basename(directory) : context.repo.split("/")[1];
    const frontmatter = parseSkillFrontmatter((await readBlob(context, entry.sha)).toString("utf8"), fallback);
    const plugin = {
      name: frontmatter.name,
      version: resolveVersion("1.0.0", context, previousEntryFor(frontmatter.name, context, directory)),
      source: catalogSource(context, directory),
      skills: ".",
      ...pluginMetadata({ context, category: "standalone-skill", description: frontmatter.description }),
      tags: ["github-skills", "standalone-skill"],
    };
    plugins.push(plugin);
    skillRecords.push({ plugin, context, skillPath: entry.path, name: frontmatter.name });
  }
  return plugins;
}

async function lastCommitForSkill({ context, skillPath }) {
  const directory = posix.dirname(skillPath) === "." ? "" : posix.dirname(skillPath);
  const key = `${context.repo}@${context.sha}:${directory}`;
  if (!lastCommitCache.has(key)) {
    lastCommitCache.set(key, (async () => {
      const query = new URLSearchParams({ sha: context.sha, per_page: "1" });
      if (directory) query.set("path", directory);
      const commits = await githubJson(`/repos/${context.repo}/commits?${query}`);
      const commit = commits[0];
      return commit
        ? {
            sha: commit.sha,
            date: commit.commit.committer?.date ?? commit.commit.author?.date,
          }
        : { sha: context.sha, date: context.committedAt };
    })());
  }
  return lastCommitCache.get(key);
}

function formatUtc(value) {
  return `${new Date(value).toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

function renderReadme(sources, rows) {
  const lines = [
    "<!-- Generated by scripts/sync-catalog.mjs. Do not edit manually. -->",
    "",
    "# Skill Bazaar",
    "",
    sources.marketplace.description,
    "",
    "This marketplace hosts its own small plugins and links external skills directly from their owners. External sources are pinned to immutable commits, and this index is regenerated daily.",
    "",
    "## Install",
    "",
    "```bash",
    "omp plugin marketplace add clssck/agent-plugins",
    "omp plugin marketplace update agent-plugins",
    "```",
    "",
    "## Available skills",
    "",
    `${rows.length} skills across ${new Set(rows.map(row => row.plugin.name)).size} plugins. “Last updated” is the newest commit that touched that skill's directory, evaluated at the source commit used to build the catalog.`,
    "",
    "| Skill | Plugin | Repository | Last updated | Install |",
    "| --- | --- | --- | --- | --- |",
  ];

  for (const row of rows) {
    const skillRevision = row.linkToLastCommit ? row.lastCommit.sha : row.context.sha;
    const skillUrl = `https://github.com/${row.context.repo}/blob/${skillRevision}/${row.skillPath}`;
    const commitUrl = `https://github.com/${row.context.repo}/commit/${row.lastCommit.sha}`;
    lines.push(
      `| [${row.name}](${skillUrl}) | \`${row.plugin.name}\` | [${row.context.repo}](${row.context.metadata.html_url}) | [${formatUtc(row.lastCommit.date)}](${commitUrl}) | \`omp plugin install ${row.plugin.name}@${sources.marketplace.name}\` |`,
    );
  }

  lines.push(
    "",
    "## Tracked repositories",
    "",
    ...sources.repositories.map(repository => {
      const repo = parseGitHubRepository(repository);
      return `- [${repo}](https://github.com/${repo})`;
    }),
    "",
    "## Add a GitHub skill",
    "",
    "Add its repository URL to [`sources.json`](./sources.json). The resolver accepts upstream marketplaces, conventional `skills/<name>/SKILL.md` repositories, and standalone `SKILL.md` directories.",
    "",
    "The scheduled workflow refreshes upstream commits once per day. To publish a new source immediately, run:",
    "",
    "```bash",
    "gh workflow run sync-upstreams.yml --repo clssck/agent-plugins --ref main",
    "```",
    "",
  );
  return lines.join("\n");
}

const sources = JSON.parse(await readFile(sourcesPath, "utf8"));
let previousCatalog = { plugins: [] };
try {
  previousCatalog = JSON.parse(await readFile(catalogPath, "utf8"));
} catch (error) {
  if (error?.code !== "ENOENT") throw error;
}
const plugins = [];

const localPluginPaths = sources.localPlugins ?? [];
if (!Array.isArray(localPluginPaths)) throw new Error("sources.localPlugins must be an array");
if (localPluginPaths.length > 0) {
  const localContext = await repositoryContext(parseGitHubRepository(sources.repository));
  const seen = new Set();
  for (const value of localPluginPaths) {
    const directory = normalizeLocalPluginPath(value);
    if (seen.has(directory)) throw new Error(`Duplicate local plugin path: ${directory}`);
    seen.add(directory);
    plugins.push(await localRepositoryPlugin(localContext, directory));
  }
}

for (const repository of sources.repositories) {
  const repo = parseGitHubRepository(repository);
  const context = await repositoryContext(repo);
  const marketplacePath = findMarketplacePath(context);
  if (marketplacePath) {
    plugins.push(...await importMarketplace(context, await readJsonAt(context, marketplacePath)));
    continue;
  }

  const manifest = await pluginManifest(context);
  const hasConventionalSkills = context.files.some(entry => /^skills\/[^/]+\/SKILL\.md$/.test(entry.path));
  if (hasConventionalSkills || declaredSkillPaths(manifest).length > 0) {
    plugins.push(await directRepositoryPlugin(context));
  } else {
    plugins.push(...await standaloneRepositoryPlugins(context));
  }
}

const nameCounts = new Map();
for (const plugin of plugins) nameCounts.set(plugin.name, (nameCounts.get(plugin.name) ?? 0) + 1);
const usedNames = new Set(plugins.filter(plugin => nameCounts.get(plugin.name) === 1).map(plugin => plugin.name));
for (const plugin of plugins.filter(plugin => nameCounts.get(plugin.name) > 1)) {
  const base = slug(`${sourceRepositorySlug(plugin.source)}-${plugin.name}`);
  let candidate = base;
  let suffix = 2;
  while (usedNames.has(candidate)) candidate = `${base}-${suffix++}`;
  plugin.name = candidate;
  usedNames.add(candidate);
}

const readmeRows = await Promise.all(
  skillRecords.map(async record => ({ ...record, lastCommit: await lastCommitForSkill(record) })),
);
readmeRows.sort((left, right) => {
  if (left.name !== right.name) return left.name < right.name ? -1 : 1;
  return left.plugin.name < right.plugin.name ? -1 : left.plugin.name > right.plugin.name ? 1 : 0;
});

const catalog = {
  name: sources.marketplace.name,
  owner: sources.marketplace.owner,
  metadata: { description: sources.marketplace.description },
  plugins,
};
const rendered = `${JSON.stringify(catalog, null, 2)}\n`;
const current = await readFile(catalogPath, "utf8").catch(() => "");
if (current === rendered) {
  console.log("Marketplace catalog is current.");
} else {
  await writeFile(catalogPath, rendered);
  console.log(`Updated ${catalogPath}`);
}

const readme = `${renderReadme(sources, readmeRows)}\n`;
const currentReadme = await readFile(readmePath, "utf8").catch(() => "");
if (currentReadme === readme) {
  console.log("README skill index is current.");
} else {
  await writeFile(readmePath, readme);
  console.log(`Updated ${readmePath}`);
}
