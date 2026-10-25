import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { checkSkill } from "./check-skill";

let root: string;
let dir: string;

const VALID = `---
name: demo
description: Demo skill for tests.
---

# Demo

Read [the guide](skill://demo/references/guide.md#first-step) before starting.

<critical>
- MUST read the guide first.
</critical>
`;

async function skill(body: string, name = "demo"): Promise<string> {
  dir = path.join(root, name);
  await mkdir(path.join(dir, "references"), { recursive: true });
  await writeFile(path.join(dir, "SKILL.md"), body);
  await writeFile(path.join(dir, "references/guide.md"), "# Guide\n\n## First step\n\nDo it.\n");
  return dir;
}

beforeEach(async () => {
  root = await mkdtemp(path.join(tmpdir(), "check-skill-"));
});
afterEach(() => rm(root, { recursive: true, force: true }));

describe("checkSkill", () => {
  test("a valid skill has no problems", async () => {
    expect(await checkSkill(await skill(VALID))).toEqual([]);
  });

  test("frontmatter name must equal the directory name", async () => {
    const problems = await checkSkill(await skill(VALID.replace("name: demo", "name: other")));
    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain('must equal the directory name "demo"');
  });

  test("an empty description is rejected", async () => {
    const problems = await checkSkill(
      await skill(VALID.replace("description: Demo skill for tests.", "description:")),
    );
    expect(problems.join("\n")).toContain("description must be a non-empty string");
  });

  test("missing frontmatter and a missing SKILL.md are reported", async () => {
    expect((await checkSkill(await skill("# Demo\n"))).join("\n")).toContain(
      "must start with YAML frontmatter",
    );
    await rm(path.join(dir, "SKILL.md"));
    expect(await checkSkill(dir)).toEqual([`${dir}: SKILL.md does not exist`]);
  });

  test("semantic tags out of order are reported with their line", async () => {
    const body = `${VALID}\n<caution>\nNEVER skip.\n</caution>\n\n<instruction>\nSHOULD check.\n</instruction>\n`;
    const problems = await checkSkill(await skill(body));
    expect(
      problems.some((problem) => /SKILL\.md:\d+: <instruction> is out of order/.test(problem)),
    ).toBe(true);
  });

  test("a link to a missing file is reported with its file and line", async () => {
    const problems = await checkSkill(
      await skill(`${VALID}\nSee skill://demo/references/missing.md.\n`),
    );
    expect(problems).toHaveLength(1);
    expect(problems[0]).toMatch(
      /SKILL\.md:\d+: skill:\/\/demo\/references\/missing\.md does not exist in demo$/,
    );
  });

  test("a stale anchor is reported, a live one passes, in references too", async () => {
    await skill(VALID);
    await writeFile(
      path.join(dir, "references/other.md"),
      "See skill://demo/references/guide.md#gone and skill://demo/references/guide.md#first-step.\n",
    );
    const problems = await checkSkill(dir);
    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain("references/other.md:1:");
    expect(problems[0]).toContain('has no heading "#gone"');
  });

  test("a link naming another skill is rejected", async () => {
    const problems = await checkSkill(await skill(`${VALID}\nSee skill://other/SKILL.md.\n`));
    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain("only skill://demo/... links are allowed outside a pack");
  });

  test("a link escaping the skill directory is rejected even when the target exists", async () => {
    await writeFile(path.join(root, "outside.md"), "# Outside\n");
    const problems = await checkSkill(await skill(`${VALID}\nSee skill://demo/../outside.md.\n`));
    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain('skill URI escapes "demo"');
  });

  test("links inside fenced examples still resolve like pack links do", async () => {
    const problems = await checkSkill(
      await skill(`${VALID}\n\`\`\`\nskill://demo/references/nope.md\n\`\`\`\n`),
    );
    expect(problems).toHaveLength(1);
  });
});

describe("check-skill CLI", () => {
  const script = path.join(import.meta.dir, "check-skill.ts");
  async function run(...args: string[]) {
    const proc = Bun.spawn(["bun", script, ...args], { stdout: "pipe", stderr: "pipe" });
    const [stdout, stderr, code] = await Promise.all([
      new Response(proc.stdout).text(),
      new Response(proc.stderr).text(),
      proc.exited,
    ]);
    return { stdout, stderr, code };
  }

  test("exits 0 with a one-line summary for passing skills", async () => {
    const result = await run(await skill(VALID));
    expect(result.code).toBe(0);
    expect(result.stdout.trim().split("\n")).toHaveLength(1);
    expect(result.stdout).toContain("demo");
  });

  test("exits 1 listing every problem across all directories", async () => {
    const good = await skill(VALID);
    const bad = await skill(`${VALID}\nSee skill://bad/missing.md.\n`, "bad");
    const result = await run(good, bad);
    expect(result.code).toBe(1);
    expect(result.stderr).toContain("SKILL.md:");
    expect(result.stderr).toContain("frontmatter name");
  });

  test("exits 2 with usage when no directory is given", async () => {
    const result = await run();
    expect(result.code).toBe(2);
    expect(result.stderr).toContain("usage:");
  });
});
