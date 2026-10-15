import { describe, expect, test } from "bun:test";
import { readdir } from "node:fs/promises";
import * as path from "node:path";

const RULES = path.join(path.resolve(import.meta.dir, ".."), "packs", "clssck-core", "rules");

/** Same translation as OMP's compileRuleCondition: a leading `(?ims)` group becomes native RegExp flags. */
function compileCondition(pattern: string): RegExp {
	const match = /^\(\?([a-z]+)\)/.exec(pattern);
	if (match && /^[ims]+$/.test(match[1])) return new RegExp(pattern.slice(match[0].length), Array.from(new Set(match[1])).join(""));
	return new RegExp(pattern);
}

const rules = new Map<string, RegExp[]>();
for (const file of (await readdir(RULES)).filter(name => name.endsWith(".md")).sort()) {
	const source = await Bun.file(path.join(RULES, file)).text();
	const end = source.indexOf("\n---", 3);
	const { condition } = Bun.YAML.parse(source.slice(4, end)) as { condition?: string | string[] };
	const conditions = condition === undefined ? [] : Array.isArray(condition) ? condition : [condition];
	rules.set(file.slice(0, -".md".length), conditions.map(compileCondition));
}

function matches(rule: string, text: string): boolean {
	const conditions = rules.get(rule);
	if (!conditions) throw new Error(`unknown rule ${rule}`);
	return conditions.some(condition => condition.test(text));
}

/** SQL fixtures are assembled so this file is not itself destructive SQL text. */
const sql = (...parts: string[]) => parts.join("");

/** Bash rules see raw streamed arguments and the final `{"command":"..."}` JSON snapshot. */
const bashCases: Record<string, { flagged: string[]; ignored: string[] }> = {
	"build-cache-deletion-safety": {
		flagged: ["rm -rf node_modules", "rm -r -f target", "sudo rm -rf ~/.cache/uv", "cargo clean", "uv cache clean"],
		ignored: ["rm file.txt", "ls node_modules", "grep -rn node_modules src", "rm -rf scratch"],
	},
	"dbt-command-scope": {
		flagged: ["dbt build", "uv run dbt test", "dbt run --select x --empty", "dbt build -s x --full-refresh"],
		ignored: ["dbt run --select my_model", "dbt test -s my_model", "dbt ls", "dbt compile", "dbt docs generate"],
	},
	"docker-data-safety": {
		flagged: ["docker system prune -af", "podman volume rm data", "docker volume prune", "docker compose down -v", "docker builder prune"],
		ignored: ["docker ps", "docker volume ls", "docker compose down", "docker inspect web"],
	},
	"gh-external-mutation-safety": {
		flagged: ["gh pr create --title x", "gh pr merge 12", "gh issue comment 3 --body hi", "gh release create v1", "gh api -X POST repos/o/r/issues", "gh api repos/o/r/labels -f name=x"],
		ignored: ["gh pr view 12", "gh pr list", "gh issue view 3", "gh api repos/o/r", "gh repo view"],
	},
	"git-commit-conventions": {
		flagged: ["git add -A", "git add .", "git add -u", "git commit -a -m x", "git commit -am x", "git -C repo add --all"],
		ignored: ["git add src/a.ts", "git add -A src", "git commit -m x", "git commit --amend", "git add -p"],
	},
	"git-push-safety": {
		flagged: ["git push", "git push --force origin feature", "git -C repo push origin main", "cd repo && git push origin main", `bash -c "git push"`],
		ignored: ["git push --dry-run origin main", "git push -n", "git status", "git log origin/main"],
	},
	"git-worktree-restore-safety": {
		flagged: ["git restore .", "git checkout -- .", "git clean -fd", "git reset --hard", "git stash drop", "git worktree remove --force ../wt"],
		ignored: ["git status", "git diff", "git clean -n", "git checkout main", "git worktree remove ../wt"],
	},
	"sql-mutation-safety": {
		flagged: [`psql -c '${sql("DELETE", " FROM users")}'`, `snowsql -q '${sql("TRUNCATE", " TABLE users;")}'`, `psql -c '${sql("TRUNCATE", " orders")}'`, `psql -c '${sql("DROP", " TABLE users")}'`, "rails db:drop", "alembic downgrade -1"],
		ignored: ["psql -c 'select 1'", "psql -c 'SELECT * FROM users'", "rails db:migrate", "dbt run-operation noop", "python -c 'f.truncate(0)'", "truncate -s 0 app.log"],
	},
	"temp-cleanup-ownership": {
		flagged: ["rm -rf /tmp/*", "rm -rf $TMPDIR/*", "rm -f /tmp/build-?", "find /tmp -mtime +1 -delete", "find /tmp -name '*.log' | xargs rm"],
		ignored: ["ls /tmp", "rm -rf /tmp/mydir-123", "find /tmp -name x"],
	},
};

