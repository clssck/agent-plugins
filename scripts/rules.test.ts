import { describe, expect, test } from "bun:test";
import { readdir } from "node:fs/promises";
import * as path from "node:path";

const RULES = path.join(path.resolve(import.meta.dir, ".."), "packs", "clssck-core", "rules");

/**
 * Local approximation of how a rule `condition` is compiled: a leading `(?ims)` group becomes native RegExp flags.
 * Canonical host compilation is exercised by the loader smoke, not here.
 */
function compileCondition(pattern: string): RegExp {
	const match = /^\(\?([a-z]+)\)/.exec(pattern);
	if (match && /^[ims]+$/.test(match[1])) return new RegExp(pattern.slice(match[0].length), Array.from(new Set(match[1])).join(""));
	return new RegExp(pattern);
}

interface Rule {
	conditions: RegExp[];
	question?: string;
	scope: string[];
}

const rules = new Map<string, Rule>();
for (const file of (await readdir(RULES)).filter(name => name.endsWith(".md")).sort()) {
	const source = await Bun.file(path.join(RULES, file)).text();
	const end = source.indexOf("\n---", 3);
	const meta = Bun.YAML.parse(source.slice(4, end)) as { condition?: string | string[]; question?: string; scope?: string };
	const conditions = meta.condition === undefined ? [] : Array.isArray(meta.condition) ? meta.condition : [meta.condition];
	rules.set(file.slice(0, -".md".length), {
		conditions: conditions.map(compileCondition),
		question: meta.question,
		scope: (meta.scope ?? "").split(/,\s*(?=tool:|text|thinking)/).filter(Boolean),
	});
}

function matches(name: string, text: string): boolean {
	const rule = rules.get(name);
	if (!rule) throw new Error(`unknown rule ${name}`);
	return rule.conditions.some(condition => condition.test(text));
}

/** Fixtures for destructive SQL and blanket lint suppressions are assembled so this file never contains them verbatim. */
const join = (...parts: string[]) => parts.join("");

interface Cases {
	flagged: string[];
	ignored: string[];
}

