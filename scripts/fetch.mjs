#!/usr/bin/env node
// Materialize every upstream pack from sources.json into upstream/<name>/ at its pinned commit.
// Packs already at their pin are left untouched, so `omp plugin link` symlinks stay valid.

import { spawn } from "node:child_process";
import { cp, mkdir, mkdtemp, readdir, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { Readable } from "node:stream";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const upstreamDir = join(root, "upstream");
const PIN_FILE = ".pin";

const sources = JSON.parse(await readFile(join(root, "sources.json"), "utf8"));

async function exists(path) {
  try {
    await stat(path);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

async function currentPin(name) {
  try {
    return (await readFile(join(upstreamDir, name, PIN_FILE), "utf8")).trim();
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

async function extractTarball(repo, sha, destination) {
  const response = await fetch(`https://codeload.github.com/${repo}/tar.gz/${sha}`);
  if (!response.ok) throw new Error(`Download failed for ${repo}@${sha}: HTTP ${response.status}`);
  const tar = spawn("tar", ["-xzf", "-", "-C", destination, "--strip-components=1"], {
    stdio: ["pipe", "ignore", "pipe"],
  });
  let stderr = "";
  tar.stderr.on("data", chunk => (stderr += chunk));
  const exited = new Promise((resolveExit, rejectExit) => {
    tar.on("error", rejectExit);
    tar.on("close", code => (code === 0 ? resolveExit() : rejectExit(new Error(`tar exited ${code}: ${stderr}`))));
  });
  Readable.fromWeb(response.body).pipe(tar.stdin);
  await exited;
}

function packageManifest(upstream) {
  return {
    name: upstream.name,
    version: `0.0.0-g${upstream.sha.slice(0, 7)}`,
    private: true,
    description: upstream.description,
    homepage: `https://github.com/${upstream.repo}/tree/${upstream.sha}`,
    repository: `https://github.com/${upstream.repo}`,
    omp: {},
  };
}

async function buildPack(upstream) {
  const scratch = await mkdtemp(join(tmpdir(), `agent-plugins-${upstream.name}-`));
  try {
    const checkout = join(scratch, "src");
    const staged = join(scratch, "pack");
    await mkdir(checkout);
    await mkdir(staged);
    await extractTarball(upstream.repo, upstream.sha, checkout);

    for (const [from, to] of Object.entries(upstream.include)) {
      const source = join(checkout, from);
      if (!(await exists(source))) throw new Error(`${upstream.name}: ${from} is missing at ${upstream.sha}`);
      await cp(source, join(staged, to), { recursive: true });
    }
    // Keep the upstream license next to the content it covers.
    for (const entry of await readdir(checkout)) {
      if (/^(licen[cs]e|copying|notice)/i.test(entry)) await cp(join(checkout, entry), join(staged, entry));
    }
    await writeFile(join(staged, "package.json"), `${JSON.stringify(packageManifest(upstream), null, 2)}\n`);
    await writeFile(join(staged, PIN_FILE), `${upstream.sha}\n`);

    // Swap in place: the directory path is what `omp plugin link` points at.
    const target = join(upstreamDir, upstream.name);
    await rm(target, { recursive: true, force: true });
    await rename(staged, target);
  } finally {
    await rm(scratch, { recursive: true, force: true });
  }
}

await mkdir(upstreamDir, { recursive: true });
const wanted = new Set(sources.upstreams.map(upstream => upstream.name));

for (const upstream of sources.upstreams) {
  if ((await currentPin(upstream.name)) === upstream.sha) {
    console.log(`= ${upstream.name} ${upstream.sha.slice(0, 7)}`);
    continue;
  }
  await buildPack(upstream);
  console.log(`↓ ${upstream.name} ${upstream.sha.slice(0, 7)}`);
}

// Drop packs this script built earlier that sources.json no longer lists.
for (const entry of await readdir(upstreamDir, { withFileTypes: true })) {
  if (!entry.isDirectory() || wanted.has(entry.name)) continue;
  if (await exists(join(upstreamDir, entry.name, PIN_FILE))) {
    await rm(join(upstreamDir, entry.name), { recursive: true, force: true });
    console.log(`- ${entry.name} (removed from sources.json; run \`omp plugin uninstall ${entry.name}\` if linked)`);
  }
}
