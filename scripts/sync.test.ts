import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { chmod, mkdir, mkdtemp, rm, symlink, truncate, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { generatedTreeDigest, generatedTreeProblems, inspectPack, stampGeneratedTree, upstreamPath } from "./sync";

let dir: string;

/** A generated pack as fetch leaves it: files, a nested directory, and a stamped package.json. */
async function stampedPack(): Promise<void> {
	await mkdir(path.join(dir, "skills/demo"), { recursive: true });
	await writeFile(path.join(dir, "skills/demo/SKILL.md"), "---\nname: demo\ndescription: demo\n---\nBody\n");
	await writeFile(path.join(dir, "LICENSE"), "MIT\n");
	await writeFile(
		path.join(dir, "package.json"),
		`${JSON.stringify({ name: "demo", version: "0.0.0-gabc", sync: { build: "b", origins: { skills: "skills" } }, omp: {} }, null, 2)}\n`,
	);
	await stampGeneratedTree(dir);
}

beforeEach(async () => {
	dir = await mkdtemp(path.join(tmpdir(), "sync-integrity-"));
});
afterEach(() => rm(dir, { recursive: true, force: true }));

describe("upstream paths", () => {
	test("resolves a curated skill directory from its SKILL.md origin", () => {
		const pack: Parameters<typeof upstreamPath>[0] = {
			name: "demo-skills",
			dir: "upstream/demo-skills",
			version: "0.0.0-g2d22863",
			attribution: false,
			skillReferences: {},
			skills: [],
			rules: [],
			agents: [],
			commands: [],
			tools: [],
			extensions: 0,
			origins: { "skills/animate/SKILL.md": "skills/animate/SKILL.md" },
		};
		expect(upstreamPath(pack, "skills/animate")).toBe("skills/animate");
		expect(upstreamPath(pack, "skills/animate/SKILL.md")).toBe("skills/animate/SKILL.md");
	});
});

describe("generated tree integrity", () => {
	test("a stamped tree has no problems", async () => {
		await stampedPack();
		expect(await generatedTreeProblems(dir)).toEqual([]);
	});

	test("stamping is deterministic and replaces any previous digest", async () => {
		await stampedPack();
		const first = await Bun.file(path.join(dir, "package.json")).text();
		await stampGeneratedTree(dir);
		expect(await Bun.file(path.join(dir, "package.json")).text()).toBe(first);
	});

	test("the recorded digest value never influences the digest", async () => {
		await stampedPack();
		const before = await generatedTreeDigest(dir);
		const manifestPath = path.join(dir, "package.json");
		const manifest = await Bun.file(manifestPath).json();
		manifest.sync.tree = "sha256:garbage";
		await Bun.write(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
		expect(await generatedTreeDigest(dir)).toBe(before);
	});

	test("editing a file fails", async () => {
		await stampedPack();
		await writeFile(path.join(dir, "skills/demo/SKILL.md"), "---\nname: demo\ndescription: demo\n---\nEdited\n");
		expect((await generatedTreeProblems(dir)).join("\n")).toContain("generated tree was modified");
	});

	test("adding a file fails", async () => {
		await stampedPack();
		await writeFile(path.join(dir, "skills/demo/extra.md"), "added\n");
		expect((await generatedTreeProblems(dir)).join("\n")).toContain("generated tree was modified");
	});

	test("adding a normally skipped artifact fails", async () => {
		await stampedPack();
		await writeFile(path.join(dir, ".DS_Store"), "added\n");
		expect((await generatedTreeProblems(dir)).join("\n")).toContain("generated tree was modified");
	});

	test("removing a file fails", async () => {
		await stampedPack();
		await rm(path.join(dir, "LICENSE"));
		expect((await generatedTreeProblems(dir)).join("\n")).toContain("generated tree was modified");
	});

	test("changing the executable bit fails", async () => {
		await stampedPack();
		await chmod(path.join(dir, "LICENSE"), 0o755);
		expect((await generatedTreeProblems(dir)).join("\n")).toContain("generated tree was modified");
	});

	test("editing package.json outside sync.tree fails", async () => {
		await stampedPack();
		const manifestPath = path.join(dir, "package.json");
		const manifest = await Bun.file(manifestPath).json();
		manifest.description = "injected";
		await Bun.write(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
		expect((await generatedTreeProblems(dir)).join("\n")).toContain("generated tree was modified");
	});

	test("a forged digest that does not match the contents fails", async () => {
		await stampedPack();
		const manifestPath = path.join(dir, "package.json");
		const manifest = await Bun.file(manifestPath).json();
		manifest.sync.tree = `sha256:${"0".repeat(64)}`;
		await Bun.write(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
		expect((await generatedTreeProblems(dir)).join("\n")).toContain("generated tree was modified");
	});

	test("a manifest without a digest fails", async () => {
		await stampedPack();
		const manifestPath = path.join(dir, "package.json");
		const manifest = await Bun.file(manifestPath).json();
		delete manifest.sync.tree;
		await Bun.write(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
		expect((await generatedTreeProblems(dir)).join("\n")).toContain("no sync.tree digest");
	});

	test("a hand-formatted package.json fails", async () => {
		await stampedPack();
		const manifestPath = path.join(dir, "package.json");
		await Bun.write(manifestPath, JSON.stringify(await Bun.file(manifestPath).json()));
		expect((await generatedTreeProblems(dir)).join("\n")).toContain("not in the form fetch writes");
	});

	test("a missing or malformed package.json fails", async () => {
		expect(await generatedTreeProblems(dir)).toEqual(["missing package.json"]);
		await writeFile(path.join(dir, "package.json"), "{");
		expect(await generatedTreeProblems(dir)).toEqual(["package.json is not valid JSON"]);
	});

	test("files larger than the generated-pack policy are rejected without being read", async () => {
		await stampedPack();
		const oversized = path.join(dir, "oversized.bin");
		await writeFile(oversized, "");
		await truncate(oversized, 16 * 1024 * 1024 + 1);
		expect((await generatedTreeProblems(dir)).join("\n")).toContain("exceeds 16 MiB limit");
		await expect(stampGeneratedTree(dir)).rejects.toThrow("exceeds 16 MiB limit");
	});

	test("symlinks are rejected by the check and never stamped", async () => {
		await stampedPack();
		await symlink("LICENSE", path.join(dir, "LICENSE.link"));
		expect((await generatedTreeProblems(dir)).join("\n")).toContain("LICENSE.link (symlink)");
		let failure = "";
		try {
			await stampGeneratedTree(dir);
		} catch (error) {
			failure = String(error);
		}
		expect(failure).toContain("LICENSE.link (symlink)");
	});

	test("a symlinked directory is rejected, not followed", async () => {
		await stampedPack();
		await symlink(path.join(dir, "skills"), path.join(dir, "skills-alias"));
		expect((await generatedTreeProblems(dir)).join("\n")).toContain("skills-alias (symlink)");
	});

});

describe("pack inspection", () => {
	async function pack(omp: unknown, rules: Record<string, string> = {}): Promise<string> {
		const packDir = path.join(dir, "demo");
		await mkdir(path.join(packDir, "rules"), { recursive: true });
		await writeFile(path.join(packDir, "package.json"), JSON.stringify({ name: "demo", version: "1.0.0", omp }));
		for (const [name, content] of Object.entries(rules)) await writeFile(path.join(packDir, "rules", name), content);
		return packDir;
	}

	test("an omp manifest field must be a non-null, non-array object", async () => {
		for (const omp of [null, [], "x", 1]) {
			const errors: string[] = [];
			await inspectPack(await pack(omp), undefined, errors);
			expect(errors.join("\n")).toContain('needs an "omp" object');
		}
		const errors: string[] = [];
		await inspectPack(await pack({}), undefined, errors);
		expect(errors).toEqual([]);
	});

	test("rules whose frontmatter sets enabled: false are not discovered, like OMP", async () => {
		const errors: string[] = [];
		const inspected = await inspectPack(
			await pack({}, {
				"on.md": "---\ncondition: x\n---\nBody\n",
				"off.md": "---\nenabled: false\ncondition: x\n---\nBody\n",
				"plain.md": "Body\n",
			}),
			undefined,
			errors,
		);
		expect(inspected?.rules.map(rule => rule.name).sort()).toEqual(["on", "plain"]);
	});
});