/** Bash rules see raw streamed arguments and the final `{"command":"..."}` JSON snapshot. */
const bashCases: Record<string, Cases> = {
	"build-cache-deletion-safety": {
		flagged: [
			"rm -rf node_modules",
			"rm -r -f target",
			"rm -fr dist",
			"rm --recursive --force .venv",
			"sudo rm -rf ~/.cache/uv",
			"cargo clean",
			"bazel clean --expunge",
			"uv cache clean",
			"npm cache clean --force",
			"pnpm store prune",
			"go clean -modcache",
		],
		ignored: [
			"rm file.txt",
			"rm node_modules/.package-lock.json",
			"ls node_modules",
			"grep -rn node_modules src",
			"rm -rf scratch",
			"cargo build",
			"npm cache verify",
			"go clean -x",
			"uv sync",
		],
	},
	"dbt-command-scope": {
		flagged: [
			"dbt build",
			"dbt run",
			"dbt seed",
			"dbt snapshot",
			"dbt clone --state prod-artifacts",
			"uv run dbt test",
			"dbt run --select x --empty",
			"dbt build -s x --full-refresh",
			"dbt build --target prod --full-refresh --select x",
		],
		ignored: [
			"dbt run --select my_model",
			"dbt test -s my_model",
			"dbt build --selector nightly",
			"dbt build --select=fct_orders+",
			"dbt ls",
			"dbt compile",
			"dbt docs generate",
			"dbt deps",
			"dbt run-operation clean_stale_models",
			"dbt run-operation grant_select --args '{role: analyst}'",
		],
	},
	"docker-data-safety": {
		flagged: [
			"docker system prune -af",
			"docker image prune -a",
			"podman volume rm data",
			"docker volume remove data",
			"docker volume prune",
			"docker compose down -v",
			"docker-compose down --volumes",
			"podman-compose down -v",
			"docker compose down --rmi all",
			"docker builder prune",
		],
		ignored: [
			"docker ps",
			"docker images",
			"docker volume ls",
			"docker compose up -d",
			"docker compose down",
			"docker compose down --remove-orphans",
			"docker rm web",
			"docker inspect web",
		],
	},
	"gh-external-mutation-safety": {
		flagged: [
			"gh pr create --title x",
			"gh pr merge 12",
			"gh pr ready 4",
			"gh issue comment 3 --body hi",
			"gh release create v1",
			"gh repo delete o/r --yes",
			"gh workflow run ci.yml",
			"gh secret set TOKEN",
			"gh gist create notes.md",
			"gh gist delete abc123",
			"gh gist edit abc123",
			"gh gist rename abc123 new.md",
			"gh project create --owner o --title t",
			"gh project delete 1 --owner o",
			"gh project close 1 --owner o",
			"gh project copy 1 --source-owner o --target-owner p",
			"gh project edit 1 --owner o --title t",
			"gh project link 1 --owner o --repo r",
			"gh project unlink 1 --owner o --repo r",
			"gh project mark-template 1 --owner o",
			"gh project field-create 1 --owner o --name n --data-type TEXT",
			"gh project field-delete --id PVTF_x",
			"gh project item-add 1 --owner o --url https://github.com/o/r/issues/1",
			"gh project item-archive 1 --owner o --id PVTI_x",
			"gh project item-create 1 --owner o --title t",
			"gh project item-delete 1 --owner o --id PVTI_x",
			"gh project item-edit --id PVTI_x --field-id PVTF_x --text y",
			"gh api -X POST repos/o/r/issues",
			"gh api --method=DELETE repos/o/r/issues/comments/1",
			"gh api repos/o/r -X PATCH -f name=y",
			"gh api --method PUT repos/o/r/topics",
			"gh api --method post repos/o/r/issues",
			"gh api repos/o/r/labels -f name=x",
			"gh api repos/o/r/issues -F title=x",
			"gh api repos/o/r/issues --input body.json",
			"gh api repos/o/r/issues -f title='graphql bug'",
			`gh api graphql -f query='mutation { addStar(input: {starrableId: "R_kg"}) { clientMutationId } }'`,
			`gh api graphql -f query="mutation { addStar(input: {starrableId: \\"R_kg\\"}) { clientMutationId } }"`,
			"gh api graphql -f query='\nmutation { addStar(input: {}) { clientMutationId } }'",
			"gh api graphql -f query='# generated operation\nmutation { addStar(input: {}) { clientMutationId } }'",
			"gh api graphql -f query='# generated operation\\nmutation { addStar(input: {}) { clientMutationId } }'",
			`gh api graphql -f query='fragment R on AddStarPayload { clientMutationId } mutation M { addStar(input: {starrableId: "R_kg"}) { ...R } }'`,
			"gh api graphql -f query='query Q { viewer { login } } mutation M { addStar(input: {}) { clientMutationId } }' -f operationName=M",
			"gh api graphql -F query=@mutation.graphql",
			"gh api graphql --input query.json",
			"gh api -H 'Accept: application/json' graphql -f query='mutation { addStar(input: {}) { clientMutationId } }'",
		],
		ignored: [
			"gh pr view 12",
			"gh pr list",
			"gh pr diff 12",
			"gh pr checks 12",
			"gh issue view 3",
			"gh issue list",
			"gh release view v1",
			"gh repo view",
			"gh repo clone o/r",
			"gh run list",
			"gh gist list",
			"gh gist view abc123",
			"gh gist clone abc123",
			"gh project list --owner o",
			"gh project view 1 --owner o",
			"gh project field-list 1 --owner o",
			"gh project item-list 1 --owner o",
			"gh api repos/o/r",
			"gh api user",
			"gh api -X GET repos/o/r/issues -f state=open",
			"gh api --method GET repos/o/r/issues -F per_page=100",
			"gh api --method=GET repos/o/r/issues -f state=open",
			"gh api --method get repos/o/r/issues -f state=open",
			"gh api graphql -f query='query { viewer { login } }'",
			"gh api graphql -f query='{ viewer { login } }'",
			`gh api graphql -f query="query { repository(owner: \\"o\\", name: \\"r\\") { id } }"`,
			"gh api graphql -F owner=o -f query='query($owner: String!) { user(login: $owner) { id } }'",
			"gh api --paginate graphql -f query='query { viewer { login } }'",
			"gh api -H 'Accept: application/json' graphql -f query='query { viewer { login } }'",
			"gh api graphql -f query='query { viewer { login } }' && bun test -t gh-external-mutation-safety",
		],
	},
	"git-commit-conventions": {
		flagged: [
			"git add -A",
			"git add .",
			"git add -- .",
			"git add -A -- .",
			"git add -u",
			"git add --all",
			"git add --update",
			"git add . && git commit -m x",
			"git commit -a -m x",
			"git commit -am x",
			"git commit -qam x",
			"git commit --all -m x",
			"git -C repo add --all",
			"git -C repo commit -a",
		],
		ignored: [
			"git add src/a.ts",
			"git add -- src/a.ts",
			"git add -- .gitignore",
			"git add .github/workflows/ci.yml",
			"git add -A src",
			"git add -u src",
			"git add -p",
			"git commit -m x",
			`git commit -m "add feature"`,
			"git commit --amend",
			"git commit -m x --amend",
		],
	},
	"git-push-safety": {
		flagged: [
			"git push",
			"git push -u origin main",
			"git push --force origin feature",
			"git push --force-with-lease origin feature",
			"git -C repo push origin main",
			"cd repo && git push origin main",
			`bash -c "git push"`,
		],
		ignored: [
			"git push --dry-run origin main",
			"git push -n",
			"git status",
			"git log origin/main",
			"git fetch origin",
			"git pull --ff-only",
			"git stash push -m wip",
		],
	},
	"git-worktree-restore-safety": {
		flagged: [
			"git restore .",
			"git restore --staged src/a.ts",
			"git checkout .",
			"git checkout -- .",
			"git checkout -- src/a.ts",
			"git checkout HEAD -- src/a.ts",
			"git checkout HEAD~1 -- src/a.ts src/b.ts",
			"git checkout origin/main -- .",
			"git checkout HEAD .",
			"git checkout -f main",
			"git -C ../wt checkout HEAD -- src/a.ts",
			"git switch -f main",
			"git switch --discard-changes main",
			"git clean -fd",
			"git clean -fdx",
			"git reset --hard",
			"git -C ../wt reset --hard HEAD~1",
			"git stash drop",
			"git stash clear",
			"git worktree remove --force ../wt",
		],
		ignored: [
			"git status",
			"git diff",
			"git diff HEAD -- src/a.ts",
			"git log -- src/a.ts",
			"git clean -n",
			"git clean --dry-run",
			"git checkout main",
			"git checkout feature/x",
			"git checkout -b feature",
			"git checkout -b feature origin/main",
			"git switch main",
			"git reset --soft HEAD~1",
			"git stash list",
			"git stash push -m wip",
			"git worktree add ../wt",
			"git worktree remove ../wt",
		],
	},
	"sql-mutation-safety": {
		flagged: [
			`psql -c '${join("DELETE", " FROM users")}'`,
			`snowsql -q '${join("TRUNCATE", " TABLE users;")}'`,
			`psql -c '${join("TRUNCATE", " orders")}'`,
			`psql -c '${join("DROP", " TABLE users")}'`,
			`mysql -e "${join("DROP", " DATABASE app")}"`,
			`psql -c '${join("UPDATE", " users SET active = false")}'`,
			`psql -c '${join("ALTER", " TABLE users DROP COLUMN email")}'`,
			`psql -c '${join("DELETE\n", "FROM users")}'`,
			`psql -c '${join("UPDATE\nusers\n", "SET active = false")}'`,
			"rails db:drop",
			"rails\ndb:drop",
			"alembic\ndowngrade -1",
			"rake db:rollback",
			"alembic downgrade -1",
			"prisma migrate reset",
			"prisma db push --force-reset",
			"flyway clean",
			"sequelize db:migrate:undo",
		],
		ignored: [
			"psql -c 'select 1'",
			"psql -c 'SELECT * FROM users'",
			"psql -c 'SELECT\n* FROM users'",
			"psql -c 'insert into users (id) values (1)'",
			"rails db:migrate",
			"alembic upgrade head",
			"prisma migrate dev",
			"prisma db push",
			"sequelize db:migrate",
			"dbt run-operation noop",
			"python -c 'f.truncate(0)'",
			"truncate -s 0 app.log",
			`echo "please update the docs"`,
		],
	},
	"temp-cleanup-ownership": {
		flagged: [
			"rm -rf /tmp/*",
			"rm -rf /private/tmp/build-*",
			"rm -rf $TMPDIR/*",
			"rm -rf ${TMPDIR}/build-*",
			"rm -f /tmp/build-?",
			"find /tmp -mtime +1 -delete",
			"find /var/folders -mtime +7 -delete",
			"find $TMPDIR -name '*.tmp' -exec rm {} +",
			"find /tmp -name '*.log' | xargs rm",
		],
		ignored: [
			"ls /tmp",
			"ls /tmp/*",
			"rm -rf /tmp/mydir-123",
			"rm /tmp/session-out.txt",
			"rm -rf ./out/*",
			"find /tmp -name x",
			"find ./build -delete",
		],
	},
};

