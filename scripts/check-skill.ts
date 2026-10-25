#!/usr/bin/env bun
// Gate for skills shipped outside packs (for example clssck/atl-cli's skills/atl): `bun scripts/check-skill.ts <skill-dir>...`.
// Per directory: SKILL.md frontmatter (name equals the directory name, non-empty description), the payload grammar,
// and every skill:// link in every .md file. An external skill cannot declare cross-pack providers, so a link
// may only name the skill itself. Static: no network, no token.

import { readdir } from "node:fs/promises";
import * as path from "node:path";
import { payloadProblems } from "./payload-grammar";
import { skillLinkProblem, skillLinks } from "./skill-links";
import { frontmatter } from "./sync";

/** Problems for one skill directory, each as `<file>:<line>: <message>`; empty when the skill passes. */
export async function checkSkill(dir: string): Promise<string[]> {
  const baseDir = path.resolve(dir);
  const name = path.basename(baseDir);
  const skillFile = Bun.file(path.join(baseDir, "SKILL.md"));
  const at = (file: string, line: number, message: string) =>
    `${path.join(dir, file)}:${line}: ${message}`;
  if (!(await skillFile.exists())) {
    return [`${dir}: SKILL.md does not exist`];
  }

  const problems: string[] = [];
  const body = await skillFile.text();
  const meta = frontmatter(body);
  if (!meta) {
    problems.push(at("SKILL.md", 1, "must start with YAML frontmatter"));
  } else {
    if (meta.name !== name) {
      problems.push(
        at(
          "SKILL.md",
          1,
          `frontmatter name ${JSON.stringify(meta.name)} must equal the directory name "${name}"`,
        ),
      );
    }
    if (typeof meta.description !== "string" || !meta.description.trim()) {
      problems.push(at("SKILL.md", 1, "frontmatter description must be a non-empty string"));
    }
  }
  for (const problem of payloadProblems("skill", body)) {
    problems.push(at("SKILL.md", problem.line, problem.message));
  }

  const files = (await readdir(baseDir, { recursive: true }))
    .filter(
      (file) =>
        /\.md$/i.test(file) && !file.split(path.sep).some((segment) => segment.startsWith(".")),
    )
    .toSorted();
  for (const file of files) {
    const contents = file === "SKILL.md" ? body : await Bun.file(path.join(baseDir, file)).text();
    for (const link of skillLinks(contents)) {
      const source = file.split(path.sep).join("/");
      if (link.root !== name.toLowerCase()) {
        problems.push(
          at(
            source,
            link.line,
            `skill://${link.root}${link.rawPath}: only skill://${name}/... links are allowed outside a pack`,
          ),
        );
        continue;
      }
      const problem = await skillLinkProblem(link, baseDir, name);
      if (problem) {
        problems.push(at(source, link.line, problem));
      }
    }
  }
  return problems;
}

if (import.meta.main) {
  const dirs = process.argv.slice(2);
  if (dirs.length === 0) {
    process.stderr.write("usage: bun scripts/check-skill.ts <skill-dir>...\n");
    process.exit(2);
  }
  const problems = (await Promise.all(dirs.map(checkSkill))).flat();
  if (problems.length > 0) {
    process.stderr.write(`${problems.length} skill problem(s):\n`);
    for (const problem of problems) {
      process.stderr.write(`  - ${problem}\n`);
    }
    process.exit(1);
  }
  process.stdout.write(
    `${dirs.length} skill(s) checked: ${dirs.map((dir) => path.basename(path.resolve(dir))).join(", ")}: no problems\n`,
  );
}
