import { describe, expect, test } from "bun:test";
import { readdir } from "node:fs/promises";
import * as path from "node:path";

const RULES = path.join(path.resolve(import.meta.dir, ".."), "packs", "clssck", "rules");

/**
 * Local approximation of how a rule `condition` is compiled: a leading `(?ims)` group becomes native RegExp flags.
 * Canonical host compilation is exercised by the loader smoke, not here.
 */
function compileCondition(pattern: string): RegExp {
	const match = /^\(\?([a-z]+)\)/.exec(pattern);
	if (match && /^[ims]+$/.test(match[1])) return new RegExp(pattern.slice(match[0].length), Array.from(new Set(match[1])).join(""));
	return new RegExp(pattern);
}

const rules = new Map<string, RegExp[]>();
for (const file of (await readdir(RULES)).filter(name => name.endsWith(".md")).sort()) {
	const source = await Bun.file(path.join(RULES, file)).text();
	const end = source.indexOf("\n---", 3);
	const meta = Bun.YAML.parse(source.slice(4, end)) as { condition?: string | string[] };
	const conditions = meta.condition === undefined ? [] : Array.isArray(meta.condition) ? meta.condition : [meta.condition];
	rules.set(file.slice(0, -".md".length), conditions.map(compileCondition));
}

function matches(name: string, text: string): boolean {
	const conditions = rules.get(name);
	if (!conditions) throw new Error(`unknown rule ${name}`);
	return conditions.some(condition => condition.test(text));
}

/** Fixtures for destructive SQL and blanket lint suppressions are assembled so this file never contains them verbatim. */
const join = (...parts: string[]) => parts.join("");

/** Bash arguments reach TTSR as raw streamed JSON fragments and as one `JSON.stringify` snapshot once finalized. */
const finalized = (command: string) => JSON.stringify({ command });
/** Raw streamed buffer holding the whole command before the closing quote of the JSON string arrives. */
const streamed = (command: string) => finalized(command).slice(0, -2);
/** Write and edit tools match raw source. */
const raw = (text: string) => text;

/**
 * Deterministic conditions identify relevance, not violations: a match is not proof of a violation and silence is
 * not authorization. `relevant` holds common actions the rule exists for; `safeCandidates` are broad matches that
 * may already comply (selected, dry-run, user-requested, owned, literal mentions). Interrupting guards can pause
 * those calls for review against the body's exceptions; `unrelated` stays silent.
 */
interface RelevanceCases {
	rule: string;
	input: string;
	forms: ((text: string) => string)[];
	relevant: string[];
	safeCandidates: string[];
	unrelated: string[];
}

const bash = (rule: string, cases: Pick<RelevanceCases, "relevant" | "safeCandidates" | "unrelated">): RelevanceCases => ({
	rule,
	input: "bash arguments",
	forms: [finalized, streamed],
	...cases,
});