/** Rules that also (or only) read file or eval source: matched against raw text, never the Bash JSON snapshot. */
const sourceCases: Record<string, Cases> = {
	"sql-mutation-safety": {
		flagged: [
			`db.execute("${join("DELETE", " FROM users")} WHERE id = 1")`,
			`cur.execute("${join("DROP", " TABLE users")}")`,
			`os.system("rails db:drop")`,
		],
		ignored: [`db.execute("SELECT * FROM users")`, `db.execute("insert into users (id) values (1)")`, `f.truncate(0)`],
	},
	"temp-cleanup-ownership": {
		flagged: [
			`for path in Path("/tmp").glob("*"): path.unlink()`,
			`for path in glob.glob("/tmp/x*"): os.remove(path)`,
			`for name in os.listdir("/tmp"): shutil.rmtree(os.path.join("/tmp", name))`,
			`for p in glob.glob(tempfile.gettempdir() + "/x*"): os.unlink(p)`,
		],
		ignored: [
			`Path(workdir).unlink()`,
			`shutil.rmtree(workdir)`,
			`d = tempfile.mkdtemp(); shutil.rmtree(d)`,
			`print(os.listdir("/tmp"))`,
		],
	},
	"dbt-test-arguments": {
		flagged: [
			"- accepted_values:\n    values: [a]\n",
			"- relationships:\n    to: ref('x')\n    field: id\n",
			"- relationships: {to: ref('x'), field: id}\n",
			"- accepted_values:\n    config:\n      severity: warn\n    values: [a]\n",
			"- accepted_values:\n    store_failures: true\n    values: [a]\n",
			"- accepted_values:\n    name: status_check\n    description: statuses\n    values: [a]\n",
			"- dbt_utils.expression_is_true:\n    expression: \"amount >= 0\"\n",
			"- dbt_utils.accepted_range:\n    name: range_check\n    min_value: 0\n",
			"- relationships: {config: {severity: warn}, to: ref('x'), field: id}\n",
			"          - accepted_values:\n              values: [a]\n",
			"- \"accepted_values\":\n    values: [a]\n",
		],
		ignored: [
			"- not_null\n- unique\n",
			"- accepted_values:\n    arguments:\n      values: [a]\n",
			"- relationships:\n    arguments:\n      to: ref('x')\n      field: id\n",
			"- relationships: {arguments: {to: ref('x'), field: id}}\n",
			"- accepted_values:\n    store_failures: true\n    arguments:\n      values: [a]\n",
			"- accepted_values:\n    config:\n      severity: warn\n    arguments:\n      values: [a]\n",
			"- accepted_values:\n    arguments:\n      values: [a]\n    config:\n      severity: warn\n",
			"- relationships: {config: {severity: warn}, arguments: {to: ref('x'), field: id}}\n",
			"- dbt_utils.expression_is_true:\n    arguments:\n      expression: \"amount >= 0\"\n    config:\n      severity: warn\n",
			"- dbt_utils.unique_combination_of_columns:\n    arguments:\n      combination_of_columns: [a, b]\n",
			"description: values must be accepted\n",
		],
	},
	"lint-suppression": {
		flagged: [
			join("x = f()  # no", "qa\n"),
			join("x = f()  # type: ig", "nore\n"),
			join("x = f()  # pyright: ig", "nore\n"),
			join("# ruff: no", "qa\n"),
			join("# flake8: no", "qa\n"),
			join("# mypy: ignore-", "errors\n"),
			join("# pylint: disable=", "all\n"),
			join("#![al", "low(dead_code)]\n"),
			join("#[al", "low(clippy::all)]\n"),
			join("#[al", "low(warnings)]\n"),
			join("// @ts-", "ignore\n"),
			join("// @ts-", "nocheck\n"),
			join("// biome-ignore", "-all lint: legacy\n"),
			join("/* eslint-", "disable */\n"),
			join("// eslint-", "disable-next-line\n"),
			join("// oxlint-", "disable-next-line\n"),
		],
		ignored: [
			"x = f()  # noqa: S603\n",
			"x = f()  # noqa:S603\n",
			"x = f()  # type: ignore[arg-type]\n",
			"x = f()  # pyright: ignore[reportGeneralTypeIssues]\n",
			"#[allow(dead_code)]\n",
			`#[allow(clippy::cargo_common_metadata, reason = "x")]\n`,
			"// eslint-disable-next-line no-console -- reason\n",
			"// @ts-expect-error reason\n",
			"x = f()  # ordinary comment\n",
		],
	},
};

