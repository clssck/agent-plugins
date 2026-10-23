import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, realpath, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import * as path from "node:path";

const SCRIPT = path.resolve(import.meta.dir, "check-omp-loader.ts");
const LOCK_PATH = path.resolve(import.meta.dir, "..", "omp-source-lock.json");

let dir: string;

beforeEach(async () => {
	dir = await realpath(await mkdtemp(path.join(tmpdir(), "omp-pin-")));
});
afterEach(() => rm(dir, { recursive: true, force: true }));

function git(cwd: string, ...args: string[]): string {
	const result = Bun.spawnSync(
		["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", ...args],
		{ cwd, stdout: "pipe", stderr: "pipe" },
	);
	if (result.exitCode !== 0) throw new Error(result.stderr.toString());
	return result.stdout.toString().trim();
}

function runSmoke(ompRoot: string) {
	const result = Bun.spawnSync(["bun", SCRIPT], {
		env: { ...process.env, OMP_ROOT: ompRoot },
		stdout: "pipe",
		stderr: "pipe",
	});
	return { code: result.exitCode, stderr: result.stderr.toString() };
}

describe("host-loader pin gate", () => {
	test("a checkout at a different commit is refused with both full SHAs, before any host module loads", async () => {
		git(dir, "init", "-q");
		git(dir, "commit", "-q", "--allow-empty", "-m", "unreviewed");
		const actual = git(dir, "rev-parse", "HEAD");
		const lock: unknown = await Bun.file(LOCK_PATH).json();
		const expected = lock && typeof lock === "object" && "reviewedCommit" in lock ? String(lock.reviewedCommit) : "";
		expect(actual).not.toBe(expected);

		const { code, stderr } = runSmoke(dir);
		expect(code).toBe(1);
		expect(stderr).toContain(expected);
		expect(stderr).toContain(actual);
		// The temporary checkout has no OMP sources: reaching module loading would fail with a resolution error instead.
		expect(stderr).not.toContain("Cannot find module");
	});

	test("a directory that is not the root of a Git checkout is refused", async () => {
		const plain = runSmoke(dir);
		expect(plain.code).toBe(2);
		expect(plain.stderr).toContain("not the root of a Git checkout");

		git(dir, "init", "-q");
		git(dir, "commit", "-q", "--allow-empty", "-m", "unreviewed");
		const nested = path.join(dir, "packages");
		await mkdir(nested);
		const sub = runSmoke(nested);
		expect(sub.code).toBe(2);
		expect(sub.stderr).toContain("not the root of a Git checkout");
	});
});