const relevanceCases: RelevanceCases[] = [
	bash("build-cache-deletion-safety", {
		relevant: [
			"rm -rf node_modules",
			"rm node_modules -rf",
			"rm -rf ~/.pnpm-store",
			"rm -rf ~/Library/Caches",
			"cargo clean",
			"bazel clean --expunge",
			"uv cache clean",
			"npm cache clean --force",
			"go clean -modcache",
		],
		safeCandidates: ["rm -rf target", "rm -f build/output.log", "pnpm store prune"],
		unrelated: ["rm -rf ./scratch-out", "rm file.txt", "ls target", "cargo build", "npm install", "git status"],
	}),
	bash("dbt-command-scope", {
		relevant: [
			"dbt build",
			"cd analytics && dbt test",
			"uv run dbt seed",
			"dbt snapshot",
			"dbt clone --state prod-artifacts",
			"dbt build --select fct_orders --full-refresh",
			"ssh host 'dbt run'",
		],
		safeCandidates: ["dbt run --select fct_orders", "dbt build --select fct_orders+", "dbt test -s my_model"],
		unrelated: [
			"dbt run-operation clean_stale_models",
			"dbt ls --select x",
			"dbt compile",
			"dbt docs generate",
			"dbt deps",
			"dbt debug",
			"git status",
		],
	}),
	bash("docker-data-safety", {
		relevant: [
			"docker system prune -a --volumes",
			"docker builder prune",
			"podman volume rm pgdata",
			"docker --context prod volume prune",
			"docker compose down -v",
			"docker-compose down --rmi all",
			"podman --remote volume rm pgdata",
			"docker compose -f a.yml down --rmi all",
		],
		safeCandidates: ["docker volume rm ci_scratch"],
		unrelated: [
			"docker ps",
			"docker volume ls",
			"docker run --rm alpine true",
			"docker compose up -d",
			"docker compose down",
			"docker compose down --remove-orphans",
			"kubectl volume rm pgdata",
			"make system prune",
			"foo down -v",
			"docker ps; npm down -v",
		],
	}),
	bash("gh-external-mutation-safety", {
		relevant: [
			"gh pr create --draft --title x",
			"gh pr merge 12 --squash",
			"gh pr ready 5",
			"gh issue close 42 --repo acme/widgets",
			"gh issue lock 3",
			"gh repo fork acme/widgets",
			"gh release create v1.2.0",
			"gh release upload v1.2.0 dist.tgz",
			"gh secret set TOKEN",
			"gh workflow run ci.yml",
			"gh run rerun 123",
			"gh project item-add 1 --owner acme",
			"gh api -X DELETE repos/acme/widgets/issues/comments/1",
			"gh api repos/acme/widgets/issues -f title=x",
			"gh api graphql -f query='mutation { addStar(input: {}) { clientMutationId } }'",
		],
		safeCandidates: ["gh api repos/acme/widgets", "gh api graphql -f query='query { viewer { login } }'"],
		unrelated: [
			"gh pr view 1",
			"gh pr list",
			"gh pr checkout 12",
			"gh issue view 3",
			"gh repo view",
			"gh run list",
			"gh workflow list",
			"gh auth status",
		],
	}),
	bash("git-commit-conventions", {
		relevant: [
			"git add -A",
			"git add .",
			"git add -u",
			"git add --all",
			"git commit -am wip",
			"git commit -a -m x",
			"cd repo && git add . && git commit -m x",
		],
		safeCandidates: ["git add -A src/"],
		unrelated: ["git add src/a.ts", "git add .gitignore", "git commit -m x", "git commit --amend -m x", "git status"],
	}),
	bash("git-push-safety", {
		relevant: [
			"git push",
			"git push origin HEAD:feature",
			"git push --force-with-lease",
			"git -C ../worktree push origin main",
			"git push --tags",
		],
		safeCandidates: ["git push --dry-run origin main"],
		unrelated: ["git pull", "git fetch origin", "git status"],
	}),
	bash("git-worktree-restore-safety", {
		relevant: [
			"git restore -- a.ts",
			"git reset --hard HEAD~1",
			"git clean -fdx",
			"git checkout .",
			"git checkout HEAD -- a.ts",
			"git switch -f main",
			"git stash drop",
			"git stash clear",
			"git worktree remove --force ../w",
		],
		safeCandidates: ["git worktree remove ../w", "git restore --staged a.ts"],
		unrelated: [
			"git checkout main",
			"git checkout -b feature",
			"git switch feature",
			"git clean -nd",
			"git reset HEAD a.ts",
			"git stash list",
			"git status",
		],
	}),
	bash("temp-cleanup-ownership", {
		relevant: [
			"rm -rf /tmp/myjob-*",
			`find "$TMPDIR" -name '*.log' -delete`,
			"cd /tmp && rm -rf foo*",
			"cd /tmp\nrm -rf foo*",
		],
		safeCandidates: [`scratch=$(mktemp -d /tmp/x.XXXX); rm -rf -- "$scratch"`, "rm -rf /tmp/exact-dir", "echo rm /tmp/x"],
		unrelated: ["ls /tmp", "mktemp -d", "rm -rf ./build-out", "cat /tmp/log", "find src -name '*.o'", "rm file.txt"],
	}),
	{
		rule: "temp-cleanup-ownership",
		input: "eval arguments",
		forms: [code => JSON.stringify({ language: "py", code })],
		relevant: [
			`d = tempfile.gettempdir()\nfor p in Path(d).glob("x*"): shutil.rmtree(p)`,
			`for name in os.listdir("/tmp"):\n    os.unlink(os.path.join("/tmp", name))`,
			`fs.readdirSync(os.tmpdir()).forEach(f => fs.rmSync(path.join(os.tmpdir(), f)));`,
			`import os, tempfile\nos.remove(os.path.join(tempfile.gettempdir(), f))`,
		],
		safeCandidates: [`for p in Path("/tmp").glob("myjob-*"): shutil.rmtree(p)`],
		unrelated: [
			`print(os.listdir("/tmp"))`,
			`shutil.rmtree(workdir)`,
			`d = tempfile.mkdtemp(); shutil.rmtree(d)`,
			`os.remove("./local.txt")`,
		],
	},
	{
		rule: "sql-mutation-safety",
		input: "raw source and serialized tool or connector arguments",
		forms: [raw, query => JSON.stringify({ query })],
		relevant: [
			join("DELETE", " FROM orders WHERE id = 1"),
			join("delete", "\nfrom orders"),
			join("UPDATE", " users SET active = false"),
			join("MERGE", " INTO orders USING staged ON orders.id = staged.id"),
			join("REPLACE", " INTO orders (id) VALUES (1)"),
			join("INSERT OR ", "REPLACE", " INTO orders (id) VALUES (1)"),
			join("TRUNC", "ATE TABLE users"),
			join("TRUNC", "ATE users"),
			join("TRUNC", "ATE\nusers"),
			join("TRUNC", 'ATE "orders"'),
			join("DROP", " TABLE orders"),
			join("DROP", " FUNCTION refresh_totals"),
			join("ALTER", " TABLE orders DROP COLUMN note"),
			"rails db:reset",
			"rake db:drop",
			"alembic downgrade -1",
			"prisma migrate reset",
			"prisma db push --force-reset",
			"flyway clean",
			"sequelize db:migrate:undo",
		],
		safeCandidates: [
			join("-- never run ", "DELETE", " FROM orders without a WHERE clause"),
			join("BEGIN; ", "DELETE", " FROM orders WHERE id = 1; ROLLBACK;"),
			"Does OMP truncate the visible skills catalog?",
		],
		unrelated: [
			"truncate -s 0 app.log",
			"SELECT * FROM orders",
			join("SELECT\n", "id FROM orders"),
			"INSERT INTO orders (id) VALUES (1)",
			join("ALTER", " TABLE orders ADD COLUMN note text"),
			"alembic current",
			"rails db:migrate",
			"rake routes",
			"f.truncate(0)",
		],
	},
	{
		rule: "dbt-test-arguments",
		input: "raw yaml",
		forms: [raw],
		relevant: [
			"      - accepted_values:\n          values: [a, b]\n",
			"- relationships:\n    to: ref('customers')\n    field: id\n",
			"- dbt_utils.expression_is_true:\n    expression: \"amount >= 0\"\n",
			"- accepted_values: {values: [a]}\n",
			"    data_tests:\n      - unique\n",
		],
		safeCandidates: [
			"- accepted_values:\n    arguments:\n      values: [a]\n",
			"- dbt_utils.expression_is_true:\n    arguments:\n      expression: \"amount >= 0\"\n    config:\n      severity: warn\n",
		],
		unrelated: [
			"columns:\n  - name: id\n",
			"models:\n  - name: orders\n    description: Accepted values come from the source system.\n",
			"vars:\n  contests: 3\n",
			"packages:\n  - package: dbt-labs/dbt_utils\n",
		],
	},
];