/**
 * Judged rules: `condition` only decides whether the judge is asked. `asked` texts open the gate (the judge then
 * answers the question); `skipped` texts never reach the judge.
 */
const judgedCases: Record<string, { scope: string; asked: string[]; skipped: string[] }> = {
	"no-silent-scope-shrink": {
		scope: "text",
		asked: [
			"Done. The MVP is complete and error handling is left as a follow-up.",
			"All set — I added a stub for now and a TODO for the retry path.",
			"The v1 covers login; logout is out of scope.",
			"Implemented a placeholder for the export step.",
		],
		skipped: [
			"All requested endpoints are implemented and covered by tests.",
			"The stubborn failure was a stale cache entry.",
			"Scaffolding was replaced with the real implementation.",
			"The API is now at v10 and the client matches.",
		],
	},
	"no-source-grep-tests": {
		scope: "tool:write(*.test.ts)",
		asked: [
			`const src = await Bun.file("src/parse.ts").text();\nexpect(src).toContain("export function parse");`,
			`const src = readFileSync("src/lib.ts", "utf8");\nexpect(src).toMatch(/retry/);`,
			`const text = await response.text();\nexpect(JSON.parse(text).ok).toBe(true);`,
		],
		skipped: [
			`test("parses", () => {\n\texpect(parse("a=1")).toEqual({ a: "1" });\n});`,
			`test("rejects empty input", () => {\n\texpect(() => parse("")).toThrow("empty");\n});`,
		],
	},
	"no-unverified-test-claims": {
		scope: "text",
		asked: [
			"All tests pass.",
			"The build succeeded cleanly.",
			"Typecheck is green.",
			"Checks passed.",
			"Ran `bun test`: 14 tests pass, 0 fail.",
		],
		skipped: [
			"I did not run the tests.",
			"The build failed with 3 errors.",
			"Tests are failing in CI.",
			"Added a lint rule for imports.",
		],
	},
};