describe("shipped rules", () => {
	test("every condition compiles the way OMP compiles it", () => {
		for (const [rule, conditions] of rules) expect(conditions.length, rule).toBeGreaterThan(0);
	});

	test("bash cases cover every bash-scoped rule", () => {
		expect(Object.keys(bashCases).sort()).toEqual(
			[...rules.keys()]
				.filter(
					rule =>
						![
							"dbt-test-arguments",
							"lint-suppression",
							"no-silent-scope-shrink",
							"no-source-grep-tests",
							"no-unverified-test-claims",
						].includes(rule),
				)
				.sort(),
		);
	});
});

describe("bash rules", () => {
	for (const [rule, cases] of Object.entries(bashCases)) {
		test(rule, () => {
			for (const command of cases.flagged) {
				expect(matches(rule, command), command).toBe(true);
				expect(matches(rule, JSON.stringify({ command })), `JSON ${command}`).toBe(true);
			}
			for (const command of cases.ignored) {
				expect(matches(rule, command), command).toBe(false);
				expect(matches(rule, JSON.stringify({ command })), `JSON ${command}`).toBe(false);
			}
		});
	}

	test("exclusions stop at a JSON-escaped newline but not at escaped quotes", () => {
		for (const [rule, command, flagged] of [
			["git-push-safety", "git push origin main\ngit log -n 3", true],
			["git-push-safety", `git push "origin" --dry-run`, false],
			["dbt-command-scope", "dbt build\ndbt ls -s x", true],
			["dbt-command-scope", `dbt build -s "x"`, false],
		] as const) {
			expect(matches(rule, JSON.stringify({ command })), command).toBe(flagged);
		}
	});
});

describe("source rules", () => {
	test("sql-mutation-safety flags destructive SQL in eval code", () => {
		expect(matches("sql-mutation-safety", `db.execute("${sql("DELETE", " FROM users")} WHERE id = 1")`)).toBe(true);
		expect(matches("sql-mutation-safety", `db.execute("SELECT * FROM users")`)).toBe(false);
	});

	test("temp-cleanup-ownership flags pattern deletion in shared temp directories", () => {
		expect(matches("temp-cleanup-ownership", `for path in Path("/tmp").glob("*"): path.unlink()`)).toBe(true);
		expect(matches("temp-cleanup-ownership", `for path in glob.glob("/tmp/x*"): os.remove(path)`)).toBe(true);
		expect(matches("temp-cleanup-ownership", `Path(workdir).unlink()`)).toBe(false);
	});

	test("dbt-test-arguments flags legacy top-level test parameters", () => {
		expect(matches("dbt-test-arguments", "- accepted_values:\n    values: [a]\n")).toBe(true);
		expect(matches("dbt-test-arguments", "- relationships: {to: ref('x'), field: id}\n")).toBe(true);
		expect(matches("dbt-test-arguments", "- accepted_values:\n    arguments:\n      values: [a]\n")).toBe(false);
		expect(matches("dbt-test-arguments", "- relationships: {arguments: {to: ref('x'), field: id}}\n")).toBe(false);
		expect(matches("dbt-test-arguments", "- accepted_values:\n    store_failures: true\n    arguments:\n      values: [a]\n")).toBe(false);
	});

	test("lint-suppression flags blanket suppressions only", () => {
		for (const flagged of ["x = f()  # noqa\n", "x = f()  # type: ignore\n", "# ruff: noqa\n", "#![allow(dead_code)]\n", "#[allow(clippy::all)]\n", "// @ts-ignore\n", "/* eslint-disable */\n", "// eslint-disable-next-line\n"]) {
			expect(matches("lint-suppression", flagged), flagged).toBe(true);
		}
		for (const named of ["x = f()  # noqa: S603\n", "x = f()  # type: ignore[arg-type]\n", "#[allow(dead_code)]\n", `#[allow(clippy::cargo_common_metadata, reason = "x")]\n`, "// eslint-disable-next-line no-console -- reason\n", "// @ts-expect-error reason\n"]) {
			expect(matches("lint-suppression", named), named).toBe(false);
		}
	});
});