/**
 * Judged rules: `condition` only decides whether the judge is asked. `asked` texts open the gate (the judge then
 * answers the question); `skipped` texts never reach the judge.
 */
const judgedCases: Record<string, { asked: string[]; skipped: string[] }> = {
	"lint-suppression": {
		asked: [
			join("x = f()  # no", "qa\n"),
			join("x = f()  # no", "qa"),
			join("x = f()  # no", "qa   "),
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
			join("// eslint-", "disable-next-line"),
			join("//  eslint-", "disable-next-line   "),
			join("// oxlint-", "disable"),
		],
		skipped: [
			"x = f()  # noqa: S603\n",
			"x = f()  # noqa:S603\n",
			"x = f()  # type: ignore[arg-type]\n",
			"x = f()  # pyright: ignore[reportGeneralTypeIssues]\n",
			"#[allow(dead_code)]\n",
			`#[allow(clippy::cargo_common_metadata, reason = "x")]\n`,
			"// eslint-disable-next-line no-console -- reason\n",
			"// @ts-expect-error reason\n",
			"x = f()  # ordinary comment\n",
			`s = "mypy: ignore-errors"\n`,
			`const note = "avoid @ts-ignore";\n`,
		],
	},
	"no-silent-scope-shrink": {
		asked: [
			"Done. The MVP is complete and error handling is left as a follow-up.",
			"All set — I added a stub for now and a TODO for the retry path.",
			"The v1 covers login; logout is out of scope.",
			"Implemented a placeholder for the export step.",
			"Done. Two placeholders remain in the export module.",
			"Complete. The export and import remain stubs.",
			"Finished the work; two TODOs remain.",
		],
		skipped: [
			"All requested endpoints are implemented and covered by tests.",
			"The stubborn failure was a stale cache entry.",
			"Scaffolding was replaced with the real implementation.",
			"The API is now at v10 and the client matches.",
		],
	},
	"no-source-grep-tests": {
		asked: [
			`const src = await Bun.file("src/parse.ts").text();\nexpect(src).toContain("export function parse");`,
			`const src = readFileSync("src/lib.ts", "utf8");\nexpect(src).toMatch(/retry/);`,
			`const text = await response.text();\nexpect(JSON.parse(text).ok).toBe(true);`,
			`import src from "../src/parse.ts?raw";\nexpect(src).toContain("export function parse");`,
		],
		skipped: [
			`test("parses", () => {\n\texpect(parse("a=1")).toEqual({ a: "1" });\n});`,
			`test("rejects empty input", () => {\n\texpect(() => parse("")).toThrow("empty");\n});`,
		],
	},
	"no-unverified-test-claims": {
		asked: [
			"All tests pass.",
			"The build succeeded cleanly.",
			"Typecheck is green.",
			"Checks passed.",
			"Ran `bun test`: 14 tests pass, 0 fail.",
			"All tests passed: 14 passed, 0 failed.",
			"Ran `bun test` and every check is green.",
			"Tests pass.",
			"Everything passed: 14 tests, 0 failures.",
			"All passed: lint, typecheck, and tests.",
			"The unit tests for the parser, the formatter, and the lexer all passed.",
			"Tests ran. All 14 passed.",
			"vitest passed: 14 green",
			"The builds passed.",
		],
		skipped: [
			"I did not run the tests.",
			"The build failed with 3 errors.",
			"Tests are failing in CI.",
			"Added a lint rule for imports.",
			"Checks were skipped; nothing was run.",
		],
	},
};

describe("deterministic triggers", () => {
	for (const cases of relevanceCases) {
		test(`${cases.rule} (${cases.input})`, () => {
			for (const [texts, expected, label] of [
				[cases.relevant, true, "relevant"],
				[cases.safeCandidates, true, "broad candidate; check exceptions"],
				[cases.unrelated, false, "unrelated"],
			] as const) {
				for (const text of texts) {
					for (const form of cases.forms) expect(matches(cases.rule, form(text)), `${label}: ${form(text)}`).toBe(expected);
				}
			}
		});
	}
});

describe("judged rules", () => {
	for (const [name, cases] of Object.entries(judgedCases)) {
		test(name, () => {
			for (const text of cases.asked) expect(matches(name, text), `asked: ${text}`).toBe(true);
			for (const text of cases.skipped) expect(matches(name, text), `skipped: ${text}`).toBe(false);
		});
	}
});