describe("shipped rules", () => {
	test("every rule declares at least one condition", () => {
		for (const [name, rule] of rules) expect(rule.conditions.length, name).toBeGreaterThan(0);
	});

	test("every rule has behavior cases with a positive and a negative", () => {
		const covered = new Set([...Object.keys(bashCases), ...Object.keys(sourceCases), ...Object.keys(judgedCases)]);
		expect([...covered].sort()).toEqual([...rules.keys()].sort());
		expect(rules.size).toBe(14);
		for (const cases of [...Object.values(bashCases), ...Object.values(sourceCases)]) {
			expect(cases.flagged.length).toBeGreaterThan(0);
			expect(cases.ignored.length).toBeGreaterThan(0);
		}
		for (const cases of Object.values(judgedCases)) {
			expect(cases.asked.length).toBeGreaterThan(0);
			expect(cases.skipped.length).toBeGreaterThan(0);
		}
	});

	test("rules without a question are plain interrupting matchers, judged rules always carry one", () => {
		for (const [name, rule] of rules) {
			expect(rule.question !== undefined, name).toBe(name in judgedCases);
		}
	});
});

describe("bash rules", () => {
	for (const [name, cases] of Object.entries(bashCases)) {
		test(name, () => {
			for (const command of cases.flagged) {
				expect(matches(name, command), command).toBe(true);
				expect(matches(name, JSON.stringify({ command })), `JSON ${command}`).toBe(true);
			}
			for (const command of cases.ignored) {
				expect(matches(name, command), command).toBe(false);
				expect(matches(name, JSON.stringify({ command })), `JSON ${command}`).toBe(false);
			}
		});
	}

	test("exclusions stop at a JSON-escaped newline but not at escaped quotes", () => {
		for (const [name, command, flagged] of [
			["git-push-safety", "git push origin main\ngit log -n 3", true],
			["git-push-safety", `git push "origin" --dry-run`, false],
			["dbt-command-scope", "dbt build\ndbt ls -s x", true],
			["dbt-command-scope", `dbt build -s "x"`, false],
			["gh-external-mutation-safety", `gh api -X "POST" repos/o/r/issues`, true],
			["gh-external-mutation-safety", `gh api -X "GET" repos/o/r/issues -f state=open`, false],
		] as const) {
			expect(matches(name, JSON.stringify({ command })), command).toBe(flagged);
		}
	});
});

describe("source rules", () => {
	for (const [name, cases] of Object.entries(sourceCases)) {
		test(name, () => {
			for (const text of cases.flagged) expect(matches(name, text), text).toBe(true);
			for (const text of cases.ignored) expect(matches(name, text), text).toBe(false);
		});
	}
});

describe("judged rules", () => {
	for (const [name, cases] of Object.entries(judgedCases)) {
		test(name, () => {
			expect(rules.get(name)?.scope, `${name} scope`).toContain(cases.scope);
			for (const text of cases.asked) expect(matches(name, text), `asked: ${text}`).toBe(true);
			for (const text of cases.skipped) expect(matches(name, text), `skipped: ${text}`).toBe(false);
		});
	}
});
